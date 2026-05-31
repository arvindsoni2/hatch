"""Abstract base class for all JobPilot agents."""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent_state import AgentState
from .tools.event_bus import EventBus


class BaseAgent(ABC):
    """Abstract base for Scout, Scorer, Tailor, Coach agents.

    Provides:
    - ``emit_event`` — persist + enqueue an event via the shared EventBus
    - ``update_state`` — upsert the agent's row in agent_state
    - ``health_check`` — return current status dict
    - Structured logging with agent-name prefix
    """

    name: str = "base"

    def __init__(self) -> None:
        self._log = logging.getLogger(f"jobpilot.agent.{self.name}")
        self._bus = EventBus.instance()
        self._started_at: datetime | None = None

    # ── Event emission ────────────────────────────────────────────────

    async def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        db: AsyncSession,
    ) -> str:
        """Emit an event via the shared bus and persist it to DB."""
        event_id = await self._bus.emit(
            event_type=event_type,
            source_agent=self.name,
            payload=payload,
            db=db,
        )
        self._log.info("Emitted '%s' (id=%s).", event_type, event_id)
        return event_id

    # ── State management ──────────────────────────────────────────────

    async def update_state(
        self,
        db: AsyncSession,
        status: str,
        current_task: dict[str, Any] | None = None,
    ) -> None:
        """Upsert this agent's row in agent_state."""
        result = await db.execute(
            select(AgentState).where(AgentState.agent_name == self.name)
        )
        row = result.scalar_one_or_none()
        now = datetime.utcnow()

        if row is None:
            row = AgentState(agent_name=self.name)
            db.add(row)

        row.status = status
        row.updated_at = now
        if current_task is not None:
            row.current_task = json.dumps(current_task)
        if status == "running" and self._started_at is None:
            self._started_at = now
        if status in ("idle", "error"):
            row.last_run_at = now
            self._started_at = None

        for attempt in range(3):
            try:
                await db.commit()
                break
            except OperationalError as exc:
                if "database is locked" in str(exc) and attempt < 2:
                    await db.rollback()
                    await asyncio.sleep(0.3 * (attempt + 1))
                else:
                    raise
        self._log.debug("State → %s", status)

    # ── Health check ──────────────────────────────────────────────────

    async def health_check(self, db: AsyncSession) -> dict[str, Any]:
        """Return the current status row as a dict."""
        result = await db.execute(
            select(AgentState).where(AgentState.agent_name == self.name)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"agent_name": self.name, "status": "never_run"}
        return {
            "agent_name": row.agent_name,
            "status": row.status,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "current_task": json.loads(row.current_task) if row.current_task else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Execute the agent's primary task.

        Returns a result dict summarising the run (counts, errors, etc.).
        """
        ...
