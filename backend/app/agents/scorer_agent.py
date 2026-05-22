"""Scorer Sub-Agent — LLM-based job fit scoring against the master profile."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import load_master_profile
from ..models.agent_event import AgentEvent
from ..models.job_score import JobScore
from ..models.job import JobPosting
from ..services.claude_client import ClaudeClient
from .base_agent import BaseAgent
from .tools.event_bus import EventBus

logger = logging.getLogger("jobpilot.agent.scorer")

_SYSTEM_PROMPT = """\
You are a job fit scorer. Given a candidate profile and a job description,
score the match on four dimensions (0.0–1.0 each):

1. skill_match: How well do the candidate's skills match the requirements?
2. experience_match: Does the seniority and domain experience align?
3. rate_match: Is the offered rate within the candidate's range?
4. location_match: Does the location/remote policy work for the candidate?

Overall score = weighted average:
  skill_match * 0.35 + experience_match * 0.30 +
  rate_match * 0.20 + location_match * 0.15

Respond with JSON only:
{
  "skill_match": 0.85,
  "experience_match": 0.90,
  "rate_match": 0.70,
  "location_match": 1.0,
  "overall_score": 0.84,
  "reasoning": "Brief explanation of scoring decision."
}
"""

_BATCH_SIZE = 10  # Max jobs scored per Claude API call


class ScorerAgent(BaseAgent):
    """Scores pending job_discovered events against the master profile.

    LLM usage: One Claude call per job (batched up to BATCH_SIZE per run).
    """

    name = "scorer"

    def __init__(self, claude: ClaudeClient | None = None) -> None:
        super().__init__()
        self._claude = claude or ClaudeClient()
        self._profile = load_master_profile()
        self._bus = EventBus.instance()

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Score pending job_discovered events.

        Picks up to BATCH_SIZE unprocessed job_discovered events and scores each.
        """
        await self.update_state(db, "running", {"task": "scoring pending jobs"})

        pending = await self._bus.poll(
            db, event_type="job_discovered", status="pending", limit=_BATCH_SIZE
        )

        if not pending:
            self._log.info("No pending job_discovered events.")
            await self.update_state(db, "idle")
            return {"scored": 0, "errors": 0}

        scored = 0
        errors = 0

        for event in pending:
            await self._bus.mark_processing(event["id"], db)
            try:
                await self._score_job(event, db)
                await self._bus.mark_completed(event["id"], db)
                scored += 1
            except Exception as exc:
                self._log.exception("Scoring error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
                errors += 1

        await self.update_state(db, "idle")
        self._log.info("Scoring run: %d scored, %d errors.", scored, errors)
        return {"scored": scored, "errors": errors}

    # ── Per-job scoring ───────────────────────────────────────────────

    async def _score_job(
        self, event: dict[str, Any], db: AsyncSession
    ) -> None:
        payload = event["payload"]
        job_id = payload["job_id"]

        # Fetch full job description from DB
        result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job {job_id} not found in DB")

        user_prompt = self._build_user_prompt(job)
        raw = await self._claude.complete_json(system=_SYSTEM_PROMPT, user=user_prompt)

        score_data = self._parse_score(raw)

        # Upsert job_scores
        existing = await db.execute(
            select(JobScore).where(JobScore.job_id == job_id)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = JobScore(
                id=str(uuid.uuid4()),
                job_id=job_id,
                **score_data,
            )
            db.add(row)
        else:
            for k, v in score_data.items():
                setattr(row, k, v)
            row.scored_at = datetime.utcnow()

        # Mark job as auto_scored
        await db.execute(
            update(JobPosting)
            .where(JobPosting.id == job_id)
            .values(auto_scored=True)
        )
        await db.commit()

        # Emit job_scored event
        await self.emit_event(
            "job_scored",
            {
                "job_id": job_id,
                "score": score_data["overall_score"],
                "skill_match": score_data.get("skill_match"),
                "experience_match": score_data.get("experience_match"),
                "rate_match": score_data.get("rate_match"),
                "location_match": score_data.get("location_match"),
                "reasoning": score_data.get("reasoning"),
            },
            db,
        )
        self._log.info(
            "Job %s scored: %.2f (%s)",
            job_id, score_data["overall_score"], score_data.get("reasoning", "")[:80]
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _build_user_prompt(self, job: JobPosting) -> str:
        profile = self._profile
        candidate = profile.get("candidate", {})
        rate = profile.get("rate", {})
        skills = profile.get("skills", {})
        domains = profile.get("domains", {})
        proof_points = profile.get("proof_points", [])

        primary_skills = ", ".join(skills.get("primary", []))
        secondary_skills = ", ".join(skills.get("secondary", []))
        preferred_domains = ", ".join(domains.get("preferred", []))
        proofs = "; ".join(p["summary"] for p in proof_points)

        return f"""
## Candidate Profile
Name: {candidate.get('name')}
Title: {candidate.get('title')}
Years Experience: {candidate.get('years_experience')}
Location: {candidate.get('location')}
Remote Preference: {candidate.get('remote_preference')}
Primary Skills: {primary_skills}
Secondary Skills: {secondary_skills}
Preferred Domains: {preferred_domains}
Rate Range: £{rate.get('min_daily')}–£{rate.get('max_daily')}/day ({rate.get('ir35_status')} IR35)
Key Achievements: {proofs}

## Job Posting
Title: {job.title}
Company: {job.company or 'Not specified'}
Location: {job.location or 'Not specified'}
Rate: {job.rate_text or 'Not specified'} (min: {job.rate_min}, max: {job.rate_max})
IR35 Status: {job.ir35_status or 'Not specified'}
Description:
{(job.description or '')[:3000]}
""".strip()

    @staticmethod
    def _parse_score(raw: dict[str, Any]) -> dict[str, Any]:
        """Validate and extract score fields from Claude response."""
        return {
            "overall_score": float(raw.get("overall_score", 0.0)),
            "skill_match": float(raw.get("skill_match", 0.0)) if raw.get("skill_match") is not None else None,
            "experience_match": float(raw.get("experience_match", 0.0)) if raw.get("experience_match") is not None else None,
            "rate_match": float(raw.get("rate_match", 0.0)) if raw.get("rate_match") is not None else None,
            "location_match": float(raw.get("location_match", 0.0)) if raw.get("location_match") is not None else None,
            "reasoning": str(raw.get("reasoning", ""))[:2000],
        }
