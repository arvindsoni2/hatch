"""Integration test: full agent pipeline from discovery to approval queue.

These tests exercise the entire Scout → Scorer → Tailor chain using the
real in-memory SQLite test database. They are expected to pass once the
scoring pipeline is wired correctly (Prompt 3).
"""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.scorer_agent import ScorerAgent
from app.agents.supervisor import SupervisorAgent
from app.agents.tools.event_bus import EventBus
from app.models.job import JobPosting
from app.models.agent_event import AgentEvent
from sqlalchemy import select


@pytest.fixture(autouse=True)
def reset_event_bus():
    EventBus._instance = None
    yield
    EventBus._instance = None


def _make_mock_profile(method: str = "local"):
    profile = MagicMock()
    profile.locale = "uk"
    profile.scoring.method = method
    profile.scoring.hybrid_llm_top_pct = 0.20
    profile.scoring.shortlist_threshold = 0.75
    profile.scoring.weights.skill_match = 0.35
    profile.scoring.weights.experience_match = 0.30
    profile.scoring.weights.rate_match = 0.20
    profile.scoring.weights.location_match = 0.15
    profile.llm.provider = "anthropic"
    profile.llm.triage_model = "claude-haiku-4-5-20251001"
    profile.llm.primary_model = "claude-sonnet-4-6"
    profile.candidate.title = "Cloud Architect"
    profile.candidate.years_experience = 15
    profile.skills.primary = ["cloud", "aws", "architecture"]
    profile.skills.secondary = ["python", "terraform"]
    profile.search.target_roles = ["Cloud Architect"]
    profile.search.locations = [MagicMock(city="London", country="UK", remote_preference="hybrid")]
    profile.compensation.min_rate = 500
    profile.compensation.max_rate = 750
    profile.compensation.rate_type = "daily"
    profile.compensation.currency = "GBP"
    profile.domains.preferred = ["Finance"]
    return profile


class TestFullPipeline:

    async def test_scorer_marks_events_completed(self, db_session):
        """Scorer (not supervisor) owns job_discovered event lifecycle end-to-end."""
        # Insert a job directly
        job_id = str(uuid.uuid4())
        job = JobPosting(
            id=job_id,
            title="AWS Cloud Architect",
            company="FinTech Ltd",
            location="London, UK",
            rate_text="£650/day",
            rate_min=650.0,
            rate_max=650.0,
            currency="GBP",
            ir35_status="outside",
            description="Senior cloud architect. AWS, architecture experience required.",
            url=f"https://example.com/{job_id}",
            source="reed",
            scraped_at=datetime.utcnow(),
            is_active=True,
            sync_status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(job)
        await db_session.commit()

        # Emit a job_discovered event via the real EventBus → real DB
        bus = EventBus.instance()
        event_id = await bus.emit(
            event_type="job_discovered",
            source_agent="scout",
            payload={"job_id": job_id, "title": "AWS Cloud Architect", "company": "FinTech Ltd"},
            db=db_session,
        )

        profile = _make_mock_profile(method="local")
        mock_triage_model = MagicMock()
        mock_triage_model.with_structured_output.return_value = AsyncMock()
        mock_primary_model = MagicMock()
        mock_primary_model.with_structured_output.return_value = AsyncMock()
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()

        with patch("app.agents.scorer_agent.load_profile", return_value=profile), \
             patch("app.agents.scorer_agent.get_triage_model", return_value=mock_triage_model), \
             patch("app.agents.scorer_agent.get_primary_model", return_value=mock_primary_model), \
             patch("app.agents.scorer_agent.get_limiter", return_value=mock_limiter):
            scorer = ScorerAgent()
            result = await scorer.run(db_session)

        assert result["scored"] == 1

        # Verify the event is now marked completed in the DB
        event_result = await db_session.execute(
            select(AgentEvent).where(AgentEvent.id == event_id)
        )
        event_row = event_result.scalar_one_or_none()
        assert event_row is not None
        assert event_row.status == "completed"

    async def test_low_score_parks_job(self, db_session):
        """A job scoring below threshold is processed but tailor is NOT triggered."""
        job_id = str(uuid.uuid4())
        job = JobPosting(
            id=job_id,
            title="Junior Developer",
            company="StartupXYZ",
            location="Remote",
            rate_text="£200/day",
            rate_min=200.0,
            rate_max=200.0,
            currency="GBP",
            ir35_status="inside",
            description="Junior developer role. HTML/CSS only.",
            url=f"https://example.com/{job_id}",
            source="reed",
            scraped_at=datetime.utcnow(),
            is_active=True,
            sync_status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db_session.add(job)
        await db_session.commit()

        bus = EventBus.instance()
        event_id = await bus.emit(
            event_type="job_discovered",
            source_agent="scout",
            payload={"job_id": job_id, "title": "Junior Developer"},
            db=db_session,
        )

        profile = _make_mock_profile(method="local")
        mock_triage_model = MagicMock()
        mock_triage_model.with_structured_output.return_value = AsyncMock()
        mock_primary_model = MagicMock()
        mock_primary_model.with_structured_output.return_value = AsyncMock()
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()

        mock_tailor = MagicMock()
        mock_tailor.run = AsyncMock()

        with patch("app.agents.scorer_agent.load_profile", return_value=profile), \
             patch("app.agents.scorer_agent.get_triage_model", return_value=mock_triage_model), \
             patch("app.agents.scorer_agent.get_primary_model", return_value=mock_primary_model), \
             patch("app.agents.scorer_agent.get_limiter", return_value=mock_limiter):
            scorer = ScorerAgent()
            result = await scorer.run(db_session)

        # Job is scored but will have low score — no tailor
        assert result["scored"] == 1
        assert result["errors"] == 0

        event_result = await db_session.execute(
            select(AgentEvent).where(AgentEvent.id == event_id)
        )
        event_row = event_result.scalar_one_or_none()
        assert event_row.status == "completed"

    async def test_supervisor_does_not_complete_job_discovered_events(self, db_session):
        """Supervisor tick leaves job_discovered events pending for the scorer to complete."""
        bus = EventBus.instance()

        # Emit a discovery event
        event_id = await bus.emit(
            event_type="job_discovered",
            source_agent="scout",
            payload={"job_id": "some-job"},
            db=db_session,
        )

        mock_scorer = MagicMock()
        mock_scorer.run = AsyncMock(return_value={"scored": 0, "skipped": 0, "errors": 0})
        mock_tailor = MagicMock()
        mock_tailor.run = AsyncMock()
        mock_coach = MagicMock()
        mock_coach.run = AsyncMock()

        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        result = await supervisor.tick(db_session)

        assert result["scorer_triggered"] is True

        # Verify event was NOT marked completed by supervisor
        event_result = await db_session.execute(
            select(AgentEvent).where(AgentEvent.id == event_id)
        )
        event_row = event_result.scalar_one_or_none()
        assert event_row.status == "pending"
