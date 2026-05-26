"""Adzuna job board scraper using the Adzuna REST API."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings
from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

def _adzuna_country() -> str:
    """Return Adzuna country code from profile locale, falling back to config."""
    try:
        from ..agents.tools.profile_loader import load_profile
        locale = (load_profile().locale or "").lower()
        _LOCALE_TO_ADZUNA = {"in": "in", "uk": "gb", "us": "us", "de": "de", "gb": "gb"}
        return _LOCALE_TO_ADZUNA.get(locale, settings.ADZUNA_COUNTRY)
    except Exception:
        return settings.ADZUNA_COUNTRY


def _adzuna_base_url() -> str:
    return f"https://api.adzuna.com/v1/api/jobs/{_adzuna_country()}/search"


def _adzuna_search_what() -> str:
    try:
        from ..agents.tools.profile_loader import load_profile
        roles = load_profile().search.target_roles
        if roles:
            return " OR ".join(roles[:6])
    except Exception:
        pass
    return (
        "solutions architect OR cloud architect OR enterprise architect OR data architect"
        " OR technical architect OR delivery manager OR technical lead"
        " OR product owner OR agile delivery"
    )
RESULTS_PER_PAGE = 50


class AdzunaScraper(BaseScraper):
    """Scrapes contract IT jobs from Adzuna using their public REST API."""

    name = "adzuna"

    async def scrape(self) -> list[JobPostingCreate]:
        """Fetch contract IT jobs from the Adzuna API.

        Returns:
            List of JobPostingCreate instances, or empty list if API credentials missing.
        """
        if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
            self.logger.info("ADZUNA credentials not set — skipping Adzuna scrape.")
            return []

        jobs: list[JobPostingCreate] = []

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": self.get_random_ua()},
        ) as client:
            try:
                params = {
                    "app_id": settings.ADZUNA_APP_ID,
                    "app_key": settings.ADZUNA_APP_KEY,
                    "results_per_page": RESULTS_PER_PAGE,
                    "what": _adzuna_search_what(),
                    "contract": 1,
                    "content-type": "application/json",
                    "posted_in": settings.SCRAPE_LOOKBACK_DAYS,
                }
                response = await client.get(f"{_adzuna_base_url()}/1", params=params)
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", []):
                    try:
                        job = self._parse_result(item)
                        if job:
                            jobs.append(job)
                    except Exception as e:
                        self.logger.debug("Failed to parse Adzuna result: %s", e)

                self.logger.info("Adzuna scrape complete: %d jobs found", len(jobs))

            except httpx.HTTPStatusError as e:
                self.logger.error("Adzuna API HTTP error %d: %s", e.response.status_code, e)
            except Exception as e:
                self.logger.error("Adzuna scraper error: %s", e)

        return jobs

    def _parse_result(self, item: dict[str, object]) -> JobPostingCreate | None:
        """Parse a single Adzuna API result dict into a JobPostingCreate.

        Args:
            item: Raw dict from the Adzuna API response.

        Returns:
            JobPostingCreate if valid, None if title or URL missing.
        """
        title = str(item.get("title", "") or "").strip()
        url = str(item.get("redirect_url", "") or "").strip()

        if not title or not url:
            return None

        company_data = item.get("company") or {}
        company = str(company_data.get("display_name", "") if isinstance(company_data, dict) else "").strip() or None

        location_data = item.get("location") or {}
        location = str(location_data.get("display_name", "") if isinstance(location_data, dict) else "").strip() or None

        description = str(item.get("description", "") or "").strip() or None

        # Salary/rate
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        rate_text: str | None = None
        rate_min: float | None = None
        rate_max: float | None = None

        if salary_min is not None:
            rate_min = float(salary_min)
        if salary_max is not None:
            rate_max = float(salary_max)
        if rate_min and rate_max:
            rate_text = f"£{rate_min:.0f}-£{rate_max:.0f}"
        elif rate_min:
            rate_text = f"£{rate_min:.0f}"

        # Posted date
        posted_at: datetime | None = None
        created_str = item.get("created")
        if created_str:
            try:
                posted_at = datetime.fromisoformat(str(created_str).replace("Z", "+00:00"))
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
