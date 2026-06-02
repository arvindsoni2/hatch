"""Tests for LinkedIn scraper full JD fetch logic."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.scrapers.linkedin import LinkedInScraper


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_card_html(title: str, company: str = "Acme", href: str = "https://www.linkedin.com/jobs/view/123", location: str = "London") -> str:
    return f"""
    <li>
      <h3>{title}</h3>
      <h4>{company}</h4>
      <span class="job-search-card__location">{location}</span>
      <a href="{href}">Apply</a>
    </li>
    """


def _make_detail_html(description: str) -> str:
    """Simulate a LinkedIn job detail page."""
    return f"""
    <html>
    <body>
      <div class="show-more-less-html__markup">
        {description}
      </div>
    </body>
    </html>
    """


def _make_detail_html_fallback(description: str) -> str:
    """Simulate a detail page with .description__text selector instead."""
    return f"""
    <html>
    <body>
      <div class="description__text">
        {description}
      </div>
    </body>
    </html>
    """


FULL_DESCRIPTION = (
    "We are looking for an experienced IT Project Manager / Technical Delivery Lead "
    "to manage a complex digital transformation programme. The ideal candidate will have "
    "20+ years of experience in project management, delivery leadership, and stakeholder "
    "engagement. PMP or equivalent certification required. You will be responsible for "
    "managing end-to-end delivery using Agile and Waterfall methodologies. "
    "Experience with cloud migration programmes, governance frameworks, and budget management "
    "of £5M+ is expected. This is an outside IR35 contract based in London, hybrid working. "
    "Rate: £600-£750 per day."
)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestLinkedInScraper:

    def test_parses_full_description_from_job_page(self):
        """_parse_detail_page extracts description from .show-more-less-html__markup."""
        from bs4 import BeautifulSoup
        scraper = LinkedInScraper()

        html = _make_detail_html(FULL_DESCRIPTION)
        soup = BeautifulSoup(html, "lxml")
        desc = scraper._extract_description_from_soup(soup)

        assert desc is not None
        assert len(desc) >= 100
        assert "IT Project Manager" in desc or "project management" in desc.lower()

    def test_card_without_description_triggers_detail_fetch(self):
        """Cards parsed from search results have short/empty description -> needs_enrichment=True."""
        scraper = LinkedInScraper()

        card_html = _make_card_html(
            title="IT Project Manager",
            href="https://www.linkedin.com/jobs/view/12345678",
        )

        from bs4 import BeautifulSoup, Tag
        soup = BeautifulSoup(card_html, "lxml")
        card = soup.find("li")
        assert isinstance(card, Tag)

        job = scraper._parse_card(card)
        # Card-level parse has no detailed description → needs_enrichment should be True
        assert job is not None
        assert job.needs_enrichment is True

    def test_description_min_length_guard(self):
        """Jobs with description < 100 chars should be flagged needs_enrichment=True."""
        scraper = LinkedInScraper()

        short_desc = "Short job post."  # < 100 chars
        from bs4 import BeautifulSoup, Tag
        card_html = f"""
        <li>
          <h3>Delivery Lead</h3>
          <h4>Corp</h4>
          <a href="https://www.linkedin.com/jobs/view/999">Apply</a>
          <p>{short_desc}</p>
        </li>
        """
        soup = BeautifulSoup(card_html, "lxml")
        card = soup.find("li")
        assert isinstance(card, Tag)
        job = scraper._parse_card(card)
        assert job is not None
        # Short description -> needs_enrichment
        assert job.needs_enrichment is True

    def test_long_description_does_not_need_enrichment(self):
        """If card-level text is >= 100 chars, needs_enrichment should be False."""
        long_text = "A" * 200  # 200 chars
        card_html = f"""
        <li>
          <h3>Senior PM</h3>
          <h4>MegaCorp</h4>
          <a href="https://www.linkedin.com/jobs/view/777">Apply</a>
          <time datetime="2026-05-01">1 month ago</time>
          <p>{long_text}</p>
        </li>
        """
        from bs4 import BeautifulSoup, Tag
        soup = BeautifulSoup(card_html, "lxml")
        card = soup.find("li")
        assert isinstance(card, Tag)
        scraper = LinkedInScraper()
        job = scraper._parse_card(card)
        assert job is not None
        assert job.needs_enrichment is False

    def test_description_truncated_to_5000_chars(self):
        """Descriptions longer than 5000 chars should be truncated."""
        scraper = LinkedInScraper()
        very_long = "X" * 10000
        html = _make_detail_html(very_long)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        desc = scraper._extract_description_from_soup(soup)
        assert desc is not None
        assert len(desc) <= 5000

    def test_extract_description_uses_fallback_selector(self):
        """If .show-more-less-html__markup absent, fall back to .description__text."""
        from bs4 import BeautifulSoup
        scraper = LinkedInScraper()
        html = _make_detail_html_fallback(FULL_DESCRIPTION)
        soup = BeautifulSoup(html, "lxml")
        desc = scraper._extract_description_from_soup(soup)
        assert desc is not None
        assert len(desc) >= 50
