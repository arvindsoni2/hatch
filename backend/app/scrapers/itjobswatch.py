"""ITJobsWatch scraper using BeautifulSoup4 for static HTML parsing."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx
from bs4 import BeautifulSoup, Tag

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.itjobswatch.co.uk"
SEARCH_URL = f"{BASE_URL}/jobs/uk/solutions+architect.do"
CONTRACT_URL = (
    f"{BASE_URL}/contract/uk/"
    "solutions+architect+OR+cloud+architect+OR+enterprise+architect"
    "+OR+data+architect+OR+delivery+manager+OR+technical+lead"
    "+OR+product+owner+OR+agile+delivery.do"
)
MAX_PAGES = 3


class ITJobsWatchScraper(BaseScraper):
    """Scrapes contract IT job listings from ITJobsWatch static HTML pages."""

    name = "itjobswatch"

    async def scrape(self) -> list[JobPostingCreate]:
        """Fetch and parse static HTML from ITJobsWatch contract listings.

        Returns:
            List of JobPostingCreate instances parsed from the HTML.
        """
        jobs: list[JobPostingCreate] = []
        headers = {
            "User-Agent": self.get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }

        async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
            for page_num in range(1, MAX_PAGES + 1):
                url = f"{CONTRACT_URL}?page={page_num}"
                self.logger.info("Scraping ITJobsWatch page %d: %s", page_num, url)

                try:
                    await self.random_delay()
                    response = await client.get(url)
                    response.raise_for_status()

                    page_jobs = self._parse_html(response.text)
                    jobs.extend(page_jobs)
                    self.logger.info("Page %d: found %d jobs", page_num, len(page_jobs))

                    if not page_jobs:
                        break

                except httpx.HTTPStatusError as e:
                    self.logger.error("ITJobsWatch HTTP error %d on page %d", e.response.status_code, page_num)
                    break
                except Exception as e:
                    self.logger.error("ITJobsWatch error on page %d: %s", page_num, e)
                    break

        self.logger.info("ITJobsWatch scrape complete: %d total jobs", len(jobs))
        return jobs

    def _parse_html(self, html: str) -> list[JobPostingCreate]:
        """Parse ITJobsWatch listing HTML into job objects.

        Args:
            html: Raw HTML string from the listing page.

        Returns:
            List of parsed JobPostingCreate objects.
        """
        jobs: list[JobPostingCreate] = []
        soup = BeautifulSoup(html, "lxml")

        # ITJobsWatch tables have job rows — adapt selectors if the site changes
        rows = soup.select("table tr[onclick], .job-list tr, #jobsTable tr")
        if not rows:
            # Fallback: look for any table rows with links
            rows = soup.select("table.table tr")

        for row in rows:
            try:
                job = self._parse_row(row)
                if job:
                    jobs.append(job)
            except Exception as e:
                self.logger.debug("Failed to parse ITJobsWatch row: %s", e)

        return jobs

    def _parse_row(self, row: Tag) -> JobPostingCreate | None:
        """Parse a single HTML table row into a JobPostingCreate.

        Args:
            row: BeautifulSoup Tag for a table row.

        Returns:
            JobPostingCreate if successfully parsed, None otherwise.
        """
        # Title link
        link = row.find("a", href=True)
        if not link or not isinstance(link, Tag):
            return None

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        href = str(link.get("href", ""))
        if not href:
            return None

        if href.startswith("/"):
            url = f"{BASE_URL}{href}"
        elif href.startswith("http"):
            url = href
        else:
            url = f"{BASE_URL}/{href}"

        # Extract all cell texts
        cells = row.find_all("td")
        cell_texts = [c.get_text(strip=True) for c in cells]

        company: str | None = None
        location: str | None = None
        rate_text: str | None = None

        if len(cell_texts) >= 3:
            # Heuristic: columns vary — try to identify by content
            for text in cell_texts[1:]:
                if "£" in text or "/day" in text.lower() or "/hr" in text.lower():
                    rate_text = text
                elif any(city in text.lower() for city in ["london", "manchester", "birmingham", "leeds", "remote", "hybrid"]):
                    location = text
                elif text and not rate_text and not location and text != title:
                    company = text

        rate_min, rate_max = self.parse_rate(rate_text or "")
        full_text = row.get_text(separator=" ")
        combined_text = title + " " + full_text
        ir35_status = self.detect_ir35(combined_text)
        skills = self.extract_skills(combined_text)
        employment_type = self.detect_employment_type(combined_text)
        working_pattern = self.detect_working_pattern(combined_text)
        rate_type = self.detect_rate_type(rate_text or "")

        return JobPostingCreate(
            title=title,
            company=company,
            location=location,
            rate_text=rate_text,
            rate_min=rate_min,
            rate_max=rate_max,
            currency="GBP",
            ir35_status=ir35_status,
            legal_fields={"ir35_status": ir35_status} if ir35_status else {},
            description=full_text[:1000] if full_text else None,
            url=url,
            source=self.name,
            posted_at=datetime.utcnow(),
            skills=skills or None,
            employment_type=employment_type,
            working_pattern=working_pattern,
            rate_type=rate_type,
        )
