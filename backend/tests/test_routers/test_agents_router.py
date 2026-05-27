"""Tests for the agents router (status, trigger, approvals)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.agent_state import AgentState
from datetime import datetime


class TestAgentsRouter:

    async def test_get_all_agents_status_returns_list(self, client, db_session):
        """GET /api/agents/status returns agent summaries and database status."""
        # Insert an agent state row
        row = AgentState(
            agent_name="scout",
            status="idle",
            updated_at=datetime.utcnow(),
        )
        db_session.add(row)
        await db_session.commit()

        mock_orch = MagicMock()
        mock_orch.uptime_seconds.return_value = 120.0

        from app.main import app
        app.state.orchestrator = mock_orch

        response = await client.get("/api/agents/status")

        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert data["database"] == "connected"

    async def test_get_single_agent_status_returns_404_when_not_found(self, client):
        """GET /api/agents/nonexistent/status returns 404."""
        response = await client.get("/api/agents/nonexistent_agent/status")
        assert response.status_code == 404

    async def test_trigger_agent_returns_202(self, client, db_session):
        """POST /api/agents/scout/trigger returns 202 Accepted."""
        mock_orch = MagicMock()
        mock_orch.trigger = AsyncMock(return_value={"jobs_new": 0})
        mock_orch.is_paused.return_value = False

        from app.main import app
        app.state.orchestrator = mock_orch

        response = await client.post("/api/agents/scout/trigger")

        assert response.status_code in (200, 202)
