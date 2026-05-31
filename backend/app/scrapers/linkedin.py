"""LinkedIn job scraper using publicly available RSS feeds."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
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

# Minimum description length to consider a job sufficiently described
_MIN_DESCRIPTION_LENGTH = 100

# Maximum description length to store
_MAX_DESCRIPTION_LENGTH = 5000


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

        try:
            from ..agents.tools.profile_loader import load_profile
            _profile = load_profile()
            _roles = list(_profile.search.target_roles)
            _loc = _profile.search.locations[0].city if _profile.search.locations else None
            _country = _profile.search.locations[0].country if _profile.search.locations else "GB"
            _location_str = _loc or (_country if len(_country) > 2 else "")
            _keywords_raw = " OR ".join(_roles[:6]) if _roles else (
                "solutions architect OR delivery manager OR technical lead OR product owner"
            )
        except Exception:
            _keywords_raw = "solutions architect OR cloud architect OR delivery manager OR technical lead"
            _location_str = ""

        keywords = quote(_keywords_raw)
        location_param = f"&location={quote(_location_str)}" if _location_str else ""
        url = (
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={keywords}"
            f"{location_param}"
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
                self.logger.info("LinkedIn scrape (cards): %d jobs", len(jobs))

                # Phase 2: fetch detail pages for jobs that need enrichment
                enriched_jobs: list[JobPostingCreate] = []
                for job in jobs:
                    if job.needs_enrichment and job.url:
                        enriched = await self._fetch_detail_page(client, job)
                        enriched_jobs.append(enriched)
                        await self.random_delay()
                    else:
                        enriched_jobs.append(job)

                jobs = enriched_jobs
                self.logger.info("LinkedIn scrape complete: %d jobs", len(jobs))

            except httpx.HTTPStatusError as e:
                self.logger.warning("LinkedIn HTTP error %d — access restricted.", e.response.status_code)
            except Exception as e:
                self.logger.error("LinkedIn scraper error: %s", e)

        return jobs

    async def _fetch_detail_page(
        self, client: httpx.AsyncClient, job: JobPostingCreate
    ) -> JobPostingCreate:
        """Fetch and parse the full job detail page, updating description.

        Args:
            client: httpx client to reuse.
            job: Partially populated JobPostingCreate from card parse.

        Returns:
            Updated JobPostingCreate with full description if available.
        """
        try:
            self.logger.debug("Fetching LinkedIn detail page: %s", job.url)
            resp = await client.get(job.url)
            if resp.status_code != 200:
                return job

            soup = BeautifulSoup(resp.text, "lxml")
            desc = self._extract_description_from_soup(soup)
            if desc:
                needs_enrichment = len(desc) < _MIN_DESCRIPTION_LENGTH
                return job.model_copy(update={
                    "description": desc[:_MAX_DESCRIPTION_LENGTH],
                    "needs_enrichment": needs_enrichment,
                })
        except Exception as e:
            self.logger.debug("Detail page fetch error for %s: %s", job.url, e)

        return job

    def _extract_description_from_soup(self, soup: object) -> str | None:
        """Extract job description text from a LinkedIn job detail page soup.

        Tries primary selector (.show-more-less-html__markup), then fallback
        (.description__text), then largest text block.

        Args:
            soup: BeautifulSoup parsed job detail page.

        Returns:
            Extracted description text, truncated to _MAX_DESCRIPTION_LENGTH,
            or None if nothing found.
        """
        from bs4 import BeautifulSoup as _BS, Tag

        if not isinstance(soup, _BS):
            try:
                # Accept Tag objects too — just get_text
                if hasattr(soup, "get_text"):
                    text = soup.get_text(separator="\n").strip()  # type: ignore[union-attr]
                    return text[:_MAX_DESCRIPTION_LENGTH] if text else None
            except Exception:
                return None

        # Primary selector
        el = soup.find(class_="show-more-less-html__markup")
        if el and isinstance(el, Tag):
            text = el.get_text(separator="\n").strip()
            if text:
                return text[:_MAX_DESCRIPTION_LENGTH]

        # Fallback selector
        el2 = soup.find(class_="description__text")
        if el2 and isinstance(el2, Tag):
            text = el2.get_text(separator="\n").strip()
            if text:
                return text[:_MAX_DESCRIPTION_LENGTH]

        # Last resort: largest text block in body
        try:
            body = soup.find("body")
            if body and isinstance(body, Tag):
                candidates = [
                    t for t in body.find_all(True)
                    if isinstance(t, Tag) and len(t.get_text(strip=True)) > 200
                ]
                if candidates:
                    largest = max(candidates, key=lambda t: len(t.get_text(strip=True)))
                    text = largest.get_text(separator="\n").strip()
                    return text[:_MAX_DESCRIPTION_LENGTH]
        except Exception:
            pass

        return None

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

    def _parse_posted_at(self, card: object) -> tuple[datetime, bool]:
        """Extract the posting date from a LinkedIn job card.

        Returns (posted_at, date_unknown). date_unknown=True means we fell back
        to scrape time and the job should be flagged needs_enrichment=True.
        """
        from bs4 import Tag

        if isinstance(card, Tag):
            time_el = card.find("time")
            if time_el and isinstance(time_el, Tag):
                attr = time_el.get("datetime", "")
                if attr:
                    try:
                        dt = datetime.fromisoformat(str(attr).replace("Z", "+00:00"))
                        return dt.replace(tzinfo=None), False
                    except ValueError:
                        pass

            text = card.get_text(separator=" ")
            m = re.search(r"(\d+)\s+(day|week|month|year)s?\s+ago", text, re.IGNORECASE)
            if m:
                value = int(m.group(1))
                unit = m.group(2).lower()
                multiplier = {"day": 1, "week": 7, "month": 30, "year": 365}[unit]
                return datetime.utcnow() - timedelta(days=value * multiplier), False

        return datetime.utcnow(), True

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

        # Determine if this card has enough description or needs enrichment
        needs_enrichment = len(full_text.strip()) < _MIN_DESCRIPTION_LENGTH

        posted_at, date_unknown = self._parse_posted_at(card)
        needs_enrichment = needs_enrichment or date_unknown

        try:
            from ..agents.tools.profile_loader import load_profile as _lp
            _currency = _lp().compensation.currency or "USD"
        except Exception:
            _currency = "USD"

        return JobPostingCreate(
            title=title,
            company=company,
            location=location,
            rate_text=None,
            rate_min=None,
            rate_max=None,
            currency=_currency,
            ir35_status=ir35_status,
            legal_fields={"ir35_status": ir35_status} if ir35_status else {},
            description=full_text[:_MAX_DESCRIPTION_LENGTH] if full_text else None,
            url=href,
            source=self.name,
            posted_at=posted_at,
            skills=skills or None,
            employment_type=employment_type,
            working_pattern=working_pattern,
            rate_type=rate_type,
            needs_enrichment=needs_enrichment,
        )
