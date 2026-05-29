"""Database access layer for job postings and scrape logs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job import JobPosting, ScrapeLog
from ..models.job_score import JobScore
from ..schemas.ghost import GhostScore, GhostStats
from ..schemas.job import (
    JobPostingCreate,
    JobPostingRead,
    JobPostingUpdate,
    StatsResponse,
)

logger = logging.getLogger(__name__)


class JobRepository:
    """All database operations for job postings and scrape logs.

    Uses SQLAlchemy async session. Returns Pydantic schemas, never raw ORM models.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ──────────────────────── Job Postings ────────────────────────

    async def create(self, job: JobPostingCreate) -> JobPostingRead:
        """Insert a new job posting into the database.

        Args:
            job: Validated Pydantic schema for the new posting.

        Returns:
            The created job as a JobPostingRead schema.
        """
        db_job = JobPosting(**job.model_dump())
        self._session.add(db_job)
        await self._session.flush()
        await self._session.refresh(db_job)
        return JobPostingRead.model_validate(db_job)

    async def get_by_url(self, url: str) -> JobPostingRead | None:
        """Fetch a job posting by its unique URL.

        Args:
            url: The canonical job posting URL.

        Returns:
            JobPostingRead if found, None otherwise.
        """
        result = await self._session.execute(
            select(JobPosting).where(JobPosting.url == url)
        )
        row = result.scalar_one_or_none()
        return JobPostingRead.model_validate(row) if row else None

    async def get_by_id(self, job_id: str) -> JobPostingRead | None:
        """Fetch a job posting by its primary key.

        Args:
            job_id: UUID string for the job.

        Returns:
            JobPostingRead if found, None otherwise.
        """
        result = await self._session.execute(
            select(JobPosting).where(JobPosting.id == job_id, JobPosting.is_active.is_(True))
        )
        row = result.scalar_one_or_none()
        return JobPostingRead.model_validate(row) if row else None

    async def list_with_filters(
        self,
        skip: int = 0,
        limit: int = 50,
        ir35_status: str | None = None,
        source: str | None = None,
        search: str | None = None,
        min_rate: float | None = None,
        max_rate: float | None = None,
        employment_type: str | None = None,
        working_pattern: str | None = None,
        posted_after: datetime | None = None,
        min_match_score: float | None = None,
        ghost_verdict: str | None = None,
        hide_ghosts: bool = True,
    ) -> tuple[list[JobPostingRead], int]:
        """List active job postings with optional filters and pagination.

        Args:
            skip: Number of records to skip (offset).
            limit: Maximum records to return.
            ir35_status: Filter by 'inside', 'outside', or 'unknown'.
            source: Filter by scraper source name.
            search: Full-text search against title, company, and description.
            min_rate: Minimum daily rate filter.
            max_rate: Maximum daily rate filter.
            employment_type: Filter by employment type ('contract', 'permanent', etc.).
            working_pattern: Filter by working pattern ('remote', 'hybrid', 'onsite').
            posted_after: Only include jobs posted after this datetime.
            min_match_score: Minimum match score (0-100).
            ghost_verdict: Filter to a specific ghost verdict.
            hide_ghosts: When True (default), exclude 'likely_ghost' listings.

        Returns:
            Tuple of (list of JobPostingRead, total count).
        """
        query = select(JobPosting).where(JobPosting.is_active.is_(True))

        if ir35_status:
            query = query.where(JobPosting.ir35_status == ir35_status)
        if source:
            query = query.where(JobPosting.source == source)
        if search:
            search_term = f"%{search}%"
            query = query.where(
                JobPosting.title.ilike(search_term)
                | JobPosting.company.ilike(search_term)
                | JobPosting.description.ilike(search_term)
            )
        if min_rate is not None:
            query = query.where(
                (JobPosting.rate_min >= min_rate) | (JobPosting.rate_max >= min_rate)
            )
        if max_rate is not None:
            query = query.where(
                (JobPosting.rate_min <= max_rate) | (JobPosting.rate_max <= max_rate)
            )
        if employment_type:
            query = query.where(JobPosting.employment_type == employment_type)
        if working_pattern:
            query = query.where(JobPosting.working_pattern == working_pattern)
        if posted_after is not None:
            query = query.where(
                (JobPosting.posted_at >= posted_after) | (JobPosting.scraped_at >= posted_after)
            )
        if min_match_score is not None:
            query = query.where(JobPosting.match_score >= min_match_score)
        if ghost_verdict:
            query = query.where(JobPosting.ghost_verdict == ghost_verdict)
        elif hide_ghosts:
            query = query.where(
                (JobPosting.ghost_verdict != "likely_ghost") | JobPosting.ghost_verdict.is_(None)
            )

        # Count total
        count_result = await self._session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        # Order by match_score when filtering by score, else by scraped_at
        if min_match_score is not None:
            query = query.order_by(JobPosting.match_score.desc().nullslast(), JobPosting.scraped_at.desc())
        else:
            query = query.order_by(JobPosting.scraped_at.desc())

        query = query.offset(skip).limit(limit)
        result = await self._session.execute(query)
        rows = result.scalars().all()

        # Bulk-fetch per-dimension scores for these jobs in one query
        score_map: dict[str, JobScore] = {}
        if rows:
            job_ids = [r.id for r in rows]
            score_res = await self._session.execute(
                select(JobScore).where(JobScore.job_id.in_(job_ids))
            )
            score_map = {s.job_id: s for s in score_res.scalars().all()}

        items: list[JobPostingRead] = []
        for r in rows:
            posting = JobPostingRead.model_validate(r)
            if r.id in score_map:
                s = score_map[r.id]
                posting = posting.model_copy(
                    update={
                        "skill_match": s.skill_match,
                        "experience_match": s.experience_match,
                        "rate_match": s.rate_match,
                        "location_match": s.location_match,
                        "scoring_method": s.scoring_method,
                        "score_reasoning": s.reasoning,
                        "keyword_matches": s.keyword_matches or [],
                        "keyword_misses": s.keyword_misses or [],
                        "fit_reasoning": getattr(s, "fit_reasoning", None),
                        "score_strengths": getattr(s, "strengths", None),
                        "score_gaps": getattr(s, "score_gaps", None),
                    }
                )
            items.append(posting)
        return items, total

    async def get_unclassified(self, limit: int = 100) -> list[JobPosting]:
        """Fetch jobs where match_score IS NULL for the classifier to process.

        Args:
            limit: Maximum number of jobs to return.

        Returns:
            List of raw JobPosting ORM objects.
        """
        result = await self._session.execute(
            select(JobPosting)
            .where(JobPosting.match_score.is_(None))
            .where(JobPosting.is_active.is_(True))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_unscored_ghost(self, limit: int = 500) -> list[JobPosting]:
        """Fetch jobs with no ghost score for the detector to process.

        Args:
            limit: Maximum number of jobs to return.

        Returns:
            List of raw JobPosting ORM objects.
        """
        result = await self._session.execute(
            select(JobPosting)
            .where(JobPosting.ghost_score.is_(None), JobPosting.is_active.is_(True))
            .order_by(JobPosting.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_ghost_score(self, job_id: str, score: GhostScore) -> None:
        """Persist ghost analysis results back to a job posting.

        Args:
            job_id: UUID of the job posting to update.
            score: The computed GhostScore from GhostDetector.
        """
        import json

        await self._session.execute(
            update(JobPosting)
            .where(JobPosting.id == job_id)
            .values(
                ghost_score=score.score,
                ghost_verdict=score.verdict,
                ghost_signals=json.dumps([(name, str(val)) for name, val in score.signals]),
                ghost_analysed_at=score.analysed_at,
                updated_at=datetime.utcnow(),
            )
        )

    async def get_ghost_stats(self) -> GhostStats:
        """Return aggregate ghost verdict counts for the dashboard.

        Returns:
            GhostStats with counts per verdict and pending total.
        """
        verdict_result = await self._session.execute(
            select(JobPosting.ghost_verdict, func.count(JobPosting.id))
            .where(JobPosting.is_active.is_(True), JobPosting.ghost_verdict.is_not(None))
            .group_by(JobPosting.ghost_verdict)
        )
        counts: dict[str, int] = {row[0]: row[1] for row in verdict_result.all()}

        pending_result = await self._session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.is_active.is_(True), JobPosting.ghost_score.is_(None)
            )
        )
        total_pending = pending_result.scalar_one() or 0
        total_analysed = sum(counts.values())

        return GhostStats(
            likely_real=counts.get("likely_real", 0),
            uncertain=counts.get("uncertain", 0),
            suspicious=counts.get("suspicious", 0),
            likely_ghost=counts.get("likely_ghost", 0),
            total_analysed=total_analysed,
            total_pending=total_pending,
        )

    async def get_flagged_jobs(
        self, min_score: int = 50, limit: int = 50
    ) -> list[JobPostingRead]:
        """Fetch ghost-flagged jobs sorted by score descending.

        Args:
            min_score: Minimum ghost score threshold (default 50 = suspicious+).
            limit: Maximum jobs to return.

        Returns:
            List of JobPostingRead sorted by ghost_score descending.
        """
        result = await self._session.execute(
            select(JobPosting)
            .where(
                JobPosting.is_active.is_(True),
                JobPosting.ghost_score >= min_score,
            )
            .order_by(JobPosting.ghost_score.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [JobPostingRead.model_validate(r) for r in rows]

    async def get_filter_counts(self) -> dict[str, dict[str, int]]:
        """Return counts grouped by filter dimensions for the frontend filter UI.

        Returns:
            Dict with keys 'employment_type', 'working_pattern', 'ir35_status',
            each mapping field values to job counts.
        """
        counts: dict[str, dict[str, int]] = {}

        for field, column in [
            ("employment_type", JobPosting.employment_type),
            ("working_pattern", JobPosting.working_pattern),
            ("ir35_status", JobPosting.ir35_status),
        ]:
            result = await self._session.execute(
                select(column, func.count(JobPosting.id))
                .where(JobPosting.is_active.is_(True))
                .group_by(column)
            )
            counts[field] = {(row[0] or "unknown"): row[1] for row in result.all()}

        return counts

    async def update(self, job_id: str, data: JobPostingUpdate) -> JobPostingRead | None:
        """Partially update a job posting.

        Args:
            job_id: UUID of the job to update.
            data: Fields to update (only non-None values applied).

        Returns:
            Updated JobPostingRead, or None if not found.
        """
        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            return await self.get_by_id(job_id)

        update_data["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(JobPosting).where(JobPosting.id == job_id).values(**update_data)
        )
        return await self.get_by_id(job_id)

    async def soft_delete(self, job_id: str) -> bool:
        """Mark a job posting as inactive (soft delete).

        Args:
            job_id: UUID of the job to deactivate.

        Returns:
            True if the job was found and deactivated, False otherwise.
        """
        result = await self._session.execute(
            update(JobPosting)
            .where(JobPosting.id == job_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        return result.rowcount > 0

    async def get_stats(self) -> StatsResponse:
        """Compute aggregate statistics for the jobs dashboard.

        Returns:
            StatsResponse with totals, breakdowns by source and IR35 status.
        """
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)

        # Total active jobs
        total_result = await self._session.execute(
            select(func.count(JobPosting.id)).where(JobPosting.is_active.is_(True))
        )
        total_jobs = total_result.scalar_one() or 0

        # By source
        source_result = await self._session.execute(
            select(JobPosting.source, func.count(JobPosting.id))
            .where(JobPosting.is_active.is_(True))
            .group_by(JobPosting.source)
        )
        by_source: dict[str, int] = {row[0]: row[1] for row in source_result.all()}

        # By IR35 status
        ir35_result = await self._session.execute(
            select(JobPosting.ir35_status, func.count(JobPosting.id))
            .where(JobPosting.is_active.is_(True))
            .group_by(JobPosting.ir35_status)
        )
        by_ir35: dict[str, int] = {(row[0] or "unknown"): row[1] for row in ir35_result.all()}

        # New today
        today_result = await self._session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.is_active.is_(True),
                JobPosting.scraped_at >= today_start,
            )
        )
        new_today = today_result.scalar_one() or 0

        # New this week
        week_result = await self._session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.is_active.is_(True),
                JobPosting.scraped_at >= week_start,
            )
        )
        new_this_week = week_result.scalar_one() or 0

        return StatsResponse(
            total_jobs=total_jobs,
            by_source=by_source,
            by_ir35=by_ir35,
            new_today=new_today,
            new_this_week=new_this_week,
        )

    async def bulk_upsert(self, jobs: list[JobPostingCreate]) -> tuple[int, int]:
        """Insert new jobs, skipping any whose URL already exists.

        Args:
            jobs: List of job postings to potentially insert.

        Returns:
            Tuple of (total_found, total_new).
        """
        found = len(jobs)
        new_count = 0
        for job in jobs:
            existing = await self.get_by_url(job.url)
            if not existing:
                await self.create(job)
                new_count += 1
        return found, new_count

    # ──────────────────────── Scrape Logs ────────────────────────

    async def create_scrape_log(self, source: str, started_at: datetime) -> int:
        """Create a new scrape log entry and return its ID.

        Args:
            source: Name of the scraper (e.g. 'reed').
            started_at: UTC datetime when the scrape started.

        Returns:
            Integer ID of the newly created log record.
        """
        log = ScrapeLog(source=source, started_at=started_at)
        self._session.add(log)
        await self._session.flush()
        await self._session.refresh(log)
        return log.id  # type: ignore[return-value]

    async def update_scrape_log(
        self,
        log_id: int,
        finished_at: datetime,
        jobs_found: int,
        jobs_new: int,
        errors: int,
        error_details: str | None = None,
    ) -> None:
        """Update an existing scrape log with run results.

        Args:
            log_id: ID of the log record to update.
            finished_at: UTC datetime when the scrape completed.
            jobs_found: Total jobs returned by the scraper.
            jobs_new: Jobs that were new (not duplicates).
            errors: Number of errors encountered.
            error_details: Optional text description of errors.
        """
        await self._session.execute(
            update(ScrapeLog)
            .where(ScrapeLog.id == log_id)
            .values(
                finished_at=finished_at,
                jobs_found=jobs_found,
                jobs_new=jobs_new,
                errors=errors,
                error_details=error_details,
            )
        )

    async def get_recent_jobs_for_dedup(self, limit: int = 500) -> list[JobPostingRead]:
        """Fetch recent active jobs for fuzzy deduplication comparison.

        Args:
            limit: Maximum number of recent jobs to load.

        Returns:
            List of JobPostingRead instances ordered by scraped_at descending.
        """
        result = await self._session.execute(
            select(JobPosting)
            .where(JobPosting.is_active.is_(True))
            .order_by(JobPosting.scraped_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [JobPostingRead.model_validate(r) for r in rows]
