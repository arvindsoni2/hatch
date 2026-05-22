"""LinkedIn job scraper using publicly available RSS feeds."""
from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

import httpx

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

# LinkedIn's public RSS feed for job search (limited but publicly accessible)
LINKEDIN_RSS_TEMPLATE = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    "?keywords={keywords}&location=United+Kingdom&f_JT=C&start=0"
)

# Alternative: RSS feed for contract jobs
LINKEDIN_RSS_URL = (
    "https://www.linkedin.com/jobs/search/?f_JT=C"
    "&keywords=solutions+architect+OR+cloud+architect+OR+enterprise+architect"
    "+OR+data+architect+OR+delivery+manager+OR+technical+lead"
    "+OR+product+owner+OR+agile+delivery"
    "&location=United+Kingdom"
)


class LinkedInScraper(BaseScraper):
    """Scrapes LinkedIn public job listings via available RSS/API endpoints.

    Note: LinkedIn heavily restricts scraping. This scraper uses only
    publicly accessible endpoints. Expect limited results.
    """

    name = "linkedin"

    async def scrape(self) -> list[JobPostingCreate]:
        """Attempt to fetch LinkedIn contract jobs via the public guest API.

        Returns:
            List of JobPostingCreate instances. Returns empty list if
            LinkedIn blocks access (expected in many environments).
        """
        jobs: list[JobPostingCreate] = []

        if not BS4_AVAILABLE:
            self.logger.warning("BeautifulSoup4 not installed — skipping LinkedIn scrape.")
            return jobs

        headers = {
            "User-Agent": self.get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Referer": "https://www.linkedin.com/",
        }

        keywords = quote(
            "solutions architect OR cloud architect OR enterprise architect"
            " OR data architect OR delivery manager OR technical lead"
            " OR product owner OR agile delivery"
        )
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={keywords}"
            "&location=United+Kingdom"
            "&f_JT=C"  # Contract type
            "&start=0"
        )

        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            try:
                self.logger.info("Fetching LinkedIn guest API: %s", url)
                await self.random_delay()
                response = await client.get(url)

                if response.status_code == 429:
                    self.logger.warning("LinkedIn rate limiting (429) — skipping.")
                    return jobs

                if response.status_code in (401, 403, 999):
                    self.logger.warning("LinkedIn access denied (%d) — limited public access.", response.status_code)
                    return jobs

                response.raise_for_status()
                jobs = self._parse_html(response.text)
                self.logger.info("LinkedIn scrape complete: %d jobs", len(jobs))

            except httpx.HTTPStatusError as e:
                self.logger.warning("LinkedIn HTTP error %d — access restricted.", e.response.status_code)
            except Exception as e:
                self.logger.error("LinkedIn scraper error: %s", e)

        return jobs

    def _parse_html(self, html: str) -> list[JobPostingCreate]:
        """Parse LinkedIn guest API HTML response into job objects.

        Args:
            html: Raw HTML from the LinkedIn guest jobs API.

        Returns:
            List of parsed JobPostingCreate objects.
        """
        jobs: list[JobPostingCreate] = []
        soup = BeautifulSoup(html, "lxml")

        listings = soup.select("li, .job-search-card, .base-card")

        for listing in listings:
            try:
                job = self._parse_card(listing)
                if job:
                    jobs.append(job)
            except Exception as e:
                self.logger.debug("LinkedIn card parse error: %s", e)

        return jobs

    def _parse_card(self, card: object) -> JobPostingCreate | None:
        """Parse a single LinkedIn job card.

        Args:
            card: BeautifulSoup Tag for one job card.

        Returns:
            JobPostingCreate if parsing succeeded, None otherwise.
        """
        from bs4 import Tag

        if not isinstance(card, Tag):
            return None

        title_el = card.find("h3") or card.find("a", class_=lambda c: c and "title" in c.lower() if c else False)
        if not title_el or not isinstance(title_el, Tag):
            return None

        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        link_el = card.find("a", href=True)
        if not link_el or not isinstance(link_el, Tag):
            return None

        href = str(link_el.get("href", ""))
        if not href or "linkedin.com" not in href and not href.startswith("/"):
            return None

        if href.startswith("/"):
            href = f"https://www.linkedin.com{href}"

        # Strip tracking params
        if "?" in href:
            href = href.split("?")[0]

        company_el = card.find("h4") or card.find(class_=lambda c: c and "company" in c.lower() if c else False)
        company = company_el.get_text(strip=True) if company_el and isinstance(company_el, Tag) else None

        location_el = card.find(class_=lambda c: c and "location" in c.lower() if c else False)
        location = location_el.get_text(strip=True) if location_el and isinstance(location_el, Tag) else None

        full_text = card.get_text(separator=" ")
        combined_text = title + " " + full_text
        ir35_status = self.detect_ir35(combined_text)
        skills = self.extract_skills(combined_text)
        employment_type = self.detect_employment_type(combined_text)
        working_pattern = self.detect_working_pattern(combined_text)
        rate_type = self.detect_rate_type("")

        return JobPostingCreate(
            title=title,
            company=company,
            location=location,
            rate_text=None,
            rate_min=None,
            rate_max=None,
            currency="GBP",
            ir35_status=ir35_status,
            description=full_text[:1000] if full_text else None,
            url=href,
            source=self.name,
            posted_at=datetime.utcnow(),
            skills=skills or None,
            employment_type=employment_type,
            working_pattern=working_pattern,
            rate_type=rate_type,
        )
