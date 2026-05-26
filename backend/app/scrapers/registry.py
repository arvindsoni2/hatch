"""Scraper registry — maps scraper IDs to classes and provides locale-aware lookups.

All scraper classes that should be discoverable must be registered in SCRAPER_REGISTRY.
The locale packs (locales/*.yaml) reference scrapers by the string keys used here.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .adzuna import AdzunaScraper
from .base import BaseScraper
from .contractoruk import ContractorUKScraper
from .cwjobs import CWJobsScraper
from .indeed_india import IndeedIndiaScraper
from .itjobswatch import ITJobsWatchScraper
from .jobserve import JobServeScraper
from .linkedin import LinkedInScraper
from .naukri import NaukriScraper
from .reed import ReedScraper

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Map locale YAML scraper IDs → scraper classes
SCRAPER_REGISTRY: dict[str, type[BaseScraper]] = {
    # UK boards
    "ReedScraper": ReedScraper,
    "CWJobsScraper": CWJobsScraper,
    "ContractorUKScraper": ContractorUKScraper,
    "JobServeScraper": JobServeScraper,
    "AdzunaScraper": AdzunaScraper,
    "ITJobsWatchScraper": ITJobsWatchScraper,
    # Global
    "LinkedInScraper": LinkedInScraper,
    # India boards
    "NaukriScraper": NaukriScraper,
    "IndeedIndiaScraper": IndeedIndiaScraper,
}


def get_scrapers_for_locale(locale_id: str) -> list[BaseScraper]:
    """Return initialised scraper instances for all enabled boards in a locale.

    Boards that reference an unknown scraper class are skipped with a warning.
    """
    from ..services.locale_service import get_job_boards  # local import to avoid circular

    boards = get_job_boards(locale_id, enabled_only=True)
    scrapers: list[BaseScraper] = []
    for board in boards:
        scraper_name: str = board.get("scraper", "")
        cls = SCRAPER_REGISTRY.get(scraper_name)
        if cls is None:
            logger.warning(
                "Locale '%s' references unknown scraper '%s' — skipping board '%s'",
                locale_id,
                scraper_name,
                board.get("id"),
            )
            continue
        scrapers.append(cls())
    return scrapers


def get_all_scrapers() -> list[BaseScraper]:
    """Return one instance of every registered scraper (used for manual / full scrapes)."""
    return [cls() for cls in SCRAPER_REGISTRY.values()]
