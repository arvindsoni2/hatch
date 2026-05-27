"""JobServe scraper using Playwright for JS-rendered contract listings."""
from __future__ import annotations

import logging
from datetime import datetime

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jobserve.com"
SEARCH_URL = f"{BASE_URL}/gb/en/JobSearch.aspx"
MAX_PAGES = 3


class JobServeScraper(BaseScraper):
    """Scrapes contract IT job listings from JobServe using Playwright."""

    name = "jobserve"

    async def scrape(self) -> list[JobPostingCreate]:
        """Navigate JobServe contract search and extract IT listings.

        Returns:
            List of JobPostingCreate instances found across up to MAX_PAGES pages.
        """
        jobs: list[JobPostingCreate] = []
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error("Playwright not installed — skipping JobServe scrape.")
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

                # JobServe has a search form — navigate and submit
                search_url = (
                    f"{BASE_URL}/gb/en/JobSearch.aspx"
                    "?shws=15&lgcl=0&stype=2&channelid=3"
                    "&skills=solutions+architect+cloud+architect+enterprise+architect"
                    "+data+architect+delivery+manager+technical+lead"
                    "+product+owner+agile+delivery"
                    "&jobtype=2"  # Contract
                )

                self.logger.info("Opening JobServe: %s", search_url)

                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    await self.random_delay()

                    for page_num in range(1, MAX_PAGES + 1):
                        try:
                            await page.wait_for_selector(".jobListingBody, .listing, [class*='job-list']", timeout=10000)
                        except Exception:
                            self.logger.warning("No job listing selector found on JobServe page %d", page_num)

                        page_jobs = await self._extract_jobs(page)
                        jobs.extend(page_jobs)
                        self.logger.info("JobServe page %d: found %d jobs", page_num, len(page_jobs))

                        if not page_jobs:
                            break

                        # Try to navigate to next page
                        try:
                            next_btn = await page.query_selector("a.nextPage, [aria-label='Next page'], .pagination .next")
                            if next_btn:
                                await next_btn.click()
                                await page.wait_for_load_state("domcontentloaded")
                                await self.random_delay()
                            else:
                                break
                        except Exception:
                            break

                except Exception as e:
                    self.logger.error("Error on JobServe search: %s", e)

                await browser.close()

        except Exception as e:
            self.logger.error("JobServe scraper failed: %s", e)

        self.logger.info("JobServe scrape complete: %d total jobs", len(jobs))
        return jobs

    async def _extract_jobs(self, page: object) -> list[JobPostingCreate]:  # type: ignore[type-arg]
        """Extract job listings from the current JobServe Playwright page.

        Args:
            page: Playwright Page object at a JobServe search results URL.

        Returns:
            List of parsed JobPostingCreate objects.
        """
        jobs: list[JobPostingCreate] = []
        try:
            listings = await page.query_selector_all(  # type: ignore[attr-defined]
                ".jobListingBody, li.job, div[id^='job_'], .listing-item"
            )
            for listing in listings:
                try:
                    job = await self._parse_listing(listing)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    self.logger.debug("Failed to parse JobServe listing: %s", e)
        except Exception as e:
            self.logger.error("JobServe extract error: %s", e)
        return jobs

    async def _parse_listing(self, element: object) -> JobPostingCreate | None:  # type: ignore[type-arg]
        """Parse a single JobServe listing element.

        Args:
            element: Playwright ElementHandle for one job listing.

        Returns:
            JobPostingCreate if parsing succeeded, None otherwise.
        """
        try:
            title_el = await element.query_selector("h2 a, h3 a, a.jobTitle, .job-title a, a[href*='/job/']")  # type: ignore[attr-defined]
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

            company_el = await element.query_selector(".jobCompany, .company, [class*='company']")  # type: ignore[attr-defined]
            company = (await company_el.inner_text()).strip() if company_el else None  # type: ignore[attr-defined]

            location_el = await element.query_selector(".jobLocation, .location, [class*='location']")  # type: ignore[attr-defined]
            location = (await location_el.inner_text()).strip() if location_el else None  # type: ignore[attr-defined]

            rate_el = await element.query_selector(".jobSalary, .salary, .rate, [class*='salary']")  # type: ignore[attr-defined]
            rate_text = (await rate_el.inner_text()).strip() if rate_el else None  # type: ignore[attr-defined]
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
            self.logger.debug("JobServe listing parse error: %s", e)
            return None
