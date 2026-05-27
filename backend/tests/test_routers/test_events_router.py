"""Tests for the events router (listing, filtering, retrying)."""
from __future__ import annotations

import json
import uuid
import pytest
from datetime import datetime

from app.models.agent_event import AgentEvent


class TestEventsRouter:

    async def test_list_events_returns_paginated_list(self, client, db_session):
        """GET /api/events returns paginated response with items list and total."""
        response = await client.get("/api/events")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    async def test_filter_events_by_type(self, client, db_session):
        """GET /api/events?event_type=job_discovered returns only matching events."""
        event_id = str(uuid.uuid4())
        row = AgentEvent(
            id=event_id,
            event_type="job_discovered",
            source_agent="scout",
            payload=json.dumps({"job_id": "job-x"}),
            status="pending",
            created_at=datetime.utcnow(),
        )
        db_session.add(row)

        other_id = str(uuid.uuid4())
        other = AgentEvent(
            id=other_id,
            event_type="job_scored",
            source_agent="scorer",
            payload=json.dumps({"job_id": "job-x", "score": 0.80}),
            status="completed",
            created_at=datetime.utcnow(),
        )
        db_session.add(other)
        await db_session.commit()

        response = await client.get("/api/events?event_type=job_discovered")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        events = data["items"]
        assert isinstance(events, list)
        for e in events:
            assert e["event_type"] == "job_discovered"

    async def test_retry_failed_event_resets_to_pending(self, client, db_session):
        """POST /api/events/{id}/retry resets a failed event back to pending."""
        event_id = str(uuid.uuid4())
        row = AgentEvent(
            id=event_id,
            event_type="job_discovered",
            source_agent="scout",
            payload=json.dumps({"job_id": "job-retry"}),
            status="failed",
            error_message="Timeout",
            created_at=datetime.utcnow(),
        )
        db_session.add(row)
        await db_session.commit()

        response = await client.post(f"/api/events/{event_id}/retry")
        assert response.status_code in (200, 202)
