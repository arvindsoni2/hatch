"""Idempotent recovery for abandoned Coach answer and report claims."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Mapping

from sqlalchemy import and_, case, exists, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.async_job import AsyncJob
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewTranscriptVersion,
    SessionQuestion,
    SessionRecording,
)
from ..repositories.conversational_session_repository import (
    AttemptProcessingClaim,
    ConversationalSessionRepository,
    SessionEventInput,
    _stage_immutable_diagnostics,
    partition_current_processing_stages,
)
from ..repositories.session_repository import SessionRepository
from .coach_contracts import CoachDiagnostic, failed_answer_payload
from .coach_conversational_contracts import (
    AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS,
    REPORT_CONTRACT,
    RUBRIC_CONTRACT,
    TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS,
)
from .coach_processing_snapshot import (
    TRANSCRIPT_BOUND_STAGES,
    ProcessingSnapshot,
    current_processing_graph_reuse_is_valid,
    exact_processing_snapshot,
    load_owned_processing_evaluation,
)

logger = logging.getLogger(__name__)


class _ReconciliationFenceLost(RuntimeError):
    """Abort and roll back a reconciliation whose persisted snapshot changed."""


def _is_due(
    now: datetime,
    reference: datetime | None,
    *,
    job_status: str | None,
    job_timeout_seconds: int,
) -> bool:
    if reference is None:
        return True
    threshold = settings.HATCH_COACH_STALE_JOB_GRACE_SECONDS
    if job_status in {"pending", "running"}:
        threshold += job_timeout_seconds
    return now - reference >= timedelta(seconds=threshold)


def _recovery_diagnostic(stage: str, gates: list[str]) -> dict:
    return CoachDiagnostic(
        stage=stage,
        outcome="failed",
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=gates,
        duration_ms=0,
    ).model_dump(mode="json")


async def reconcile_session(
    db: AsyncSession,
    session_id: str,
    *,
    now: datetime | None = None,
) -> int:
    """Recover stale pending attempts and a stale building report for one session."""
    now = now or datetime.utcnow()
    changed = 0
    recordings = list(
        (
            await db.execute(
                select(SessionRecording).where(
                    SessionRecording.session_id == session_id,
                    SessionRecording.evaluation_state == "pending",
                )
            )
        ).scalars()
    )
    repository = SessionRepository(db)
    for recording in recordings:
        job = (
            await db.execute(
                select(AsyncJob).where(AsyncJob.id == recording.async_job_id)
            )
        ).scalar_one_or_none()
        reference = job.updated_at if job else recording.created_at
        status = job.status if job else None
        if not _is_due(
            now,
            reference,
            job_status=status,
            job_timeout_seconds=settings.HATCH_COACH_TIMEOUT_ANSWER_SUBMIT_JOB_SECONDS,
        ):
            continue
        gates = ["coach_async_job_failed"]
        if status == "done":
            gates.append("coach_persistence_failed")
        payload = failed_answer_payload(reason_code="stale_async_job_recovered")
        payload["diagnostic"]["gate_codes"] = gates
        reconciled = await repository.finalize_answer_attempt(
            recording.id,
            recording.async_job_id or "",
            evaluation_state="failed",
            evaluation_json=json.dumps(payload),
        )
        if reconciled:
            changed += 1
            if job and job.status in {"pending", "running"}:
                await db.execute(
                    update(AsyncJob)
                    .where(
                        AsyncJob.id == job.id,
                        AsyncJob.status.in_(("pending", "running")),
                    )
                    .values(
                        status="failed",
                        error="stale_async_job_recovered",
                        updated_at=now,
                    )
                )

    session = (
        await db.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
    ).scalar_one_or_none()
    if session and session.report_state == "building":
        job = (
            await db.execute(
                select(AsyncJob).where(AsyncJob.id == session.report_job_id)
            )
        ).scalar_one_or_none()
        reference = job.updated_at if job else session.report_started_at
        status = job.status if job else None
        if _is_due(
            now,
            reference,
            job_status=status,
            job_timeout_seconds=settings.HATCH_COACH_TIMEOUT_SESSION_END_JOB_SECONDS,
        ):
            gates = ["coach_async_job_failed"]
            if status == "done":
                gates.append("coach_persistence_failed")
            diagnostic = _recovery_diagnostic("session_report", gates)
            reconciled = await repository.fail_report_claim(
                session.id,
                session.report_job_id or "",
                diagnostic,
                reason_code="stale_async_job_recovered",
            )
            if reconciled:
                changed += 1
                if job and job.status in {"pending", "running"}:
                    await db.execute(
                        update(AsyncJob)
                        .where(
                            AsyncJob.id == job.id,
                            AsyncJob.status.in_(("pending", "running")),
                        )
                        .values(
                            status="failed",
                            error="stale_async_job_recovered",
                            updated_at=now,
                        )
                    )
    if changed:
        await db.commit()
    return changed


async def _fail_async_job(
    db: AsyncSession, *, job_id: str | None, code: str, now: datetime
) -> None:
    """Fence a generic job using content-free diagnostics only."""
    if job_id is None:
        return
    await db.execute(
        update(AsyncJob)
        .where(
            AsyncJob.id == job_id,
            AsyncJob.status.in_(("pending", "running")),
        )
        .values(status="failed", error=code, result_json=None, updated_at=now)
    )


async def _reconcile_expired_setup_claim(
    db: AsyncSession, session: InterviewSession, now: datetime
) -> int:
    if (
        session.status != "setup"
        or session.conversation_state != "planning"
        or session.setup_job_id is None
        or session.setup_claim_token is None
        or session.setup_claim_expires_at is None
        or session.setup_claim_expires_at >= now
        or session.deletion_state != "not_requested"
    ):
        return 0
    terminal = session.setup_attempt_count >= session.setup_max_attempts
    prior_version = session.state_version
    setup_job_id = session.setup_job_id
    setup_claim_token = session.setup_claim_token
    setup_claim_expires_at = session.setup_claim_expires_at
    changed = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session.id,
            InterviewSession.experience_version == "conversational_v1",
            InterviewSession.status == "setup",
            InterviewSession.conversation_state == "planning",
            InterviewSession.state_version == prior_version,
            InterviewSession.setup_generation == session.setup_generation,
            InterviewSession.setup_job_id == setup_job_id,
            InterviewSession.setup_claim_token == setup_claim_token,
            InterviewSession.setup_claim_expires_at == setup_claim_expires_at,
            InterviewSession.setup_claim_expires_at < now,
            InterviewSession.deletion_state == "not_requested",
        )
        .values(
            status="failed" if terminal else "setup",
            conversation_state="failed" if terminal else "recoverable_error",
            recoverable_error_scope="setup",
            recoverable_error_code="coach_setup_claim_expired",
            recoverable_error_context_json=None,
            setup_job_id=None,
            setup_claim_token=None,
            setup_claimed_at=None,
            setup_claim_expires_at=None,
            state_version=InterviewSession.state_version + 1,
            last_activity_at=now,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = changed.scalar_one_or_none()
    if state_version is None:
        return 0
    await _fail_async_job(
        db,
        job_id=setup_job_id,
        code="coach_setup_claim_expired",
        now=now,
    )
    await ConversationalSessionRepository(db).append_session_events(
        session_id=session.id,
        events=(
            SessionEventInput(
                event_type="session_plan_claim_expired",
                actor_type="reconciler",
                state_version=state_version,
                state_before="planning",
                state_after="failed" if terminal else "recoverable_error",
                payload_json={"reason_code": "coach_setup_claim_expired"},
            ),
        ),
    )
    return 1


def _terminal_attempt_state(value: str | None) -> bool:
    return value in {"completed", "unavailable"}


_ACTIVE_STAGE_STATES = frozenset({"pending", "running"})
_TERMINAL_STAGE_STATES = frozenset(
    {"completed", "reused", "not_applicable", "unavailable", "failed_terminal"}
)
_RECOVERY_STAGE_STATES = frozenset(
    {
        "not_started",
        "pending",
        "running",
        "unavailable",
        "failed_retryable",
        "failed_terminal",
    }
)
_HARD_FAILURE_STAGES = frozenset(
    {"audio_persist", "transcription", "content_evaluation"}
)
_TERMINAL_FALLBACK_STAGES = frozenset(
    {
        "speech_analysis",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
        "audio_cleanup",
    }
)


async def _terminal_processing_form_is_valid(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    stages: list[InterviewAttemptStage],
    snapshot: ProcessingSnapshot,
) -> bool:
    if any(stage.stage_state not in _TERMINAL_STAGE_STATES for stage in stages):
        return False
    stage_by_name = {stage.stage_name: stage for stage in stages}
    transcript_id = evaluation.transcript_version_id
    result = evaluation.diagnostics_json.get("result")
    if not isinstance(result, dict):
        return False
    reason = result.get("reason_code", result.get("code"))
    if evaluation.state == "completed":
        if (
            transcript_id is None
            or attempt.current_transcript_version_id != transcript_id
        ):
            return False
        transcript = await db.get(InterviewTranscriptVersion, transcript_id)
        return bool(
            transcript is not None
            and transcript.recording_id == attempt.id
            and (
                attempt.recording_type != "audio"
                or transcript.processing_generation == attempt.processing_generation
            )
            and stage_by_name.get("content_evaluation") is not None
            and stage_by_name["content_evaluation"].stage_state == "completed"
        )
    if evaluation.state != "unavailable":
        return False
    downstream = {
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
    }
    if transcript_id is None:
        transcription = stage_by_name.get("transcription")
        created = await db.scalar(
            select(InterviewTranscriptVersion.id)
            .where(
                InterviewTranscriptVersion.recording_id == attempt.id,
                InterviewTranscriptVersion.processing_generation
                == attempt.processing_generation,
            )
            .limit(1)
        )
        return bool(
            attempt.recording_type == "audio"
            and attempt.current_transcript_version_id is None
            and created is None
            and reason in AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS
            and transcription is not None
            and transcription.stage_state in {"unavailable", "failed_terminal"}
            and transcription.last_error_code == reason
            and not any(
                stage.stage_name in downstream
                and stage.stage_state in {"completed", "reused"}
                for stage in stages
            )
        )
    content = stage_by_name.get("content_evaluation")
    return bool(
        attempt.current_transcript_version_id == transcript_id
        and reason in TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS
        and content is not None
        and content.stage_state in {"unavailable", "failed_terminal"}
        and content.last_error_code == reason
        and not any(
            stage.stage_name
            in {"evidence_grounding", "follow_up_decision", "coaching_enrichment"}
            and stage.stage_state in {"completed", "reused"}
            for stage in stages
        )
    )


def _unavailable_rubric() -> dict[str, str]:
    return {
        "answer_level": "not_assessed",
        "contract_version": RUBRIC_CONTRACT,
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


async def _supersede_prior_evaluation(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
) -> None:
    prior_id = attempt.current_evaluation_version_id
    if prior_id is None or prior_id == evaluation.id:
        return
    changed = await db.execute(
        update(InterviewAttemptEvaluation)
        .where(
            InterviewAttemptEvaluation.id == prior_id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.state.in_(
                ("completed", "unavailable", "invalid", "failed")
            ),
        )
        .values(state="superseded")
    )
    if changed.rowcount != 1:
        raise _ReconciliationFenceLost


async def _publish_downstream_processing_fallback(
    db: AsyncSession,
    *,
    session: InterviewSession,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    job: AsyncJob,
    snapshot: ProcessingSnapshot,
    recovery_stages: list[InterviewAttemptStage],
    rubric: dict,
    error_code: str,
    now: datetime,
) -> int:
    """Publish completed content while terminalizing optional downstream work."""
    claim = snapshot.claim
    recovery_ids = [stage.id for stage in recovery_stages]
    stage_change = await db.execute(
        update(InterviewAttemptStage)
        .where(
            InterviewAttemptStage.id.in_(recovery_ids),
            InterviewAttemptStage.recording_id == attempt.id,
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.job_id == job.id,
            InterviewAttemptStage.claim_token == claim["claim_token"],
            InterviewAttemptStage.expected_processing_generation
            == attempt.processing_generation,
            InterviewAttemptStage.stage_state.in_(_RECOVERY_STAGE_STATES),
            InterviewAttemptStage.job_deadline_at == snapshot.deadline,
        )
        .values(
            stage_state="unavailable",
            last_error_code=error_code,
            completed_at=now,
            claim_token=None,
        )
    )
    await _supersede_prior_evaluation(
        db,
        attempt=attempt,
        evaluation=evaluation,
    )
    attempt_change = await db.execute(
        update(SessionRecording)
        .where(
            SessionRecording.id == attempt.id,
            SessionRecording.session_id == session.id,
            SessionRecording.question_id == session.active_question_id,
            SessionRecording.processing_generation == attempt.processing_generation,
            SessionRecording.async_job_id == job.id,
            SessionRecording.current_transcript_version_id.is_not_distinct_from(
                snapshot.transcript_version_id
            ),
            SessionRecording.audio_content_hash.is_not_distinct_from(
                attempt.audio_content_hash
            ),
            SessionRecording.attempt_state == "pending_processing",
            SessionRecording.evaluation_state == "pending",
        )
        .values(
            attempt_state="completed",
            evaluation_state="completed",
            evaluation_json=_canonical_json(rubric),
            current_evaluation_version_id=evaluation.id,
            async_job_id=None,
            processing_completed_at=now,
        )
    )
    evaluation_change = await db.execute(
        update(InterviewAttemptEvaluation)
        .where(
            InterviewAttemptEvaluation.id == evaluation.id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.async_job_id == job.id,
            InterviewAttemptEvaluation.transcript_version_id.is_not_distinct_from(
                snapshot.transcript_version_id
            ),
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"][
                "claim_token"
            ].as_string()
            == claim["claim_token"],
            InterviewAttemptEvaluation.state == "pending",
        )
        .values(
            state="completed",
            rubric_json=dict(rubric),
            completed_at=now,
            diagnostics_json={
                "processing_claim": dict(claim),
                "result": {"code": "completed"},
            },
        )
    )
    session_change = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session.id,
            InterviewSession.status == "active",
            InterviewSession.conversation_state == "processing_answer",
            InterviewSession.state_version == session.state_version,
            InterviewSession.active_question_id == attempt.question_id,
            InterviewSession.active_recording_id == attempt.id,
            InterviewSession.deletion_state == "not_requested",
        )
        .values(
            conversation_state="awaiting_next_action",
            recoverable_error_scope=None,
            recoverable_error_code=None,
            recoverable_error_context_json=None,
            state_version=InterviewSession.state_version + 1,
            activity_version=InterviewSession.activity_version + 1,
            last_activity_at=now,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = session_change.scalar_one_or_none()
    if (
        stage_change.rowcount != len(recovery_stages)
        or attempt_change.rowcount != 1
        or evaluation_change.rowcount != 1
        or state_version is None
    ):
        raise _ReconciliationFenceLost
    await _fail_async_job(db, job_id=job.id, code=error_code, now=now)
    await ConversationalSessionRepository(db).append_session_events(
        session_id=session.id,
        events=(
            SessionEventInput(
                event_type="attempt_processing_completed",
                actor_type="reconciler",
                state_version=state_version,
                state_before="processing_answer",
                state_after="awaiting_next_action",
                question_id=attempt.question_id,
                recording_id=attempt.id,
                payload_json={"state": "completed"},
            ),
        ),
    )
    return 1


async def _reconcile_processing_answer(
    db: AsyncSession,
    session: InterviewSession,
    now: datetime,
    *,
    forced_retryable_failure: bool = False,
) -> int:
    if (
        session.status != "active"
        or session.conversation_state != "processing_answer"
        or session.active_question_id is None
        or session.active_recording_id is None
        or session.deletion_state != "not_requested"
    ):
        return 0
    attempt = await db.scalar(
        select(SessionRecording).where(
            SessionRecording.id == session.active_recording_id,
            SessionRecording.session_id == session.id,
            SessionRecording.question_id == session.active_question_id,
        )
    )
    if attempt is None:
        return 0
    evaluation = await load_owned_processing_evaluation(db, attempt)
    job_id = attempt.async_job_id or (evaluation.async_job_id if evaluation else None)
    job = await db.get(AsyncJob, job_id) if job_id else None
    all_stages = list(
        (
            await db.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
                )
            )
        ).all()
        if evaluation is not None
        else ()
    )
    partition = (
        await partition_current_processing_stages(
            db,
            attempt=attempt,
            evaluation=evaluation,
            stages=all_stages,
            processing_job_id=job.id,
        )
        if evaluation is not None and job is not None
        else None
    )
    stages = list(partition[0]) if partition is not None else all_stages
    snapshot = (
        exact_processing_snapshot(
            session=session,
            attempt=attempt,
            evaluation=evaluation,
            job=job,
            stages=stages,
        )
        if evaluation is not None and job is not None and partition is not None
        else None
    )
    if snapshot is not None and not await current_processing_graph_reuse_is_valid(
        db,
        attempt=attempt,
        evaluation=evaluation,
        stages=stages,
        snapshot=snapshot,
    ):
        snapshot = None
    claim = snapshot.claim if snapshot is not None else None
    deadline = snapshot.deadline if snapshot is not None else None

    # A worker may commit the terminal attempt/evaluation immediately before losing
    # its final session transition. Repair only that exact current generation.
    if (
        evaluation is not None
        and _terminal_attempt_state(attempt.attempt_state)
        and attempt.evaluation_state == attempt.attempt_state
        and evaluation.state == attempt.attempt_state
        and snapshot is not None
        and job is not None
        and job.status == "done"
        and await _terminal_processing_form_is_valid(
            db,
            attempt=attempt,
            evaluation=evaluation,
            stages=stages,
            snapshot=snapshot,
        )
    ):
        terminal_exists = exists().where(
            InterviewAttemptEvaluation.id == evaluation.id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.state == evaluation.state,
            InterviewAttemptEvaluation.async_job_id == job.id,
            InterviewAttemptEvaluation.transcript_version_id
            == snapshot.transcript_version_id,
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"][
                "claim_token"
            ].as_string()
            == claim["claim_token"],
        )
        terminal_attempt_exists = exists().where(
            SessionRecording.id == attempt.id,
            SessionRecording.session_id == session.id,
            SessionRecording.current_evaluation_version_id == evaluation.id,
            SessionRecording.current_transcript_version_id
            == snapshot.transcript_version_id,
            SessionRecording.processing_generation == attempt.processing_generation,
            SessionRecording.audio_content_hash == attempt.audio_content_hash,
            SessionRecording.attempt_state == attempt.attempt_state,
            SessionRecording.evaluation_state == attempt.evaluation_state,
            SessionRecording.async_job_id.is_(None),
        )
        terminal_stage_count = (
            select(func.count(InterviewAttemptStage.id))
            .where(
                InterviewAttemptStage.recording_id == attempt.id,
                InterviewAttemptStage.evaluation_version_id == evaluation.id,
                InterviewAttemptStage.job_id == job.id,
                InterviewAttemptStage.claim_token == claim["claim_token"],
                InterviewAttemptStage.expected_processing_generation
                == attempt.processing_generation,
                InterviewAttemptStage.job_deadline_at == snapshot.deadline,
                InterviewAttemptStage.stage_state.in_(_TERMINAL_STAGE_STATES),
                or_(
                    and_(
                        InterviewAttemptStage.stage_name.in_(TRANSCRIPT_BOUND_STAGES),
                        InterviewAttemptStage.source_transcript_version_id
                        == snapshot.transcript_version_id,
                    ),
                    and_(
                        InterviewAttemptStage.stage_name.not_in(
                            TRANSCRIPT_BOUND_STAGES
                        ),
                        InterviewAttemptStage.source_transcript_version_id.is_(None),
                    ),
                ),
            )
            .correlate(InterviewSession)
            .scalar_subquery()
        )
        changed = await db.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session.id,
                InterviewSession.status == "active",
                InterviewSession.conversation_state == "processing_answer",
                InterviewSession.state_version == session.state_version,
                InterviewSession.active_question_id == attempt.question_id,
                InterviewSession.active_recording_id == attempt.id,
                InterviewSession.deletion_state == "not_requested",
                terminal_exists,
                terminal_attempt_exists,
                terminal_stage_count == len(stages),
            )
            .values(
                conversation_state="awaiting_next_action",
                state_version=InterviewSession.state_version + 1,
                activity_version=InterviewSession.activity_version + 1,
                last_activity_at=now,
            )
            .returning(InterviewSession.state_version)
        )
        state_version = changed.scalar_one_or_none()
        if state_version is None:
            return 0
        await ConversationalSessionRepository(db).append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type=(
                        "attempt_processing_completed"
                        if evaluation.state == "completed"
                        else "attempt_processing_failed"
                    ),
                    actor_type="reconciler",
                    state_version=state_version,
                    state_before="processing_answer",
                    state_after="awaiting_next_action",
                    question_id=attempt.question_id,
                    recording_id=attempt.id,
                    payload_json={"state": evaluation.state},
                ),
            ),
        )
        return 1

    if (
        evaluation is None
        or attempt.attempt_state != "pending_processing"
        or snapshot is None
        or deadline is None
        or job is None
    ):
        return 0
    failed_job = forced_retryable_failure or job.status == "failed"
    expired = deadline < now
    if not failed_job and not expired:
        return 0
    recovery_stages = [
        stage
        for stage in stages
        if stage.stage_state in _RECOVERY_STAGE_STATES
        and not (
            stage.stage_name == "speech_analysis"
            and stage.stage_state in {"unavailable", "failed_terminal"}
        )
    ]
    if not recovery_stages:
        return 0

    budget_retryable = attempt.processing_retry_count < attempt.processing_retry_limit
    terminal_failure = any(
        stage.stage_state in {"failed_terminal", "unavailable"}
        for stage in recovery_stages
    )
    retryable = budget_retryable and not terminal_failure
    transcript_id = evaluation.transcript_version_id
    if attempt.recording_type == "text" and transcript_id is None:
        return 0
    recovery_names = {stage.stage_name for stage in recovery_stages}
    if transcript_id is None and any(
        stage.stage_name in TRANSCRIPT_BOUND_STAGES
        and stage.stage_state != "not_started"
        for stage in recovery_stages
    ):
        return 0
    stage_by_name = {stage.stage_name: stage for stage in stages}
    transcription_failure = (
        stage_by_name.get("transcription")
        if "transcription" in recovery_names
        else None
    )
    pretranscription_audio = (
        attempt.recording_type == "audio"
        and transcript_id is None
        and attempt.current_transcript_version_id is None
        and transcription_failure is not None
    )
    if pretranscription_audio:
        created_transcript = await db.scalar(
            select(InterviewTranscriptVersion.id)
            .where(
                InterviewTranscriptVersion.recording_id == attempt.id,
                InterviewTranscriptVersion.processing_generation
                == attempt.processing_generation,
            )
            .limit(1)
        )
        if created_transcript is not None:
            return 0
    session_error_code = (
        "coach_attempt_job_budget_exhausted"
        if expired
        else "coach_evaluation_unavailable"
    )

    content_stage = stage_by_name.get("content_evaluation")
    content_succeeded = bool(
        content_stage is not None
        and content_stage.stage_state in {"completed", "reused"}
    )
    hard_recovery = any(
        stage.stage_name in _HARD_FAILURE_STAGES for stage in recovery_stages
    )
    downstream_only_recovery = all(
        stage.stage_name in _TERMINAL_FALLBACK_STAGES for stage in recovery_stages
    )
    if (
        not retryable
        and transcript_id is not None
        and content_succeeded
        and not hard_recovery
        and downstream_only_recovery
        and isinstance(evaluation.rubric_json, dict)
    ):
        transcript = await db.get(InterviewTranscriptVersion, transcript_id)
        if (
            transcript is None
            or transcript.recording_id != attempt.id
            or (
                attempt.recording_type == "audio"
                and transcript.processing_generation != attempt.processing_generation
            )
        ):
            return 0
        return await _publish_downstream_processing_fallback(
            db,
            session=session,
            attempt=attempt,
            evaluation=evaluation,
            job=job,
            snapshot=snapshot,
            recovery_stages=recovery_stages,
            rubric=dict(evaluation.rubric_json),
            error_code=session_error_code,
            now=now,
        )

    if not retryable:
        if transcript_id is None and not pretranscription_audio:
            return 0
        if transcript_id is not None and (
            content_stage is None
            or content_stage.stage_state not in _RECOVERY_STAGE_STATES
        ):
            return 0

    terminal_state = "recoverable_error" if retryable else "unavailable"
    terminal_reason = (
        "transcription_unavailable" if pretranscription_audio else session_error_code
    )
    stage_error_code = session_error_code if retryable else terminal_reason
    recovery_ids = [stage.id for stage in recovery_stages]
    stage_change = await db.execute(
        update(InterviewAttemptStage)
        .where(
            InterviewAttemptStage.id.in_(recovery_ids),
            InterviewAttemptStage.recording_id == attempt.id,
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.job_id == job_id,
            InterviewAttemptStage.claim_token == claim["claim_token"],
            InterviewAttemptStage.expected_processing_generation
            == attempt.processing_generation,
            InterviewAttemptStage.stage_state.in_(_RECOVERY_STAGE_STATES),
            InterviewAttemptStage.job_deadline_at == deadline,
            or_(
                and_(
                    InterviewAttemptStage.stage_name.in_(TRANSCRIPT_BOUND_STAGES),
                    InterviewAttemptStage.source_transcript_version_id
                    == evaluation.transcript_version_id,
                ),
                and_(
                    InterviewAttemptStage.stage_name.not_in(TRANSCRIPT_BOUND_STAGES),
                    InterviewAttemptStage.source_transcript_version_id.is_(None),
                ),
            ),
        )
        .values(
            stage_state=(
                "failed_retryable"
                if retryable
                else case(
                    (
                        InterviewAttemptStage.stage_name.in_(_HARD_FAILURE_STAGES),
                        "failed_terminal",
                    ),
                    else_="unavailable",
                )
            ),
            last_error_code=(
                case(
                    (
                        InterviewAttemptStage.last_error_code.is_not(None),
                        InterviewAttemptStage.last_error_code,
                    ),
                    else_=stage_error_code,
                )
                if retryable
                else stage_error_code
            ),
            completed_at=now,
        )
    )
    if not retryable:
        await _supersede_prior_evaluation(
            db,
            attempt=attempt,
            evaluation=evaluation,
        )
    attempt_values: dict[str, object] = {
        "attempt_state": terminal_state,
        "evaluation_state": "failed" if retryable else "unavailable",
        "async_job_id": None,
        "processing_completed_at": now,
    }
    if not retryable:
        unavailable_rubric = _unavailable_rubric()
        attempt_values.update(
            {
                "evaluation_json": _canonical_json(unavailable_rubric),
                "current_evaluation_version_id": evaluation.id,
            }
        )
    attempt_change = await db.execute(
        update(SessionRecording)
        .where(
            SessionRecording.id == attempt.id,
            SessionRecording.session_id == session.id,
            SessionRecording.question_id == session.active_question_id,
            SessionRecording.processing_generation == attempt.processing_generation,
            SessionRecording.async_job_id == attempt.async_job_id,
            SessionRecording.current_transcript_version_id.is_not_distinct_from(
                evaluation.transcript_version_id
            ),
            SessionRecording.current_evaluation_version_id.is_not_distinct_from(
                attempt.current_evaluation_version_id
            ),
            SessionRecording.audio_content_hash.is_not_distinct_from(
                attempt.audio_content_hash
            ),
            SessionRecording.attempt_state == "pending_processing",
            SessionRecording.evaluation_state == "pending",
        )
        .values(**attempt_values)
    )
    evaluation_values: dict[str, object] = {
        "state": "failed" if retryable else "unavailable",
        "completed_at": now,
        "diagnostics_json": {
            "processing_claim": dict(claim),
            "result": {
                "reason_code": session_error_code if retryable else terminal_reason
            },
        },
    }
    if not retryable:
        evaluation_values["rubric_json"] = _unavailable_rubric()
    evaluation_change = await db.execute(
        update(InterviewAttemptEvaluation)
        .where(
            InterviewAttemptEvaluation.id == evaluation.id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.async_job_id == evaluation.async_job_id,
            InterviewAttemptEvaluation.transcript_version_id
            == snapshot.transcript_version_id,
            InterviewAttemptEvaluation.diagnostics_json["processing_claim"][
                "claim_token"
            ].as_string()
            == claim["claim_token"],
            InterviewAttemptEvaluation.state == "pending",
        )
        .values(**evaluation_values)
    )
    session_values: dict[str, object] = {
        "conversation_state": "recoverable_error",
        "recoverable_error_scope": "attempt_processing",
        "recoverable_error_code": session_error_code,
        "recoverable_error_context_json": None,
        "state_version": InterviewSession.state_version + 1,
        "last_activity_at": now,
    }
    if not retryable:
        session_values["activity_version"] = InterviewSession.activity_version + 1
    session_change = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session.id,
            InterviewSession.status == "active",
            InterviewSession.conversation_state == "processing_answer",
            InterviewSession.state_version == session.state_version,
            InterviewSession.active_question_id == attempt.question_id,
            InterviewSession.active_recording_id == attempt.id,
            InterviewSession.deletion_state == "not_requested",
        )
        .values(**session_values)
        .returning(InterviewSession.state_version)
    )
    state_version = session_change.scalar_one_or_none()
    if (
        stage_change.rowcount != len(recovery_stages)
        or attempt_change.rowcount != 1
        or evaluation_change.rowcount != 1
        or state_version is None
    ):
        raise _ReconciliationFenceLost
    job_change = await db.execute(
        update(AsyncJob)
        .where(
            AsyncJob.id == job_id,
            AsyncJob.type == "coach_attempt_processing",
            AsyncJob.status.in_(("pending", "running", "failed")),
        )
        .values(
            status="failed",
            error=stage_error_code,
            result_json=None,
            updated_at=now,
        )
    )
    if job_change.rowcount != 1:
        raise _ReconciliationFenceLost
    await ConversationalSessionRepository(db).append_session_events(
        session_id=session.id,
        events=(
            SessionEventInput(
                event_type="attempt_processing_failed",
                actor_type="reconciler",
                state_version=state_version,
                state_before="processing_answer",
                state_after="recoverable_error",
                question_id=attempt.question_id,
                recording_id=attempt.id,
                payload_json={
                    "reason_code": session_error_code,
                    "retryable": retryable,
                },
            ),
        ),
    )
    return 1


async def _reconcile_transient_state(
    db: AsyncSession, session: InterviewSession, now: datetime
) -> int:
    transient = session.conversation_state
    if transient not in {"advancing", "asking_follow_up"}:
        return 0
    prior_question = (
        await db.scalar(
            select(SessionQuestion).where(
                SessionQuestion.id == session.active_question_id,
                SessionQuestion.session_id == session.id,
            )
        )
        if session.active_question_id is not None
        else None
    )
    accepted_attempt = (
        await db.scalar(
            select(SessionRecording).where(
                SessionRecording.id == prior_question.accepted_recording_id,
                SessionRecording.session_id == session.id,
                SessionRecording.question_id == prior_question.id,
                SessionRecording.accepted_at.is_not(None),
            )
        )
        if prior_question is not None
        and prior_question.accepted_recording_id is not None
        else None
    )
    valid_prior = prior_question is not None and (
        (prior_question.question_state == "answered" and accepted_attempt is not None)
        or (
            transient == "advancing"
            and prior_question.question_state == "skipped"
            and prior_question.accepted_recording_id is None
        )
    )
    if not valid_prior:
        return 0
    query = select(SessionQuestion).where(
        SessionQuestion.session_id == session.id,
        SessionQuestion.question_state == "pending",
    )
    if transient == "asking_follow_up":
        if (
            accepted_attempt is None
            or accepted_attempt.attempt_state in {"deleted", "cancelled", "invalid"}
            or accepted_attempt.current_transcript_version_id is None
        ):
            return 0
        query = query.where(
            SessionQuestion.question_kind == "adaptive_follow_up",
            SessionQuestion.parent_question_id == session.active_question_id,
            SessionQuestion.root_question_id == session.active_root_question_id,
            SessionQuestion.follow_up_source_recording_id == accepted_attempt.id,
            SessionQuestion.follow_up_source_transcript_version_id
            == accepted_attempt.current_transcript_version_id,
            SessionQuestion.source_deleted.is_(False),
        )
    else:
        query = query.where(SessionQuestion.question_kind == "planned")
    candidates = list(
        (
            await db.scalars(
                query.order_by(
                    SessionQuestion.order_in_session, SessionQuestion.id
                ).limit(2 if transient == "asking_follow_up" else 1)
            )
        ).all()
    )
    if transient == "asking_follow_up" and len(candidates) > 1:
        return 0
    next_question = candidates[0] if candidates else None
    if next_question is None:
        # A transient may finish into reporting only when another transaction already
        # persisted the complete initial-report ownership snapshot.
        report_job = (
            await db.get(AsyncJob, session.report_job_id)
            if session.report_job_id is not None
            else None
        )
        if not (
            transient == "advancing"
            and session.report_state == "building"
            and session.report_build_reason == "initial_completion"
            and session.report_job_id is not None
            and report_job is not None
            and report_job.type == "coach_conversational_report"
            and report_job.status in {"pending", "running"}
            and session.report_started_at is not None
            and session.report_contract_version == REPORT_CONTRACT
        ):
            return 0
        changed = await db.execute(
            update(InterviewSession)
            .where(
                InterviewSession.id == session.id,
                InterviewSession.status == "active",
                InterviewSession.conversation_state == "advancing",
                InterviewSession.state_version == session.state_version,
                InterviewSession.report_state == "building",
                InterviewSession.report_build_reason == "initial_completion",
                InterviewSession.report_job_id == session.report_job_id,
                InterviewSession.deletion_state == "not_requested",
            )
            .values(
                conversation_state="reporting",
                state_version=InterviewSession.state_version + 1,
                last_activity_at=now,
            )
            .returning(InterviewSession.state_version)
        )
        state_version = changed.scalar_one_or_none()
        if state_version is None:
            return 0
        await ConversationalSessionRepository(db).append_session_events(
            session_id=session.id,
            events=(
                SessionEventInput(
                    event_type="report_claimed",
                    actor_type="reconciler",
                    state_version=state_version,
                    state_before="advancing",
                    state_after="reporting",
                    question_id=session.active_question_id,
                ),
            ),
        )
        return 1

    asked_sequence = (
        int(
            await db.scalar(
                select(func.count(SessionQuestion.id)).where(
                    SessionQuestion.session_id == session.id,
                    SessionQuestion.asked_sequence.is_not(None),
                )
            )
            or 0
        )
        + 1
    )
    question_change = await db.execute(
        update(SessionQuestion)
        .where(
            SessionQuestion.id == next_question.id,
            SessionQuestion.session_id == session.id,
            SessionQuestion.question_state == "pending",
            SessionQuestion.asked_sequence.is_(None),
        )
        .values(question_state="asked", asked_sequence=asked_sequence)
    )
    session_change = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session.id,
            InterviewSession.status == "active",
            InterviewSession.conversation_state == transient,
            InterviewSession.state_version == session.state_version,
            InterviewSession.active_question_id == session.active_question_id,
            InterviewSession.deletion_state == "not_requested",
        )
        .values(
            conversation_state="asking",
            active_question_id=next_question.id,
            active_root_question_id=(
                next_question.root_question_id or next_question.id
            ),
            active_recording_id=None,
            state_version=InterviewSession.state_version + 1,
            last_activity_at=now,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = session_change.scalar_one_or_none()
    if question_change.rowcount != 1 or state_version is None:
        raise _ReconciliationFenceLost
    event_types = (
        ("follow_up_presented", "question_presented")
        if transient == "asking_follow_up"
        else ("question_advanced", "question_presented")
    )
    await ConversationalSessionRepository(db).append_session_events(
        session_id=session.id,
        events=tuple(
            SessionEventInput(
                event_type=event_type,
                actor_type="reconciler",
                state_version=state_version,
                state_before=transient,
                state_after="asking",
                question_id=next_question.id,
            )
            for event_type in event_types
        ),
    )
    return 1


async def recover_exhausted_transcription_claim(
    db: AsyncSession,
    *,
    claim: AttemptProcessingClaim,
    error_code: str,
    attempt_count: int,
    repair_count: int,
    speech_state: str,
    speech_error_code: str | None,
    speech_metrics: Mapping[str, object] | None,
) -> bool:
    """Atomically fence and publish exhausted provider work as recoverable."""
    expected_names = {
        "audio_persist",
        "transcription",
        "speech_analysis",
        "content_evaluation",
        "evidence_grounding",
        "follow_up_decision",
        "coaching_enrichment",
        "audio_cleanup",
    }
    now = datetime.utcnow()
    try:
        session = await db.get(InterviewSession, claim.session_id)
        attempt = await db.get(SessionRecording, claim.recording_id)
        evaluation = await db.get(
            InterviewAttemptEvaluation, claim.evaluation_version_id
        )
        job = await db.get(AsyncJob, claim.job_id)
        stages = list(
            (
                await db.scalars(
                    select(InterviewAttemptStage).where(
                        InterviewAttemptStage.recording_id == claim.recording_id,
                        InterviewAttemptStage.evaluation_version_id
                        == claim.evaluation_version_id,
                    )
                )
            ).all()
        )
        snapshot = (
            exact_processing_snapshot(
                session=session,
                attempt=attempt,
                evaluation=evaluation,
                job=job,
                stages=stages,
            )
            if session is not None
            and attempt is not None
            and evaluation is not None
            and job is not None
            else None
        )
        if (
            snapshot is None
            or snapshot.claim["claim_token"] is None
            or snapshot.deadline != claim.deadline_at
            or len(stages) != len(expected_names)
            or {stage.stage_name for stage in stages} != expected_names
            or attempt.processing_retry_count >= attempt.processing_retry_limit
            or not await current_processing_graph_reuse_is_valid(
                db,
                attempt=attempt,
                evaluation=evaluation,
                stages=stages,
                snapshot=snapshot,
            )
        ):
            raise _ReconciliationFenceLost
        token = snapshot.claim["claim_token"]
        result_transcript = (
            await db.get(
                InterviewTranscriptVersion,
                evaluation.transcript_version_id,
            )
            if evaluation.transcript_version_id is not None
            else None
        )
        if (
            evaluation.transcript_version_id is not None
            and result_transcript is None
        ):
            raise _ReconciliationFenceLost
        expected_diagnostics = {
            stage.stage_name: _stage_immutable_diagnostics(
                stage_name=stage.stage_name,
                audio_content_hash=attempt.audio_content_hash,
                transcript_version_id=evaluation.transcript_version_id,
                transcript_content_hash=(
                    result_transcript.content_hash
                    if result_transcript is not None
                    else None
                ),
                evaluation_contract_version=evaluation.evaluation_contract_version,
                evidence_contract_version=evaluation.evidence_contract_version,
                follow_up_contract_version=evaluation.follow_up_contract_version,
            )
            for stage in stages
        }
        mutable: list[InterviewAttemptStage] = []
        immutable: list[InterviewAttemptStage] = []
        for stage in stages:
            if (
                stage.stage_state in {"not_started", "pending", "running"}
                and stage.reused_from_stage_id is None
                and stage.completed_at is None
            ):
                mutable.append(stage)
                continue
            valid_immutable = (
                stage.stage_name == "audio_persist"
                and stage.stage_state in {"completed", "reused"}
            ) or (
                stage.stage_name == "speech_analysis"
                and stage.stage_state
                in {"completed", "reused", "unavailable", "failed_terminal"}
            )
            if (
                not valid_immutable
                or stage.completed_at is None
                or stage.diagnostics_json
                != expected_diagnostics[stage.stage_name]
                or (stage.stage_state == "reused")
                != (stage.reused_from_stage_id is not None)
                or (
                    stage.stage_state == "completed"
                    and stage.last_error_code is not None
                )
                or (
                    stage.stage_state in {"unavailable", "failed_terminal"}
                    and not stage.last_error_code
                )
            ):
                raise _ReconciliationFenceLost
            immutable.append(stage)
        if not any(stage.stage_name == "transcription" for stage in mutable):
            raise _ReconciliationFenceLost
        for stage in immutable:
            immutable_change = await db.execute(
                update(InterviewAttemptStage)
                .where(
                    InterviewAttemptStage.id == stage.id,
                    InterviewAttemptStage.recording_id == claim.recording_id,
                    InterviewAttemptStage.evaluation_version_id
                    == claim.evaluation_version_id,
                    InterviewAttemptStage.stage_name == stage.stage_name,
                    InterviewAttemptStage.stage_state == stage.stage_state,
                    InterviewAttemptStage.job_id == claim.job_id,
                    InterviewAttemptStage.claim_token == token,
                    InterviewAttemptStage.expected_processing_generation
                    == claim.processing_generation,
                    InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                    InterviewAttemptStage.source_transcript_version_id.is_not_distinct_from(
                        stage.source_transcript_version_id
                    ),
                    InterviewAttemptStage.reused_from_stage_id.is_not_distinct_from(
                        stage.reused_from_stage_id
                    ),
                    InterviewAttemptStage.completed_at == stage.completed_at,
                    InterviewAttemptStage.last_error_code.is_not_distinct_from(
                        stage.last_error_code
                    ),
                    InterviewAttemptStage.diagnostics_json
                    == expected_diagnostics[stage.stage_name],
                )
                .values(stage_state=stage.stage_state)
            )
            if immutable_change.rowcount != 1:
                raise _ReconciliationFenceLost
        mutable_ids = [stage.id for stage in mutable]
        stage_change = await db.execute(
            update(InterviewAttemptStage)
            .where(
                InterviewAttemptStage.id.in_(mutable_ids),
                or_(
                    *(
                        and_(
                            InterviewAttemptStage.id == stage.id,
                            InterviewAttemptStage.diagnostics_json
                            == expected_diagnostics[stage.stage_name],
                        )
                        for stage in mutable
                    )
                ),
                InterviewAttemptStage.recording_id == claim.recording_id,
                InterviewAttemptStage.evaluation_version_id
                == claim.evaluation_version_id,
                InterviewAttemptStage.job_id == claim.job_id,
                InterviewAttemptStage.claim_token == token,
                InterviewAttemptStage.expected_processing_generation
                == claim.processing_generation,
                InterviewAttemptStage.job_deadline_at == claim.deadline_at,
                InterviewAttemptStage.source_transcript_version_id.is_(None),
                InterviewAttemptStage.reused_from_stage_id.is_(None),
                InterviewAttemptStage.completed_at.is_(None),
                InterviewAttemptStage.stage_state.in_(
                    ("not_started", "pending", "running")
                ),
            )
            .values(
                stage_state=case(
                    (
                        InterviewAttemptStage.stage_name == "audio_persist",
                        "completed",
                    ),
                    (
                        InterviewAttemptStage.stage_name == "speech_analysis",
                        speech_state,
                    ),
                    (
                        InterviewAttemptStage.stage_name == "transcription",
                        "running",
                    ),
                    else_="not_started",
                ),
                attempt_count=case(
                    (
                        InterviewAttemptStage.stage_name == "transcription",
                        attempt_count,
                    ),
                    else_=InterviewAttemptStage.attempt_count,
                ),
                repair_count=case(
                    (
                        InterviewAttemptStage.stage_name == "transcription",
                        repair_count,
                    ),
                    else_=InterviewAttemptStage.repair_count,
                ),
                last_error_code=case(
                    (
                        InterviewAttemptStage.stage_name == "transcription",
                        error_code,
                    ),
                    (
                        InterviewAttemptStage.stage_name == "speech_analysis",
                        speech_error_code,
                    ),
                    else_=None,
                ),
                completed_at=case(
                    (
                        InterviewAttemptStage.stage_name.in_(
                            ("audio_persist", "speech_analysis")
                        ),
                        now,
                    ),
                    else_=None,
                ),
            )
        )
        if stage_change.rowcount != len(mutable):
            raise _ReconciliationFenceLost
        attempt.speech_metrics = dict(speech_metrics) if speech_metrics else None
        changed = await _reconcile_processing_answer(
            db,
            session,
            now,
            forced_retryable_failure=True,
        )
        if changed != 1:
            raise _ReconciliationFenceLost
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        return False


async def reconcile_conversational_session(
    db: AsyncSession,
    session_id: str,
    now: datetime | None = None,
) -> int:
    """Idempotently repair one owned conversational aggregate from persisted facts."""
    now = now or datetime.utcnow()
    session = await db.scalar(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.experience_version == "conversational_v1",
            InterviewSession.deletion_state == "not_requested",
        )
    )
    if session is None:
        return 0
    try:
        changed = await _reconcile_expired_setup_claim(db, session, now)
        if not changed:
            changed = await _reconcile_processing_answer(db, session, now)
        if not changed:
            from .coach_retention import CoachRetentionService

            retention = CoachRetentionService(db)
            cleanup_cursor: tuple[datetime, str] | None = None
            while not changed:
                cleanup_query = select(
                    SessionRecording.id, SessionRecording.created_at
                ).where(
                    SessionRecording.session_id == session.id,
                    SessionRecording.recording_type == "audio",
                    SessionRecording.audio_retention_policy
                    == "delete_after_processing",
                    SessionRecording.audio_retention_state.in_(
                        ("temporary", "delete_failed", "delete_pending")
                    ),
                )
                if cleanup_cursor is not None:
                    cursor_created_at, cursor_id = cleanup_cursor
                    cleanup_query = cleanup_query.where(
                        or_(
                            SessionRecording.created_at > cursor_created_at,
                            and_(
                                SessionRecording.created_at == cursor_created_at,
                                SessionRecording.id > cursor_id,
                            ),
                        )
                    )
                cleanup_rows = (
                    await db.execute(
                        cleanup_query.order_by(
                            SessionRecording.created_at, SessionRecording.id
                        )
                        .limit(20)
                    )
                ).all()
                if not cleanup_rows:
                    break
                for recording_id, created_at in cleanup_rows:
                    cleanup_cursor = (created_at, recording_id)
                    retention_attempt = await db.get(SessionRecording, recording_id)
                    if (
                        retention_attempt is not None
                        and retention_attempt.audio_retention_state == "delete_pending"
                    ):
                        changed = int(
                            await retention.recover_expired_cleanup(recording_id, now)
                        )
                        if changed:
                            await db.commit()
                            break
                    if not await retention.default_cleanup_is_due(recording_id, now):
                        continue
                    cleanup_claim = await retention.claim_default_cleanup(
                        recording_id, now
                    )
                    if cleanup_claim is None:
                        preclaim_result = await retention.classify_cleanup_preclaim(
                            recording_id
                        )
                        changed = int(
                            preclaim_result is not None
                            and await retention.record_cleanup_claim_failure(
                                recording_id,
                                now,
                                result=preclaim_result,
                                actor_type="reconciler",
                            )
                        )
                        if changed:
                            await db.commit()
                            break
                        continue
                    await db.commit()
                    cleanup_result = await retention.delete_claimed_audio(
                        cleanup_claim
                    )
                    if cleanup_result != "stale_claim":
                        changed = int(
                            await retention.finalise_reconciled_audio_cleanup(
                                cleanup_claim, cleanup_result
                            )
                        )
                        if changed:
                            await db.commit()
                    break
        if not changed:
            changed = await _reconcile_transient_state(db, session, now)
        if changed:
            await db.commit()
        return changed
    except _ReconciliationFenceLost:
        await db.rollback()
        return 0
    except Exception:
        await db.rollback()
        raise


async def reconcile_job(db: AsyncSession, job_id: str) -> int:
    """Find and lazily reconcile the Coach session linked to a polled job."""
    recording = (
        await db.execute(
            select(SessionRecording)
            .where(SessionRecording.async_job_id == job_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if recording:
        experience = await db.scalar(
            select(InterviewSession.experience_version).where(
                InterviewSession.id == recording.session_id
            )
        )
        if experience == "conversational_v1":
            return await reconcile_conversational_session(db, recording.session_id)
        return await reconcile_session(db, recording.session_id)
    session_id = (
        await db.execute(
            select(InterviewSession.id)
            .where(
                or_(
                    InterviewSession.report_job_id == job_id,
                    InterviewSession.setup_job_id == job_id,
                )
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if session_id is None:
        return 0
    experience = await db.scalar(
        select(InterviewSession.experience_version).where(
            InterviewSession.id == session_id
        )
    )
    if experience == "conversational_v1":
        return await reconcile_conversational_session(db, session_id)
    return await reconcile_session(db, session_id)


async def reconcile_stale_coach_state(batch_size: int = 100) -> int:
    """Run bounded startup recovery using a fresh database session."""
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be an integer from 1 through 100")
    now = datetime.utcnow()
    total = 0
    async with AsyncSessionLocal() as db:
        grace_cutoff = now - timedelta(
            seconds=settings.HATCH_COACH_STALE_JOB_GRACE_SECONDS
        )
        legacy_answer_cutoff = grace_cutoff - timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_ANSWER_SUBMIT_JOB_SECONDS
        )
        legacy_report_cutoff = grace_cutoff - timedelta(
            seconds=settings.HATCH_COACH_TIMEOUT_SESSION_END_JOB_SECONDS
        )
        pending_legacy_attempt = exists().where(
            SessionRecording.session_id == InterviewSession.id,
            SessionRecording.evaluation_state == "pending",
            or_(
                and_(
                    ~exists().where(AsyncJob.id == SessionRecording.async_job_id),
                    SessionRecording.created_at <= grace_cutoff,
                ),
                exists().where(
                    AsyncJob.id == SessionRecording.async_job_id,
                    or_(
                        and_(
                            AsyncJob.status.in_(("pending", "running")),
                            AsyncJob.updated_at <= legacy_answer_cutoff,
                        ),
                        and_(
                            AsyncJob.status.in_(("failed", "done")),
                            AsyncJob.updated_at <= grace_cutoff,
                        ),
                    ),
                ),
            ),
        )
        due_legacy_report = and_(
            InterviewSession.report_state == "building",
            or_(
                and_(
                    ~exists().where(AsyncJob.id == InterviewSession.report_job_id),
                    InterviewSession.report_started_at <= grace_cutoff,
                ),
                exists().where(
                    AsyncJob.id == InterviewSession.report_job_id,
                    or_(
                        and_(
                            AsyncJob.status.in_(("pending", "running")),
                            AsyncJob.updated_at <= legacy_report_cutoff,
                        ),
                        and_(
                            AsyncJob.status.in_(("failed", "done")),
                            AsyncJob.updated_at <= grace_cutoff,
                        ),
                    ),
                ),
            ),
        )
        processing_attempt = aliased(SessionRecording)
        processing_evaluation = aliased(InterviewAttemptEvaluation)
        processing_job = aliased(AsyncJob)
        processing_stage = aliased(InterviewAttemptStage)
        invalid_stage = aliased(InterviewAttemptStage)
        form_stage = aliased(InterviewAttemptStage)
        form_transcript = aliased(InterviewTranscriptVersion)
        retry_transcription = aliased(InterviewAttemptStage)
        reused_transcription_source = aliased(InterviewAttemptStage)
        reused_transcription_evaluation = aliased(InterviewAttemptEvaluation)
        reused_transcript = aliased(InterviewTranscriptVersion)
        cleanup_attempt = aliased(SessionRecording)
        cleanup_evaluation = aliased(InterviewAttemptEvaluation)
        cleanup_stage = aliased(InterviewAttemptStage)
        cleanup_transcription = aliased(InterviewAttemptStage)
        cleanup_speech = aliased(InterviewAttemptStage)
        cleanup_job = aliased(AsyncJob)
        claim_path = "$.processing_claim"
        safe_diagnostics = case(
            (
                func.json_valid(processing_evaluation.diagnostics_json) == 1,
                processing_evaluation.diagnostics_json,
            ),
            else_=literal("{}"),
        )

        def claim_type(name: str):
            return func.json_type(
                safe_diagnostics,
                f"{claim_path}.{name}",
            )

        def claim_value(name: str):
            return func.json_extract(
                safe_diagnostics,
                f"{claim_path}.{name}",
            )

        claim_members = func.json_each(
            func.json_extract(safe_diagnostics, claim_path)
        ).table_valued("key", "value")
        claim_member_count = (
            select(func.count())
            .select_from(claim_members)
            .correlate(processing_evaluation)
            .scalar_subquery()
        )
        exact_claim_shape = and_(
            func.json_type(safe_diagnostics, claim_path) == "object",
            claim_member_count == 7,
            claim_type("processing_generation") == "integer",
            claim_type("job_deadline_at") == "text",
            claim_type("source_audio_content_hash").in_(("null", "text")),
            claim_type("source_transcript_version_id").in_(("null", "text")),
            claim_type("expected_session_state_version") == "integer",
            claim_type("processing_contract_version") == "text",
            claim_type("claim_token") == "text",
            func.length(claim_value("claim_token")) > 0,
            claim_value("processing_generation")
            == processing_attempt.processing_generation,
            claim_value("processing_contract_version") == "coach_processing_v1",
        )

        def canonical_utc_deadline(value):
            value_length = func.length(value)
            body = case(
                (
                    func.substr(value, -1) == "Z",
                    func.substr(value, 1, value_length - 1),
                ),
                (
                    func.substr(value, -6) == "+00:00",
                    func.substr(value, 1, value_length - 6),
                ),
                else_=value,
            )
            body_length = func.length(body)
            base = func.substr(body, 1, 19)
            fraction = case(
                (body_length == 19, literal("")),
                (
                    and_(
                        body_length.between(21, 26),
                        func.substr(body, 20, 1) == ".",
                    ),
                    func.substr(body, 21),
                ),
                else_=None,
            )
            normalized_base = (
                func.substr(base, 1, 10)
                .concat(literal("T"))
                .concat(func.substr(base, 12, 8))
            )
            base_digits = (
                func.substr(base, 1, 4)
                .concat(func.substr(base, 6, 2))
                .concat(func.substr(base, 9, 2))
                .concat(func.substr(base, 12, 2))
                .concat(func.substr(base, 15, 2))
                .concat(func.substr(base, 18, 2))
            )
            valid = and_(
                value.is_not(None),
                func.length(base) == 19,
                func.substr(base, 1, 4) != "0000",
                func.substr(base, 5, 1) == "-",
                func.substr(base, 8, 1) == "-",
                func.substr(base, 11, 1).in_(("T", " ")),
                func.substr(base, 14, 1) == ":",
                func.substr(base, 17, 1) == ":",
                ~base_digits.op("GLOB")("*[^0-9]*"),
                fraction.is_not(None),
                ~fraction.op("GLOB")("*[^0-9]*"),
                func.strftime(
                    "%Y-%m-%dT%H:%M:%S", func.julianday(base)
                ).is_not_distinct_from(normalized_base),
            )
            padded_fraction = fraction.concat(
                func.substr(literal("000000"), 1, 6 - func.length(fraction))
            )
            return case(
                (
                    valid,
                    normalized_base.concat(literal(".")).concat(padded_fraction),
                ),
                else_=None,
            )

        claim_deadline = claim_value("job_deadline_at")
        canonical_claim_deadline = canonical_utc_deadline(claim_deadline)
        exact_deadline = canonical_claim_deadline.is_not(None)
        exact_audio_retry_transcript_reuse = exists().where(
            retry_transcription.recording_id == processing_attempt.id,
            retry_transcription.evaluation_version_id == processing_evaluation.id,
            retry_transcription.stage_name == "transcription",
            retry_transcription.stage_state == "reused",
            retry_transcription.job_id == processing_job.id,
            retry_transcription.claim_token == claim_value("claim_token"),
            retry_transcription.expected_processing_generation
            == processing_attempt.processing_generation,
            retry_transcription.source_transcript_version_id.is_(None),
            canonical_utc_deadline(retry_transcription.job_deadline_at)
            == canonical_claim_deadline,
            retry_transcription.reused_from_stage_id
            == reused_transcription_source.id,
            reused_transcription_source.recording_id == processing_attempt.id,
            reused_transcription_source.stage_name == "transcription",
            reused_transcription_source.stage_state.in_(("completed", "reused")),
            reused_transcription_source.expected_processing_generation
            == processing_attempt.processing_generation - 1,
            reused_transcription_source.evaluation_version_id
            == reused_transcription_evaluation.id,
            reused_transcription_evaluation.recording_id == processing_attempt.id,
            reused_transcription_evaluation.transcript_version_id
            == processing_evaluation.transcript_version_id,
            reused_transcription_evaluation.async_job_id
            == reused_transcription_source.job_id,
            func.json_extract(
                reused_transcription_evaluation.diagnostics_json,
                "$.processing_claim.processing_generation",
            )
            == reused_transcription_source.expected_processing_generation,
            func.json_extract(
                reused_transcription_evaluation.diagnostics_json,
                "$.processing_claim.claim_token",
            )
            == reused_transcription_source.claim_token,
            canonical_utc_deadline(
                func.json_extract(
                    reused_transcription_evaluation.diagnostics_json,
                    "$.processing_claim.job_deadline_at",
                )
            )
            == canonical_utc_deadline(reused_transcription_source.job_deadline_at),
            reused_transcript.id == processing_evaluation.transcript_version_id,
            reused_transcript.recording_id == processing_attempt.id,
        )
        exact_source = or_(
            and_(
                processing_attempt.recording_type == "text",
                claim_type("source_audio_content_hash") == "null",
                processing_attempt.audio_content_hash.is_(None),
                claim_type("source_transcript_version_id") == "text",
                claim_value("source_transcript_version_id")
                == processing_attempt.current_transcript_version_id,
                processing_evaluation.transcript_version_id
                == processing_attempt.current_transcript_version_id,
            ),
            and_(
                processing_attempt.recording_type == "audio",
                claim_type("source_audio_content_hash") == "text",
                claim_value("source_audio_content_hash")
                == processing_attempt.audio_content_hash,
                processing_attempt.current_transcript_version_id.is_not_distinct_from(
                    processing_evaluation.transcript_version_id
                ),
                or_(
                    claim_type("source_transcript_version_id") == "null",
                    and_(
                        claim_type("source_transcript_version_id") == "text",
                        claim_value("source_transcript_version_id")
                        == processing_attempt.current_transcript_version_id,
                        exact_audio_retry_transcript_reuse,
                    ),
                ),
            ),
        )
        exact_stage_source = or_(
            and_(
                invalid_stage.stage_name.in_(TRANSCRIPT_BOUND_STAGES),
                invalid_stage.source_transcript_version_id.is_not_distinct_from(
                    processing_evaluation.transcript_version_id
                ),
            ),
            and_(
                invalid_stage.stage_name.not_in(TRANSCRIPT_BOUND_STAGES),
                invalid_stage.source_transcript_version_id.is_(None),
            ),
        )
        malformed_owned_stage = exists().where(
            invalid_stage.recording_id == processing_attempt.id,
            invalid_stage.evaluation_version_id == processing_evaluation.id,
            or_(
                invalid_stage.job_id.is_distinct_from(processing_job.id),
                invalid_stage.expected_processing_generation.is_distinct_from(
                    processing_attempt.processing_generation
                ),
                invalid_stage.claim_token.is_distinct_from(claim_value("claim_token")),
                canonical_utc_deadline(invalid_stage.job_deadline_at).is_distinct_from(
                    canonical_claim_deadline
                ),
                ~exact_stage_source,
            ),
        )
        selected_stage_is_exact = and_(
            processing_stage.recording_id == processing_attempt.id,
            processing_stage.evaluation_version_id == processing_evaluation.id,
            processing_stage.job_id == processing_job.id,
            processing_stage.expected_processing_generation
            == processing_attempt.processing_generation,
            processing_stage.claim_token == claim_value("claim_token"),
            canonical_utc_deadline(processing_stage.job_deadline_at)
            == canonical_claim_deadline,
            or_(
                and_(
                    processing_stage.stage_name.in_(TRANSCRIPT_BOUND_STAGES),
                    processing_stage.source_transcript_version_id.is_not_distinct_from(
                        processing_evaluation.transcript_version_id
                    ),
                ),
                and_(
                    processing_stage.stage_name.not_in(TRANSCRIPT_BOUND_STAGES),
                    processing_stage.source_transcript_version_id.is_(None),
                ),
            ),
        )
        pending_processing_is_actionable = and_(
            processing_attempt.attempt_state == "pending_processing",
            processing_attempt.evaluation_state == "pending",
            processing_attempt.async_job_id == processing_job.id,
            processing_evaluation.state == "pending",
            processing_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
            or_(
                processing_stage.job_deadline_at < now,
                processing_job.status == "failed",
            ),
        )
        created_current_generation_transcript = exists().where(
            form_transcript.recording_id == processing_attempt.id,
            form_transcript.processing_generation
            == processing_attempt.processing_generation,
        )
        recovery_transcription_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name == "transcription",
            form_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
        )
        recovery_content_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name == "content_evaluation",
            form_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
        )
        claimed_transcript_bound_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name.in_(TRANSCRIPT_BOUND_STAGES),
            form_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
            form_stage.stage_state != "not_started",
        )
        terminal_failure_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_state.in_(("failed_terminal", "unavailable")),
        )
        recovery_hard_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name.in_(_HARD_FAILURE_STAGES),
            form_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
        )
        recovery_downstream_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name.in_(_TERMINAL_FALLBACK_STAGES),
            form_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
        )
        recovery_nonfallback_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name.not_in(_TERMINAL_FALLBACK_STAGES),
            form_stage.stage_state.in_(_RECOVERY_STAGE_STATES),
        )
        content_success_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name == "content_evaluation",
            form_stage.stage_state.in_(("completed", "reused")),
        )
        budget_retryable = (
            processing_attempt.processing_retry_count
            < processing_attempt.processing_retry_limit
        )
        retryable_processing_form = and_(
            budget_retryable,
            ~terminal_failure_stage,
            or_(
                processing_evaluation.transcript_version_id.is_not(None),
                and_(
                    processing_attempt.recording_type == "audio",
                    processing_attempt.current_transcript_version_id.is_(None),
                    ~claimed_transcript_bound_stage,
                    or_(
                        ~recovery_transcription_stage,
                        ~created_current_generation_transcript,
                    ),
                ),
            ),
        )
        terminal_hard_processing_form = and_(
            or_(~budget_retryable, terminal_failure_stage),
            or_(
                and_(
                    processing_evaluation.transcript_version_id.is_(None),
                    processing_attempt.recording_type == "audio",
                    processing_attempt.current_transcript_version_id.is_(None),
                    recovery_transcription_stage,
                    ~claimed_transcript_bound_stage,
                    ~created_current_generation_transcript,
                ),
                and_(
                    processing_evaluation.transcript_version_id.is_not(None),
                    recovery_content_stage,
                ),
            ),
        )
        terminal_fallback_processing_form = and_(
            or_(~budget_retryable, terminal_failure_stage),
            processing_evaluation.transcript_version_id.is_not(None),
            func.json_type(processing_evaluation.rubric_json) == "object",
            content_success_stage,
            recovery_downstream_stage,
            ~recovery_hard_stage,
            ~recovery_nonfallback_stage,
        )
        pending_processing_form_is_actionable = and_(
            pending_processing_is_actionable,
            or_(
                retryable_processing_form,
                terminal_hard_processing_form,
                terminal_fallback_processing_form,
            ),
        )
        nonterminal_stage = exists().where(
            invalid_stage.recording_id == processing_attempt.id,
            invalid_stage.evaluation_version_id == processing_evaluation.id,
            invalid_stage.stage_state.not_in(_TERMINAL_STAGE_STATES),
        )
        result_is_mapping = func.json_type(safe_diagnostics, "$.result") == "object"
        result_reason = case(
            (
                func.json_type(safe_diagnostics, "$.result.reason_code").is_not(None),
                func.json_extract(safe_diagnostics, "$.result.reason_code"),
            ),
            else_=func.json_extract(safe_diagnostics, "$.result.code"),
        )
        completed_content_stage = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name == "content_evaluation",
            form_stage.stage_state == "completed",
        )
        current_completed_transcript = exists().where(
            form_transcript.id == processing_evaluation.transcript_version_id,
            form_transcript.recording_id == processing_attempt.id,
            or_(
                processing_attempt.recording_type != "audio",
                form_transcript.processing_generation
                == processing_attempt.processing_generation,
            ),
        )
        completed_terminal_form = and_(
            processing_evaluation.state == "completed",
            processing_evaluation.transcript_version_id.is_not(None),
            processing_attempt.current_transcript_version_id
            == processing_evaluation.transcript_version_id,
            current_completed_transcript,
            completed_content_stage,
        )
        transcription_terminal_unavailable = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name == "transcription",
            form_stage.stage_state.in_(("unavailable", "failed_terminal")),
            form_stage.last_error_code == result_reason,
        )
        no_completed_audio_downstream = ~exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name.in_(
                (
                    "content_evaluation",
                    "evidence_grounding",
                    "follow_up_decision",
                    "coaching_enrichment",
                )
            ),
            form_stage.stage_state.in_(("completed", "reused")),
        )
        audio_unavailable_terminal_form = and_(
            processing_evaluation.state == "unavailable",
            processing_evaluation.transcript_version_id.is_(None),
            processing_attempt.recording_type == "audio",
            processing_attempt.current_transcript_version_id.is_(None),
            result_reason.in_(AUDIO_PRETRANSCRIPTION_UNAVAILABLE_REASONS),
            transcription_terminal_unavailable,
            ~created_current_generation_transcript,
            no_completed_audio_downstream,
        )
        content_terminal_unavailable = exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name == "content_evaluation",
            form_stage.stage_state.in_(("unavailable", "failed_terminal")),
            form_stage.last_error_code == result_reason,
        )
        no_completed_content_downstream = ~exists().where(
            form_stage.recording_id == processing_attempt.id,
            form_stage.evaluation_version_id == processing_evaluation.id,
            form_stage.stage_name.in_(
                ("evidence_grounding", "follow_up_decision", "coaching_enrichment")
            ),
            form_stage.stage_state.in_(("completed", "reused")),
        )
        content_unavailable_terminal_form = and_(
            processing_evaluation.state == "unavailable",
            processing_evaluation.transcript_version_id.is_not(None),
            processing_attempt.current_transcript_version_id
            == processing_evaluation.transcript_version_id,
            result_reason.in_(TRANSCRIPT_TERMINAL_UNAVAILABLE_REASONS),
            content_terminal_unavailable,
            no_completed_content_downstream,
        )
        terminal_processing_is_actionable = and_(
            processing_attempt.attempt_state.in_(("completed", "unavailable")),
            processing_attempt.evaluation_state == processing_attempt.attempt_state,
            processing_attempt.async_job_id.is_(None),
            processing_evaluation.state == processing_attempt.attempt_state,
            processing_job.status == "done",
            processing_stage.stage_state.in_(_TERMINAL_STAGE_STATES),
            ~nonterminal_stage,
            result_is_mapping,
            or_(
                completed_terminal_form,
                audio_unavailable_terminal_form,
                content_unavailable_terminal_form,
            ),
        )
        due_processing_claim = exists().where(
            processing_attempt.session_id == InterviewSession.id,
            processing_attempt.id == InterviewSession.active_recording_id,
            processing_attempt.question_id == InterviewSession.active_question_id,
            or_(
                and_(
                    processing_attempt.attempt_state == "pending_processing",
                    processing_attempt.evaluation_state == "pending",
                    processing_attempt.async_job_id == processing_job.id,
                    processing_evaluation.state == "pending",
                ),
                and_(
                    processing_attempt.current_evaluation_version_id
                    == processing_evaluation.id,
                    processing_attempt.attempt_state.in_(("completed", "unavailable")),
                ),
            ),
            processing_evaluation.recording_id == processing_attempt.id,
            processing_evaluation.async_job_id == processing_job.id,
            processing_job.type == "coach_attempt_processing",
            exact_claim_shape,
            exact_deadline,
            exact_source,
            selected_stage_is_exact,
            ~malformed_owned_stage,
            or_(
                pending_processing_form_is_actionable,
                terminal_processing_is_actionable,
            ),
        )
        prior = aliased(SessionQuestion)
        accepted = aliased(SessionRecording)
        candidate = aliased(SessionQuestion)
        valid_answered_prior = exists().where(
            prior.id == InterviewSession.active_question_id,
            prior.session_id == InterviewSession.id,
            prior.question_state == "answered",
            prior.accepted_recording_id == accepted.id,
            accepted.session_id == InterviewSession.id,
            accepted.question_id == prior.id,
            accepted.accepted_at.is_not(None),
        )
        valid_skipped_prior = exists().where(
            prior.id == InterviewSession.active_question_id,
            prior.session_id == InterviewSession.id,
            prior.question_state == "skipped",
            prior.accepted_recording_id.is_(None),
        )
        planned_candidate_count = (
            select(func.count(candidate.id))
            .where(
                candidate.session_id == InterviewSession.id,
                candidate.question_state == "pending",
                candidate.question_kind == "planned",
            )
            .correlate(InterviewSession)
            .scalar_subquery()
        )
        valid_report_claim = and_(
            InterviewSession.report_state == "building",
            InterviewSession.report_build_reason == "initial_completion",
            InterviewSession.report_started_at.is_not(None),
            InterviewSession.report_contract_version == REPORT_CONTRACT,
            exists().where(
                AsyncJob.id == InterviewSession.report_job_id,
                AsyncJob.type == "coach_conversational_report",
                AsyncJob.status.in_(("pending", "running")),
            ),
        )
        actionable_advancing = and_(
            InterviewSession.conversation_state == "advancing",
            or_(valid_answered_prior, valid_skipped_prior),
            or_(
                planned_candidate_count >= 1,
                and_(planned_candidate_count == 0, valid_report_claim),
            ),
        )
        follow_up_candidate_count = (
            select(func.count(candidate.id))
            .select_from(prior)
            .join(accepted, accepted.id == prior.accepted_recording_id)
            .join(
                candidate,
                and_(
                    candidate.session_id == InterviewSession.id,
                    candidate.question_state == "pending",
                    candidate.question_kind == "adaptive_follow_up",
                    candidate.parent_question_id == InterviewSession.active_question_id,
                    candidate.root_question_id
                    == InterviewSession.active_root_question_id,
                    candidate.follow_up_source_recording_id == accepted.id,
                    candidate.follow_up_source_transcript_version_id
                    == accepted.current_transcript_version_id,
                    candidate.source_deleted.is_(False),
                ),
            )
            .where(
                prior.id == InterviewSession.active_question_id,
                prior.session_id == InterviewSession.id,
                prior.question_state == "answered",
                accepted.session_id == InterviewSession.id,
                accepted.question_id == prior.id,
                accepted.accepted_at.is_not(None),
                accepted.attempt_state.not_in(("deleted", "cancelled", "invalid")),
                accepted.current_transcript_version_id.is_not(None),
            )
            .correlate(InterviewSession)
            .scalar_subquery()
        )
        actionable_follow_up = and_(
            InterviewSession.conversation_state == "asking_follow_up",
            follow_up_candidate_count == 1,
        )
        due_audio_cleanup = exists().where(
            cleanup_attempt.session_id == InterviewSession.id,
            cleanup_attempt.recording_type == "audio",
            cleanup_attempt.audio_retention_policy == "delete_after_processing",
            cleanup_attempt.audio_uri.is_not(None),
            cleanup_attempt.audio_content_hash.is_not(None),
            cleanup_evaluation.recording_id == cleanup_attempt.id,
            cleanup_evaluation.id == cleanup_stage.evaluation_version_id,
            cleanup_stage.recording_id == cleanup_attempt.id,
            cleanup_stage.stage_name == "audio_cleanup",
            cleanup_stage.expected_processing_generation
            == cleanup_attempt.processing_generation,
            cleanup_transcription.recording_id == cleanup_attempt.id,
            cleanup_transcription.evaluation_version_id == cleanup_evaluation.id,
            cleanup_transcription.stage_name == "transcription",
            cleanup_transcription.expected_processing_generation
            == cleanup_attempt.processing_generation,
            cleanup_speech.recording_id == cleanup_attempt.id,
            cleanup_speech.evaluation_version_id == cleanup_evaluation.id,
            cleanup_speech.stage_name == "speech_analysis",
            cleanup_speech.expected_processing_generation
            == cleanup_attempt.processing_generation,
            or_(
                and_(
                    cleanup_attempt.audio_retention_state.in_(
                        ("temporary", "delete_failed")
                    ),
                    or_(
                        and_(
                            cleanup_attempt.current_transcript_version_id.is_not(None),
                            cleanup_evaluation.transcript_version_id
                            == cleanup_attempt.current_transcript_version_id,
                            cleanup_transcription.stage_state.in_(
                                ("completed", "reused")
                            ),
                            cleanup_speech.stage_state.in_(
                                (
                                    "completed",
                                    "reused",
                                    "unavailable",
                                    "not_applicable",
                                    "failed_terminal",
                                )
                            ),
                        ),
                        and_(
                            cleanup_transcription.stage_state.in_(
                                (
                                    "unavailable",
                                    "failed_retryable",
                                    "failed_terminal",
                                )
                            ),
                            cleanup_transcription.completed_at
                            <= now
                            - timedelta(
                                hours=settings.HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS
                            ),
                        ),
                    ),
                ),
                and_(
                    cleanup_attempt.audio_retention_state == "delete_pending",
                    cleanup_stage.stage_state == "running",
                    cleanup_stage.job_deadline_at <= now,
                    cleanup_stage.job_id == cleanup_job.id,
                    cleanup_job.type == "coach_audio_cleanup",
                    cleanup_job.status.in_(("pending", "running")),
                ),
            ),
        )
        candidate_cursor: tuple[datetime, str] | None = None
        while total < batch_size:
            candidate_query = select(
                InterviewSession.id,
                InterviewSession.experience_version,
                InterviewSession.created_at,
            ).where(
                or_(
                    and_(
                        InterviewSession.experience_version != "conversational_v1",
                        or_(
                            pending_legacy_attempt,
                            due_legacy_report,
                        ),
                    ),
                    and_(
                        InterviewSession.experience_version == "conversational_v1",
                        InterviewSession.deletion_state == "not_requested",
                        or_(
                            and_(
                                InterviewSession.status == "setup",
                                InterviewSession.conversation_state == "planning",
                                InterviewSession.setup_job_id.is_not(None),
                                InterviewSession.setup_claim_token.is_not(None),
                                InterviewSession.setup_claim_expires_at < now,
                            ),
                            actionable_advancing,
                            actionable_follow_up,
                            due_audio_cleanup,
                            and_(
                                InterviewSession.status == "active",
                                InterviewSession.conversation_state
                                == "processing_answer",
                                due_processing_claim,
                            ),
                        ),
                    ),
                )
            )
            if candidate_cursor is not None:
                cursor_created_at, cursor_id = candidate_cursor
                candidate_query = candidate_query.where(
                    or_(
                        InterviewSession.created_at > cursor_created_at,
                        and_(
                            InterviewSession.created_at == cursor_created_at,
                            InterviewSession.id > cursor_id,
                        ),
                    )
                )
            candidate_rows = (
                await db.execute(
                    candidate_query.order_by(
                        InterviewSession.created_at, InterviewSession.id
                    ).limit(batch_size)
                )
            ).all()
            if not candidate_rows:
                break
            for session_id, experience, created_at in candidate_rows:
                candidate_cursor = (created_at, session_id)
                if total >= batch_size:
                    break
                try:
                    if experience == "conversational_v1":
                        total += await reconcile_conversational_session(db, session_id)
                    else:
                        total += await reconcile_session(db, session_id)
                except Exception:
                    await db.rollback()
                    logger.exception(
                        "Coach stale-state recovery failed for session %s", session_id
                    )
    return total
