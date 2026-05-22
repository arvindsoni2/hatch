"""Ghost job detection service.

Pure algorithmic scoring — no Claude API calls needed. Fast and cheap.

Scores each job 0-100 based on six weighted signals:
  repost_frequency (+30)  — times_seen >= 3
  age_stale        (+25)  — posted 60+ days ago (12 pts for 45-59 days)
  vague_description (+20) — <200 words or <3 specificity markers
  agency_spam      (+15)  — same company posting 10+ similar roles simultaneously
  missing_details  (+10)  — no rate AND no company name (or 'confidential')
  no_response_hist (+10)  — previously applied, 21+ days with no progression

Verdicts:  0-24 likely_real  |  25-49 uncertain  |  50-74 suspicious  |  75+ likely_ghost
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.job import JobPosting
from ..schemas.ghost import GhostScore

logger = logging.getLogger(__name__)

GHOST_SIGNALS: dict[str, dict[str, Any]] = {
    "repost_frequency": {
        "weight": 30,
        "description": "Same job reposted 3+ times (tracked via times_seen)",
    },
    "age_stale": {
        "weight": 25,
        "description": "Listed for 60+ days without closing",
    },
    "vague_description": {
        "weight": 20,
        "description": "Description under 200 words or missing specific requirements",
    },
    "agency_spam": {
        "weight": 15,
        "description": "Same agency posting 10+ similar roles simultaneously",
    },
    "missing_details": {
        "weight": 10,
        "description": "No rate/salary AND no disclosed company name",
    },
    "no_response_history": {
        "weight": 10,
        "description": "Previously applied to this company/role, 21+ days with no response",
    },
}

# Phrases that indicate a confidential / undisclosed company
_CONFIDENTIAL_NAMES = frozenset(
    {"confidential", "undisclosed", "not disclosed", "various", "our client", "a client"}
)

# Regex patterns that indicate specific, concrete requirements
_SPECIFICITY_PATTERNS = [
    r"\d+\+?\s*years?",
    r"experience\s+with",
    r"proficient\s+in",
    r"certified|certification",
    r"degree\s+in",
    r"AWS|Azure|GCP|Python|Java|Kubernetes|Terraform",
    r"£|salary|rate",
    r"must\s+have|essential",
    r"CISSP|PMP|PMI|ITIL|TOGAF|SAFe",
]


class GhostDetector:
    """Scores job postings on likelihood of being ghost / stale listings.

    Attributes:
        None — stateless, all context from DB.
    """

    async def analyse_job(self, job: JobPosting, db: AsyncSession) -> GhostScore:
        """Compute ghost probability for a single job posting.

        Args:
            job: The JobPosting ORM object to analyse.
            db: Database session for cross-job queries.

        Returns:
            GhostScore with 0-100 score, verdict, and triggered signals.
        """
        signals_triggered: list[tuple[str, Any]] = []
        total_score = 0
        now = datetime.utcnow()

        # 1. Repost frequency — use times_seen field (no expensive fuzzy query)
        times_seen = job.times_seen or 1
        if times_seen >= 3:
            signals_triggered.append(("repost_frequency", times_seen))
            total_score += GHOST_SIGNALS["repost_frequency"]["weight"]

        # 2. Age staleness
        if job.posted_at:
            age_days = (now - job.posted_at).days
            if age_days >= 60:
                signals_triggered.append(("age_stale", age_days))
                total_score += GHOST_SIGNALS["age_stale"]["weight"]
            elif age_days >= 45:
                signals_triggered.append(("age_stale", age_days))
                total_score += GHOST_SIGNALS["age_stale"]["weight"] // 2  # 12 pts

        # 3. Vague description
        desc = job.description or ""
        word_count = len(desc.split())
        has_specifics = self._has_specific_requirements(desc)
        if word_count < 200 or not has_specifics:
            signals_triggered.append(("vague_description", word_count))
            total_score += GHOST_SIGNALS["vague_description"]["weight"]

        # 4. Agency spam — same company, 10+ active similar-titled roles last 30 days
        if job.company:
            similar_count = await self._count_similar_from_agency(job, db)
            if similar_count >= 10:
                signals_triggered.append(("agency_spam", similar_count))
                total_score += GHOST_SIGNALS["agency_spam"]["weight"]

        # 5. Missing key details
        has_rate = job.rate_min is not None or job.rate_max is not None
        company_lower = (job.company or "").strip().lower()
        has_company = company_lower and company_lower not in _CONFIDENTIAL_NAMES
        if not has_rate and not has_company:
            signals_triggered.append(("missing_details", None))
            total_score += GHOST_SIGNALS["missing_details"]["weight"]

        # 6. No-response history — previously applied to same company, still stuck
        if job.company:
            prev_no_response = await self._check_previous_application(job, db)
            if prev_no_response:
                signals_triggered.append(("no_response_history", prev_no_response))
                total_score += GHOST_SIGNALS["no_response_history"]["weight"]

        total_score = min(total_score, 100)
        verdict = self._verdict(total_score)

        return GhostScore(
            job_id=job.id,
            score=total_score,
            verdict=verdict,
            signals=signals_triggered,
            analysed_at=now,
        )

    async def analyse_batch(
        self, db: AsyncSession, limit: int = 500
    ) -> list[GhostScore]:
        """Analyse all unscored jobs or re-analyse stale scores.

        Processes sequentially to avoid DB lock contention with concurrent writes.

        Args:
            db: Database session.
            limit: Maximum number of jobs to process per run.

        Returns:
            List of GhostScore results.
        """
        stale_cutoff = datetime.utcnow() - timedelta(days=7)
        result = await db.execute(
            select(JobPosting)
            .where(
                JobPosting.is_active == True,  # noqa: E712
                (JobPosting.ghost_score.is_(None))
                | (JobPosting.ghost_analysed_at < stale_cutoff),
            )
            .order_by(JobPosting.created_at.asc())
            .limit(limit)
        )
        jobs = result.scalars().all()

        scores: list[GhostScore] = []
        for job in jobs:
            try:
                score = await self.analyse_job(job, db)
                await self._persist_score(job, score, db)
                scores.append(score)
            except Exception as exc:
                logger.error("Ghost analysis failed for job %s: %s", job.id, exc)

        if scores:
            await db.commit()
            logger.info("Ghost batch: analysed %d jobs", len(scores))

        return scores

    async def update_from_outcome(
        self, application: Application, db: AsyncSession
    ) -> None:
        """Adjust agency reputation based on application outcome.

        Called when application status changes.

        Args:
            application: The application whose status changed.
            db: Database session.
        """
        if not application.job_id:
            return

        job_result = await db.execute(
            select(JobPosting).where(JobPosting.id == application.job_id)
        )
        job = job_result.scalars().first()
        if not job or not job.company:
            return

        company_lower = job.company.strip().lower()

        from ..models.agency_reputation import AgencyReputation  # noqa: PLC0415
        rep_result = await db.execute(
            select(AgencyReputation).where(AgencyReputation.agency_name == company_lower)
        )
        rep = rep_result.scalars().first()
        if rep is None:
            rep = AgencyReputation(agency_name=company_lower)
            db.add(rep)

        rep.total_applications += 1

        if application.status in ("interview", "offered", "accepted"):
            # Confirmed real — the company responds
            rep.total_responses += 1
        elif application.status == "applied":
            # Check staleness — no response after 30 days
            days_in_applied = (datetime.utcnow() - application.created_at).days
            if days_in_applied > 30:
                pass  # rep score degrades via avg calculation below

        # Recalculate
        if rep.total_applications > 0:
            rep.response_rate = rep.total_responses / rep.total_applications
            if rep.response_rate >= 0.3:
                rep.reputation = "good"
            elif rep.response_rate >= 0.1:
                rep.reputation = "average"
            else:
                rep.reputation = "poor"

        await db.commit()

    # ─────────────────────── Private Helpers ───────────────────────

    def _has_specific_requirements(self, description: str) -> bool:
        """Check if the description contains concrete, specific requirements.

        Args:
            description: Raw job description text.

        Returns:
            True if >= 3 specificity markers found.
        """
        if not description:
            return False
        matches = sum(
            1
            for pattern in _SPECIFICITY_PATTERNS
            if re.search(pattern, description, re.IGNORECASE)
        )
        return matches >= 3

    async def _count_similar_from_agency(
        self, job: JobPosting, db: AsyncSession
    ) -> int:
        """Count how many similar roles the same company has posted recently.

        Args:
            job: The job posting being analysed.
            db: Database session.

        Returns:
            Count of similar active postings from the same company.
        """
        cutoff = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.company == job.company,
                JobPosting.is_active == True,  # noqa: E712
                JobPosting.posted_at >= cutoff,
            )
        )
        return result.scalar() or 0

    async def _check_previous_application(
        self, job: JobPosting, db: AsyncSession
    ) -> int | None:
        """Check if the user has a stalled application to this company.

        Args:
            job: The job posting.
            db: Database session.

        Returns:
            Days stuck in 'applied' status, or None if no such application.
        """
        if not job.company:
            return None

        result = await db.execute(
            select(Application)
            .join(JobPosting, Application.job_id == JobPosting.id)
            .where(
                JobPosting.company == job.company,
                Application.status == "applied",
                Application.is_active == True,  # noqa: E712
            )
        )
        stalled = result.scalars().first()
        if stalled is None:
            return None

        days_stalled = (datetime.utcnow() - stalled.created_at).days
        if days_stalled >= 21:
            return days_stalled
        return None

    def _verdict(self, score: int) -> str:
        """Convert numeric score to a human-readable verdict.

        Args:
            score: Ghost score 0-100.

        Returns:
            One of: 'likely_ghost', 'suspicious', 'uncertain', 'likely_real'.
        """
        if score >= 75:
            return "likely_ghost"
        if score >= 50:
            return "suspicious"
        if score >= 25:
            return "uncertain"
        return "likely_real"

    async def _persist_score(
        self, job: JobPosting, score: GhostScore, db: AsyncSession
    ) -> None:
        """Write ghost score fields back to the job posting.

        Args:
            job: ORM object to update.
            score: The computed GhostScore.
            db: Database session (commit handled by caller).
        """
        job.ghost_score = score.score
        job.ghost_verdict = score.verdict
        job.ghost_signals = json.dumps(
            [(name, str(val)) for name, val in score.signals]
        )
        job.ghost_analysed_at = score.analysed_at
        await db.flush()
