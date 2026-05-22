"""Pydantic schemas for agent state."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AgentStateRead(BaseModel):
    agent_name: str
    last_run_at: datetime | None = None
    status: str
    current_task: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentStatusSummary(BaseModel):
    """Lightweight status for the dashboard health endpoint."""
    agent_name: str
    status: str
    last_run_at: datetime | None = None


class AllAgentStatus(BaseModel):
    agents: list[AgentStatusSummary]
    database: str = "connected"
    uptime_seconds: float = 0.0
