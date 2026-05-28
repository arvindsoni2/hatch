"""Jobs.ie scraper for Ireland job market. TODO: implement."""
from __future__ import annotations

from ..schemas.job import JobPostingCreate
from .base import BaseScraper


class JobsIeScraper(BaseScraper):
    """Jobs.ie scraper for Ireland job market. TODO: implement."""

    name = "jobs_ie"

    async def scrape(self) -> list[JobPostingCreate]:
        self.logger.info("JobsIeScraper not yet implemented — returning empty results")
        return []
