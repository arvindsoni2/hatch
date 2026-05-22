"""Business logic layer for job scraping, persistence, and querying."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from ..repositories.job_repository import JobRepository
from ..schemas.job import JobPostingCreate, ScrapeResult
from ..scrapers.scheduler import SCRAPER_REGISTRY, _import_scraper as _load_scraper_class
from .dedup import DedupService

logger = logging.getLogger(__name__)


class JobService:
    """Coordinates scrapers, deduplication, and persistence."""

    def __init__(self, repo: JobRepository) -> None:
        self._repo = repo
        self._dedup = DedupService()

    async def save_jobs(
        self, jobs: list[JobPostingCreate], source: str
    ) -> ScrapeResult:
        """Persist a list of scraped jobs, skipping duplicates.

        Logs the scrape run to the scrape_logs table.

        Args:
            jobs: Jobs returned by a scraper.
            source: Scraper source name for logging.

        Returns:
            ScrapeResult summarising the run.
        """
        started_at = datetime.utcnow()
        start_time = time.monotonic()
        log_id = await self._repo.create_scrape_log(source, started_at)

        jobs_found = len(jobs)
        jobs_new = 0
        errors = 0
        error_msgs: list[str] = []

        for job in jobs:
            try:
                # URL-based dedup first (fast, exact)
                existing = await self._repo.get_by_url(job.url)
                if existing:
                    continue

                # Fuzzy title+company dedup (catches same job posted multiple times)
                is_dupe = await self._dedup.is_duplicate(
                    job.title, job.company, self._repo
                )
                if is_dupe:
                    logger.debug("Fuzzy duplicate skipped: %s @ %s", job.title, job.company)
                    continue

                await self._repo.create(job)
                jobs_new += 1

            except Exception as e:
                errors += 1
                msg = f"Failed to save job '{job.title}': {e}"
                logger.error(msg)
                error_msgs.append(msg)

        duration = time.monotonic() - start_time
        finished_at = datetime.utcnow()

        await self._repo.update_scrape_log(
            log_id=log_id,
            finished_at=finished_at,
            jobs_found=jobs_found,
            jobs_new=jobs_new,
            errors=errors,
            error_details="\n".join(error_msgs) if error_msgs else None,
        )

        logger.info(
            "save_jobs [%s]: found=%d, new=%d, errors=%d (%.1fs)",
            source,
            jobs_found,
            jobs_new,
            errors,
            duration,
        )

        return ScrapeResult(
            source=source,
            jobs_found=jobs_found,
            jobs_new=jobs_new,
            errors=errors,
            duration_seconds=round(duration, 2),
        )

    async def run_scraper(self, source: str) -> ScrapeResult:
        """Instantiate and run a single scraper by name.

        Args:
            source: Key in SCRAPER_REGISTRY (e.g. 'reed').

        Returns:
            ScrapeResult from the run.

        Raises:
            ValueError: If source name is not found in the registry.
        """
        dotted_path = SCRAPER_REGISTRY.get(source)
        if not dotted_path:
            raise ValueError(f"Unknown scraper source: '{source}'. Valid: {list(SCRAPER_REGISTRY)}")

        start_time = time.monotonic()
        jobs: list[JobPostingCreate] = []
        errors = 0

        try:
            scraper_cls = _load_scraper_class(dotted_path)
            scraper = scraper_cls()
            jobs = await scraper.scrape()
        except Exception as e:
            logger.error("Scraper '%s' raised exception: %s", source, e)
            errors += 1
            # Return a failed result without persisting anything
            return ScrapeResult(
                source=source,
                jobs_found=0,
                jobs_new=0,
                errors=errors,
                duration_seconds=round(time.monotonic() - start_time, 2),
            )

        result = await self.save_jobs(jobs, source)
        # Accumulate any errors from the scraper itself
        return ScrapeResult(
            source=result.source,
            jobs_found=result.jobs_found,
            jobs_new=result.jobs_new,
            errors=result.errors + errors,
            duration_seconds=result.duration_seconds,
        )

    async def run_all_scrapers(self) -> list[ScrapeResult]:
        """Run all registered scrapers sequentially and return results.

        Returns:
            List of ScrapeResult, one per scraper.
        """
        results: list[ScrapeResult] = []
        for source in SCRAPER_REGISTRY:
            logger.info("Running scraper: %s", source)
            try:
                result = await self.run_scraper(source)
                results.append(result)
            except Exception as e:
                logger.error("run_all_scrapers: '%s' failed: %s", source, e)
                results.append(
                    ScrapeResult(
                        source=source,
                        jobs_found=0,
                        jobs_new=0,
                        errors=1,
                        duration_seconds=0.0,
                    )
                )
        return results
