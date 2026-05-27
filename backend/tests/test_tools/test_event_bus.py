"""Tests for EventBus persistence, polling, and status transitions."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.agents.tools.event_bus import EventBus
from app.models.agent_event import AgentEvent


@pytest.fixture(autouse=True)
def reset_event_bus_singleton():
    """Reset EventBus singleton between tests to prevent cross-test pollution."""
    EventBus._instance = None
    yield
    EventBus._instance = None


class TestEventBus:

    async def test_emit_persists_to_db(self, db_session):
        """emit() writes an AgentEvent row to the DB with status='pending'."""
        bus = EventBus.instance()
        event_id = await bus.emit(
            event_type="job_discovered",
            source_agent="scout",
            payload={"job_id": "job-1", "title": "Test Job"},
            db=db_session,
        )

        result = await db_session.execute(
            select(AgentEvent).where(AgentEvent.id == event_id)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.event_type == "job_discovered"
        assert row.source_agent == "scout"
        assert row.status == "pending"

    async def test_poll_returns_pending_only(self, db_session):
        """After emitting 3 events and marking 1 completed, poll returns the 2 pending ones."""
        bus = EventBus.instance()
        ids = []
        for i in range(3):
            eid = await bus.emit(
                event_type="job_discovered",
                source_agent="scout",
                payload={"job_id": f"job-{i}"},
                db=db_session,
            )
            ids.append(eid)

        await bus.mark_completed(ids[0], db_session)

        pending = await bus.poll(db_session, event_type="job_discovered", status="pending")
        pending_ids = {e["id"] for e in pending}

        assert ids[0] not in pending_ids
        assert ids[1] in pending_ids
        assert ids[2] in pending_ids

    async def test_mark_completed_updates_status(self, db_session):
        """mark_completed() transitions the event from 'pending' to 'completed'."""
        bus = EventBus.instance()
        event_id = await bus.emit(
            event_type="job_scored",
            source_agent="scorer",
            payload={"job_id": "job-x", "score": 0.80},
            db=db_session,
        )

        await bus.mark_completed(event_id, db_session)

        result = await db_session.execute(
            select(AgentEvent).where(AgentEvent.id == event_id)
        )
        row = result.scalar_one_or_none()
        assert row.status == "completed"
        assert row.processed_at is not None

        still_pending = await bus.poll(db_session, event_type="job_scored", status="pending")
        assert not any(e["id"] == event_id for e in still_pending)

    async def test_poll_filters_by_event_type(self, db_session):
        """poll(event_type=...) returns only events of the specified type."""
        bus = EventBus.instance()
        discovery_id = await bus.emit(
            event_type="job_discovered",
            source_agent="scout",
            payload={"job_id": "job-a"},
            db=db_session,
        )
        scored_id = await bus.emit(
            event_type="job_scored",
            source_agent="scorer",
            payload={"job_id": "job-a", "score": 0.85},
            db=db_session,
        )

        discoveries = await bus.poll(db_session, event_type="job_discovered")
        scored_events = await bus.poll(db_session, event_type="job_scored")

        discovery_ids = {e["id"] for e in discoveries}
        scored_ids = {e["id"] for e in scored_events}

        assert discovery_id in discovery_ids
        assert discovery_id not in scored_ids
        assert scored_id in scored_ids
        assert scored_id not in discovery_ids
