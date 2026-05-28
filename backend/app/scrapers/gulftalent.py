"""GulfTalent scraper for UAE job market. TODO: implement."""
from __future__ import annotations

from ..schemas.job import JobPostingCreate
from .base import BaseScraper


class GulfTalentScraper(BaseScraper):
    """GulfTalent scraper for UAE job market. TODO: implement."""

    name = "gulftalent"

    async def scrape(self) -> list[JobPostingCreate]:
        self.logger.info("GulfTalentScraper not yet implemented — returning empty results")
        return []
