"""Idempotent recovery for abandoned Coach answer and report claims."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.async_job import AsyncJob
from ..models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    SessionQuestion,
    SessionRecording,
)
from ..repositories.conversational_session_repository import (
    ConversationalSessionRepository,
    SessionEventInput,
)
from ..repositories.session_repository import SessionRepository
from .coach_contracts import CoachDiagnostic, failed_answer_payload

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


async def _reconcile_processing_answer(
    db: AsyncSession, session: InterviewSession, now: datetime
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
    if attempt is None or attempt.current_evaluation_version_id is None:
        return 0
    evaluation = await db.scalar(
        select(InterviewAttemptEvaluation).where(
            InterviewAttemptEvaluation.id == attempt.current_evaluation_version_id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
        )
    )
    job_id = attempt.async_job_id or (evaluation.async_job_id if evaluation else None)
    job = await db.get(AsyncJob, job_id) if job_id else None

    # A worker may commit the terminal attempt/evaluation immediately before losing
    # its final session transition. Repair only that exact current generation.
    if (
        evaluation is not None
        and _terminal_attempt_state(attempt.attempt_state)
        and attempt.evaluation_state == attempt.attempt_state
        and evaluation.state == attempt.attempt_state
        and job is not None
        and job.status == "done"
        and ((evaluation.diagnostics_json or {}).get("processing_claim") or {}).get(
            "processing_generation"
        )
        == attempt.processing_generation
    ):
        terminal_exists = exists().where(
            InterviewAttemptEvaluation.id == evaluation.id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.state == evaluation.state,
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
            )
            .values(
                conversation_state="awaiting_next_action",
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

    if evaluation is None or attempt.attempt_state != "pending_processing":
        return 0
    active_stage = await db.scalar(
        select(InterviewAttemptStage)
        .where(
            InterviewAttemptStage.recording_id == attempt.id,
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.job_id == job_id,
            InterviewAttemptStage.expected_processing_generation
            == attempt.processing_generation,
            InterviewAttemptStage.stage_state.in_(("pending", "running")),
        )
        .order_by(InterviewAttemptStage.started_at.desc(), InterviewAttemptStage.id)
        .limit(1)
    )
    failed_job = job is None or job.status == "failed"
    expired = (
        active_stage is not None
        and active_stage.job_deadline_at is not None
        and active_stage.job_deadline_at < now
    )
    if not failed_job and not expired:
        return 0
    if active_stage is None:
        return 0

    retryable = attempt.processing_retry_count < attempt.processing_retry_limit
    terminal_state = "recoverable_error" if retryable else "unavailable"
    stage_state = "failed_retryable" if retryable else "failed_terminal"
    error_code = (
        "coach_attempt_job_budget_exhausted"
        if expired
        else "coach_evaluation_unavailable"
    )
    stage_change = await db.execute(
        update(InterviewAttemptStage)
        .where(
            InterviewAttemptStage.id == active_stage.id,
            InterviewAttemptStage.recording_id == attempt.id,
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.job_id == job_id,
            InterviewAttemptStage.claim_token == active_stage.claim_token,
            InterviewAttemptStage.expected_processing_generation
            == attempt.processing_generation,
            InterviewAttemptStage.stage_state == active_stage.stage_state,
            InterviewAttemptStage.job_deadline_at == active_stage.job_deadline_at,
        )
        .values(
            stage_state=stage_state,
            last_error_code=error_code,
            completed_at=now,
            claim_token=None,
        )
    )
    attempt_change = await db.execute(
        update(SessionRecording)
        .where(
            SessionRecording.id == attempt.id,
            SessionRecording.session_id == session.id,
            SessionRecording.question_id == session.active_question_id,
            SessionRecording.current_evaluation_version_id == evaluation.id,
            SessionRecording.processing_generation == attempt.processing_generation,
            SessionRecording.async_job_id == attempt.async_job_id,
            SessionRecording.attempt_state == "pending_processing",
            SessionRecording.evaluation_state == "pending",
        )
        .values(
            attempt_state=terminal_state,
            evaluation_state="failed" if retryable else "unavailable",
            async_job_id=None,
            processing_completed_at=now,
        )
    )
    evaluation_change = await db.execute(
        update(InterviewAttemptEvaluation)
        .where(
            InterviewAttemptEvaluation.id == evaluation.id,
            InterviewAttemptEvaluation.recording_id == attempt.id,
            InterviewAttemptEvaluation.async_job_id == evaluation.async_job_id,
            InterviewAttemptEvaluation.state == "pending",
        )
        .values(
            state="failed" if retryable else "unavailable",
            completed_at=now,
            diagnostics_json={"reason_code": error_code},
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
            conversation_state="recoverable_error",
            recoverable_error_scope="attempt_processing",
            recoverable_error_code=error_code,
            recoverable_error_context_json=None,
            state_version=InterviewSession.state_version + 1,
            last_activity_at=now,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = session_change.scalar_one_or_none()
    if (
        stage_change.rowcount != 1
        or attempt_change.rowcount != 1
        or evaluation_change.rowcount != 1
        or state_version is None
    ):
        raise _ReconciliationFenceLost
    await _fail_async_job(db, job_id=job_id, code=error_code, now=now)
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
                payload_json={"reason_code": error_code, "retryable": retryable},
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
        query = query.where(
            SessionQuestion.question_kind == "adaptive_follow_up",
            SessionQuestion.parent_question_id == session.active_question_id,
            SessionQuestion.root_question_id == session.active_root_question_id,
        )
    else:
        query = query.where(SessionQuestion.question_kind == "planned")
    next_question = await db.scalar(
        query.order_by(SessionQuestion.order_in_session, SessionQuestion.id).limit(1)
    )
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
            and report_job.status in {"pending", "running"}
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
            changed = await _reconcile_transient_state(db, session, now)
        if changed:
            await db.commit()
        return changed
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
    total = 0
    async with AsyncSessionLocal() as db:
        pending_legacy_attempt = exists().where(
            SessionRecording.session_id == InterviewSession.id,
            SessionRecording.evaluation_state == "pending",
        )
        candidate_ids = list(
            (
                await db.execute(
                    select(InterviewSession.id)
                    .where(
                        or_(
                            and_(
                                InterviewSession.experience_version
                                != "conversational_v1",
                                or_(
                                    pending_legacy_attempt,
                                    InterviewSession.report_state == "building",
                                ),
                            ),
                            and_(
                                InterviewSession.experience_version
                                == "conversational_v1",
                                InterviewSession.deletion_state == "not_requested",
                                or_(
                                    and_(
                                        InterviewSession.status == "setup",
                                        InterviewSession.conversation_state
                                        == "planning",
                                        InterviewSession.setup_job_id.is_not(None),
                                        InterviewSession.setup_claim_token.is_not(None),
                                    ),
                                    InterviewSession.conversation_state.in_(
                                        (
                                            "processing_answer",
                                            "asking_follow_up",
                                            "advancing",
                                        )
                                    ),
                                ),
                            ),
                        )
                    )
                    .order_by(InterviewSession.created_at, InterviewSession.id)
                    .limit(batch_size)
                )
            ).scalars()
        )
        for session_id in candidate_ids:
            try:
                experience = await db.scalar(
                    select(InterviewSession.experience_version).where(
                        InterviewSession.id == session_id
                    )
                )
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
