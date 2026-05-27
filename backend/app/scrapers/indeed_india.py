"""Indeed India (in.indeed.com) job scraper using HTML parsing."""
from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote_plus

import httpx

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from ..schemas.job import JobPostingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

_INDEED_IN_BASE = "https://in.indeed.com/jobs"
_RESULTS_LIMIT = 50


def _build_query(roles: list[str]) -> str:
    if not roles:
        return "delivery manager OR programme manager OR technical project manager"
    return " OR ".join(f'"{r}"' if " " in r else r for r in roles[:5])


class IndeedIndiaScraper(BaseScraper):
    """Scrapes job listings from Indeed India via HTML page parsing."""

    name = "indeed_india"

    async def scrape(self) -> list[JobPostingCreate]:
        """Fetch jobs from Indeed India matching the profile's roles and location.

        Returns:
            List of JobPostingCreate instances.
        """
        if not BS4_AVAILABLE:
            self.logger.warning("BeautifulSoup4 not installed — skipping Indeed India scrape.")
            return []

        try:
            from ..agents.tools.profile_loader import load_profile
            profile = load_profile()
            roles = list(profile.search.target_roles)
            location = profile.search.locations[0].city if profile.search.locations else "India"
        except Exception:
            roles = []
            location = "India"

        query = _build_query(roles)
        params = {
            "q": query,
            "l": location,
            "fromage": "14",
            "limit": str(_RESULTS_LIMIT),
            "lang": "en",
        }

        headers = {
            "User-Agent": self.get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
            "Referer": "https://in.indeed.com/",
        }

        jobs: list[JobPostingCreate] = []

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
            follow_redirects=True,
        ) as client:
            try:
                await self.random_delay()
                response = await client.get(_INDEED_IN_BASE, params=params)

                if response.status_code == 403:
                    self.logger.warning("Indeed India returned 403 — access restricted.")
                    return jobs

                response.raise_for_status()
                jobs = self._parse_html(response.text)
                self.logger.info("Indeed India scrape complete: %d jobs", len(jobs))

            except httpx.HTTPStatusError as exc:
                self.logger.error("Indeed India HTTP error %d: %s", exc.response.status_code, exc)
            except Exception as exc:
                self.logger.error("Indeed India scraper error: %s", exc)

        return jobs

    def _parse_html(self, html: str) -> list[JobPostingCreate]:
        soup = BeautifulSoup(html, "lxml")
        jobs: list[JobPostingCreate] = []

        # Indeed uses data-jk as the unique job key
        cards = soup.select("div.job_seen_beacon, div[data-jk], li.css-5lfssm")
        if not cards:
            # Fallback selector
            cards = soup.select("a[data-jk], td.resultContent")

        for card in cards:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as exc:
                self.logger.debug("Indeed India card parse error: %s", exc)

        return jobs

    def _parse_card(self, card) -> JobPostingCreate | None:
        from bs4 import Tag

        if not isinstance(card, Tag):
            return None

        # Title
        title_el = (
            card.find("h2", class_=lambda c: c and "jobTitle" in c if c else False)
            or card.find("a", {"data-jk": True})
            or card.find("h2")
        )
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        # URL — build from data-jk if available
        jk = card.get("data-jk") or (title_el.get("data-jk") if isinstance(title_el, Tag) else None)
        link_el = card.find("a", href=True)
        if jk:
            url = f"https://in.indeed.com/viewjob?jk={jk}"
        elif link_el and isinstance(link_el, Tag):
            href = str(link_el.get("href", ""))
            if href.startswith("/"):
                href = f"https://in.indeed.com{href}"
            url = href
        else:
            return None

        # Company
        company_el = card.find(
            class_=lambda c: c and ("companyName" in c or "company" in c.lower()) if c else False
        )
        company = company_el.get_text(strip=True) if isinstance(company_el, Tag) else None

        # Location
        location_el = card.find(
            class_=lambda c: c and ("companyLocation" in c or "location" in c.lower()) if c else False
        )
        location = location_el.get_text(strip=True) if isinstance(location_el, Tag) else None

        # Salary
        salary_el = card.find(
            class_=lambda c: c and ("salary" in c.lower() or "estimated" in c.lower()) if c else False
        )
        rate_text = salary_el.get_text(strip=True) if isinstance(salary_el, Tag) else None

        full_text = card.get_text(separator=" ")
        combined = f"{title} {full_text}"
        skills = self.extract_skills(combined)
        employment_type = self.detect_employment_type(combined)
        working_pattern = self.detect_working_pattern(combined)

        return JobPostingCreate(
            title=title,
            company=company,
            location=location,
            rate_text=rate_text,
            rate_min=None,
            rate_max=None,
            currency="INR",
            ir35_status=None,
            legal_fields={"notice_period": "30_days"},
            description=full_text[:1000] if full_text else None,
            url=url,
            source=self.name,
            posted_at=datetime.utcnow(),
            skills=skills or None,
            employment_type=employment_type,
            working_pattern=working_pattern,
            rate_type="annual",
        )
