"""Tests for ScoutAgent scraping, deduplication, and event emission."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.job import JobPostingCreate
from tests.conftest import make_job_create


def _make_job_schema(title: str = "Test Job", company: str = "Corp") -> JobPostingCreate:
    return make_job_create(title=title, company=company)


class TestScoutAgent:

    async def test_run_emits_job_discovered_for_new_jobs(self, db_session):
        """Scout discovers 3 jobs; dedup passes all → 3 job_discovered events emitted."""
        mock_bus = AsyncMock()
        mock_bus.emit = AsyncMock(return_value="event-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        jobs = [_make_job_schema(f"Job {i}", "Corp") for i in range(3)]

        mock_scraper = AsyncMock()
        mock_scraper.scrape = AsyncMock(return_value=jobs)
        mock_scraper_cls = MagicMock(return_value=mock_scraper)

        mock_dedup = AsyncMock()
        mock_dedup.is_duplicate = AsyncMock(return_value=False)

        with patch("app.agents.base_agent.EventBus") as MockEB, \
             patch("app.agents.scout_agent.DedupService", return_value=mock_dedup), \
             patch("app.agents.scout_agent.SCRAPER_REGISTRY", {"test_source": mock_scraper_cls}):
            MockEB.instance.return_value = mock_bus

            from app.agents.scout_agent import ScoutAgent
            scout = ScoutAgent(sources=["test_source"])
            scout._bus = mock_bus
            scout._dedup = mock_dedup

            result = await scout.run(db_session)

        assert result["jobs_new"] == 3
        assert result["jobs_found"] == 3
        assert mock_bus.emit.call_count >= 3
        emitted_types = [c.kwargs.get("event_type") or c.args[0] for c in mock_bus.emit.call_args_list]
        assert emitted_types.count("job_discovered") == 3

    async def test_run_filters_duplicates(self, db_session):
        """Scout returns 5 jobs; dedup filters 2 → only 3 job_discovered events emitted."""
        mock_bus = AsyncMock()
        mock_bus.emit = AsyncMock(return_value="event-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        jobs = [_make_job_schema(f"Job {i}", "Corp") for i in range(5)]

        mock_scraper = AsyncMock()
        mock_scraper.scrape = AsyncMock(return_value=jobs)
        mock_scraper_cls = MagicMock(return_value=mock_scraper)

        # First 2 are duplicates, remaining 3 are new
        mock_dedup = AsyncMock()
        mock_dedup.is_duplicate = AsyncMock(side_effect=[True, True, False, False, False])

        with patch("app.agents.base_agent.EventBus") as MockEB, \
             patch("app.agents.scout_agent.DedupService", return_value=mock_dedup), \
             patch("app.agents.scout_agent.SCRAPER_REGISTRY", {"test_source": mock_scraper_cls}):
            MockEB.instance.return_value = mock_bus

            from app.agents.scout_agent import ScoutAgent
            scout = ScoutAgent(sources=["test_source"])
            scout._bus = mock_bus
            scout._dedup = mock_dedup

            result = await scout.run(db_session)

        assert result["jobs_found"] == 5
        assert result["jobs_new"] == 3

    async def test_run_handles_scraper_failure_gracefully(self, db_session):
        """If a scraper raises, a scout_error event is emitted and no crash occurs."""
        mock_bus = AsyncMock()
        mock_bus.emit = AsyncMock(return_value="event-id")
        mock_bus.mark_processing = AsyncMock()
        mock_bus.mark_completed = AsyncMock()
        mock_bus.mark_failed = AsyncMock()

        mock_scraper = AsyncMock()
        mock_scraper.scrape = AsyncMock(side_effect=RuntimeError("Network timeout"))
        mock_scraper_cls = MagicMock(return_value=mock_scraper)

        mock_dedup = AsyncMock()

        with patch("app.agents.base_agent.EventBus") as MockEB, \
             patch("app.agents.scout_agent.DedupService", return_value=mock_dedup), \
             patch("app.agents.scout_agent.SCRAPER_REGISTRY", {"bad_source": mock_scraper_cls}):
            MockEB.instance.return_value = mock_bus

            from app.agents.scout_agent import ScoutAgent
            scout = ScoutAgent(sources=["bad_source"])
            scout._bus = mock_bus
            scout._dedup = mock_dedup

            result = await scout.run(db_session)

        # Should not crash
        assert result["jobs_new"] == 0
        assert len(result["errors"]) == 1
        assert result["errors"][0]["source"] == "bad_source"

        emitted_types = [c.kwargs.get("event_type") or c.args[0] for c in mock_bus.emit.call_args_list]
        assert "scout_error" in emitted_types
