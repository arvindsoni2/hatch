"""Tests for SupervisorAgent.tick() event routing logic."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_event(event_id: str, event_type: str, payload: dict) -> dict:
    return {
        "id": event_id,
        "event_type": event_type,
        "source_agent": "test",
        "payload": payload,
        "created_at": "2025-01-01T00:00:00",
    }


@pytest.fixture
def mock_scorer():
    scorer = MagicMock()
    scorer.run = AsyncMock(return_value={"scored": 1, "skipped": 0, "errors": 0})
    return scorer


@pytest.fixture
def mock_tailor():
    tailor = MagicMock()
    tailor.run = AsyncMock(return_value={"tailored": 1, "errors": 0})
    return tailor


@pytest.fixture
def mock_coach():
    coach = MagicMock()
    coach.run = AsyncMock(return_value={"prepared": 1, "errors": 0})
    return coach


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.poll = AsyncMock(return_value=[])
    bus.emit = AsyncMock(return_value="new-event-id")
    bus.mark_processing = AsyncMock()
    bus.mark_completed = AsyncMock()
    bus.mark_failed = AsyncMock()
    return bus


class TestSupervisorTick:

    async def test_tick_triggers_scorer_when_discoveries_pending(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """When job_discovered events are pending, tick() returns scorer_triggered=True."""
        discovery = _make_event("evt-1", "job_discovered", {"job_id": "job-1", "title": "Test"})
        # First poll (job_discovered filter) returns the event; second (all events) returns empty
        mock_bus.poll = AsyncMock(side_effect=[[discovery], []])

        with patch("app.agents.supervisor.EventBus") as MockEB:
            MockEB.instance.return_value = mock_bus
            from app.agents.supervisor import SupervisorAgent
            supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
            supervisor._bus = mock_bus

            result = await supervisor.tick(db_session)

        assert result["scorer_triggered"] is True
        assert result["processed"] >= 1

    async def test_tick_routes_job_scored_above_threshold_to_tailor(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """job_scored with score >= threshold triggers tailor and emits job_shortlisted."""
        scored_evt = _make_event("evt-2", "job_scored", {"job_id": "job-2", "score": 0.90})
        mock_bus.poll = AsyncMock(side_effect=[[], [scored_evt]])

        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75

        with patch("app.agents.supervisor.load_profile", return_value=mock_profile):
            from app.agents.supervisor import SupervisorAgent
            supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
            supervisor._bus = mock_bus

            result = await supervisor.tick(db_session)

        mock_bus.emit.assert_called_once()
        emitted_type = mock_bus.emit.call_args.kwargs.get("event_type") or mock_bus.emit.call_args.args[0]
        assert emitted_type == "job_shortlisted"
        mock_tailor.run.assert_called_once_with(db_session)
        assert result["processed"] >= 1

    async def test_tick_parks_job_scored_below_threshold(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """job_scored with score < threshold parks the job — tailor is NOT triggered."""
        scored_evt = _make_event("evt-3", "job_scored", {"job_id": "job-3", "score": 0.40})
        mock_bus.poll = AsyncMock(side_effect=[[], [scored_evt]])

        mock_profile = MagicMock()
        mock_profile.scoring.shortlist_threshold = 0.75

        with patch("app.agents.supervisor.load_profile", return_value=mock_profile):
            from app.agents.supervisor import SupervisorAgent
            supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
            supervisor._bus = mock_bus

            result = await supervisor.tick(db_session)

        mock_tailor.run.assert_not_called()
        mock_bus.emit.assert_not_called()
        assert result["processed"] >= 1

    async def test_tick_does_not_mark_job_discovered_as_completed(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """Supervisor must NOT call mark_completed on job_discovered events; scorer owns that."""
        discovery = _make_event("evt-4", "job_discovered", {"job_id": "job-4"})
        mock_bus.poll = AsyncMock(side_effect=[[discovery], []])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        await supervisor.tick(db_session)

        completed_ids = [call.args[0] for call in mock_bus.mark_completed.call_args_list]
        assert "evt-4" not in completed_ids
