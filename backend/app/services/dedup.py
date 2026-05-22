"""Fuzzy deduplication engine using rapidfuzz for near-duplicate job detection."""
from __future__ import annotations

import logging

from rapidfuzz import fuzz

from ..repositories.job_repository import JobRepository
from ..schemas.job import JobPostingRead

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 90.0  # Percent — jobs above this are considered duplicates


class DedupService:
    """Detects near-duplicate job postings using fuzzy string matching."""

    def _job_fingerprint(self, title: str, company: str | None) -> str:
        """Build a normalised comparison string for fuzzy matching.

        Args:
            title: Job title string.
            company: Company name (may be None).

        Returns:
            Lowercased, stripped comparison string.
        """
        parts = [title.strip().lower()]
        if company:
            parts.append(company.strip().lower())
        return " | ".join(parts)

    async def is_duplicate(
        self,
        title: str,
        company: str | None,
        repo: JobRepository,
    ) -> bool:
        """Check if a job with a similar title and company already exists.

        Uses rapidfuzz token_sort_ratio for robust title comparison that
        handles word-order differences.

        Args:
            title: Job title to check.
            company: Company name to check.
            repo: JobRepository for fetching recent jobs to compare against.

        Returns:
            True if a sufficiently similar job already exists.
        """
        recent_jobs = await repo.get_recent_jobs_for_dedup(limit=500)
        candidate = self._job_fingerprint(title, company)

        for job in recent_jobs:
            existing = self._job_fingerprint(job.title, job.company)
            score = fuzz.token_sort_ratio(candidate, existing)
            if score >= SIMILARITY_THRESHOLD:
                logger.debug(
                    "Duplicate detected (%.0f%%): '%s' ~ '%s'",
                    score,
                    candidate,
                    existing,
                )
                return True

        return False

    async def find_similar(
        self,
        title: str,
        repo: JobRepository,
        threshold: float = 80.0,
    ) -> list[JobPostingRead]:
        """Find all existing jobs with a similar title.

        Args:
            title: Job title to search for similar postings.
            repo: JobRepository for fetching recent jobs.
            threshold: Minimum similarity percentage (default 80%).

        Returns:
            List of JobPostingRead instances that are similar to the given title.
        """
        recent_jobs = await repo.get_recent_jobs_for_dedup(limit=500)
        title_lower = title.strip().lower()
        similar: list[JobPostingRead] = []

        for job in recent_jobs:
            score = fuzz.token_sort_ratio(title_lower, job.title.strip().lower())
            if score >= threshold:
                similar.append(job)

        similar.sort(key=lambda j: fuzz.token_sort_ratio(title_lower, j.title.lower()), reverse=True)
        return similar
