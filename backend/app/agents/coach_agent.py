"""Coach Agent — triggered by interview_scheduled events, generates prep materials."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application, InterviewRound
from ..models.cost_tracking import CostTracking
from ..models.job import JobPosting
from ..schemas.coach import CreateSessionRequest
from ..services.coach_service import CoachService
from .base_agent import BaseAgent
from .tools.event_bus import EventBus
from .tools.llm_factory import estimate_cost, estimate_tokens
from .tools.profile_loader import load_profile

logger = logging.getLogger("jobpilot.agent.coach")


class CoachAgent(BaseAgent):
    """Processes interview_scheduled events — researches company, generates Q&A prep.

    LLM usage: Heavy — delegates to existing CoachService.
    User skills and proof points are injected from profile.yaml.
    """

    name = "coach"

    def __init__(self) -> None:
        super().__init__()
        self._coach = CoachService()
        self._bus = EventBus.instance()

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Process pending interview_scheduled events."""
        await self.update_state(db, "running", {"task": "preparing interview sessions"})

        pending = await self._bus.poll(
            db, event_type="interview_scheduled", status="pending"
        )

        if not pending:
            self._log.info("No pending interview_scheduled events.")
            await self.update_state(db, "idle")
            return {"prepared": 0, "errors": 0}

        prepared = 0
        errors = 0

        for event in pending:
            await self._bus.mark_processing(event["id"], db)
            try:
                await self._prepare_interview(event, db)
                await self._bus.mark_completed(event["id"], db)
                prepared += 1
            except Exception as exc:
                self._log.exception("Coach error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
                errors += 1

        await self.update_state(db, "idle")
        self._log.info("Coach run: %d prepared, %d errors.", prepared, errors)
        return {"prepared": prepared, "errors": errors}

    # ── Per-interview prep ────────────────────────────────────────────

    async def _prepare_interview(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        payload = event["payload"]
        application_id = payload["application_id"]
        round_type = payload.get("round_type", "general")

        # Fetch application and job
        app_result = await db.execute(
            select(Application).where(Application.id == application_id)
        )
        application = app_result.scalar_one_or_none()
        if application is None:
            raise ValueError(f"Application {application_id} not found")

        job: JobPosting | None = None
        if application.job_id:
            job_result = await db.execute(
                select(JobPosting).where(JobPosting.id == application.job_id)
            )
            job = job_result.scalar_one_or_none()

        company_name = job.company or "Unknown Company" if job else "Unknown Company"
        role_title = job.title if job else "Contract Role"
        jd_text = job.description if job else None

        self._log.info(
            "Preparing interview for application %s — %s at %s (%s).",
            application_id, role_title, company_name, round_type,
        )

        request = CreateSessionRequest(
            application_id=application_id,
            company_name=company_name,
            role_title=role_title,
            jd_text=jd_text,
        )
        session = await self._coach.create_session(request, db)

        self._log.info(
            "Interview prep ready: session %s, %d questions.",
            session.id, len(session.questions),
        )

        # Track LLM cost: estimate based on context in, Q&A pairs out
        profile = load_profile()
        primary_model = profile.llm.primary_model
        context_text = (jd_text or "") + company_name + role_title
        tok_in = estimate_tokens(context_text)
        tok_out = estimate_tokens(context_text) // 2 + len(session.questions) * 200
        db.add(CostTracking(
            agent_name="coach",
            job_id=application.job_id,
            model=primary_model,
            tokens_in=tok_in,
            tokens_out=tok_out,
            cost_estimate=estimate_cost(primary_model, tok_in, tok_out),
        ))
        await db.commit()

        await self.emit_event(
            "prep_ready",
            {
                "application_id": application_id,
                "session_id": session.id,
                "questions_count": len(session.questions),
            },
            db,
        )
