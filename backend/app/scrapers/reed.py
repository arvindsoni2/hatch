"""Reed.co.uk job board scraper using the Reed Jobs REST API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings
from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

REED_API_BASE = "https://www.reed.co.uk/api/1.0"
SEARCH_KEYWORDS = (
    "solutions architect OR cloud architect OR enterprise architect OR data architect"
    " OR technical architect OR infrastructure architect OR delivery manager"
    " OR technical lead OR product owner OR agile delivery"
)
RESULTS_TO_FETCH = 100


class ReedScraper(BaseScraper):
    """Scrapes contract IT job listings from Reed.co.uk using their REST API."""

    name = "reed"

    async def scrape(self) -> list[JobPostingCreate]:
        """Fetch contract IT jobs from the Reed API.

        Returns:
            List of JobPostingCreate instances, or empty list if no API key configured.
        """
        if not settings.REED_API_KEY:
            self.logger.info("REED_API_KEY not set — skipping Reed scrape.")
            return []

        jobs: list[JobPostingCreate] = []

        async with httpx.AsyncClient(
            auth=(settings.REED_API_KEY, ""),
            timeout=30.0,
            headers={"User-Agent": self.get_random_ua()},
        ) as client:
            try:
                lookback_date = datetime.now(timezone.utc) - timedelta(days=settings.SCRAPE_LOOKBACK_DAYS)
                params = {
                    "keywords": SEARCH_KEYWORDS,
                    "contract": "true",
                    "resultsToTake": RESULTS_TO_FETCH,
                    "resultsToSkip": 0,
                    "dateFrom": lookback_date.strftime("%Y-%m-%d"),
                }
                response = await client.get(f"{REED_API_BASE}/search", params=params)
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", []):
                    try:
                        job = self._parse_result(item)
                        if job:
                            jobs.append(job)
                    except Exception as e:
                        self.logger.debug("Failed to parse Reed result: %s", e)

                self.logger.info("Reed scrape complete: %d jobs found", len(jobs))

            except httpx.HTTPStatusError as e:
                self.logger.error("Reed API HTTP error %d: %s", e.response.status_code, e)
            except Exception as e:
                self.logger.error("Reed scraper error: %s", e)

        return jobs

    def _parse_result(self, item: dict[str, object]) -> JobPostingCreate | None:
        """Parse a single Reed API result dict into a JobPostingCreate.

        Args:
            item: Raw dict from the Reed API response.

        Returns:
            JobPostingCreate if valid, None if URL is missing.
        """
        job_id = item.get("jobId")
        if not job_id:
            return None

        title = str(item.get("jobTitle", "")).strip()
        if not title:
            return None

        url = f"https://www.reed.co.uk/jobs/{job_id}"
        company = str(item.get("employerName", "") or "").strip() or None
        location = str(item.get("locationName", "") or "").strip() or None
        description = str(item.get("jobDescription", "") or "").strip() or None

        # Rate / salary from Reed API
        min_salary = item.get("minimumSalary")
        max_salary = item.get("maximumSalary")
        salary_type = str(item.get("salaryType", "")).lower()

        rate_text: str | None = None
        rate_min: float | None = None
        rate_max: float | None = None

        # Reed's API returns salaryType as text ("Annual", "Daily", etc.) but
        # inconsistently labels contract day rates as "Annual". Use a numeric
        # heuristic: any rate < £2000 is unambiguously a day rate for UK IT
        # contracts — no architect earns £500/year.
        _DAY_RATE_THRESHOLD = 2_000

        if min_salary and max_salary:
            rate_min = float(min_salary)
            rate_max = float(max_salary)
            is_day = (
                "day" in salary_type.lower()
                or "daily" in salary_type.lower()
                or salary_type == "2"
                or rate_min < _DAY_RATE_THRESHOLD
            )
            if is_day:
                rate_text = f"£{rate_min:.0f}-£{rate_max:.0f}/day"
            else:
                rate_text = f"£{rate_min:.0f}-£{rate_max:.0f}/year"
        elif min_salary:
            rate_min = rate_max = float(min_salary)
            is_day = (
                "day" in salary_type.lower()
                or rate_min < _DAY_RATE_THRESHOLD
            )
            rate_text = f"£{rate_min:.0f}/day" if is_day else f"£{rate_min:.0f}"

        # Posted date
        posted_at: datetime | None = None
        date_str = item.get("date")
        if date_str:
            try:
                posted_at = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            except ValueError:
                pass

        combined_text = f"{title} {description or ''}"
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
            description=description,
            url=url,
            source=self.name,
            posted_at=posted_at,
            skills=skills or None,
            employment_type=employment_type,
            working_pattern=working_pattern,
            rate_type=rate_type,
        )
