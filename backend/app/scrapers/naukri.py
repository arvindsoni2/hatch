"""Naukri.com job scraper using the public Naukri search JSON API."""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

_NAUKRI_API = "https://www.naukri.com/jobapi/v3/search"
_NAUKRI_HEADERS = {
    "appid": "109",
    "systemid": "109",
    "gzip": "true",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "x-requested-with": "XMLHttpRequest",
}
_RESULTS_PER_PAGE = 20
_LAKH_TO_INR = 100_000  # 1 Lakh = 100,000 INR


def _build_keyword(roles: list[str]) -> str:
    """Build Naukri keyword string from target roles."""
    if not roles:
        return "delivery manager programme manager project manager"
    # Use the first 4 roles to keep the query focused
    return " ".join(roles[:4])


def _parse_naukri_salary(salary_str: str | None) -> tuple[float | None, float | None, str | None]:
    """Parse Naukri salary string into (min, max, rate_text).

    Handles formats like '30-40 Lacs PA', '₹25 LPA', '2-3 Lacs',
    '25000-35000/month', 'Not Disclosed'.
    """
    if not salary_str or "not disclosed" in salary_str.lower():
        return None, None, None

    import re

    s = salary_str.strip()
    # LPA / Lacs PA / Lakh PA → annual INR
    lpa_match = re.search(r"([\d.]+)\s*[-–to]\s*([\d.]+)\s*l(?:ac|akh|pa)", s, re.IGNORECASE)
    single_lpa = re.search(r"([\d.]+)\s*(?:l(?:ac|akh|pa)|lpa)", s, re.IGNORECASE)
    if lpa_match:
        lo = float(lpa_match.group(1)) * _LAKH_TO_INR
        hi = float(lpa_match.group(2)) * _LAKH_TO_INR
        return lo, hi, f"₹{lpa_match.group(1)}-{lpa_match.group(2)} LPA"
    if single_lpa:
        val = float(single_lpa.group(1)) * _LAKH_TO_INR
        return val, val, f"₹{single_lpa.group(1)} LPA"

    return None, None, s[:40] if s else None


class NaukriScraper(BaseScraper):
    """Scrapes job listings from Naukri.com using their public search JSON API."""

    name = "naukri"

    async def scrape(self) -> list[JobPostingCreate]:
        """Fetch jobs from Naukri matching the profile's target roles and location.

        Returns:
            List of JobPostingCreate instances.
        """
        try:
            from ..agents.tools.profile_loader import load_profile
            profile = load_profile()
            roles = list(profile.search.target_roles)
            location = profile.search.locations[0].city if profile.search.locations else "India"
            experience = str(profile.candidate.years_experience or 5)
        except Exception:
            roles = []
            location = "India"
            experience = "5"

        keyword = _build_keyword(roles)
        params = {
            "noOfResults": str(_RESULTS_PER_PAGE),
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": keyword,
            "location": location,
            "experience": experience,
            "pageNo": "1",
        }

        jobs: list[JobPostingCreate] = []
        headers = {**_NAUKRI_HEADERS, "User-Agent": self.get_random_ua()}

        async with httpx.AsyncClient(timeout=30.0, headers=headers, follow_redirects=True) as client:
            try:
                await self.random_delay()
                response = await client.get(_NAUKRI_API, params=params)
                response.raise_for_status()
                data = response.json()

                for item in data.get("jobDetails", []):
                    try:
                        job = self._parse_result(item)
                        if job:
                            jobs.append(job)
                    except Exception as exc:
                        self.logger.debug("Failed to parse Naukri result: %s", exc)

                self.logger.info("Naukri scrape complete: %d jobs found", len(jobs))
            except httpx.HTTPStatusError as exc:
                self.logger.error("Naukri API HTTP error %d: %s", exc.response.status_code, exc)
            except Exception as exc:
                self.logger.error("Naukri scraper error: %s", exc)

        return jobs

    def _parse_result(self, item: dict) -> JobPostingCreate | None:
        title = str(item.get("title", "") or "").strip()
        if not title:
            return None

        jd_url = str(item.get("jdURL", "") or "").strip()
        if not jd_url:
            return None
        if not jd_url.startswith("http"):
            jd_url = f"https://www.naukri.com{jd_url}"

        company = str(item.get("companyName", "") or "").strip() or None
        location = str(item.get("location", "") or "").strip() or None
        description = str(item.get("jobDescription", "") or "").strip() or None
        skills_str = str(item.get("tagsAndSkills", "") or "")

        rate_min, rate_max, rate_text = _parse_naukri_salary(item.get("salary"))

        combined = f"{title} {description or ''} {skills_str}"
        skills = self.extract_skills(combined)
        employment_type = self.detect_employment_type(combined)
        working_pattern = self.detect_working_pattern(combined)

        posted_at: datetime | None = None
        post_date_str = str(item.get("postDate", "") or "")
        if "day" in post_date_str.lower() or "hour" in post_date_str.lower():
            posted_at = datetime.utcnow()

        return JobPostingCreate(
            title=title,
            company=company,
            location=location,
            rate_text=rate_text,
            rate_min=rate_min,
            rate_max=rate_max,
            currency="INR",
            ir35_status=None,
            legal_fields={"notice_period": "30_days"},
            description=description,
            url=jd_url,
            source=self.name,
            posted_at=posted_at,
            skills=skills or None,
            employment_type=employment_type,
            working_pattern=working_pattern,
            rate_type="annual",
        )
