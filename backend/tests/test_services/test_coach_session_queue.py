from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession
from app.schemas.coach import CreateSessionRequest
from app.services.coach_session_queue import queue_coach_session


@pytest.mark.asyncio
async def test_queue_creates_visible_stub_and_async_job(db_session):
    request = CreateSessionRequest(
        application_id=None,
        company_name="Iron Mountain",
        role_title="Solutions Architect",
        jd_text="Design customer solutions.",
    )

    with patch("app.services.coach_session_queue.AsyncJobService.run") as run:
        result = await queue_coach_session(request, db_session, MagicMock())

    session = (
        await db_session.execute(select(InterviewSession).where(InterviewSession.id == result["session_id"]))
    ).scalar_one()
    async_job = (
        await db_session.execute(select(AsyncJob).where(AsyncJob.id == result["job_id"]))
    ).scalar_one()
    assert session.status == "setup"
    assert session.company_name == "Iron Mountain"
    assert async_job.type == "coach_session"
    run.assert_called_once()
    run.call_args.args[1].close()


@pytest.mark.asyncio
async def test_queue_deduplicates_linked_application(db_session):
    existing = InterviewSession(
        application_id="app-1",
        company_name="Iron Mountain",
        role_title="Solutions Architect",
        config={},
        status="setup",
    )
    db_session.add(existing)
    await db_session.commit()

    result = await queue_coach_session(
        CreateSessionRequest(
            application_id="app-1",
            company_name="Iron Mountain",
            role_title="Solutions Architect",
        ),
        db_session,
        MagicMock(),
        deduplicate_application=True,
    )

    assert result["session_id"] == existing.id
    assert result["created"] is False
    sessions = (await db_session.execute(select(InterviewSession))).scalars().all()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_default_session_list_hides_user_abandoned_but_keeps_failed(db_session):
    db_session.add_all(
        [
            InterviewSession(
                application_id="app-deleted",
                company_name="Veovo",
                role_title="Agile Delivery Lead",
                config={},
                status="abandoned",
            ),
            InterviewSession(
                application_id="app-failed",
                company_name="Acme",
                role_title="Delivery Lead",
                config={},
                status="failed",
            ),
        ]
    )
    await db_session.commit()

    from app.repositories.session_repository import SessionRepository

    visible = await SessionRepository(db_session).list_sessions(
        exclude_abandoned=True,
    )

    assert [session.status for session in visible] == ["failed"]
