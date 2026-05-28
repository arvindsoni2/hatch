"""Bayt.com scraper for UAE job market. TODO: implement."""
from __future__ import annotations

from ..schemas.job import JobPostingCreate
from .base import BaseScraper


class BaytScraper(BaseScraper):
    """Bayt.com scraper for UAE job market. TODO: implement."""

    name = "bayt"

    async def scrape(self) -> list[JobPostingCreate]:
        self.logger.info("BaytScraper not yet implemented — returning empty results")
        return []
