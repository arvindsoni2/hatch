"""Characterize current Coach stale-work recovery semantics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from app.services.coach_reconciliation import reconcile_session


async def test_legacy_coach_reconciliation_is_idempotent(db_session, runtime_fixture) -> None:
    case = runtime_fixture("coach_cases.json")
    session = InterviewSession(
        company_name=case["session"]["company_name"],
        role_title=case["session"]["role_title"],
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
        text=case["question"],
        category="Technical",
        difficulty="realistic",
        order_in_session=1,
    )
    db_session.add(question)
    await db_session.flush()
    old = datetime.utcnow() - timedelta(days=1)
    job = AsyncJob(type="submit_answer", status="running", created_at=old, updated_at=old)
    db_session.add(job)
    await db_session.flush()
    recording = SessionRecording(
        session_id=session.id,
        question_id=question.id,
        recording_type="text",
        transcript=case["answer"],
        evaluation_state="pending",
        async_job_id=job.id,
        created_at=old,
    )
    db_session.add(recording)
    await db_session.commit()

    first = await reconcile_session(db_session, session.id)
    second = await reconcile_session(db_session, session.id)
    await db_session.refresh(recording)
    await db_session.refresh(job)
    payload = json.loads(recording.evaluation_json)

    assert (first, second) == (1, 0)
    assert recording.evaluation_state == "failed"
    assert payload["scores"] == {}
    assert payload["overall"] is None
    assert payload["reason_code"] == case["expected_reason_code"]
    assert job.status == "failed"
