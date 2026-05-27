"""Tests for ScorerAgent scoring strategies and event lifecycle."""
from __future__ import annotations

import uuid
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.job import JobPosting


def _insert_job(db_session, job_id: str, description: str = "Senior cloud architect role remote") -> JobPosting:
    job = JobPosting(
        id=job_id,
        title="Cloud Architect",
        company="Test Corp",
        location="London, UK",
        rate_text="£650/day",
        rate_min=650.0,
        rate_max=650.0,
        currency="GBP",
        ir35_status="outside",
        description=description,
        url=f"https://example.com/{job_id}",
        source="test",
        scraped_at=datetime.utcnow(),
        is_active=True,
        sync_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    return job


def _make_discovery_event(job_id: str, event_id: str | None = None) -> dict:
    return {
        "id": event_id or str(uuid.uuid4()),
        "event_type": "job_discovered",
        "source_agent": "scout",
        "payload": {"job_id": job_id, "title": "Cloud Architect", "company": "Test Corp"},
        "created_at": "2025-01-01T00:00:00",
    }


def _make_mock_profile(method: str = "hybrid", top_pct: float = 0.20):
    profile = MagicMock()
    profile.locale = "uk"
    profile.scoring.method = method
    profile.scoring.hybrid_llm_top_pct = top_pct
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


def _make_mock_llm(triage_relevant: bool = True, score: float = 0.85):
    triage_result = MagicMock(relevant=triage_relevant, reason="relevant")
    score_result = MagicMock(
        skill_match=score, experience_match=score, rate_match=score, location_match=score,
        overall_score=score, reasoning="good match",
        keyword_matches=["cloud", "aws"], keyword_misses=[],
    )
    # ainvoke is the actual method called by the scorer — configure it explicitly
    triage_llm = MagicMock()
    triage_llm.ainvoke = AsyncMock(return_value=triage_result)
    primary_llm = MagicMock()
    primary_llm.ainvoke = AsyncMock(return_value=score_result)

    mock_triage_model = MagicMock()
    mock_triage_model.with_structured_output.return_value = triage_llm
    mock_primary_model = MagicMock()
    mock_primary_model.with_structured_output.return_value = primary_llm

    return mock_triage_model, mock_primary_model, triage_llm, primary_llm


class TestScorerAgent:

    async def test_hybrid_scores_all_locally_then_llm_top_pct(self, db_session):
        """Hybrid mode: local-scores 5 jobs, LLM called only for top 20% (1 job)."""
        job_ids = [str(uuid.uuid4()) for _ in range(5)]
        for jid in job_ids:
            db_session.add(_insert_job(db_session, jid))
        await db_session.commit()

        events = [_make_discovery_event(jid) for jid in job_ids]
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=events)
        mock_bus.emit = AsyncMock(return_value="event-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        profile = _make_mock_profile(method="hybrid", top_pct=0.20)
        mock_triage_model, mock_primary_model, triage_llm, primary_llm = _make_mock_llm()
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()
        mock_limiter.record_429 = MagicMock()

        with patch("app.agents.scorer_agent.load_profile", return_value=profile), \
             patch("app.agents.scorer_agent.get_triage_model", return_value=mock_triage_model), \
             patch("app.agents.scorer_agent.get_primary_model", return_value=mock_primary_model), \
             patch("app.agents.scorer_agent.get_limiter", return_value=mock_limiter):
            from app.agents.scorer_agent import ScorerAgent
            scorer = ScorerAgent()
            scorer._bus = mock_bus
            result = await scorer.run(db_session)

        # 5 jobs, top_pct=0.20 → llm_count = max(1, round(5*0.2)) = 1 LLM call
        assert triage_llm.ainvoke.call_count == 1
        assert result["scored"] + result["skipped"] + result["errors"] == 5

    async def test_local_only_makes_zero_llm_calls(self, db_session):
        """Local method: no LLM ainvoke calls, all jobs scored via keyword matching."""
        job_id = str(uuid.uuid4())
        db_session.add(_insert_job(db_session, job_id))
        await db_session.commit()

        events = [_make_discovery_event(job_id)]
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=events)
        mock_bus.emit = AsyncMock(return_value="event-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        profile = _make_mock_profile(method="local")
        mock_triage_model, mock_primary_model, triage_llm, primary_llm = _make_mock_llm()
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()

        with patch("app.agents.scorer_agent.load_profile", return_value=profile), \
             patch("app.agents.scorer_agent.get_triage_model", return_value=mock_triage_model), \
             patch("app.agents.scorer_agent.get_primary_model", return_value=mock_primary_model), \
             patch("app.agents.scorer_agent.get_limiter", return_value=mock_limiter):
            from app.agents.scorer_agent import ScorerAgent
            scorer = ScorerAgent()
            scorer._bus = mock_bus
            await scorer.run(db_session)

        triage_llm.assert_not_called()
        primary_llm.assert_not_called()

    async def test_marks_events_completed_after_scoring(self, db_session):
        """Every processed job_discovered event must be marked completed by scorer."""
        job_ids = [str(uuid.uuid4()) for _ in range(3)]
        event_ids = [str(uuid.uuid4()) for _ in range(3)]
        for jid in job_ids:
            db_session.add(_insert_job(db_session, jid))
        await db_session.commit()

        events = [_make_discovery_event(jid, eid) for jid, eid in zip(job_ids, event_ids)]
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=events)
        mock_bus.emit = AsyncMock(return_value="event-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        profile = _make_mock_profile(method="local")
        mock_triage_model, mock_primary_model, _, _ = _make_mock_llm()
        mock_limiter = MagicMock()
        mock_limiter.acquire = AsyncMock()

        with patch("app.agents.scorer_agent.load_profile", return_value=profile), \
             patch("app.agents.scorer_agent.get_triage_model", return_value=mock_triage_model), \
             patch("app.agents.scorer_agent.get_primary_model", return_value=mock_primary_model), \
             patch("app.agents.scorer_agent.get_limiter", return_value=mock_limiter):
            from app.agents.scorer_agent import ScorerAgent
            scorer = ScorerAgent()
            scorer._bus = mock_bus
            await scorer.run(db_session)

        completed = {call.args[0] for call in mock_bus.mark_completed.call_args_list}
        for eid in event_ids:
            assert eid in completed

    async def test_run_returns_zero_when_no_pending_events(self, db_session):
        """If no pending job_discovered events, run() returns all-zero counts."""
        mock_bus = AsyncMock()
        mock_bus.poll = AsyncMock(return_value=[])

        profile = _make_mock_profile()
        mock_triage_model, mock_primary_model, _, _ = _make_mock_llm()
        mock_limiter = MagicMock()

        with patch("app.agents.scorer_agent.load_profile", return_value=profile), \
             patch("app.agents.scorer_agent.get_triage_model", return_value=mock_triage_model), \
             patch("app.agents.scorer_agent.get_primary_model", return_value=mock_primary_model), \
             patch("app.agents.scorer_agent.get_limiter", return_value=mock_limiter):
            from app.agents.scorer_agent import ScorerAgent
            scorer = ScorerAgent()
            scorer._bus = mock_bus
            result = await scorer.run(db_session)

        assert result == {"scored": 0, "skipped": 0, "errors": 0}
