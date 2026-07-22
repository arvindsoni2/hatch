"""Recovery and report-claim tests for Coach C1."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from app.repositories.session_repository import SessionRepository
from app.services.coach_reconciliation import (
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
        difficulty="medium",
        order_in_session=1,
    )
    db_session.add(question)
    await db_session.flush()
    return session, question


@pytest.mark.asyncio
async def test_stale_answer_recovery_is_no_score_and_idempotent(db_session) -> None:
    session, question = await _session_with_question(db_session)
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="submit_answer", status="running", created_at=old, updated_at=old)
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
    db_session.add(SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        evaluation_state="pending",
        async_job_id=pending_job.id,
    ))
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
    assert await repo.fail_report_claim(session_id, "report-1", {
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
    })
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
