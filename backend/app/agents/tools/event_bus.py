"""In-process async event bus using asyncio.Queue.

Events are persisted to the agent_events table on emit and
status-updated as they are processed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.agent_event import AgentEvent

logger = logging.getLogger("jobpilot.event_bus")

# Type alias for async handler callbacks
EventHandler = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    """Singleton in-process event bus.

    Usage::

        bus = EventBus.instance()
        bus.subscribe("job_discovered", my_handler)
        await bus.emit("job_discovered", source_agent="scout", payload={...}, db=session)
    """

    _instance: EventBus | None = None

    def __init__(self) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running = False

    @classmethod
    def instance(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Subscription ──────────────────────────────────────────────────

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register an async handler for the given event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler to '%s'.", event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    # ── Emit ──────────────────────────────────────────────────────────

    async def emit(
        self,
        event_type: str,
        source_agent: str,
        payload: dict[str, Any],
        db: AsyncSession,
    ) -> str:
        """Persist event to DB and enqueue for dispatch.

        Returns the new event id.
        """
        event_id = str(uuid.uuid4())
        record = AgentEvent(
            id=event_id,
            event_type=event_type,
            source_agent=source_agent,
            payload=json.dumps(payload),
            status="pending",
        )
        db.add(record)
        await db.commit()

        envelope = {
            "id": event_id,
            "event_type": event_type,
            "source_agent": source_agent,
            "payload": payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        await self._queue.put(envelope)
        logger.info("Event emitted: %s (id=%s)", event_type, event_id)
        return event_id

    # ── Poll (for supervisor) ─────────────────────────────────────────

    async def poll(
        self,
        db: AsyncSession,
        event_type: str | None = None,
        status: str = "pending",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return up to *limit* persisted events matching filters.

        This is the supervisor's primary intake — it polls the DB rather
        than the in-process queue so it survives restarts.
        """
        stmt = select(AgentEvent).where(AgentEvent.status == status)
        if event_type:
            stmt = stmt.where(AgentEvent.event_type == event_type)
        stmt = stmt.order_by(AgentEvent.created_at).limit(limit)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "event_type": r.event_type,
                "source_agent": r.source_agent,
                "payload": json.loads(r.payload),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ── Status updates ────────────────────────────────────────────────

    async def mark_processing(self, event_id: str, db: AsyncSession) -> None:
        await db.execute(
            update(AgentEvent)
            .where(AgentEvent.id == event_id)
            .values(status="processing")
        )
        await db.commit()

    async def mark_completed(self, event_id: str, db: AsyncSession) -> None:
        await db.execute(
            update(AgentEvent)
            .where(AgentEvent.id == event_id)
            .values(status="completed", processed_at=datetime.utcnow())
        )
        await db.commit()

    async def mark_failed(
        self, event_id: str, error: str, db: AsyncSession
    ) -> None:
        await db.execute(
            update(AgentEvent)
            .where(AgentEvent.id == event_id)
            .values(
                status="failed",
                processed_at=datetime.utcnow(),
                error_message=error,
            )
        )
        await db.commit()

    # ── Dispatcher loop (optional in-process fanout) ──────────────────

    async def start_dispatch_loop(self) -> None:
        """Continuously pull from the in-memory queue and call subscribers."""
        self._running = True
        logger.info("EventBus dispatch loop started.")
        while self._running:
            try:
                envelope = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                event_type = envelope["event_type"]
                handlers = self._handlers.get(event_type, []) + self._handlers.get("*", [])
                for handler in handlers:
                    try:
                        await handler(envelope)
                    except Exception as exc:
                        logger.exception(
                            "Handler error for event '%s': %s", event_type, exc
                        )
                self._queue.task_done()
            except asyncio.TimeoutError:
                pass

    def stop_dispatch_loop(self) -> None:
        self._running = False
