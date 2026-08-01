"""Typed, dependency-safe processing primitives for conversational attempts.

The durable database claim remains owned by the repository.  This module owns
only the stable PR3-facing stage contract and the small orchestration seam.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from pathlib import Path
from datetime import datetime
from typing import Literal, Mapping, Protocol, Sequence

from ..repositories.conversational_session_repository import (
    AttemptProcessingClaim,
    AttemptProcessingResult,
)
from ..models.async_job import AsyncJob
from ..config import settings
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewAttemptUpload,
    InterviewSession,
    SessionRecording,
    InterviewTranscriptVersion,
)
from sqlalchemy import select, update
from .async_job_service import AsyncJobService

logger = logging.getLogger(__name__)

__all__ = (
    "AttemptStage", "AttemptProcessingContext", "StageResult",
    "SpeechMetricsSnapshot", "SessionEvidenceSnapshot",
)

PIPELINE_ORDER = (
    "audio_persist", "transcription", "speech_analysis", "content_evaluation",
    "evidence_grounding", "follow_up_decision", "coaching_enrichment", "audio_cleanup",
)


class AttemptPipelineError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class SpeechMetricsSnapshot:
    duration_ms: int
    word_count: int
    words_per_minute: float
    filler_count: int
    filler_rate_per_minute: float
    hedging_count: int
    pause_count: int
    long_pause_count: int
    restart_count: int | None


@dataclass(frozen=True)
class SessionEvidenceSnapshot:
    evidence_id: str
    source_type: str
    source_record_id: str
    source_record_version: str
    source_path: str
    snapshot_text: str
    approval_state: str
    content_hash: str
    snapshot_hash: str


@dataclass(frozen=True)
class StageResult:
    stage_name: str
    stage_state: Literal["completed", "unavailable", "failed_retryable", "failed_terminal"]
    output: Mapping[str, object] | None
    error_code: str | None
    retryable: bool
    attempt_count: int
    repair_count: int


@dataclass(frozen=True)
class AttemptProcessingContext:
    session_id: str
    question_id: str
    recording_id: str
    transcript_version_id: str | None
    evaluation_version_id: str
    processing_generation: int
    deadline_at: datetime
    recording_type: Literal["text", "audio"]
    normalized_transcript: str | None
    speech_metrics: SpeechMetricsSnapshot | None
    evidence_records: tuple[SessionEvidenceSnapshot, ...]


class AttemptStage(Protocol):
    name: str

    async def run(self, context: AttemptProcessingContext) -> StageResult: ...


def effective_timeout(deadline: datetime, ceiling_seconds: int, now: datetime) -> float:
    remaining = (deadline - now).total_seconds()
    if remaining <= 0:
        raise AttemptPipelineError("coach_attempt_job_budget_exhausted", retryable=True)
    return min(float(ceiling_seconds), remaining)


def require_bound_transcript(context: AttemptProcessingContext) -> tuple[str, str]:
    if context.transcript_version_id is None or context.normalized_transcript is None:
        raise AttemptPipelineError("coach_attempt_stage_dependency_missing", retryable=False)
    return context.transcript_version_id, context.normalized_transcript


def queue_attempt_processing(claim: AttemptProcessingClaim) -> None:
    """Schedule processing after the request transaction has committed."""
    AsyncJobService.run(claim.job_id, _safe_process_attempt_claim(claim))


async def _safe_process_attempt_claim(claim: AttemptProcessingClaim) -> None:
    try:
        await _process_attempt_claim(claim)
    except AttemptPipelineError:
        raise
    except Exception as error:
        logger.error("Coach attempt worker failed: %s", type(error).__name__)
        raise AttemptPipelineError("coach_attempt_worker_failed", retryable=False) from None


async def _process_attempt_claim(
    claim: AttemptProcessingClaim, *, session_factory=None, transcriber_factory=None
) -> None:
    """Own a fresh worker session; durable fences decide whether work is current."""
    from ..database import AsyncSessionLocal
    from ..repositories.conversational_session_repository import ConversationalSessionRepository
    from ..services.speech_analyser import SpeechAnalyserService
    from ..agents.tools.perception_factory import get_transcriber

    session_factory = session_factory or AsyncSessionLocal
    transcriber_factory = transcriber_factory or get_transcriber

    async with session_factory() as db:
        repository = ConversationalSessionRepository(db)
        snapshot = await repository.get_attempt_processing_snapshot(
            recording_id=claim.recording_id,
            processing_generation=claim.processing_generation,
        )
        if snapshot is None or snapshot.claim != claim:
            raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(InterviewAttemptEvaluation, claim.evaluation_version_id)
        session = await db.get(InterviewSession, claim.session_id)
        if (
            attempt is None or evaluation is None or session is None
            or session.conversation_state != "processing_answer"
            or session.deletion_state != "not_requested"
            or session.active_recording_id != claim.recording_id
            or attempt.question_id != claim.question_id
            or attempt.async_job_id != claim.job_id
            or evaluation.async_job_id != claim.job_id
            or evaluation.state != "pending"
        ):
            raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)

        async def finish(result: AttemptProcessingResult) -> None:
            """Fence generic-job ownership and attempt terminalisation together."""
            job_change = await db.execute(
                update(AsyncJob)
                .where(AsyncJob.id == claim.job_id, AsyncJob.status.in_(("pending", "running")))
                .values(status="done", result_json='{"status":"unavailable"}', error=None)
            )
            if job_change.rowcount != 1:
                await db.rollback()
                raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
            if not await repository.finalise_attempt_processing(claim=claim, result=result):
                await db.rollback()
                raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
            await db.commit()
        transcript_id = claim.transcript_version_id
        reason = "coach_evaluation_unavailable"
        speech_unavailable = False
        stages = (await db.scalars(select(InterviewAttemptStage).where(
            InterviewAttemptStage.recording_id == claim.recording_id,
            InterviewAttemptStage.evaluation_version_id == claim.evaluation_version_id,
        ))).all()
        if attempt.recording_type == "audio":
            fence = await repository._get_attempt_processing_fence(claim)
            upload = await db.scalar(select(InterviewAttemptUpload).where(
                InterviewAttemptUpload.attempt_id == claim.recording_id,
                InterviewAttemptUpload.result_state == "completed",
                InterviewAttemptUpload.content_sha256 == fence.expected_audio_content_hash if fence else False,
            ))
            if (
                fence is None or upload is None or not attempt.audio_uri
                or upload.storage_uri != attempt.audio_uri or not fence.expected_audio_content_hash
            ):
                raise AttemptPipelineError("coach_attempt_stage_dependency_missing", retryable=False)
            speech_transcription = None
            try:
                from ..services.coach_media_storage import open_verified_audio_read_lease
                with open_verified_audio_read_lease(
                    Path(settings.HATCH_COACH_MEDIA_ROOT), Path(attempt.audio_uri),
                    fence.expected_audio_content_hash,
                ) as lease:
                    # Independent providers receive the same inode-pinned bytes;
                    # speech must not depend on content transcription succeeding.
                    try:
                        speech_transcription = transcriber_factory().transcribe(str(lease.path))
                    except Exception:
                        speech_transcription = None
                    transcription = transcriber_factory().transcribe(str(lease.path))
            except Exception:  # provider detail must not enter durable diagnostics
                transcription = None
                reason = "transcription_unavailable"
            if transcription is not None and not transcription.text.strip():
                transcription = None
                reason = "transcription_unavailable"
            if speech_transcription is None:
                speech_unavailable = True
                metrics = None
                words: list[dict[str, object]] = []
            else:
                words = [{"w": word.w, "start": word.start, "end": word.end} for word in speech_transcription.words]
                try:
                    metrics = SpeechAnalyserService().analyse_from_timestamps(speech_transcription.text, words)
                except Exception:
                    metrics = None
                    speech_unavailable = True
            if metrics is not None:
                attempt.speech_metrics = {"duration_ms": metrics.duration_ms, "word_count": len(words), "words_per_minute": metrics.wpm, "filler_count": metrics.filler_count, "filler_rate_per_minute": metrics.filler_rate, "hedging_count": metrics.hedging_count, "pause_count": metrics.pause_count, "long_pause_count": metrics.pause_count}
            if transcription is None:
                for stage in stages:
                    if stage.stage_name == "audio_persist":
                        stage.stage_state = "completed"
                        stage.last_error_code = None
                        stage.completed_at = datetime.utcnow()
                    elif stage.stage_name == "transcription":
                        stage.stage_state = "unavailable"
                        stage.last_error_code = reason
                        stage.completed_at = datetime.utcnow()
                    elif stage.stage_name in {"content_evaluation", "evidence_grounding", "follow_up_decision", "coaching_enrichment"}:
                        stage.stage_state = "not_applicable"
                        stage.completed_at = datetime.utcnow()
                    elif stage.stage_name == "speech_analysis":
                        stage.stage_state = "unavailable" if speech_unavailable else "completed"
                        stage.last_error_code = "speech_analysis_unavailable" if speech_unavailable else None
                        stage.completed_at = datetime.utcnow()
                    elif stage.stage_name == "audio_cleanup":
                        stage.stage_state = "not_applicable"
                        stage.last_error_code = None
                        stage.completed_at = datetime.utcnow()
                result = AttemptProcessingResult("unavailable", {"answer_level": "not_assessed"}, None, {"reason": reason, "execution_mode": "deterministic_stub"})
                await finish(result)
                return
            transcript = await repository.create_worker_transcript_version(
                recording_id=claim.recording_id, transcript=transcription.text,
                expected_job_id=claim.job_id, expected_processing_generation=claim.processing_generation,
                expected_audio_content_hash=fence.expected_audio_content_hash,
                expected_evaluation_version_id=claim.evaluation_version_id,
                expected_claim_token=fence.claim_token,
            )
            if transcript is None:
                raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
            transcript_id = transcript.id
        for stage in stages:
            if stage.stage_state == "not_applicable":
                continue
            if stage.stage_name == "audio_persist" and attempt.recording_type == "audio":
                stage.stage_state = "completed"
            elif stage.stage_name == "transcription" and transcript_id is not None:
                stage.stage_state = "completed"
            elif stage.stage_name == "speech_analysis" and attempt.recording_type == "audio":
                stage.stage_state = "unavailable" if speech_unavailable else "completed"
            else:
                stage.stage_state = "unavailable" if stage.stage_name == "content_evaluation" else "not_applicable"
            stage.last_error_code = (
                reason if stage.stage_name == "content_evaluation"
                else "speech_analysis_unavailable" if stage.stage_name == "speech_analysis" and speech_unavailable
                else None
            )
            if stage.stage_name in {"content_evaluation", "evidence_grounding", "follow_up_decision", "coaching_enrichment"}:
                stage.source_transcript_version_id = transcript_id
            stage.completed_at = datetime.utcnow()
        result = AttemptProcessingResult(
            evaluation_state="unavailable",
            evaluation_json={"answer_level": "not_assessed"},
            transcript_version_id=transcript_id,
            diagnostics={"code": reason, "execution_mode": "deterministic_stub"},
        )
        await finish(result)


async def run_attempt_pipeline(
    claim: AttemptProcessingClaim, stages: Sequence[AttemptStage]
) -> AttemptProcessingResult:
    """Run supplied stages, refusing content work before a transcript is bound.

    PR3 owns evaluation.  Until then the deterministic unavailable result is the
    only truthful terminal projection.
    """
    names = tuple(stage.name for stage in stages)
    if (
        len(names) != len(set(names))
        or any(name not in PIPELINE_ORDER for name in names)
        or any(PIPELINE_ORDER.index(left) >= PIPELINE_ORDER.index(right) for left, right in zip(names, names[1:]))
    ):
        raise AttemptPipelineError("coach_attempt_stage_graph_invalid", retryable=False)
    normalized_transcript = None
    if claim.transcript_version_id is not None and any(
        name in {"content_evaluation", "evidence_grounding", "follow_up_decision"}
        for name in names
    ):
        normalized_transcript = await _load_claim_transcript(claim)
    context = AttemptProcessingContext(
        session_id=claim.session_id, question_id=claim.question_id,
        recording_id=claim.recording_id, transcript_version_id=claim.transcript_version_id,
        evaluation_version_id=claim.evaluation_version_id,
        processing_generation=claim.processing_generation, deadline_at=claim.deadline_at,
        recording_type="text" if claim.transcript_version_id is not None else "audio",
        normalized_transcript=normalized_transcript, speech_metrics=None, evidence_records=(),
    )
    for stage in stages:
        if stage.name in {"content_evaluation", "evidence_grounding", "follow_up_decision"}:
            require_bound_transcript(context)
        stage_result = await stage.run(context)
        if (
            stage.name == "transcription"
            and context.transcript_version_id is None
            and stage_result.stage_state == "completed"
        ):
            output = stage_result.output or {}
            transcript_version_id = output.get("transcript_version_id")
            normalized_transcript = output.get("normalized_transcript")
            if isinstance(transcript_version_id, str) and isinstance(
                normalized_transcript, str
            ):
                context = replace(
                    context,
                    transcript_version_id=transcript_version_id,
                    normalized_transcript=normalized_transcript,
                )
    return AttemptProcessingResult(
        evaluation_state="unavailable",
        evaluation_json={"answer_level": "not_assessed"},
        transcript_version_id=context.transcript_version_id,
        diagnostics={"code": "coach_evaluation_unavailable", "execution_mode": "deterministic_stub"},
    )


async def _load_claim_transcript(claim: AttemptProcessingClaim) -> str | None:
    """Read the immutable typed transcript without widening the public claim."""
    if claim.transcript_version_id is None:
        return None
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        transcript = await db.scalar(select(InterviewTranscriptVersion).where(
            InterviewTranscriptVersion.id == claim.transcript_version_id,
            InterviewTranscriptVersion.recording_id == claim.recording_id,
            InterviewTranscriptVersion.processing_generation == claim.processing_generation,
        ))
        return transcript.transcript if transcript is not None else None
