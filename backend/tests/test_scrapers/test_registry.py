"""Tests for scraper registry — verify all locales have registered scrapers."""
from __future__ import annotations

import asyncio
import pytest


class TestScraperRegistry:
    """Verify scrapers are registered for all target locales."""

    def test_uae_scrapers_registered(self):
        from app.scrapers.registry import get_scrapers_for_locale
        scrapers = get_scrapers_for_locale("ae")
        names = [s.name for s in scrapers]
        assert any("linkedin" in n.lower() for n in names), \
            "LinkedIn scraper must be registered for UAE"

    def test_ireland_scrapers_registered(self):
        from app.scrapers.registry import get_scrapers_for_locale
        scrapers = get_scrapers_for_locale("ie")
        names = [s.name for s in scrapers]
        assert any("linkedin" in n.lower() for n in names), \
            "LinkedIn scraper must be registered for Ireland"

    def test_uk_scrapers_still_registered(self):
        from app.scrapers.registry import get_scrapers_for_locale
        scrapers = get_scrapers_for_locale("uk")
        assert len(scrapers) >= 3, "UK should have at least 3 scrapers"

    def test_stub_scrapers_return_empty_list(self):
        from app.scrapers.bayt import BaytScraper
        scraper = BaytScraper()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(scraper.scrape())
        finally:
            loop.close()
        assert result == [], "Stub scraper should return empty list"
