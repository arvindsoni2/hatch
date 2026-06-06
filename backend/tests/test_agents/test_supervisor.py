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

    async def test_tick_returns_zero_when_no_events(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """tick() returns processed=0, scorer_triggered=False when the bus is empty."""
        mock_bus.poll = AsyncMock(return_value=[])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        result = await supervisor.tick(db_session)

        assert result == {"processed": 0, "scorer_triggered": False}
        mock_scorer.run.assert_not_called()

    async def test_tick_marks_informational_events_completed(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """agent_heartbeat, job_shortlisted, and prep_ready are marked completed without side effects."""
        for event_type in ("agent_heartbeat", "job_shortlisted", "prep_ready"):
            mock_bus.reset_mock()
            evt = _make_event(f"evt-{event_type}", event_type, {})
            mock_bus.poll = AsyncMock(side_effect=[[], [evt]])

            from app.agents.supervisor import SupervisorAgent
            supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
            supervisor._bus = mock_bus

            result = await supervisor.tick(db_session)

            mock_bus.mark_completed.assert_called_once_with(f"evt-{event_type}", db_session)
            mock_tailor.run.assert_not_called()
            assert result["processed"] >= 1

    async def test_tick_handles_unknown_event_type(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """Unknown event types are logged and marked completed — no crash."""
        unknown = _make_event("evt-unk", "totally_unknown_event", {"data": "x"})
        mock_bus.poll = AsyncMock(side_effect=[[], [unknown]])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        result = await supervisor.tick(db_session)

        completed_ids = [call.args[0] for call in mock_bus.mark_completed.call_args_list]
        assert "evt-unk" in completed_ids
        assert result["processed"] >= 1

    async def test_tick_handles_routing_error_gracefully(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """A routing exception marks the event failed and does not crash the tick loop."""
        bad_event = _make_event("evt-bad", "job_scored", {"job_id": "j1", "score": 0.9})
        mock_bus.poll = AsyncMock(side_effect=[[], [bad_event]])
        mock_bus.mark_processing = AsyncMock(side_effect=RuntimeError("DB hiccup"))

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        result = await supervisor.tick(db_session)

        mock_bus.mark_failed.assert_called_once()
        failed_id = mock_bus.mark_failed.call_args.args[0]
        assert failed_id == "evt-bad"
        # processed is not incremented for failed events (exception raised before counter)
        assert result["scorer_triggered"] is False

    async def test_tick_handles_cv_tailored_event(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """cv_tailored event emits application_ready and marks the event completed."""
        payload = {"application_id": "app-1", "job_id": "job-1",
                   "cv_document_id": "cv-1", "cl_document_id": "cl-1"}
        cv_evt = _make_event("evt-cv", "cv_tailored", payload)
        mock_bus.poll = AsyncMock(side_effect=[[], [cv_evt]])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        await supervisor.tick(db_session)

        # Must emit application_ready
        emitted_type = mock_bus.emit.call_args.kwargs.get("event_type") or mock_bus.emit.call_args.args[0]
        assert emitted_type == "application_ready"
        emitted_payload = mock_bus.emit.call_args.kwargs.get("payload") or mock_bus.emit.call_args.args[1]
        assert emitted_payload["application_id"] == "app-1"
        # Must mark original event completed
        completed_ids = [c.args[0] for c in mock_bus.mark_completed.call_args_list]
        assert "evt-cv" in completed_ids

    async def test_tick_handles_interview_scheduled(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """interview_scheduled event marks completed and delegates to CoachAgent."""
        interview_evt = _make_event("evt-int", "interview_scheduled",
                                    {"application_id": "app-2", "interview_date": "2026-07-01"})
        mock_bus.poll = AsyncMock(side_effect=[[], [interview_evt]])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        await supervisor.tick(db_session)

        mock_coach.run.assert_called_once_with(db_session)
        completed_ids = [c.args[0] for c in mock_bus.mark_completed.call_args_list]
        assert "evt-int" in completed_ids

    async def test_tick_handles_scout_error(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """scout_error event is logged and marked completed — no re-raise, no crash."""
        error_evt = _make_event("evt-err", "scout_error",
                                {"source": "reed", "error": "HTTP 429", "retry_count": 1})
        mock_bus.poll = AsyncMock(side_effect=[[], [error_evt]])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        result = await supervisor.tick(db_session)

        completed_ids = [c.args[0] for c in mock_bus.mark_completed.call_args_list]
        assert "evt-err" in completed_ids
        mock_tailor.run.assert_not_called()
        assert result["processed"] >= 1

    async def test_tick_handles_application_approved(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """application_approved marks the event completed (DB update runs without error)."""
        approved_evt = _make_event("evt-app", "application_approved",
                                   {"application_id": "non-existent-app"})
        mock_bus.poll = AsyncMock(side_effect=[[], [approved_evt]])

        from app.agents.supervisor import SupervisorAgent
        supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
        supervisor._bus = mock_bus

        result = await supervisor.tick(db_session)

        completed_ids = [c.args[0] for c in mock_bus.mark_completed.call_args_list]
        assert "evt-app" in completed_ids
        assert result["processed"] >= 1

    async def test_tick_uses_fallback_threshold_when_profile_missing(
        self, db_session, mock_scorer, mock_tailor, mock_coach, mock_bus
    ):
        """job_scored uses the 0.75 fallback threshold when profile.yaml cannot be loaded."""
        scored_evt = _make_event("evt-noprof", "job_scored", {"job_id": "j-np", "score": 0.80})
        mock_bus.poll = AsyncMock(side_effect=[[], [scored_evt]])

        with patch("app.agents.supervisor.load_profile", side_effect=FileNotFoundError("no profile")):
            from app.agents.supervisor import SupervisorAgent
            supervisor = SupervisorAgent(scorer=mock_scorer, tailor=mock_tailor, coach=mock_coach)
            supervisor._bus = mock_bus

            result = await supervisor.tick(db_session)

        # 0.80 >= 0.75 fallback → shortlisted
        emitted_type = mock_bus.emit.call_args.kwargs.get("event_type") or mock_bus.emit.call_args.args[0]
        assert emitted_type == "job_shortlisted"
        assert result["processed"] >= 1
