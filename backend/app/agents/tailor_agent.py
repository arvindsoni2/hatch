"""Tailor Agent — wraps existing CV/CL generation services for auto-tailoring."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.job import JobPosting
from ..services.claude_client import ClaudeClient
from ..services.tailor_service import TailorService
from .base_agent import BaseAgent
from .tools.event_bus import EventBus

logger = logging.getLogger("jobpilot.agent.tailor")

# Only tailor jobs that score above this threshold
SCORE_THRESHOLD = 0.75


class TailorAgent(BaseAgent):
    """Processes job_shortlisted events — generates CV + cover letter.

    LLM usage: Heavy (delegates to existing TailorService).
    """

    name = "tailor"

    def __init__(self, claude: ClaudeClient | None = None) -> None:
        super().__init__()
        self._claude = claude or ClaudeClient()
        self._tailor = TailorService()
        self._bus = EventBus.instance()

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Process pending job_shortlisted events and generate application docs."""
        await self.update_state(db, "running", {"task": "tailoring pending jobs"})

        pending = await self._bus.poll(
            db, event_type="job_shortlisted", status="pending"
        )

        if not pending:
            self._log.info("No pending job_shortlisted events.")
            await self.update_state(db, "idle")
            return {"tailored": 0, "errors": 0}

        tailored = 0
        errors = 0

        for event in pending:
            await self._bus.mark_processing(event["id"], db)
            try:
                await self._tailor_job(event, db)
                await self._bus.mark_completed(event["id"], db)
                tailored += 1
            except Exception as exc:
                self._log.exception("Tailor error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
                errors += 1

        await self.update_state(db, "idle")
        self._log.info("Tailor run: %d tailored, %d errors.", tailored, errors)
        return {"tailored": tailored, "errors": errors}

    # ── Per-job tailoring ─────────────────────────────────────────────

    async def _tailor_job(self, event: dict[str, Any], db: AsyncSession) -> None:
        payload = event["payload"]
        job_id = payload["job_id"]
        score = payload.get("score", 0.0)

        if score < SCORE_THRESHOLD:
            self._log.info("Job %s score %.2f below threshold — skipping.", job_id, score)
            return

        # Fetch job
        result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job {job_id} not found")

        jd_text = job.description or f"{job.title} at {job.company}"

        # Create an Application record (agent-created, pending approval)
        app_id = str(uuid.uuid4())
        application = Application(
            id=app_id,
            job_id=job_id,
            status="ready_to_apply",
            agent_created=True,
            approval_status="pending",
        )
        db.add(application)
        await db.flush()

        # Run tailor pipeline
        bundle = await self._tailor.generate_all(
            application_id=app_id,
            variant="A",
            jd_text=jd_text,
            db=db,
        )

        # Mark job as auto_tailored
        await db.execute(
            update(JobPosting)
            .where(JobPosting.id == job_id)
            .values(auto_tailored=True)
        )
        await db.commit()

        ats_score = bundle.ats_score.overall_score if bundle.ats_score else None
        self._log.info(
            "Tailored job %s → application %s (ATS: %s).",
            job_id, app_id, ats_score,
        )

        await self.emit_event(
            "cv_tailored",
            {
                "job_id": job_id,
                "application_id": app_id,
                "cv_document_id": bundle.cv_document_id,
                "cl_document_id": bundle.cl_document_id,
                "ats_score": ats_score,
            },
            db,
        )
