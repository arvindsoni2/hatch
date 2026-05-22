"""Agent Orchestrator — lifecycle manager for all agentic components.

Responsibilities:
- Initialise all agents on FastAPI startup
- Start APScheduler cron for Scout (every SCRAPE_INTERVAL_HOURS)
- Start the Supervisor event-polling loop
- Expose methods for manual trigger, pause, resume of individual agents
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..agents.coach_agent import CoachAgent
from ..agents.scout_agent import ScoutAgent
from ..agents.scorer_agent import ScorerAgent
from ..agents.supervisor import SupervisorAgent
from ..agents.tailor_agent import TailorAgent
from ..agents.tools.event_bus import EventBus
from ..config import settings

logger = logging.getLogger("jobpilot.orchestrator")


class AgentOrchestrator:
    """Single entry point for the agentic sub-system.

    Usage in FastAPI lifespan::

        orch = AgentOrchestrator(db_factory=AsyncSessionLocal)
        orch.start()
        ...
        orch.stop()
    """

    def __init__(self, db_factory: Any) -> None:
        self._db_factory = db_factory
        self._started_at: float = 0.0
        self._paused: set[str] = set()

        # Instantiate agents once (shared Claude client would be ideal; kept simple)
        self.scout = ScoutAgent()
        self.scorer = ScorerAgent()
        self.tailor = TailorAgent()
        self.coach = CoachAgent()
        self.supervisor = SupervisorAgent(
            scorer=self.scorer,
            tailor=self.tailor,
            coach=self.coach,
        )

        self._bus = EventBus.instance()
        self._scheduler: AsyncIOScheduler | None = None
        self._supervisor_task: asyncio.Task | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler and supervisor polling loop."""
        self._started_at = time.monotonic()
        self._scheduler = AsyncIOScheduler()

        # Scout cron — every SCRAPE_INTERVAL_HOURS
        self._scheduler.add_job(
            self._run_scout,
            trigger=IntervalTrigger(hours=settings.SCRAPE_INTERVAL_HOURS),
            id="agent_scout",
            name="Scout Agent",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "Agent scheduler started (scout every %dh).",
            settings.SCRAPE_INTERVAL_HOURS,
        )

        # Start supervisor polling loop as background asyncio task
        self._supervisor_task = asyncio.ensure_future(self._supervisor_loop())
        logger.info("Supervisor polling loop started.")

    def stop(self) -> None:
        """Gracefully stop scheduler and supervisor loop."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        if self._supervisor_task and not self._supervisor_task.done():
            self._supervisor_task.cancel()
        logger.info("Agent orchestrator stopped.")

    # ── Manual controls ───────────────────────────────────────────────

    async def trigger(self, agent_name: str) -> dict[str, Any]:
        """Manually trigger a named agent run."""
        if agent_name in self._paused:
            return {"status": "paused", "agent": agent_name}

        async with self._db_factory() as db:
            match agent_name:
                case "scout":
                    return await self.scout.run(db)
                case "scorer":
                    return await self.scorer.run(db)
                case "tailor":
                    return await self.tailor.run(db)
                case "coach":
                    return await self.coach.run(db)
                case "supervisor":
                    return await self.supervisor.tick(db)
                case _:
                    return {"error": f"Unknown agent: {agent_name}"}

    def pause(self, agent_name: str) -> None:
        """Prevent an agent from running on the next scheduled tick."""
        self._paused.add(agent_name)
        logger.info("Agent '%s' paused.", agent_name)

    def resume(self, agent_name: str) -> None:
        """Allow a paused agent to run again."""
        self._paused.discard(agent_name)
        logger.info("Agent '%s' resumed.", agent_name)

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._started_at if self._started_at else 0.0

    # ── Background loops ──────────────────────────────────────────────

    async def _run_scout(self) -> None:
        """APScheduler callback — run Scout then yield to Supervisor."""
        if "scout" in self._paused:
            logger.info("Scout is paused — skipping scheduled run.")
            return
        logger.info("Scheduled Scout run starting...")
        try:
            async with self._db_factory() as db:
                result = await self.scout.run(db)
                logger.info("Scout run complete: %s", result)
        except Exception as exc:
            logger.exception("Scout scheduled run failed: %s", exc)

    async def _supervisor_loop(self) -> None:
        """Continuously poll the event bus and route events."""
        poll_interval = settings.SUPERVISOR_POLL_INTERVAL_SECONDS
        logger.info(
            "Supervisor loop polling every %ds.", poll_interval
        )
        while True:
            try:
                if "supervisor" not in self._paused:
                    async with self._db_factory() as db:
                        result = await self.supervisor.tick(db)
                        if result.get("processed", 0) > 0:
                            logger.info("Supervisor processed %d events.", result["processed"])
            except asyncio.CancelledError:
                logger.info("Supervisor loop cancelled.")
                break
            except Exception as exc:
                logger.exception("Supervisor loop error: %s", exc)

            await asyncio.sleep(poll_interval)
