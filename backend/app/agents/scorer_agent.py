"""Scorer Sub-Agent — LLM-based job fit scoring driven by profile.yaml.

All scoring weights, target roles, compensation range, skills, and location
preferences are read from the user's profile.yaml at runtime via profile_loader.
The LLM used is determined by profile.yaml llm config via llm_factory.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job_score import JobScore
from ..models.job import JobPosting
from .base_agent import BaseAgent
from .tools.event_bus import EventBus
from .tools.llm_factory import get_triage_model, get_primary_model
from .tools.profile_loader import load_profile

logger = logging.getLogger("jobpilot.agent.scorer")

_BATCH_SIZE = 10


class _TriageResult(BaseModel):
    relevant: bool
    reason: str = ""


class _ScoreResult(BaseModel):
    skill_match: float
    experience_match: float
    rate_match: float
    location_match: float
    overall_score: float
    reasoning: str


class ScorerAgent(BaseAgent):
    """Scores pending job_discovered events against the user's profile.

    Two-tier LLM usage (both models configured in profile.yaml):
    - triage_model: fast pre-filter to skip irrelevant listings cheaply
    - primary_model: detailed 4-dimension scoring for relevant jobs
    """

    name = "scorer"

    def __init__(self) -> None:
        super().__init__()
        self._bus = EventBus.instance()

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Score pending job_discovered events (up to BATCH_SIZE per run)."""
        await self.update_state(db, "running", {"task": "scoring pending jobs"})

        pending = await self._bus.poll(
            db, event_type="job_discovered", status="pending", limit=_BATCH_SIZE
        )

        if not pending:
            self._log.info("No pending job_discovered events.")
            await self.update_state(db, "idle")
            return {"scored": 0, "skipped": 0, "errors": 0}

        profile = load_profile()
        triage_llm = get_triage_model().with_structured_output(_TriageResult)
        primary_llm = get_primary_model().with_structured_output(_ScoreResult)

        scored = skipped = errors = 0

        for event in pending:
            await self._bus.mark_processing(event["id"], db)
            try:
                result = await self._score_job(event, db, profile, triage_llm, primary_llm)
                await self._bus.mark_completed(event["id"], db)
                if result == "skipped":
                    skipped += 1
                else:
                    scored += 1
            except Exception as exc:
                self._log.exception("Scoring error for event %s: %s", event["id"], exc)
                await self._bus.mark_failed(event["id"], str(exc), db)
                errors += 1

        await self.update_state(db, "idle")
        self._log.info(
            "Scoring run: %d scored, %d skipped, %d errors.", scored, skipped, errors
        )
        return {"scored": scored, "skipped": skipped, "errors": errors}

    # ── Per-job scoring ───────────────────────────────────────────────

    async def _score_job(
        self,
        event: dict[str, Any],
        db: AsyncSession,
        profile: Any,
        triage_llm: Any,
        primary_llm: Any,
    ) -> str:
        payload = event["payload"]
        job_id = payload["job_id"]

        result = await db.execute(select(JobPosting).where(JobPosting.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job {job_id} not found in DB")

        # Triage pre-filter (cheap model — rejects obvious non-matches)
        triage_prompt = self._build_triage_prompt(job, profile)
        triage: _TriageResult = await triage_llm.ainvoke(triage_prompt)
        if not triage.relevant:
            self._log.info("Job %s pre-filtered: %s", job_id, triage.reason)
            return "skipped"

        # Detailed scoring (primary model — weights from profile.yaml)
        scoring_prompt = self._build_scoring_prompt(job, profile)
        score: _ScoreResult = await primary_llm.ainvoke(scoring_prompt)

        # Persist score
        existing = await db.execute(select(JobScore).where(JobScore.job_id == job_id))
        row = existing.scalar_one_or_none()
        score_data = score.model_dump()
        if row is None:
            db.add(JobScore(id=str(uuid.uuid4()), job_id=job_id, **score_data))
        else:
            for k, v in score_data.items():
                setattr(row, k, v)
            row.scored_at = datetime.utcnow()

        await db.execute(
            update(JobPosting).where(JobPosting.id == job_id).values(auto_scored=True)
        )
        await db.commit()

        await self.emit_event(
            "job_scored",
            {
                "job_id": job_id,
                "score": score.overall_score,
                "skill_match": score.skill_match,
                "experience_match": score.experience_match,
                "rate_match": score.rate_match,
                "location_match": score.location_match,
                "reasoning": score.reasoning,
            },
            db,
        )
        self._log.info("Job %s scored %.2f — %s", job_id, score.overall_score, score.reasoning[:80])
        return "scored"

    # ── Prompt builders — all data sourced from profile.yaml ─────────

    def _build_triage_prompt(self, job: JobPosting, profile: Any) -> str:
        roles = ", ".join(profile.search.target_roles)
        locations = ", ".join(
            f"{loc.city}, {loc.country}" for loc in profile.search.locations
        )
        return (
            f"You are a job relevance filter for a {profile.candidate.title} "
            f"with {profile.candidate.years_experience} years experience.\n\n"
            f"Target roles: {roles}\n"
            f"Target locations: {locations}\n\n"
            f"Job title: {job.title}\n"
            f"Company: {job.company or 'unknown'}\n"
            f"Location: {job.location or 'unknown'}\n"
            f"Description (first 500 chars): {(job.description or '')[:500]}\n\n"
            "Is this job relevant? Reject: junior roles, unrelated domains, locations "
            "clearly outside target. Pass: anything plausibly matching the profile."
        )

    def _build_scoring_prompt(self, job: JobPosting, profile: Any) -> str:
        weights = profile.scoring.weights
        comp = profile.compensation
        primary_skills = ", ".join(profile.skills.primary)
        secondary_skills = ", ".join(profile.skills.secondary)
        preferred_domains = ", ".join(profile.domains.preferred)
        proof_summaries = "; ".join(p.summary for p in profile.proof_points)
        locations = "; ".join(
            f"{loc.city} ({loc.remote_preference})" for loc in profile.search.locations
        )

        # Inject locale-specific scoring context for location_match dimension
        locale_context = self._get_locale_scoring_context(profile)

        return (
            f"Score this job for a candidate with the following profile:\n\n"
            f"Title: {profile.candidate.title}, {profile.candidate.years_experience} years experience\n"
            f"Primary skills: {primary_skills}\n"
            f"Secondary skills: {secondary_skills}\n"
            f"Preferred domains: {preferred_domains}\n"
            f"Key achievements: {proof_summaries}\n"
            f"Target locations: {locations}\n"
            f"Rate range: {comp.currency} {comp.min_rate}–{comp.max_rate} ({comp.rate_type})\n\n"
            f"Job:\nTitle: {job.title}\nCompany: {job.company or 'N/A'}\n"
            f"Location: {job.location or 'N/A'}\nRate: {job.rate_text or 'N/A'}\n"
            f"IR35/contract status: {job.ir35_status or 'N/A'}\n"
            f"Description:\n{(job.description or '')[:3000]}\n\n"
            f"Score on four dimensions (0.0–1.0):\n"
            f"- skill_match (weight {weights.skill_match}): how well skills match?\n"
            f"- experience_match (weight {weights.experience_match}): seniority/domain alignment?\n"
            f"- rate_match (weight {weights.rate_match}): rate within candidate range?\n"
            f"- location_match (weight {weights.location_match}): location/remote policy match?\n"
            f"{locale_context}\n"
            f"overall_score = weighted sum using the weights above."
        )

    def _get_locale_scoring_context(self, profile: Any) -> str:
        """Return locale-specific instructions for the location_match dimension."""
        try:
            from ..services.locale_service import get_scoring_context
            legal_prefs: dict[str, str] = getattr(profile.compensation, "legal_preferences", {})
            ctx = get_scoring_context(profile.locale, legal_prefs)
            if ctx:
                return f"Additional location_match guidance ({profile.locale} locale):\n{ctx}"
        except Exception:
            pass
        return ""
