"""Supervisor Agent — LangGraph StateGraph orchestrating the full pipeline.

The Supervisor polls the event bus, routes events to sub-agents, enforces the
human-in-the-loop approval checkpoint, and handles errors.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings as app_settings
from ..models.application import Application
from ..models.job_score import JobScore
from .coach_agent import CoachAgent
from .scorer_agent import ScorerAgent
from .tailor_agent import TailorAgent
from .tools.event_bus import EventBus

logger = logging.getLogger("jobpilot.agent.supervisor")

# ── Score threshold for shortlisting ─────────────────────────────────────────
SCORE_THRESHOLD = 0.75


class SupervisorAgent:
    """Routes events between Scout, Scorer, Tailor, and Coach sub-agents.

    Instead of a full LangGraph compile (which requires the package to be
    available), this implements the same state-machine logic directly so it
    can run inside the existing FastAPI lifespan without additional deps at
    import time.  When langgraph *is* available the ``compile_graph`` method
    returns a proper ``CompiledGraph``.
    """

    def __init__(
        self,
        scorer: ScorerAgent | None = None,
        tailor: TailorAgent | None = None,
        coach: CoachAgent | None = None,
    ) -> None:
        self._scorer = scorer or ScorerAgent()
        self._tailor = tailor or TailorAgent()
        self._coach = coach or CoachAgent()
        self._bus = EventBus.instance()

    # ── Single-tick processing ────────────────────────────────────────

    async def tick(self, db: AsyncSession) -> dict[str, Any]:
        """Process one batch of pending events.

        Returns a summary of actions taken this tick.
        """
        events = await self._bus.poll(db, limit=20)
        if not events:
            return {"processed": 0}

        processed = 0
        for event in events:
            try:
                await self._route(event, db)
                processed += 1
            except Exception as exc:
                logger.exception("Supervisor routing error for %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)

        return {"processed": processed}

    # ── Event routing ─────────────────────────────────────────────────

    async def _route(self, event: dict[str, Any], db: AsyncSession) -> None:
        """Dispatch a single event to the appropriate handler."""
        event_type = event["event_type"]
        await self._bus.mark_processing(event["id"], db)

        match event_type:
            case "job_discovered":
                await self._handle_job_discovered(event, db)
            case "job_scored":
                await self._handle_job_scored(event, db)
            case "cv_tailored":
                await self._handle_cv_tailored(event, db)
            case "application_approved":
                await self._handle_application_approved(event, db)
            case "interview_scheduled":
                await self._handle_interview_scheduled(event, db)
            case "scout_error":
                await self._handle_scout_error(event, db)
            case "agent_heartbeat" | "job_shortlisted" | "prep_ready":
                # These are informational / terminal for the supervisor loop
                await self._bus.mark_completed(event["id"], db)
            case _:
                logger.warning("Unknown event type '%s' — logging and discarding.", event_type)
                await self._bus.mark_completed(event["id"], db)

    # ── Handlers ──────────────────────────────────────────────────────

    async def _handle_job_discovered(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        """Trigger scorer for newly discovered jobs."""
        # The scorer agent polls job_discovered events itself; we just
        # acknowledge here and delegate batch scoring via ScorerAgent.run().
        await self._bus.mark_completed(event["id"], db)
        # Fire a scorer pass (will batch internally)
        await self._scorer.run(db)

    async def _handle_job_scored(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        """If score >= threshold, emit job_shortlisted; otherwise park."""
        payload = event["payload"]
        job_id = payload["job_id"]
        score = float(payload.get("score", 0.0))

        if score >= SCORE_THRESHOLD:
            logger.info("Job %s scored %.2f — shortlisting.", job_id, score)
            await self._bus.emit(
                "job_shortlisted",
                source_agent="supervisor",
                payload={"job_id": job_id, "score": score},
                db=db,
            )
            await self._bus.mark_completed(event["id"], db)
            # Trigger tailor immediately
            await self._tailor.run(db)
        else:
            logger.info("Job %s scored %.2f — parking (below %.2f).", job_id, score, SCORE_THRESHOLD)
            await self._park_job(job_id, score, db)
            await self._bus.mark_completed(event["id"], db)

    async def _handle_cv_tailored(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        """Create application record and notify human for approval."""
        payload = event["payload"]
        application_id = payload["application_id"]

        # Application was already created by TailorAgent; emit ready notification
        await self._bus.emit(
            "application_ready",
            source_agent="supervisor",
            payload={
                "application_id": application_id,
                "job_id": payload.get("job_id"),
                "cv_document_id": payload.get("cv_document_id"),
                "cl_document_id": payload.get("cl_document_id"),
            },
            db=db,
        )
        await self._bus.mark_completed(event["id"], db)
        logger.info("Application %s ready for human approval.", application_id)

    async def _handle_application_approved(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        """Mark application as applied when human approves."""
        payload = event["payload"]
        application_id = payload["application_id"]

        await db.execute(
            update(Application)
            .where(Application.id == application_id)
            .values(status="applied", approval_status="approved", applied_date=datetime.utcnow())
        )
        await db.commit()
        await self._bus.mark_completed(event["id"], db)
        logger.info("Application %s marked as applied.", application_id)

    async def _handle_interview_scheduled(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        """Delegate to CoachAgent for interview prep."""
        await self._bus.mark_completed(event["id"], db)
        await self._coach.run(db)

    async def _handle_scout_error(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        """Log scraper errors — could trigger retry logic here in future."""
        payload = event["payload"]
        logger.warning(
            "Scout error from %s: %s (retry #%d)",
            payload.get("source"), payload.get("error"), payload.get("retry_count", 0)
        )
        await self._bus.mark_completed(event["id"], db)

    # ── Helpers ───────────────────────────────────────────────────────

    async def _park_job(self, job_id: str, score: float, db: AsyncSession) -> None:
        """Log that a job was parked below threshold — no action needed."""
        logger.debug("Parked job %s (score=%.2f).", job_id, score)

    # ── Optional LangGraph compile (if available) ─────────────────────

    def compile_graph(self) -> Any:
        """Return a LangGraph CompiledGraph if langgraph is installed.

        This is the *official* LangGraph wiring described in the spec.
        Falls back gracefully if the package is not yet installed.
        """
        try:
            from typing import TypedDict
            from langgraph.graph import StateGraph, END
            from langgraph.checkpoint.sqlite import SqliteSaver

            class SupervisorState(TypedDict):
                pending_events: list[dict]
                current_event: dict | None
                agent_results: dict
                human_approval_needed: bool
                approved_applications: list[str]
                errors: list[dict]

            def route_event(state: SupervisorState) -> str:
                event = state.get("current_event")
                if event is None:
                    return "poll_events"
                match event.get("event_type"):
                    case "job_discovered":
                        return "score_job"
                    case "job_scored":
                        score = event.get("payload", {}).get("score", 0.0)
                        return "tailor_job" if float(score) >= SCORE_THRESHOLD else "park_job"
                    case "cv_tailored":
                        return "request_approval"
                    case "application_approved":
                        return "mark_applied"
                    case "interview_scheduled":
                        return "prepare_interview"
                    case _:
                        return "log_unknown"

            graph = StateGraph(SupervisorState)
            graph.set_entry_point("poll_events")
            graph.add_node("poll_events", lambda s: s)
            graph.add_node("score_job", lambda s: s)
            graph.add_node("tailor_job", lambda s: s)
            graph.add_node("park_job", lambda s: s)
            graph.add_node("request_approval", lambda s: s)
            graph.add_node("mark_applied", lambda s: s)
            graph.add_node("prepare_interview", lambda s: s)
            graph.add_node("log_unknown", lambda s: s)

            graph.add_conditional_edges("poll_events", route_event)
            for node in ["score_job", "tailor_job", "park_job", "request_approval",
                         "mark_applied", "prepare_interview", "log_unknown"]:
                graph.add_edge(node, "poll_events")

            checkpoint_db = getattr(app_settings, "LANGGRAPH_CHECKPOINT_DB",
                                    "sqlite:///data/langgraph_checkpoints.db")
            memory = SqliteSaver.from_conn_string(checkpoint_db)
            return graph.compile(
                checkpointer=memory,
                interrupt_before=["request_approval"],
            )
        except ImportError:
            logger.warning(
                "langgraph not installed — using direct Supervisor.tick() instead."
            )
            return None
