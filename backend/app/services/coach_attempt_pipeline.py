"""Typed, dependency-safe processing primitives for conversational attempts.

The durable database claim remains owned by the repository.  This module owns
only the stable PR3-facing stage contract and the small orchestration seam.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import logging
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Literal, Mapping, Protocol, Sequence

from ..repositories.conversational_session_repository import (
    AttemptProcessingClaim,
    AttemptProcessingResult,
    _stage_immutable_diagnostics,
)
from ..models.async_job import AsyncJob
from ..config import settings
from .coach_media_storage import CoachMediaError
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
    "SpeechMetricsSnapshot", "SessionEvidenceSnapshot", "select_restart_stage",
)

PIPELINE_ORDER = (
    "audio_persist", "transcription", "speech_analysis", "content_evaluation",
    "evidence_grounding", "follow_up_decision", "coaching_enrichment", "audio_cleanup",
)

_STAGE_TIMEOUT_SECONDS = {
    "transcription": "HATCH_COACH_TIMEOUT_TRANSCRIPTION_SECONDS",
    "speech_analysis": "HATCH_COACH_TIMEOUT_SPEECH_ANALYSIS_SECONDS",
    "content_evaluation": "HATCH_COACH_TIMEOUT_CONVERSATIONAL_EVALUATION_SECONDS",
    "evidence_grounding": "HATCH_COACH_TIMEOUT_EVIDENCE_GROUNDING_SECONDS",
    "follow_up_decision": "HATCH_COACH_TIMEOUT_FOLLOWUP_DECISION_SECONDS",
}

_STAGE_MAX_INVOCATIONS = {
    "transcription": 3,
    "speech_analysis": 2,
    "content_evaluation": 3,
    "evidence_grounding": 3,
    "follow_up_decision": 2,
}

_STAGE_MAX_REPAIRS = {
    "transcription": 0,
    "speech_analysis": 0,
    "content_evaluation": 1,
    "evidence_grounding": 1,
    "follow_up_decision": 1,
}

_SCHEMA_REPAIRABLE_ERROR_CODES = frozenset(
    {
        "coach_transcript_schema_invalid",
        "coach_evaluation_evidence_span_invalid",
        "coach_evaluation_prohibited_inference",
        "coach_grounding_evidence_id_invalid",
        "coach_followup_reason_invalid",
    }
)

_SUCCESS_EQUIVALENT_STAGE_STATES = frozenset(
    {"completed", "reused", "not_applicable", "unavailable", "failed_terminal"}
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


def _stage_state(previous_stages: object, stage_name: str) -> str | None:
    if isinstance(previous_stages, Mapping):
        value = previous_stages.get(stage_name)
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping):
            state = value.get("stage_state", value.get("state"))
            return state if isinstance(state, str) else None
        state = getattr(value, "stage_state", None)
        return state if isinstance(state, str) else None
    if isinstance(previous_stages, Sequence) and not isinstance(
        previous_stages, (str, bytes)
    ):
        for value in previous_stages:
            name = getattr(value, "stage_name", None)
            if name is None and isinstance(value, Mapping):
                name = value.get("stage_name", value.get("name"))
            if name == stage_name:
                state = getattr(value, "stage_state", None)
                if state is None and isinstance(value, Mapping):
                    state = value.get("stage_state", value.get("state"))
                return state if isinstance(state, str) else None
    return None


def select_restart_stage(
    previous_stages: object, immutable_inputs: Mapping[str, object]
) -> str:
    """Select the deterministic manual-retry boundary from immutable inputs.

    Transcription and speech analysis are sibling audio branches.  Speech is
    therefore considered independently after a usable transcript is established;
    later callers decide reuse by graph descendants rather than tuple position.
    """
    recording_type = immutable_inputs.get("recording_type")
    has_transcript = immutable_inputs.get("has_usable_transcript") is True
    has_audio = immutable_inputs.get("has_audio_source") is True
    if recording_type not in {"text", "audio"}:
        raise AttemptPipelineError("coach_attempt_retry_source_unavailable", retryable=False)
    if recording_type == "text" and not has_transcript:
        raise AttemptPipelineError("coach_attempt_retry_source_unavailable", retryable=False)
    if recording_type == "audio":
        if not has_transcript:
            if not has_audio:
                raise AttemptPipelineError(
                    "coach_attempt_retry_source_unavailable", retryable=False
                )
            return "transcription"
        speech_state = _stage_state(previous_stages, "speech_analysis")
        if speech_state not in _SUCCESS_EQUIVALENT_STAGE_STATES:
            if not has_audio:
                raise AttemptPipelineError(
                    "coach_attempt_retry_source_unavailable", retryable=False
                )
            return "speech_analysis"
    for stage_name in (
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    ):
        if _stage_state(previous_stages, stage_name) not in _SUCCESS_EQUIVALENT_STAGE_STATES:
            return stage_name
    raise AttemptPipelineError("coach_attempt_retry_source_unavailable", retryable=False)


def _stage_timeout_seconds(stage_name: str) -> int:
    setting_name = _STAGE_TIMEOUT_SECONDS.get(stage_name)
    if setting_name is None:
        return settings.HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS
    return int(getattr(settings, setting_name))


async def _run_stage_with_budget(
    stage: AttemptStage,
    context: AttemptProcessingContext,
    *,
    persist_counters: Callable[[int, int], Awaitable[None]] | None = None,
) -> StageResult:
    """Run one stage within the V6 retry, repair, and absolute-deadline budgets."""
    maximum_invocations = _STAGE_MAX_INVOCATIONS.get(stage.name, 1)
    maximum_repairs = _STAGE_MAX_REPAIRS.get(stage.name, 0)
    attempt_count = 0
    repair_count = 0

    async def persist() -> None:
        if persist_counters is not None:
            await persist_counters(attempt_count, repair_count)

    async def invoke(
        operation: Callable[[], Awaitable[StageResult]],
        *,
        invocation_deadline: datetime,
        started_at: datetime,
    ) -> StageResult:
        timeout_seconds = effective_timeout(
            invocation_deadline,
            _stage_timeout_seconds(stage.name),
            started_at,
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                return await operation()
        except TimeoutError as error:
            if datetime.utcnow() >= context.deadline_at:
                raise AttemptPipelineError(
                    "coach_attempt_job_budget_exhausted", retryable=True
                ) from error
            return StageResult(
                stage.name,
                "failed_retryable",
                None,
                "coach_stage_timeout",
                True,
                attempt_count,
                repair_count,
            )

    while attempt_count < maximum_invocations:
        started_at = datetime.utcnow()
        remaining = effective_timeout(
            context.deadline_at,
            _stage_timeout_seconds(stage.name),
            started_at,
        )
        invocation_deadline = min(
            context.deadline_at,
            started_at + timedelta(seconds=remaining),
        )
        attempt_count += 1
        await persist()
        result = await invoke(
            lambda: stage.run(context),
            invocation_deadline=invocation_deadline,
            started_at=started_at,
        )
        if result.stage_name != stage.name:
            raise AttemptPipelineError(
                "coach_attempt_stage_graph_invalid", retryable=False
            )
        result = replace(
            result,
            attempt_count=attempt_count,
            repair_count=repair_count,
        )

        repair = getattr(stage, "repair", None)
        if (
            result.stage_state == "failed_retryable"
            and result.error_code in _SCHEMA_REPAIRABLE_ERROR_CODES
            and repair_count < maximum_repairs
            and callable(repair)
        ):
            repair_count += 1
            await persist()
            result = await invoke(
                lambda: repair(context, result),
                invocation_deadline=invocation_deadline,
                started_at=datetime.utcnow(),
            )
            if result.stage_name != stage.name:
                raise AttemptPipelineError(
                    "coach_attempt_stage_graph_invalid", retryable=False
                )
            result = replace(
                result,
                attempt_count=attempt_count,
                repair_count=repair_count,
            )

        if result.stage_state != "failed_retryable" or not result.retryable:
            return result
    return result


async def _transcribe_with_budget(
    transcriber_factory,
    media_path: str,
    *,
    stage_name: Literal["transcription", "speech_analysis"],
    context: AttemptProcessingContext,
    persist_counters: Callable[[int, int], Awaitable[None]],
):
    class ProviderStage:
        name = stage_name

        async def run(self, _context: AttemptProcessingContext) -> StageResult:
            try:
                transcriber = transcriber_factory()
                transcription = await asyncio.to_thread(
                    transcriber.transcribe, media_path
                )
            except Exception:
                return StageResult(
                    self.name,
                    "failed_retryable",
                    None,
                    (
                        "transcription_unavailable"
                        if self.name == "transcription"
                        else "speech_analysis_unavailable"
                    ),
                    True,
                    0,
                    0,
                )
            return StageResult(
                self.name,
                "completed",
                {"transcription": transcription},
                None,
                False,
                0,
                0,
            )

    result = await _run_stage_with_budget(
        ProviderStage(),
        context,
        persist_counters=persist_counters,
    )
    return result


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
        job = await db.get(AsyncJob, claim.job_id)
        if (
            attempt is None or evaluation is None or session is None
            or job is None or job.status not in {"pending", "running"}
            or session.status != "active"
            or session.experience_version != "conversational_v1"
            or session.conversation_state != "processing_answer"
            or session.deletion_state != "not_requested"
            or session.active_recording_id != claim.recording_id
            or session.active_question_id != claim.question_id
            or attempt.question_id != claim.question_id
            or attempt.async_job_id != claim.job_id
            or evaluation.async_job_id != claim.job_id
            or evaluation.state != "pending"
            or job.type != "coach_attempt_processing"
        ):
            raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)

        async def finish(result: AttemptProcessingResult, *, invalid_media: bool = False) -> None:
            """Fence generic-job ownership and attempt terminalisation together."""
            job_change = await db.execute(
                update(AsyncJob)
                .where(AsyncJob.id == claim.job_id, AsyncJob.status.in_(("pending", "running")))
                .values(
                    status="done",
                    result_json=json.dumps({"status": "invalid" if invalid_media else result.evaluation_state}),
                    error=None,
                    updated_at=datetime.utcnow(),
                )
            )
            if job_change.rowcount != 1:
                await db.rollback()
                raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
            finalised = (
                await repository.finalise_invalid_attempt_media(claim=claim)
                if invalid_media
                else await repository.finalise_attempt_processing(claim=claim, result=result)
            )
            if not finalised:
                await db.rollback()
                raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
            await db.commit()
        transcript_id = claim.transcript_version_id
        reason = "coach_evaluation_unavailable"
        media_invalid = False
        speech_unavailable = False
        stages = (await db.scalars(select(InterviewAttemptStage).where(
            InterviewAttemptStage.recording_id == claim.recording_id,
            InterviewAttemptStage.evaluation_version_id == claim.evaluation_version_id,
        ))).all()
        from .coach_processing_snapshot import (
            current_processing_graph_reuse_is_valid,
            exact_processing_snapshot,
        )

        processing_snapshot = exact_processing_snapshot(
            session=session,
            attempt=attempt,
            evaluation=evaluation,
            job=job,
            stages=stages,
        )
        if processing_snapshot is None or not await current_processing_graph_reuse_is_valid(
            db,
            attempt=attempt,
            evaluation=evaluation,
            stages=stages,
            snapshot=processing_snapshot,
        ):
            raise AttemptPipelineError("coach_attempt_stale_claim", retryable=False)
        effective_timeout(
            claim.deadline_at,
            settings.HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS,
            datetime.utcnow(),
        )
        if attempt.recording_type == "audio":
            fence = await repository._get_attempt_processing_fence(claim)
            stage_by_name = {stage.stage_name: stage for stage in stages}
            transcription_stage = stage_by_name.get("transcription")
            speech_stage = stage_by_name.get("speech_analysis")
            if fence is None or transcription_stage is None or speech_stage is None:
                raise AttemptPipelineError("coach_attempt_stage_dependency_missing", retryable=False)
            transcription_needed = transcription_stage.stage_state not in {
                "completed",
                "reused",
                "not_applicable",
            }
            speech_needed = speech_stage.stage_state not in {
                "completed",
                "reused",
                "not_applicable",
                "unavailable",
                "failed_terminal",
            }
            upload = None
            if transcription_needed or speech_needed:
                upload = await db.scalar(select(InterviewAttemptUpload).where(
                    InterviewAttemptUpload.attempt_id == claim.recording_id,
                    InterviewAttemptUpload.result_state == "completed",
                    InterviewAttemptUpload.content_sha256 == fence.expected_audio_content_hash,
                ))
                if (
                    upload is None or not attempt.audio_uri
                    or upload.storage_uri != attempt.audio_uri
                    or not fence.expected_audio_content_hash
                ):
                    raise AttemptPipelineError(
                        "coach_attempt_stage_dependency_missing", retryable=False
                    )
            provider_context = AttemptProcessingContext(
                session_id=claim.session_id,
                question_id=claim.question_id,
                recording_id=claim.recording_id,
                transcript_version_id=claim.transcript_version_id,
                evaluation_version_id=claim.evaluation_version_id,
                processing_generation=claim.processing_generation,
                deadline_at=claim.deadline_at,
                recording_type="audio",
                normalized_transcript=None,
                speech_metrics=None,
                evidence_records=(),
            )

            def persist_provider_counters(stage_name: str):
                async def persist(attempt_count: int, repair_count: int) -> None:
                    changed = await repository.persist_attempt_stage_counters(
                        claim=claim,
                        stage_name=stage_name,
                        attempt_count=attempt_count,
                        repair_count=repair_count,
                    )
                    if not changed:
                        await db.rollback()
                        raise AttemptPipelineError(
                            "coach_attempt_stale_claim", retryable=False
                        )
                    await db.commit()

                return persist

            speech_transcription = None
            transcription = None
            transcription_result = None
            metrics = None
            words: list[dict[str, object]] = []
            if transcription_needed or speech_needed:
                try:
                    from ..services.coach_media_storage import open_verified_audio_read_lease
                    with open_verified_audio_read_lease(
                        Path(settings.HATCH_COACH_MEDIA_ROOT), Path(attempt.audio_uri),
                        fence.expected_audio_content_hash,
                    ) as lease:
                        # The siblings share inode-pinned bytes but retain independent
                        # provider budgets and failure outcomes.
                        if speech_needed:
                            try:
                                speech_result = await _transcribe_with_budget(
                                    transcriber_factory,
                                    str(lease.path),
                                    stage_name="speech_analysis",
                                    context=provider_context,
                                    persist_counters=persist_provider_counters(
                                        "speech_analysis"
                                    ),
                                )
                                speech_transcription = (
                                    speech_result.output.get("transcription")
                                    if speech_result.stage_state == "completed"
                                    and speech_result.output is not None
                                    else None
                                )
                            except AttemptPipelineError:
                                raise
                            except Exception:
                                speech_transcription = None
                        if transcription_needed:
                            try:
                                transcription_result = await _transcribe_with_budget(
                                    transcriber_factory,
                                    str(lease.path),
                                    stage_name="transcription",
                                    context=provider_context,
                                    persist_counters=persist_provider_counters(
                                        "transcription"
                                    ),
                                )
                                transcription = (
                                    transcription_result.output.get("transcription")
                                    if transcription_result.stage_state == "completed"
                                    and transcription_result.output is not None
                                    else None
                                )
                            except AttemptPipelineError:
                                raise
                            except Exception:
                                transcription = None
                                reason = "transcription_unavailable"
                except AttemptPipelineError:
                    raise
                except CoachMediaError:
                    if transcription_needed:
                        reason = "invalid_audio"
                        media_invalid = True
                    speech_unavailable = speech_needed
                except Exception:  # provider detail must not enter durable diagnostics
                    if transcription_needed:
                        reason = "transcription_unavailable"
                    speech_unavailable = speech_needed
            if transcription_needed and (
                transcription is None or not transcription.text.strip()
            ):
                transcription = None
                if not media_invalid:
                    reason = "transcription_unavailable"
            if speech_needed:
                if (
                    speech_transcription is None
                    or not speech_transcription.text.strip()
                    or not speech_transcription.words
                ):
                    speech_unavailable = True
                else:
                    words = [
                        {"w": word.w, "start": word.start, "end": word.end}
                        for word in speech_transcription.words
                    ]
                    try:
                        metrics = SpeechAnalyserService().analyse_from_timestamps(
                            speech_transcription.text, words
                        )
                    except Exception:
                        metrics = None
                        speech_unavailable = True
            speech_metrics_payload = None
            if metrics is not None:
                speech_metrics_payload = {"duration_ms": metrics.duration_ms, "word_count": len(words), "words_per_minute": metrics.wpm, "filler_count": metrics.filler_count, "filler_rate_per_minute": metrics.filler_rate, "hedging_count": metrics.hedging_count, "pause_count": metrics.pause_count, "long_pause_count": metrics.pause_count}
            if (
                transcription_needed
                and transcription_result is not None
                and transcription_result.stage_state == "failed_retryable"
            ):
                from .coach_reconciliation import (
                    recover_exhausted_transcription_claim,
                )
                recovered = await recover_exhausted_transcription_claim(
                    db,
                    claim=claim,
                    error_code=transcription_result.error_code
                    or "transcription_unavailable",
                    attempt_count=transcription_result.attempt_count,
                    repair_count=transcription_result.repair_count,
                    speech_state=(
                        "unavailable" if speech_unavailable else "completed"
                    ),
                    speech_error_code=(
                        "speech_analysis_unavailable" if speech_unavailable else None
                    ),
                    speech_metrics=speech_metrics_payload,
                )
                if not recovered:
                    raise AttemptPipelineError(
                        "coach_attempt_stale_claim", retryable=False
                    )
                return
            if transcription_needed and transcription is None:
                for stage in stages:
                    if stage.stage_state == "reused":
                        continue
                    if stage.stage_name == "audio_persist":
                        stage.stage_state = "unavailable" if media_invalid else "completed"
                        stage.last_error_code = "invalid_audio" if media_invalid else None
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
                result = AttemptProcessingResult(
                    "unavailable", {"answer_level": "not_assessed"}, None,
                    {"reason": reason, "execution_mode": "deterministic_stub"},
                )
                await finish(result, invalid_media=media_invalid)
                return
            if transcription_needed:
                transcript_publish_fence = await db.execute(
                    update(SessionRecording)
                    .where(
                        SessionRecording.id == claim.recording_id,
                        SessionRecording.attempt_state == "pending_processing",
                        SessionRecording.async_job_id == claim.job_id,
                        SessionRecording.processing_generation
                        == claim.processing_generation,
                        SessionRecording.audio_content_hash
                        == fence.expected_audio_content_hash,
                        SessionRecording.current_transcript_version_id.is_(None),
                    )
                    .values(attempt_version=SessionRecording.attempt_version)
                )
                if transcript_publish_fence.rowcount != 1:
                    await db.rollback()
                    raise AttemptPipelineError(
                        "coach_attempt_stale_claim", retryable=False
                    )
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
                    stage.diagnostics_json = _stage_immutable_diagnostics(
                        stage_name=stage.stage_name,
                        audio_content_hash=attempt.audio_content_hash,
                        transcript_version_id=transcript.id,
                        transcript_content_hash=transcript.content_hash,
                        evaluation_contract_version=(
                            evaluation.evaluation_contract_version
                        ),
                        evidence_contract_version=(
                            evaluation.evidence_contract_version
                        ),
                        follow_up_contract_version=(
                            evaluation.follow_up_contract_version
                        ),
                    )
            if speech_metrics_payload is not None:
                attempt.speech_metrics = speech_metrics_payload
        for stage in stages:
            if stage.stage_state in {"not_applicable", "reused"}:
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
        stage_result = await _run_stage_with_budget(stage, context)
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
    from ..repositories.conversational_session_repository import (
        ConversationalSessionRepository,
    )

    async with AsyncSessionLocal() as db:
        repository = ConversationalSessionRepository(db)
        snapshot = await repository.get_attempt_processing_snapshot(
            recording_id=claim.recording_id,
            processing_generation=claim.processing_generation,
        )
        if snapshot is None or snapshot.claim != claim:
            return None
        fence = await repository._get_attempt_processing_fence(claim)
        if (
            fence is None
            or not fence.claim_token
            or fence.processing_contract_version != "coach_processing_v1"
            or fence.source_transcript_version_id != claim.transcript_version_id
            or fence.expected_audio_content_hash is not None
        ):
            return None
        stages = (
            await db.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == claim.recording_id,
                    InterviewAttemptStage.evaluation_version_id
                    == claim.evaluation_version_id,
                    InterviewAttemptStage.job_id == claim.job_id,
                    InterviewAttemptStage.expected_processing_generation
                    == claim.processing_generation,
                    InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                )
            )
        ).all()
        required_stages = {
            "audio_persist", "transcription", "speech_analysis",
            "content_evaluation", "evidence_grounding", "follow_up_decision",
            "coaching_enrichment", "audio_cleanup",
        }
        transcript_bound = {
            "content_evaluation", "evidence_grounding", "follow_up_decision",
            "coaching_enrichment",
        }
        if (
            len(stages) != 8
            or {stage.stage_name for stage in stages} != required_stages
            or any(stage.claim_token != fence.claim_token for stage in stages)
            or any(
                stage.source_transcript_version_id != claim.transcript_version_id
                for stage in stages if stage.stage_name in transcript_bound
            )
            or any(
                stage.source_transcript_version_id is not None
                for stage in stages if stage.stage_name not in transcript_bound
            )
        ):
            return None
        transcript = await db.scalar(
            select(InterviewTranscriptVersion)
            .join(SessionRecording, SessionRecording.id == InterviewTranscriptVersion.recording_id)
            .join(InterviewAttemptEvaluation, InterviewAttemptEvaluation.id == claim.evaluation_version_id)
            .join(InterviewSession, InterviewSession.id == SessionRecording.session_id)
            .join(AsyncJob, AsyncJob.id == claim.job_id)
            .where(
                InterviewTranscriptVersion.id == claim.transcript_version_id,
                InterviewTranscriptVersion.recording_id == claim.recording_id,
                InterviewTranscriptVersion.processing_generation == claim.processing_generation,
                SessionRecording.session_id == claim.session_id,
                SessionRecording.question_id == claim.question_id,
                SessionRecording.current_transcript_version_id == claim.transcript_version_id,
                SessionRecording.processing_generation == claim.processing_generation,
                SessionRecording.async_job_id == claim.job_id,
                SessionRecording.attempt_state == "pending_processing",
                InterviewAttemptEvaluation.recording_id == claim.recording_id,
                InterviewAttemptEvaluation.transcript_version_id == claim.transcript_version_id,
                InterviewAttemptEvaluation.async_job_id == claim.job_id,
                InterviewAttemptEvaluation.state == "pending",
                InterviewSession.active_question_id == claim.question_id,
                InterviewSession.active_recording_id == claim.recording_id,
                InterviewSession.conversation_state == "processing_answer",
                InterviewSession.status == "active",
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.deletion_state == "not_requested",
                AsyncJob.type == "coach_attempt_processing",
                AsyncJob.status.in_(("pending", "running")),
            )
        )
        return transcript.transcript if transcript is not None else None
