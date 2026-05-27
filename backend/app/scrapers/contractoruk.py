"""ContractorUK job board scraper (Playwright — JS-rendered site)."""
from __future__ import annotations

import logging
from datetime import datetime

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.contractoruk.com/jobs"
SEARCH_KEYWORDS = (
    "solutions architect cloud architect enterprise architect data architect"
    " technical architect delivery manager technical lead product owner agile delivery"
)
MAX_PAGES = 3


class ContractorUKScraper(BaseScraper):
    """Scrapes contract IT job listings from ContractorUK using Playwright."""

    name = "contractoruk"

    async def scrape(self) -> list[JobPostingCreate]:
        """Navigate ContractorUK job search and extract listings.

        Returns:
            List of JobPostingCreate instances found across up to MAX_PAGES pages.
        """
        jobs: list[JobPostingCreate] = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error("Playwright not installed — skipping ContractorUK scrape.")
            return jobs

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.get_random_ua(),
                    viewport={"width": 1280, "height": 800},
                    extra_http_headers={
                        "Accept-Language": "en-GB,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                page = await context.new_page()

                for page_num in range(1, MAX_PAGES + 1):
                    url = (
                        f"{BASE_URL}?keywords={SEARCH_KEYWORDS.replace(' ', '+')}"
                        f"&contract=1&page={page_num}"
                    )
                    self.logger.info("Scraping ContractorUK page %d: %s", page_num, url)

                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        await self.random_delay()

                        # Wait for job listings to render
                        try:
                            await page.wait_for_selector(".job-listing, .joblist, article.job", timeout=10000)
                        except Exception:
                            self.logger.warning("No job listing selector found on page %d", page_num)

                        page_jobs = await self._extract_jobs(page)
                        jobs.extend(page_jobs)
                        self.logger.info("Page %d: found %d jobs", page_num, len(page_jobs))

                        if not page_jobs:
                            # No more results
                            break

                    except Exception as e:
                        self.logger.error("Error scraping ContractorUK page %d: %s", page_num, e)
                        break

                await browser.close()

        except Exception as e:
            self.logger.error("ContractorUK scraper failed: %s", e)

        self.logger.info("ContractorUK scrape complete: %d total jobs", len(jobs))
        return jobs

    async def _extract_jobs(self, page: object) -> list[JobPostingCreate]:  # type: ignore[type-arg]
        """Extract job listings from the current Playwright page.

        Args:
            page: Playwright Page object with job listing HTML loaded.

        Returns:
            List of parsed JobPostingCreate objects.
        """
        jobs: list[JobPostingCreate] = []

        try:
            # ContractorUK uses various selectors depending on their current theme
            listings = await page.query_selector_all(  # type: ignore[attr-defined]
                ".job, .job-listing, article.job-post, .joblist-item, [class*='job-item']"
            )

            if not listings:
                # Fallback: try to find any linked headings that look like jobs
                listings = await page.query_selector_all("h2 a, h3 a")  # type: ignore[attr-defined]

            for listing in listings:
                try:
                    job = await self._parse_listing(listing)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    self.logger.debug("Failed to parse listing: %s", e)

        except Exception as e:
            self.logger.error("Error extracting jobs: %s", e)

        return jobs

    async def _parse_listing(self, element: object) -> JobPostingCreate | None:  # type: ignore[type-arg]
        """Parse a single job listing element into a JobPostingCreate.

        Args:
            element: Playwright ElementHandle for one job listing.

        Returns:
            JobPostingCreate if parsing succeeded, None otherwise.
        """
        try:
            # Title & URL
            title_el = await element.query_selector("h2 a, h3 a, a.job-title, .title a")  # type: ignore[attr-defined]
            if not title_el:
                title_el = element  # type: ignore[assignment]

            title_text: str = await title_el.inner_text() if title_el else ""  # type: ignore[attr-defined]
            title_text = title_text.strip()
            if not title_text:
                return None

            href: str | None = await title_el.get_attribute("href")  # type: ignore[attr-defined]
            if not href:
                return None

            if href.startswith("/"):
                href = f"https://www.contractoruk.com{href}"

            # Company
            company_el = await element.query_selector(".company, .recruiter, [class*='company']")  # type: ignore[attr-defined]
            company = (await company_el.inner_text()).strip() if company_el else None  # type: ignore[attr-defined]

            # Location
            location_el = await element.query_selector(".location, [class*='location']")  # type: ignore[attr-defined]
            location = (await location_el.inner_text()).strip() if location_el else None  # type: ignore[attr-defined]

            # Rate
            rate_el = await element.query_selector(".rate, .salary, [class*='rate'], [class*='salary']")  # type: ignore[attr-defined]
            rate_text = (await rate_el.inner_text()).strip() if rate_el else None  # type: ignore[attr-defined]
            rate_min, rate_max = self.parse_rate(rate_text or "")

            # Full text for IR35 detection
            full_text: str = await element.inner_text()  # type: ignore[attr-defined]
            combined_text = title_text + " " + (full_text or "")
            ir35_status = self.detect_ir35(combined_text)
            skills = self.extract_skills(full_text or "")
            employment_type = self.detect_employment_type(combined_text)
            working_pattern = self.detect_working_pattern(combined_text)
            rate_type = self.detect_rate_type(rate_text or "")

            return JobPostingCreate(
                title=title_text,
                company=company,
                location=location,
                rate_text=rate_text,
                rate_min=rate_min,
                rate_max=rate_max,
                currency="GBP",
                ir35_status=ir35_status,
            legal_fields={"ir35_status": ir35_status} if ir35_status else {},
                description=full_text[:2000] if full_text else None,
                url=href,
                source=self.name,
                posted_at=datetime.utcnow(),
                skills=skills or None,
                employment_type=employment_type,
                working_pattern=working_pattern,
                rate_type=rate_type,
            )

        except Exception as e:
            self.logger.debug("Listing parse error: %s", e)
            return None
