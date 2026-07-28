"""Idempotent recovery for abandoned Coach answer and report claims."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
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
    InterviewTranscriptVersion,
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
_ACTIVE_STAGE_STATES = frozenset({"pending", "running"})
_TERMINAL_STAGE_STATES = frozenset(
    {"completed", "reused", "not_applicable", "unavailable", "failed_terminal"}
)


def _strict_processing_claim(
    evaluation: InterviewAttemptEvaluation,
) -> tuple[Mapping[str, object], datetime] | None:
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
    try:
        deadline = datetime.fromisoformat(claim["job_deadline_at"])
    except (TypeError, ValueError):
        return None
    if deadline.tzinfo is not None:
        return None
    return claim, deadline


async def _current_claim_stages(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    job_id: str,
    claim: Mapping[str, object],
    deadline: datetime,
) -> list[InterviewAttemptStage] | None:
    stages = list(
        (
            await db.scalars(
                select(InterviewAttemptStage).where(
                    InterviewAttemptStage.recording_id == attempt.id,
                    InterviewAttemptStage.evaluation_version_id == evaluation.id,
                )
            )
        ).all()
    )
    generation = claim["processing_generation"]
    token = claim["claim_token"]
    if not stages or any(
        stage.job_id != job_id
        or stage.expected_processing_generation != generation
        or stage.job_deadline_at != deadline
        or stage.claim_token != token
        for stage in stages
    ):
        return None
    return stages


async def _terminal_processing_form_is_valid(
    db: AsyncSession,
    *,
    attempt: SessionRecording,
    evaluation: InterviewAttemptEvaluation,
    stages: list[InterviewAttemptStage],
    claim: Mapping[str, object],
) -> bool:
    if any(stage.stage_state not in _TERMINAL_STAGE_STATES for stage in stages):
        return False
    stage_by_name = {stage.stage_name: stage for stage in stages}
    transcript_id = evaluation.transcript_version_id
    result = evaluation.diagnostics_json.get("result")
    if not isinstance(result, Mapping):
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
            and reason in {"transcription_unavailable", "invalid_audio"}
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
        and reason == "coach_evaluation_unavailable"
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
    parsed_claim = (
        _strict_processing_claim(evaluation) if evaluation is not None else None
    )
    claim = parsed_claim[0] if parsed_claim is not None else None
    deadline = parsed_claim[1] if parsed_claim is not None else None
    stages = (
        await _current_claim_stages(
            db,
            attempt=attempt,
            evaluation=evaluation,
            job_id=job_id,
            claim=claim,
            deadline=deadline,
        )
        if evaluation is not None
        and job_id is not None
        and claim is not None
        and deadline is not None
        else None
    )
    claim_matches = bool(
        claim is not None
        and stages is not None
        and job is not None
        and job.type == "coach_attempt_processing"
        and evaluation is not None
        and evaluation.id == attempt.current_evaluation_version_id
        and evaluation.async_job_id == job_id
        and claim["processing_generation"] == attempt.processing_generation
        and claim["source_audio_content_hash"] == attempt.audio_content_hash
        and claim["expected_session_state_version"] == session.state_version
        and claim["processing_contract_version"] == "coach_processing_v1"
        and (
            (
                attempt.recording_type == "text"
                and claim["source_transcript_version_id"]
                == attempt.current_transcript_version_id
            )
            or (
                attempt.recording_type == "audio"
                and claim["source_transcript_version_id"] is None
            )
        )
    )

    # A worker may commit the terminal attempt/evaluation immediately before losing
    # its final session transition. Repair only that exact current generation.
    if (
        evaluation is not None
        and _terminal_attempt_state(attempt.attempt_state)
        and attempt.evaluation_state == attempt.attempt_state
        and evaluation.state == attempt.attempt_state
        and claim_matches
        and stages is not None
        and job is not None
        and job.status == "done"
        and await _terminal_processing_form_is_valid(
            db,
            attempt=attempt,
            evaluation=evaluation,
            stages=stages,
            claim=claim,
        )
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
        or not claim_matches
        or stages is None
        or deadline is None
        or job is None
    ):
        return 0
    active_stages = [
        stage for stage in stages if stage.stage_state in _ACTIVE_STAGE_STATES
    ]
    failed_job = job.status == "failed"
    expired = deadline < now
    if not failed_job and not expired:
        return 0
    if not active_stages:
        return 0

    retryable = attempt.processing_retry_count < attempt.processing_retry_limit
    transcript_id = evaluation.transcript_version_id
    if attempt.recording_type == "text" and transcript_id is None:
        return 0
    active_names = {stage.stage_name for stage in active_stages}
    pretranscription_audio = (
        attempt.recording_type == "audio"
        and transcript_id is None
        and attempt.current_transcript_version_id is None
        and "transcription" in active_names
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
    if not retryable and transcript_id is None and not pretranscription_audio:
        return 0
    if (
        not retryable
        and transcript_id is not None
        and "content_evaluation" not in active_names
    ):
        return 0
    terminal_state = "recoverable_error" if retryable else "unavailable"
    stage_state = "failed_retryable" if retryable else "failed_terminal"
    session_error_code = (
        "coach_attempt_job_budget_exhausted"
        if expired
        else "coach_evaluation_unavailable"
    )
    terminal_reason = (
        "transcription_unavailable"
        if pretranscription_audio
        else "coach_evaluation_unavailable"
    )
    stage_error_code = session_error_code if retryable else terminal_reason
    stage_change = await db.execute(
        update(InterviewAttemptStage)
        .where(
            InterviewAttemptStage.recording_id == attempt.id,
            InterviewAttemptStage.evaluation_version_id == evaluation.id,
            InterviewAttemptStage.job_id == job_id,
            InterviewAttemptStage.claim_token == claim["claim_token"],
            InterviewAttemptStage.expected_processing_generation
            == attempt.processing_generation,
            InterviewAttemptStage.stage_state.in_(_ACTIVE_STAGE_STATES),
            InterviewAttemptStage.job_deadline_at == deadline,
        )
        .values(
            stage_state=stage_state,
            last_error_code=stage_error_code,
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
            diagnostics_json={
                "processing_claim": dict(claim),
                "result": {
                    "reason_code": session_error_code if retryable else terminal_reason
                },
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
            conversation_state="recoverable_error",
            recoverable_error_scope="attempt_processing",
            recoverable_error_code=session_error_code,
            recoverable_error_context_json=None,
            state_version=InterviewSession.state_version + 1,
            last_activity_at=now,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = session_change.scalar_one_or_none()
    if (
        stage_change.rowcount != len(active_stages)
        or attempt_change.rowcount != 1
        or evaluation_change.rowcount != 1
        or state_version is None
    ):
        raise _ReconciliationFenceLost
    await _fail_async_job(db, job_id=job_id, code=session_error_code, now=now)
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
                ).limit(2)
            )
        ).all()
    )
    if len(candidates) > 1:
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
            and session.report_contract_version == "coach_conversational_report_v1"
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
        pending_legacy_attempt = exists().where(
            SessionRecording.session_id == InterviewSession.id,
            SessionRecording.evaluation_state == "pending",
        )
        due_processing_claim = exists().where(
            SessionRecording.session_id == InterviewSession.id,
            SessionRecording.id == InterviewSession.active_recording_id,
            SessionRecording.current_evaluation_version_id
            == InterviewAttemptEvaluation.id,
            InterviewAttemptEvaluation.async_job_id == AsyncJob.id,
            InterviewAttemptStage.recording_id == SessionRecording.id,
            InterviewAttemptStage.evaluation_version_id
            == InterviewAttemptEvaluation.id,
            or_(
                InterviewAttemptStage.job_deadline_at < now,
                AsyncJob.status.in_(("failed", "done")),
            ),
        )
        candidate_rows = list(
            (
                await db.execute(
                    select(InterviewSession.id, InterviewSession.experience_version)
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
                                        InterviewSession.setup_claim_expires_at < now,
                                    ),
                                    InterviewSession.conversation_state.in_(
                                        (
                                            "asking_follow_up",
                                            "advancing",
                                        )
                                    ),
                                    and_(
                                        InterviewSession.conversation_state
                                        == "processing_answer",
                                        due_processing_claim,
                                    ),
                                ),
                            ),
                        )
                    )
                    .order_by(InterviewSession.created_at, InterviewSession.id)
                    .limit(batch_size)
                )
            ).all()
        )
        for session_id, experience in candidate_rows:
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
