"""Tests for CoachAgent interview preparation flow."""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.application import Application
from app.models.job import JobPosting


def _insert_job(db_session, job_id: str, company: str = "HSBC") -> JobPosting:
    job = JobPosting(
        id=job_id,
        title="Delivery Lead",
        company=company,
        location="London, UK",
        rate_text="£650/day",
        rate_min=650.0,
        rate_max=650.0,
        currency="GBP",
        ir35_status="outside",
        description="Senior delivery lead role. Agile required.",
        url=f"https://example.com/{job_id}",
        source="reed",
        scraped_at=datetime.utcnow(),
        is_active=True,
        sync_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return job


def _insert_application(db_session, app_id: str, job_id: str) -> Application:
    return Application(
        id=app_id,
        job_id=job_id,
        status="applied",
        agent_created=True,
        approval_status="approved",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


def _make_interview_event(app_id: str, round_type: str = "technical") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "event_type": "interview_scheduled",
        "source_agent": "test",
        "payload": {"application_id": app_id, "round_type": round_type},
        "created_at": "2025-01-01T00:00:00",
    }


class TestCoachAgent:

    async def test_run_generates_questions_for_scheduled_interview(self, db_session):
        """CoachAgent calls create_session for each pending interview_scheduled event."""
        job_id = str(uuid.uuid4())
        app_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id))
        db_session.add(_insert_application(db_session, app_id, job_id))
        await db_session.commit()

        event = _make_interview_event(app_id)
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[event])
        mock_bus.emit = AsyncMock(return_value="evt-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_session = MagicMock()
        mock_session.id = "session-1"
        mock_session.questions = [MagicMock(), MagicMock(), MagicMock()]

        mock_coach_service = AsyncMock()
        mock_coach_service.create_session = AsyncMock(return_value=mock_session)

        mock_profile = MagicMock()
        mock_profile.llm.primary_model = "claude-sonnet-4-6"

        with patch("app.agents.coach_agent.CoachService", return_value=mock_coach_service), \
             patch("app.agents.coach_agent.load_profile", return_value=mock_profile), \
             patch("app.agents.coach_agent.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus

            from app.agents.coach_agent import CoachAgent
            agent = CoachAgent()
            agent._bus = mock_bus
            agent._coach = mock_coach_service

            result = await agent.run(db_session)

        mock_coach_service.create_session.assert_called_once()
        assert result["prepared"] == 1
        assert result["errors"] == 0

    async def test_run_emits_prep_ready_event(self, db_session):
        """After preparing, a prep_ready event is emitted with session_id."""
        job_id = str(uuid.uuid4())
        app_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id))
        db_session.add(_insert_application(db_session, app_id, job_id))
        await db_session.commit()

        event = _make_interview_event(app_id)
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[event])
        mock_bus.emit = AsyncMock(return_value="evt-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_session = MagicMock()
        mock_session.id = "session-abc"
        mock_session.questions = [MagicMock(), MagicMock()]

        mock_coach_service = AsyncMock()
        mock_coach_service.create_session = AsyncMock(return_value=mock_session)

        mock_profile = MagicMock()
        mock_profile.llm.primary_model = "claude-sonnet-4-6"

        with patch("app.agents.coach_agent.CoachService", return_value=mock_coach_service), \
             patch("app.agents.coach_agent.load_profile", return_value=mock_profile), \
             patch("app.agents.coach_agent.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus

            from app.agents.coach_agent import CoachAgent
            agent = CoachAgent()
            agent._bus = mock_bus
            agent._coach = mock_coach_service

            await agent.run(db_session)

        emitted_types = [c.kwargs.get("event_type") or c.args[0] for c in mock_bus.emit.call_args_list]
        assert "prep_ready" in emitted_types

        prep_call = next(c for c in mock_bus.emit.call_args_list
                         if (c.kwargs.get("event_type") or c.args[0]) == "prep_ready")
        payload = prep_call.kwargs.get("payload") or prep_call.args[2]
        assert payload["session_id"] == "session-abc"
        assert payload["application_id"] == app_id

    async def test_run_uses_company_and_role_from_job_record(self, db_session):
        """CoachAgent passes correct company name and role from job record to create_session."""
        job_id = str(uuid.uuid4())
        app_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id, company="Goldman Sachs"))
        db_session.add(_insert_application(db_session, app_id, job_id))
        await db_session.commit()

        event = _make_interview_event(app_id)
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[event])
        mock_bus.emit = AsyncMock(return_value="evt-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_session = MagicMock()
        mock_session.id = "session-2"
        mock_session.questions = []

        mock_coach_service = AsyncMock()
        mock_coach_service.create_session = AsyncMock(return_value=mock_session)

        mock_profile = MagicMock()
        mock_profile.llm.primary_model = "claude-sonnet-4-6"

        with patch("app.agents.coach_agent.CoachService", return_value=mock_coach_service), \
             patch("app.agents.coach_agent.load_profile", return_value=mock_profile), \
             patch("app.agents.coach_agent.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus

            from app.agents.coach_agent import CoachAgent
            agent = CoachAgent()
            agent._bus = mock_bus
            agent._coach = mock_coach_service

            await agent.run(db_session)

        call_args = mock_coach_service.create_session.call_args
        request_arg = call_args.args[0]
        assert request_arg.company_name == "Goldman Sachs"
