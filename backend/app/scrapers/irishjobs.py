"""IrishJobs.ie scraper for Ireland job market. TODO: implement."""
from __future__ import annotations

from ..schemas.job import JobPostingCreate
from .base import BaseScraper


class IrishJobsScraper(BaseScraper):
    """IrishJobs.ie scraper for Ireland job market. TODO: implement."""

    name = "irishjobs"

    async def scrape(self) -> list[JobPostingCreate]:
        self.logger.info("IrishJobsScraper not yet implemented — returning empty results")
        return []
