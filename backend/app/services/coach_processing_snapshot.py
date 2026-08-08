"""Pure validation of one persisted conversational processing ownership snapshot."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.async_job import AsyncJob
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewTranscriptVersion,
    SessionRecording,
)
from .coach_conversational_contracts import (
    EVIDENCE_GROUNDING_CONTRACT,
    ERROR_REGISTRY,
    FOLLOW_UP_CONTRACT,
    RUBRIC_CONTRACT,
)


_CLAIM_KEYS = frozenset(
    {
        "processing_generation",
        "job_deadline_at",
        "source_audio_content_hash",
        "source_transcript_version_id",
        "expected_session_state_version",
        "processing_contract_version",
        "claim_token",
    }
)
TRANSCRIPT_BOUND_STAGES = frozenset(
    {
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    }
)
_TRANSCRIPT_PROVENANCE_STAGES = TRANSCRIPT_BOUND_STAGES | {"transcription"}
_DEADLINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)?$"
)
_PROCESSING_STAGE_NAMES = frozenset(
    {
        "audio_persist",
        "transcription",
        "speech_analysis",
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
        "audio_cleanup",
    }
)


@dataclass(frozen=True)
class ProcessingSnapshot:
    claim: Mapping[str, object]
    deadline: datetime
    transcript_version_id: str | None


@dataclass(frozen=True)
class _RetryableProcessingSnapshot:
    evaluation: InterviewAttemptEvaluation
    stages: tuple[InterviewAttemptStage, ...]
    snapshot: ProcessingSnapshot


async def load_retryable_processing_snapshot(
    db: AsyncSession,
    *,
    session: InterviewSession,
    attempt: SessionRecording,
) -> _RetryableProcessingSnapshot | None:
    """Load the exact failed generation that manual retry admission may consume."""
    session = await db.scalar(
        select(InterviewSession)
        .where(InterviewSession.id == session.id)
        .execution_options(populate_existing=True)
    )
    attempt = await db.scalar(
        select(SessionRecording)
        .where(SessionRecording.id == attempt.id)
        .execution_options(populate_existing=True)
    )
    if session is None or attempt is None:
        return None
    error = ERROR_REGISTRY.get(session.recoverable_error_code or "")
    if (
        session.status != "active"
        or session.conversation_state != "recoverable_error"
        or session.recoverable_error_scope != "attempt_processing"
        or session.deletion_state != "not_requested"
        or session.active_recording_id != attempt.id
        or session.active_question_id != attempt.question_id
        or attempt.session_id != session.id
        or attempt.attempt_state != "recoverable_error"
        or attempt.evaluation_state != "failed"
        or attempt.async_job_id is not None
        or attempt.processing_retry_count >= attempt.processing_retry_limit
        or error is None
        or not error.retryable
    ):
        return None
    evaluations = list(
        (
            await db.scalars(
                select(InterviewAttemptEvaluation)
                .where(InterviewAttemptEvaluation.recording_id == attempt.id)
                .order_by(InterviewAttemptEvaluation.version_number.desc())
                .limit(2)
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if not evaluations:
        return None
    evaluation = evaluations[0]
    if evaluation.state != "failed" or evaluation.async_job_id is None:
        return None
    result = (
        evaluation.diagnostics_json.get("result")
        if isinstance(evaluation.diagnostics_json, Mapping)
        else None
    )
    if (
        not isinstance(result, Mapping)
        or set(result) != {"reason_code"}
        or result.get("reason_code") != session.recoverable_error_code
        or evaluation.evaluation_contract_version != RUBRIC_CONTRACT
        or evaluation.evidence_contract_version != EVIDENCE_GROUNDING_CONTRACT
        or evaluation.follow_up_contract_version != FOLLOW_UP_CONTRACT
    ):
        return None
    stages = tuple(
        (
            await db.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
                ).execution_options(populate_existing=True)
            )
        ).all()
    )
    if (
        len(stages) != len(_PROCESSING_STAGE_NAMES)
        or {stage.stage_name for stage in stages} != _PROCESSING_STAGE_NAMES
        or any(stage.stage_state in {"pending", "running"} for stage in stages)
        or not any(stage.stage_state == "failed_retryable" for stage in stages)
    ):
        return None
    snapshot = exact_processing_snapshot(
        session=session,
        attempt=attempt,
        evaluation=evaluation,
        job=None,
        stages=stages,
        allow_detached_retry_failure=True,
    )
    if snapshot is None or not await current_processing_graph_reuse_is_valid(
        db,
        attempt=attempt,
        evaluation=evaluation,
        stages=stages,
        snapshot=snapshot,
    ):
        return None
    return _RetryableProcessingSnapshot(
        evaluation=evaluation,
        stages=stages,
        snapshot=snapshot,
    )


def _parse_claim(evaluation: InterviewAttemptEvaluation) -> ProcessingSnapshot | None:
    diagnostics = evaluation.diagnostics_json
    if not isinstance(diagnostics, Mapping):
        return None
    claim = diagnostics.get("processing_claim")
    if not isinstance(claim, Mapping) or frozenset(claim) != _CLAIM_KEYS:
        return None
    if (
        type(claim.get("processing_generation")) is not int
        or type(claim.get("expected_session_state_version")) is not int
        or not isinstance(claim.get("job_deadline_at"), str)
        or not isinstance(claim.get("processing_contract_version"), str)
        or not isinstance(claim.get("claim_token"), str)
        or not claim.get("claim_token")
        or (
            claim.get("source_audio_content_hash") is not None
            and not isinstance(claim.get("source_audio_content_hash"), str)
        )
        or (
            claim.get("source_transcript_version_id") is not None
            and not isinstance(claim.get("source_transcript_version_id"), str)
        )
    ):
        return None
    deadline_text = claim["job_deadline_at"]
    if _DEADLINE_RE.fullmatch(deadline_text) is None:
        return None
    try:
        deadline = datetime.fromisoformat(deadline_text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if deadline.tzinfo is not None:
        if deadline.utcoffset() != timezone.utc.utcoffset(deadline):
            return None
        deadline = deadline.astimezone(timezone.utc).replace(tzinfo=None)
    return ProcessingSnapshot(
        claim=claim,
        deadline=deadline,
        transcript_version_id=evaluation.transcript_version_id,
    )


async def load_owned_processing_evaluation(
    db: AsyncSession, attempt: SessionRecording
) -> InterviewAttemptEvaluation | None:
    """Resolve the owned pending generation without consulting the terminal pointer."""
    if (
        attempt.attempt_state == "pending_processing"
        and attempt.async_job_id is not None
    ):
        candidates = list(
            (
                await db.scalars(
                    select(InterviewAttemptEvaluation)
                    .where(
                        InterviewAttemptEvaluation.recording_id == attempt.id,
                        InterviewAttemptEvaluation.async_job_id == attempt.async_job_id,
                        InterviewAttemptEvaluation.state == "pending",
                    )
                    .order_by(InterviewAttemptEvaluation.version_number.desc())
                    .limit(2)
                )
            ).all()
        )
        exact = [
            candidate
            for candidate in candidates
            if (snapshot := _parse_claim(candidate)) is not None
            and snapshot.claim["processing_generation"] == attempt.processing_generation
        ]
        return exact[0] if len(exact) == 1 else None
    if attempt.current_evaluation_version_id is None:
        return None
    return await db.scalar(
        select(InterviewAttemptEvaluation).where(
            InterviewAttemptEvaluation.id == attempt.current_evaluation_version_id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
        )
    )


def exact_processing_snapshot(
    *,
    session: InterviewSession,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    job: AsyncJob | None,
    stages: Sequence[InterviewAttemptStage],
    allow_detached_retry_failure: bool = False,
) -> ProcessingSnapshot | None:
    """Return the exact current claim, or fail closed without inspecting content."""
    snapshot = _parse_claim(evaluation)
    if snapshot is None:
        return None
    claim = snapshot.claim
    job_id = job.id if job is not None else evaluation.async_job_id
    transcript_id = evaluation.transcript_version_id
    if (
        session.active_recording_id != attempt.id
        or attempt.session_id != session.id
        or evaluation.recording_id != attempt.id
        or evaluation.async_job_id != job_id
        or job_id is None
        or (job is None and not allow_detached_retry_failure)
        or (job is not None and job.type != "coach_attempt_processing")
        or claim["processing_generation"] != attempt.processing_generation
        or claim["source_audio_content_hash"] != attempt.audio_content_hash
        or claim["processing_contract_version"] != "coach_processing_v1"
        or not stages
        or len({stage.stage_name for stage in stages}) != len(stages)
    ):
        return None
    if attempt.attempt_state == "pending_processing":
        if attempt.async_job_id != job_id:
            return None
    elif (
        allow_detached_retry_failure
        and attempt.attempt_state == "recoverable_error"
        and attempt.evaluation_state == "failed"
        and attempt.async_job_id is None
        and evaluation.state == "failed"
    ):
        pass
    elif (
        attempt.async_job_id is not None
        or attempt.current_evaluation_version_id != evaluation.id
    ):
        return None
    if attempt.recording_type == "text":
        if (
            transcript_id is None
            or claim["source_transcript_version_id"] != transcript_id
            or attempt.current_transcript_version_id != transcript_id
        ):
            return None
    elif attempt.recording_type == "audio":
        source_transcript_id = claim["source_transcript_version_id"]
        if attempt.current_transcript_version_id != transcript_id:
            return None
        if source_transcript_id is None:
            pass
        else:
            transcription_rows = [
                stage for stage in stages if stage.stage_name == "transcription"
            ]
            if (
                transcript_id is None
                or source_transcript_id != transcript_id
                or len(transcription_rows) != 1
                or transcription_rows[0].stage_state != "reused"
                or transcription_rows[0].reused_from_stage_id is None
            ):
                return None
    else:
        return None
    for stage in stages:
        expected_source = (
            transcript_id if stage.stage_name in TRANSCRIPT_BOUND_STAGES else None
        )
        if (
            stage.recording_id != attempt.id
            or stage.evaluation_version_id != evaluation.id
            or stage.job_id != job_id
            or stage.expected_processing_generation != attempt.processing_generation
            or stage.job_deadline_at != snapshot.deadline
            or stage.claim_token != claim["claim_token"]
            or stage.source_transcript_version_id != expected_source
        ):
            return None
    return snapshot


async def _claim_source_transcript_is_valid(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    claim: Mapping[str, object],
    require_transcription_row: bool = True,
) -> bool:
    if attempt.recording_type == "text":
        return (
            evaluation.transcript_version_id is not None
            and claim["source_transcript_version_id"]
            == evaluation.transcript_version_id
        )
    if attempt.recording_type != "audio":
        return False
    transcription_rows = list(
        (
            await db.scalars(
                select(InterviewAttemptStage)
                .where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
                    InterviewAttemptStage.stage_name == "transcription",
                )
                .limit(2)
            )
        ).all()
    )
    if len(transcription_rows) != 1:
        return bool(
            not require_transcription_row
            and not transcription_rows
            and claim["source_transcript_version_id"] is None
        )
    transcription = transcription_rows[0]
    expected_source = (
        evaluation.transcript_version_id
        if transcription.stage_state == "reused"
        and transcription.reused_from_stage_id is not None
        else None
    )
    return claim["source_transcript_version_id"] == expected_source


async def current_processing_graph_reuse_is_valid(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    stages: Sequence[InterviewAttemptStage],
    snapshot: ProcessingSnapshot,
) -> bool:
    """Recursively prove every reused row in the current processing graph."""
    if any(
        (stage.stage_state == "reused")
        != (stage.reused_from_stage_id is not None)
        for stage in stages
    ):
        return False
    reused = [stage for stage in stages if stage.stage_state == "reused"]
    if not await _claim_source_transcript_is_valid(
        db,
        attempt=attempt,
        evaluation=evaluation,
        claim=snapshot.claim,
        require_transcription_row=bool(reused),
    ):
        return False
    transcript = (
        await db.get(InterviewTranscriptVersion, evaluation.transcript_version_id)
        if evaluation.transcript_version_id is not None
        else None
    )
    if evaluation.transcript_version_id is not None and (
        transcript is None
        or transcript.recording_id != attempt.id
        or transcript.processing_generation is None
        or transcript.processing_generation > attempt.processing_generation
    ):
        return False
    return all(
        [
            await reused_stage_lineage_is_valid(
                db,
                attempt=attempt,
                evaluation=evaluation,
                stage=stage,
                result_transcript=(
                    transcript
                    if stage.stage_name in _TRANSCRIPT_PROVENANCE_STAGES
                    else None
                ),
            )
            for stage in reused
        ]
    )


async def reused_stage_lineage_is_valid(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    stage: InterviewAttemptStage,
    result_transcript: InterviewTranscriptVersion | None,
    visited: frozenset[str] = frozenset(),
) -> bool:
    """Recursively prove every ownership and immutable-input hop of a reuse."""
    current_snapshot = _parse_claim(evaluation)
    if current_snapshot is None:
        return False
    current_claim = current_snapshot.claim
    transcript_provenance = stage.stage_name in _TRANSCRIPT_PROVENANCE_STAGES
    current_expected_source = (
        evaluation.transcript_version_id
        if stage.stage_name in TRANSCRIPT_BOUND_STAGES
        else None
    )
    from ..repositories.conversational_session_repository import (
        _stage_immutable_diagnostics,
    )

    current_expected_diagnostics = _stage_immutable_diagnostics(
        stage_name=stage.stage_name,
        audio_content_hash=attempt.audio_content_hash,
        transcript_version_id=(
            result_transcript.id if result_transcript is not None else None
        ),
        transcript_content_hash=(
            result_transcript.content_hash if result_transcript is not None else None
        ),
        evaluation_contract_version=evaluation.evaluation_contract_version,
        evidence_contract_version=evaluation.evidence_contract_version,
        follow_up_contract_version=evaluation.follow_up_contract_version,
    )
    if (
        (
            transcript_provenance
            and not await _claim_source_transcript_is_valid(
                db,
                attempt=attempt,
                evaluation=evaluation,
                claim=current_claim,
            )
        )
        or stage.recording_id != attempt.id
        or stage.evaluation_version_id != evaluation.id
        or stage.expected_processing_generation
        != current_claim["processing_generation"]
        or stage.job_id != evaluation.async_job_id
        or stage.claim_token != current_claim["claim_token"]
        or stage.job_deadline_at != current_snapshot.deadline
        or stage.source_transcript_version_id != current_expected_source
        or current_claim["processing_contract_version"] != "coach_processing_v1"
        or current_claim["source_audio_content_hash"] != attempt.audio_content_hash
        or stage.diagnostics_json != current_expected_diagnostics
        or (
            transcript_provenance
            and evaluation.transcript_version_id
            != (result_transcript.id if result_transcript is not None else None)
        )
    ):
        return False
    if stage.stage_state == "completed":
        return stage.reused_from_stage_id is None
    if (
        stage.stage_state != "reused"
        or stage.reused_from_stage_id is None
        or stage.id in visited
        or len(visited) > 32
    ):
        return False
    source = await db.get(InterviewAttemptStage, stage.reused_from_stage_id)
    if (
        source is None
        or source.recording_id != attempt.id
        or source.stage_name != stage.stage_name
        or source.expected_processing_generation
        != stage.expected_processing_generation - 1
        or source.stage_state not in {"completed", "reused"}
    ):
        return False
    source_evaluation = await db.get(
        InterviewAttemptEvaluation, source.evaluation_version_id
    )
    if (
        source_evaluation is None
        or source_evaluation.recording_id != attempt.id
        or source_evaluation.version_number != evaluation.version_number - 1
        or source_evaluation.async_job_id is None
        or source_evaluation.evaluation_contract_version
        != evaluation.evaluation_contract_version
        or source_evaluation.evidence_contract_version
        != evaluation.evidence_contract_version
        or source_evaluation.follow_up_contract_version
        != evaluation.follow_up_contract_version
    ):
        return False
    source_snapshot = _parse_claim(source_evaluation)
    if source_snapshot is None:
        return False
    claim = source_snapshot.claim
    expected_source = (
        source_evaluation.transcript_version_id
        if source.stage_name in TRANSCRIPT_BOUND_STAGES
        else None
    )
    expected_diagnostics = _stage_immutable_diagnostics(
        stage_name=source.stage_name,
        audio_content_hash=attempt.audio_content_hash,
        transcript_version_id=(
            result_transcript.id if result_transcript is not None else None
        ),
        transcript_content_hash=(
            result_transcript.content_hash if result_transcript is not None else None
        ),
        evaluation_contract_version=source_evaluation.evaluation_contract_version,
        evidence_contract_version=source_evaluation.evidence_contract_version,
        follow_up_contract_version=source_evaluation.follow_up_contract_version,
    )
    if (
        claim["processing_generation"] != source.expected_processing_generation
        or claim["processing_contract_version"] != "coach_processing_v1"
        or claim["source_audio_content_hash"] != attempt.audio_content_hash
        or source.job_id != source_evaluation.async_job_id
        or source.claim_token != claim["claim_token"]
        or source.job_deadline_at != source_snapshot.deadline
        or source.source_transcript_version_id != expected_source
        or source.diagnostics_json != expected_diagnostics
        or (
            transcript_provenance
            and source_evaluation.transcript_version_id
            != (result_transcript.id if result_transcript is not None else None)
        )
    ):
        return False
    return await reused_stage_lineage_is_valid(
        db,
        attempt=attempt,
        evaluation=source_evaluation,
        stage=source,
        result_transcript=result_transcript,
        visited=visited | {stage.id},
    )
