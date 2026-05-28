"""NaukriGulf scraper for UAE job market. TODO: implement."""
from __future__ import annotations

from ..schemas.job import JobPostingCreate
from .base import BaseScraper


class NaukriGulfScraper(BaseScraper):
    """NaukriGulf scraper for UAE job market. TODO: implement."""

    name = "naukrigulf"

    async def scrape(self) -> list[JobPostingCreate]:
        self.logger.info("NaukriGulfScraper not yet implemented — returning empty results")
        return []
