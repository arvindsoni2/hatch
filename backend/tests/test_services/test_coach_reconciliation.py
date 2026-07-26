"""Recovery and report-claim tests for Coach C1."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.async_job import AsyncJob
from app.models.coach_session import (
    InterviewAttemptEvaluation,
    InterviewAttemptStage,
    InterviewSession,
    InterviewSessionEvent,
    SessionQuestion,
    SessionRecording,
)
from app.repositories.session_repository import SessionRepository
from app.services.coach_reconciliation import (
    reconcile_conversational_session,
    reconcile_job,
    reconcile_session,
    reconcile_stale_coach_state,
)
from app.services.coach_service import CoachService


async def _session_with_question(db_session):
    session = InterviewSession(
        company_name="Example",
        role_title="Engineer",
        config={},
        status="active",
        report_state="not_started",
        activity_version=0,
    )
    db_session.add(session)
    await db_session.flush()
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Explain a migration.",
        category="Technical",
        difficulty="realistic",
        order_in_session=1,
    )
    db_session.add(question)
    await db_session.flush()
    return session, question


async def _conversational_session(db_session, *, state: str, status: str = "active"):
    session = InterviewSession(
        company_name="Example",
        role_title="Engineer",
        config={},
        experience_version="conversational_v1",
        status=status,
        conversation_state=state,
        state_version=3,
        activity_version=1,
        deletion_state="not_requested",
        report_state="not_started",
        retention_policy_json={
            "audio": "delete_after_processing",
            "transcript": "retain",
        },
    )
    db_session.add(session)
    await db_session.flush()
    return session


async def _event_count(db_session, session_id: str, event_type: str) -> int:
    rows = await db_session.scalars(
        select(InterviewSessionEvent.id).where(
            InterviewSessionEvent.session_id == session_id,
            InterviewSessionEvent.event_type == event_type,
        )
    )
    return len(rows.all())


@pytest.mark.asyncio
async def test_expired_setup_claim_is_fenced_once_without_spending_retry(
    db_session,
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 7
    session.setup_attempt_count = 2
    session.setup_max_attempts = 3
    session.setup_job_id = job.id
    session.setup_claim_token = "setup-token"
    session.setup_claimed_at = now - timedelta(minutes=2)
    session.setup_claim_expires_at = now - timedelta(seconds=1)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    await db_session.refresh(job)

    assert (session.status, session.conversation_state) == (
        "setup",
        "recoverable_error",
    )
    assert session.recoverable_error_code == "coach_setup_claim_expired"
    assert session.recoverable_error_scope == "setup"
    assert session.setup_job_id is None
    assert session.setup_claim_token is None
    assert session.setup_attempt_count == 2
    assert session.setup_generation == 7
    assert job.status == "failed"
    assert job.error == "coach_setup_claim_expired"
    assert job.result_json is None
    assert await _event_count(db_session, session.id, "session_plan_claim_expired") == 1


@pytest.mark.asyncio
async def test_expired_setup_claim_at_budget_becomes_terminal_failed(
    db_session,
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="pending")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 2
    session.setup_attempt_count = 3
    session.setup_max_attempts = 3
    session.setup_job_id = job.id
    session.setup_claim_token = "terminal-token"
    session.setup_claim_expires_at = now - timedelta(seconds=1)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    await db_session.refresh(session)

    assert (session.status, session.conversation_state) == ("failed", "failed")
    assert session.setup_attempt_count == 3


@pytest.mark.asyncio
async def test_unexpired_or_superseded_setup_claim_is_noop(db_session) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 4
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "newer-token"
    session.setup_claim_expires_at = now + timedelta(minutes=1)
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "planning"
    assert session.setup_generation == 4
    assert await _event_count(db_session, session.id, "session_plan_claim_expired") == 0


async def _processing_claim(
    db_session, *, deadline: datetime, retries: int, limit: int
):
    session = await _conversational_session(db_session, state="processing_answer")
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Explain a migration.",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="asked",
        asked_sequence=1,
    )
    db_session.add(question)
    await db_session.flush()
    job = AsyncJob(type="coach_attempt_processing", status="running")
    db_session.add(job)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="bounded answer",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="pending_processing",
        evaluation_state="pending",
        processing_generation=2,
        processing_retry_count=retries,
        processing_retry_limit=limit,
        async_job_id=job.id,
        audio_retention_policy="delete_after_processing",
        audio_retention_state="not_applicable",
    )
    db_session.add(attempt)
    await db_session.flush()
    evaluation = InterviewAttemptEvaluation(
        recording_id=attempt.id,
        version_number=1,
        state="pending",
        evaluation_contract_version="coach_rubric_v1",
        evidence_contract_version="coach_evidence_grounding_v1",
        follow_up_contract_version="coach_follow_up_v1",
        async_job_id=job.id,
    )
    db_session.add(evaluation)
    await db_session.flush()
    attempt.current_evaluation_version_id = evaluation.id
    stage = InterviewAttemptStage(
        recording_id=attempt.id,
        evaluation_version_id=evaluation.id,
        stage_name="content_evaluation",
        stage_state="running",
        attempt_count=1,
        repair_count=0,
        job_id=job.id,
        claim_token="stage-token",
        expected_processing_generation=2,
        job_deadline_at=deadline,
    )
    db_session.add(stage)
    session.active_question_id = question.id
    session.active_root_question_id = question.id
    session.active_recording_id = attempt.id
    await db_session.commit()
    return session, question, attempt, evaluation, stage, job


async def _add_accepted_question(db_session, session, now: datetime) -> None:
    question = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="Accepted question",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="answered",
        asked_sequence=1,
    )
    db_session.add(question)
    await db_session.flush()
    attempt = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="accepted answer",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        accepted_at=now,
    )
    db_session.add(attempt)
    await db_session.flush()
    question.accepted_recording_id = attempt.id
    session.active_question_id = question.id
    session.active_root_question_id = question.id


@pytest.mark.asyncio
async def test_processing_claim_within_deadline_is_noop(db_session) -> None:
    now = datetime.utcnow()
    session, _, attempt, _, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(attempt)
    await db_session.refresh(stage)
    await db_session.refresh(job)
    assert attempt.attempt_state == "pending_processing"
    assert stage.stage_state == "running"
    assert job.status == "running"


@pytest.mark.asyncio
async def test_expired_processing_claim_becomes_recoverable_without_retry_spend(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=1, limit=2
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    for row in (session, attempt, evaluation, stage, job):
        await db_session.refresh(row)

    assert session.conversation_state == "recoverable_error"
    assert session.recoverable_error_scope == "attempt_processing"
    assert session.recoverable_error_code == "coach_attempt_job_budget_exhausted"
    assert attempt.attempt_state == "recoverable_error"
    assert attempt.processing_retry_count == 1
    assert attempt.async_job_id is None
    assert evaluation.state == "failed"
    assert stage.stage_state == "failed_retryable"
    assert job.status == "failed"
    assert job.result_json is None


@pytest.mark.asyncio
async def test_expired_processing_claim_at_retry_limit_becomes_unavailable(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, _ = await _processing_claim(
        db_session, deadline=now - timedelta(seconds=1), retries=2, limit=2
    )

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    for row in (session, attempt, evaluation, stage):
        await db_session.refresh(row)

    assert session.conversation_state == "recoverable_error"
    assert attempt.attempt_state == "unavailable"
    assert attempt.evaluation_state == "unavailable"
    assert evaluation.state == "unavailable"
    assert stage.stage_state == "failed_terminal"
    assert attempt.processing_retry_count == 2


@pytest.mark.asyncio
async def test_terminal_evaluation_missed_transition_moves_to_awaiting_once(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )
    attempt.attempt_state = "completed"
    attempt.evaluation_state = "completed"
    evaluation.state = "completed"
    evaluation.diagnostics_json = {
        "processing_claim": {"processing_generation": attempt.processing_generation}
    }
    stage.stage_state = "completed"
    job.status = "done"
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "awaiting_next_action"
    assert (
        await _event_count(db_session, session.id, "attempt_processing_completed") == 1
    )


@pytest.mark.asyncio
async def test_terminal_evaluation_from_superseded_generation_is_noop(
    db_session,
) -> None:
    now = datetime.utcnow()
    session, _, attempt, evaluation, stage, job = await _processing_claim(
        db_session, deadline=now + timedelta(minutes=1), retries=0, limit=2
    )
    attempt.attempt_state = "completed"
    attempt.evaluation_state = "completed"
    evaluation.state = "completed"
    evaluation.diagnostics_json = {
        "processing_claim": {"processing_generation": attempt.processing_generation - 1}
    }
    stage.stage_state = "completed"
    job.status = "done"
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    assert session.conversation_state == "processing_answer"
    assert (
        await _event_count(db_session, session.id, "attempt_processing_completed") == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("transient", ["advancing", "asking_follow_up"])
async def test_transient_state_presents_existing_next_question_once(
    db_session, transient: str
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(db_session, state=transient)
    prior = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="First question",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="answered",
        accepted_recording_id=None,
        asked_sequence=1,
    )
    db_session.add(prior)
    await db_session.flush()
    accepted = SessionRecording(
        session_id=session.id,
        question_id=prior.id,
        recording_type="text",
        transcript="accepted answer",
        attempt_number=1,
        attempt_kind="primary",
        attempt_state="completed",
        evaluation_state="completed",
        processing_generation=1,
        processing_retry_count=0,
        processing_retry_limit=2,
        accepted_at=now,
    )
    db_session.add(accepted)
    await db_session.flush()
    prior.accepted_recording_id = accepted.id
    if transient == "asking_follow_up":
        next_question = SessionQuestion(
            session_id=session.id,
            question_num=2,
            text="Give a measurable result.",
            category="technical",
            difficulty="realistic",
            order_in_session=2,
            question_kind="adaptive_follow_up",
            question_state="pending",
            root_question_id=prior.id,
            parent_question_id=prior.id,
            follow_up_depth=1,
            follow_up_reason="measurable_result",
        )
    else:
        next_question = SessionQuestion(
            session_id=session.id,
            question_num=2,
            text="Second question",
            category="behavioural",
            difficulty="realistic",
            order_in_session=2,
            question_kind="planned",
            question_state="pending",
        )
    db_session.add(next_question)
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()

    assert await reconcile_conversational_session(db_session, session.id, now) == 1
    assert await reconcile_conversational_session(db_session, session.id, now) == 0
    await db_session.refresh(session)
    await db_session.refresh(next_question)
    assert session.conversation_state == "asking"
    assert session.active_question_id == next_question.id
    assert next_question.question_state == "asked"
    assert next_question.asked_sequence == 2
    assert await _event_count(db_session, session.id, "question_presented") == 1


@pytest.mark.asyncio
async def test_transient_without_persisted_acceptance_is_noop(db_session) -> None:
    session = await _conversational_session(db_session, state="advancing")
    prior = SessionQuestion(
        session_id=session.id,
        question_num=1,
        text="First question",
        category="technical",
        difficulty="realistic",
        order_in_session=1,
        question_kind="planned",
        question_state="answered",
        asked_sequence=1,
    )
    next_question = SessionQuestion(
        session_id=session.id,
        question_num=2,
        text="Second question",
        category="behavioural",
        difficulty="realistic",
        order_in_session=2,
        question_kind="planned",
        question_state="pending",
    )
    db_session.add_all((prior, next_question))
    await db_session.flush()
    session.active_question_id = prior.id
    session.active_root_question_id = prior.id
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(next_question)
    assert next_question.question_state == "pending"


@pytest.mark.asyncio
async def test_advancing_without_question_or_existing_report_claim_fails_closed(
    db_session,
) -> None:
    session = await _conversational_session(db_session, state="advancing")
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(session)
    assert session.conversation_state == "advancing"
    assert session.report_job_id is None


@pytest.mark.asyncio
async def test_advancing_rejects_dangling_report_claim(db_session) -> None:
    session = await _conversational_session(db_session, state="advancing")
    await _add_accepted_question(db_session, session, datetime.utcnow())
    session.report_state = "building"
    session.report_build_reason = "initial_completion"
    session.report_job_id = "missing-job"
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(session)
    assert session.conversation_state == "advancing"


@pytest.mark.asyncio
async def test_advancing_finishes_existing_report_claim_once(db_session) -> None:
    session = await _conversational_session(db_session, state="advancing")
    await _add_accepted_question(db_session, session, datetime.utcnow())
    job = AsyncJob(type="coach_conversational_report", status="pending")
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_build_reason = "initial_completion"
    session.report_job_id = job.id
    await db_session.commit()

    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 1
    )
    assert (
        await reconcile_conversational_session(
            db_session, session.id, datetime.utcnow()
        )
        == 0
    )
    await db_session.refresh(session)
    assert session.conversation_state == "reporting"
    assert await _event_count(db_session, session.id, "report_claimed") == 1


@pytest.mark.asyncio
async def test_reconciliation_event_failure_rolls_back_state(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 1
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "rollback-token"
    session.setup_claim_expires_at = now - timedelta(seconds=1)
    session_id = session.id
    job_id = job.id
    await db_session.commit()

    async def fail_event(*args, **kwargs):
        raise RuntimeError("event insert failed")

    monkeypatch.setattr(
        "app.services.coach_reconciliation.ConversationalSessionRepository.append_session_events",
        fail_event,
    )
    with pytest.raises(RuntimeError, match="event insert failed"):
        await reconcile_conversational_session(db_session, session_id, now)
    await db_session.rollback()
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "planning"
    assert recovered.setup_job_id == job_id


@pytest.mark.asyncio
async def test_job_poll_uses_targeted_conversational_reconciliation(db_session) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 1
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "poll-token"
    session.setup_claim_expires_at = now - timedelta(days=1)
    session_id = session.id
    job_id = job.id
    await db_session.commit()

    assert await reconcile_job(db_session, job_id) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_startup_reconciliation_uses_shared_conversational_routine(
    db_session, monkeypatch
) -> None:
    now = datetime.utcnow()
    session = await _conversational_session(
        db_session, state="planning", status="setup"
    )
    job = AsyncJob(type="coach_session_setup", status="running")
    db_session.add(job)
    await db_session.flush()
    session.setup_generation = 1
    session.setup_attempt_count = 1
    session.setup_job_id = job.id
    session.setup_claim_token = "startup-token"
    session.setup_claim_expires_at = now - timedelta(days=1)
    session_id = session.id
    await db_session.commit()

    fresh_session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.services.coach_reconciliation.AsyncSessionLocal",
        fresh_session_factory,
    )

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await db_session.get(InterviewSession, session_id)
    assert recovered is not None
    assert recovered.conversation_state == "recoverable_error"


@pytest.mark.asyncio
async def test_stale_answer_recovery_is_no_score_and_idempotent(db_session) -> None:
    session, question = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(
        type="submit_answer", status="running", created_at=old, updated_at=old
    )
    db_session.add(job)
    await db_session.flush()
    recording = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript="answer",
        evaluation_state="pending",
        async_job_id=job.id,
        created_at=old,
    )
    db_session.add(recording)
    await db_session.commit()

    assert await reconcile_session(db_session, session.id) == 1
    await db_session.refresh(recording)
    await db_session.refresh(job)
    payload = json.loads(recording.evaluation_json)
    assert recording.evaluation_state == "failed"
    assert payload["scores"] == {}
    assert payload["overall"] is None
    assert payload["reason_code"] == "stale_async_job_recovered"
    assert job.status == "failed"
    assert await reconcile_session(db_session, session.id) == 0


@pytest.mark.asyncio
async def test_done_job_pending_recording_marks_persistence_failure(db_session) -> None:
    session, question = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="submit_answer", status="done", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    recording = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        evaluation_state="pending",
        async_job_id=job.id,
        created_at=old,
    )
    db_session.add(recording)
    await db_session.commit()

    await reconcile_session(db_session, session.id)
    await db_session.refresh(recording)
    gates = json.loads(recording.evaluation_json)["diagnostic"]["gate_codes"]
    assert gates == ["coach_async_job_failed", "coach_persistence_failed"]


@pytest.mark.asyncio
async def test_report_claim_rejects_pending_and_fences_old_worker(db_session) -> None:
    session, question = await _session_with_question(db_session)
    repo = SessionRepository(db_session)
    pending_job = AsyncJob(type="submit_answer")
    db_session.add(pending_job)
    await db_session.flush()
    db_session.add(
        SessionRecording(
            session_id=session.id,
            question_id=question.id,
            recording_type="text",
            evaluation_state="pending",
            async_job_id=pending_job.id,
        )
    )
    session_id = session.id
    await db_session.commit()

    assert not await repo.claim_report(session_id, "report-1", 0)
    await db_session.rollback()

    session = await repo.get_session(session_id)
    recording = (await repo.get_recordings(session_id))[0]
    recording.evaluation_state = "failed"
    await db_session.commit()
    assert await repo.claim_report(session_id, "report-1", session.activity_version)
    await db_session.commit()
    assert await repo.fail_report_claim(
        session_id,
        "report-1",
        {
            "validation_schema_version": "1.0.0",
            "stage": "session_report",
            "outcome": "failed",
            "execution_mode": "deterministic",
            "prompt_id": None,
            "prompt_version": None,
            "output_schema_version": None,
            "model_id": None,
            "attempt_count": 0,
            "repair_count": 0,
            "gate_codes": ["coach_async_job_failed"],
            "duration_ms": 0,
        },
    )
    await db_session.commit()
    assert not await repo.finalize_report_claim(
        session_id,
        "report-1",
        report_json={},
        rubric={},
        overall_score=None,
        feedback_summary="",
        report_state="fallback",
        report_diagnostic={},
        aggregation_diagnostic={},
    )


@pytest.mark.asyncio
async def test_stale_report_recovery_is_retryable_idempotent_and_fenced(
    db_session,
) -> None:
    session, _ = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="end_coach_session", status="running", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_job_id = job.id
    session.report_started_at = old
    old_job_id = job.id
    session_id = session.id
    await db_session.commit()

    assert await reconcile_session(db_session, session_id) == 1
    await db_session.refresh(session)
    await db_session.refresh(job)
    assert session.report_state == "failed"
    assert session.status == "active"
    assert session.report_started_at is None
    assert job.status == "failed"
    report_diagnostic = session.diagnostics["stages"]["session_report"]
    assert report_diagnostic["reason_code"] == "stale_async_job_recovered"
    assert report_diagnostic["final"]["gate_codes"] == ["coach_async_job_failed"]
    assert await reconcile_session(db_session, session_id) == 0

    repository = SessionRepository(db_session)
    assert await repository.claim_report(session_id, "replacement-job", 0)
    await db_session.commit()
    assert not await repository.finalize_report_claim(
        session_id,
        old_job_id,
        report_json={},
        rubric={},
        overall_score=None,
        feedback_summary="",
        report_state="fallback",
        report_diagnostic={},
        aggregation_diagnostic={},
    )


@pytest.mark.asyncio
async def test_done_job_building_report_records_persistence_failure(db_session) -> None:
    session, _ = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="end_coach_session", status="done", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_job_id = job.id
    session.report_started_at = old
    await db_session.commit()

    assert await reconcile_session(db_session, session.id) == 1
    await db_session.refresh(session)
    await db_session.refresh(job)
    gates = session.diagnostics["stages"]["session_report"]["final"]["gate_codes"]
    assert gates == ["coach_async_job_failed", "coach_persistence_failed"]
    assert session.report_state == "failed"
    assert session.status == "active"
    assert job.status == "done"


@pytest.mark.asyncio
async def test_startup_reconciliation_uses_fresh_session_for_stale_report(
    db_session,
    monkeypatch,
) -> None:
    session, _ = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="end_coach_session", status="running", updated_at=old)
    db_session.add(job)
    await db_session.flush()
    session.report_state = "building"
    session.report_job_id = job.id
    session.report_started_at = old
    session_id = session.id
    await db_session.commit()

    fresh_session_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        "app.services.coach_reconciliation.AsyncSessionLocal",
        fresh_session_factory,
    )

    assert await reconcile_stale_coach_state(batch_size=1) == 1
    db_session.expire_all()
    recovered = await SessionRepository(db_session).get_session(session_id)
    assert recovered is not None
    assert recovered.report_state == "failed"
    assert recovered.status == "active"


@pytest.mark.asyncio
async def test_get_report_returns_snapshot_without_mutation(db_session) -> None:
    session, _ = await _session_with_question(db_session)
    snapshot = {
        "session_id": session.id,
        "report_state": "completed",
        "overall_score": None,
        "question_count_total": 1,
        "question_count_evaluated": 0,
        "question_count_skipped": 0,
        "question_count_unavailable": 0,
        "question_count_unanswered": 1,
        "category_scores": {},
        "executive_summary": "Stored snapshot",
        "strengths": [],
        "improvement_areas": [],
        "coaching_points": [],
        "practice_plan": [],
        "question_evaluations": [],
    }
    session.status = "completed"
    session.report_state = "completed"
    session.report_json = snapshot
    await db_session.commit()

    report = await CoachService.__new__(CoachService).get_report(session.id, db_session)

    assert report.model_dump(mode="json") == snapshot | {"diagnostic": None}
    assert not db_session.dirty


@pytest.mark.asyncio
async def test_legacy_completed_report_is_in_memory_fallback(db_session) -> None:
    session, _ = await _session_with_question(db_session)
    session.status = "completed"
    await db_session.commit()

    report = await CoachService.__new__(CoachService).get_report(session.id, db_session)

    assert report.report_state == "fallback"
    assert report.overall_score is None
    assert report.diagnostic is not None
    await db_session.refresh(session)
    assert session.report_json is None
