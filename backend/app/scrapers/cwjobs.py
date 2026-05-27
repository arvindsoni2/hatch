"""CWJobs scraper using Playwright for JS-rendered contract listings."""
from __future__ import annotations

import logging
from datetime import datetime

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.cwjobs.co.uk"
SEARCH_KEYWORDS = (
    "solutions architect OR cloud architect OR enterprise architect OR data architect"
    " OR technical architect OR delivery manager OR technical lead"
    " OR product owner OR agile delivery"
)
MAX_PAGES = 3


class CWJobsScraper(BaseScraper):
    """Scrapes contract IT job listings from CWJobs using Playwright."""

    name = "cwjobs"

    async def scrape(self) -> list[JobPostingCreate]:
        """Navigate CWJobs contract search pages and extract listings.

        Returns:
            List of JobPostingCreate instances found across up to MAX_PAGES pages.
        """
        jobs: list[JobPostingCreate] = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error("Playwright not installed — skipping CWJobs scrape.")
            return jobs

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self.get_random_ua(),
                    viewport={"width": 1366, "height": 768},
                    extra_http_headers={
                        "Accept-Language": "en-GB,en;q=0.9",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    },
                )
                page = await context.new_page()

                for page_num in range(1, MAX_PAGES + 1):
                    url = (
                        f"{BASE_URL}/jobs/{SEARCH_KEYWORDS.replace(' ', '-')}"
                        f"?ContractType=contract&page={page_num}"
                    )
                    self.logger.info("Scraping CWJobs page %d: %s", page_num, url)

                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        await self.random_delay()

                        # Handle cookie consent if present
                        try:
                            accept_btn = await page.query_selector("[id*='accept'], [class*='accept-cookies'], button[data-action*='accept']")
                            if accept_btn:
                                await accept_btn.click()
                                await page.wait_for_timeout(1000)
                        except Exception:
                            pass

                        try:
                            await page.wait_for_selector("article[data-job-id], .job, [data-at='job-item']", timeout=10000)
                        except Exception:
                            self.logger.warning("No job listing selector found on CWJobs page %d", page_num)

                        page_jobs = await self._extract_jobs(page)
                        jobs.extend(page_jobs)
                        self.logger.info("CWJobs page %d: found %d jobs", page_num, len(page_jobs))

                        if not page_jobs:
                            break

                    except Exception as e:
                        self.logger.error("Error scraping CWJobs page %d: %s", page_num, e)
                        break

                await browser.close()

        except Exception as e:
            self.logger.error("CWJobs scraper failed: %s", e)

        self.logger.info("CWJobs scrape complete: %d total jobs", len(jobs))
        return jobs

    async def _extract_jobs(self, page: object) -> list[JobPostingCreate]:  # type: ignore[type-arg]
        """Extract job listings from the current CWJobs Playwright page.

        Args:
            page: Playwright Page object at a CWJobs search results URL.

        Returns:
            List of parsed JobPostingCreate objects.
        """
        jobs: list[JobPostingCreate] = []

        try:
            listings = await page.query_selector_all(  # type: ignore[attr-defined]
                "article[data-job-id], div[data-job-id], [data-at='job-item'], .job-item"
            )

            for listing in listings:
                try:
                    job = await self._parse_listing(listing)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    self.logger.debug("Failed to parse CWJobs listing: %s", e)

        except Exception as e:
            self.logger.error("CWJobs extract error: %s", e)

        return jobs

    async def _parse_listing(self, element: object) -> JobPostingCreate | None:  # type: ignore[type-arg]
        """Parse a single CWJobs listing element.

        Args:
            element: Playwright ElementHandle for one job listing.

        Returns:
            JobPostingCreate if parsing succeeded, None otherwise.
        """
        try:
            title_el = await element.query_selector(  # type: ignore[attr-defined]
                "h2 a, h3 a, [data-at='job-item-title'] a, .job-title a"
            )
            if not title_el:
                return None

            title_text: str = (await title_el.inner_text()).strip()  # type: ignore[attr-defined]
            if not title_text:
                return None

            href: str | None = await title_el.get_attribute("href")  # type: ignore[attr-defined]
            if not href:
                return None

            if href.startswith("/"):
                href = f"{BASE_URL}{href}"

            company_el = await element.query_selector("[data-at='job-item-company-name'], .company, .employer")  # type: ignore[attr-defined]
            company = (await company_el.inner_text()).strip() if company_el else None  # type: ignore[attr-defined]

            location_el = await element.query_selector("[data-at='job-item-location'], .location, .job-location")  # type: ignore[attr-defined]
            location = (await location_el.inner_text()).strip() if location_el else None  # type: ignore[attr-defined]

            salary_el = await element.query_selector("[data-at='job-item-salary-info'], .salary, .job-salary")  # type: ignore[attr-defined]
            rate_text = (await salary_el.inner_text()).strip() if salary_el else None  # type: ignore[attr-defined]
            rate_min, rate_max = self.parse_rate(rate_text or "")

            full_text: str = await element.inner_text()  # type: ignore[attr-defined]
            combined_text = title_text + " " + (full_text or "")
            ir35_status = self.detect_ir35(combined_text)
            skills = self.extract_skills(full_text)
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
                description=full_text[:2000],
                url=href,
                source=self.name,
                posted_at=datetime.utcnow(),
                skills=skills or None,
                employment_type=employment_type,
                working_pattern=working_pattern,
                rate_type=rate_type,
            )

        except Exception as e:
            self.logger.debug("CWJobs listing parse error: %s", e)
            return None
