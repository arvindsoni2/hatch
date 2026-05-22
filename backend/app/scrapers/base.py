"""Abstract base class for all job board scrapers."""
from __future__ import annotations

import asyncio
import logging
import random
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..config import settings
from ..schemas.job import JobPostingCreate


class BaseScraper(ABC):
    """Abstract base scraper — all job board scrapers inherit from this."""

    name: str = "base"

    def __init__(self) -> None:
        self.logger = logging.getLogger(f"jobpilot.scrapers.{self.name}")

    @abstractmethod
    async def scrape(self) -> list[JobPostingCreate]:
        """Run the scraper and return a list of job postings.

        Returns:
            A list of JobPostingCreate instances ready to be saved.
        """
        ...

    async def random_delay(self) -> None:
        """Sleep for a random duration to avoid rate limiting."""
        delay = random.uniform(
            settings.SCRAPE_DELAY_MIN_SECONDS,
            settings.SCRAPE_DELAY_MAX_SECONDS,
        )
        self.logger.debug("Waiting %.1f seconds before next request...", delay)
        await asyncio.sleep(delay)

    def get_random_ua(self) -> str:
        """Return a random User-Agent string from the configured pool."""
        return random.choice(settings.USER_AGENTS)

    def parse_rate(self, rate_text: str) -> tuple[float | None, float | None]:
        """Parse a rate string like '£500-£700/day' into (min, max) floats.

        Args:
            rate_text: Raw rate string from the job listing.

        Returns:
            Tuple of (rate_min, rate_max). Both None if no numbers found.
        """
        if not rate_text:
            return None, None

        # Strip commas so "1,000" becomes "1000"
        cleaned = rate_text.replace(",", "")
        nums = re.findall(r"\d+(?:\.\d+)?", cleaned)
        floats = [float(n) for n in nums if float(n) > 0]

        if not floats:
            return None, None
        elif len(floats) == 1:
            return floats[0], floats[0]
        else:
            return min(floats), max(floats)

    def detect_ir35(self, text: str) -> str:
        """Infer IR35 status from the job description or title text.

        Args:
            text: Combined text to search (title + description).

        Returns:
            One of 'outside', 'inside', 'not_applicable', or 'unknown'.
        """
        text_lower = text.lower()
        outside_signals = [
            "outside ir35",
            "outside of ir35",
            "b2b",
            "ltd company",
            "ltd co",
            "via ltd",
            "through ltd",
            "sc cleared outside",
        ]
        inside_signals = [
            "inside ir35",
            "inside of ir35",
            "paye only",
            "paye contract",
        ]

        if any(kw in text_lower for kw in outside_signals):
            return "outside"
        if any(kw in text_lower for kw in inside_signals):
            return "inside"
        # Permanent/salary roles don't have IR35 relevance
        if self.detect_employment_type(text) == "permanent":
            return "not_applicable"
        return "unknown"

    def detect_employment_type(self, text: str) -> str:
        """Infer employment type from job title/description text.

        Args:
            text: Combined text to search (title + description).

        Returns:
            One of 'contract', 'permanent', 'part_time', 'fixed_term',
            'freelance', or 'unknown'.
        """
        text_lower = text.lower()
        if any(kw in text_lower for kw in [
            "contract", "contractor", "contracting", "freelance", "outside ir35",
            "inside ir35", "ltd company", "b2b", "day rate", "daily rate",
        ]):
            return "contract"
        if any(kw in text_lower for kw in [
            "permanent", "perm", "full-time", "full time", "staff", "employee",
            "employment", "salary", "per annum", "pa)", "p.a.",
        ]):
            return "permanent"
        if any(kw in text_lower for kw in ["part-time", "part time", " pt ", "part_time"]):
            return "part_time"
        if any(kw in text_lower for kw in [
            "fixed term", "fixed-term", "ftc", "temporary", "temp role",
            "maternity cover", "parental cover",
        ]):
            return "fixed_term"
        return "unknown"

    def detect_working_pattern(self, text: str) -> str:
        """Infer working pattern (remote/hybrid/onsite) from text.

        Args:
            text: Combined text to search (title + description).

        Returns:
            One of 'remote', 'hybrid', 'onsite', or 'unknown'.
        """
        text_lower = text.lower()
        if any(kw in text_lower for kw in [
            "fully remote", "100% remote", "remote only", "remote first",
            "remote-first", "work from home", "wfh", "home based", "home-based",
            "anywhere in the uk",
        ]):
            return "remote"
        if "hybrid" in text_lower:
            return "hybrid"
        if any(kw in text_lower for kw in [
            "on-site", "onsite", "on site", "office based", "office-based",
            "in office", "in-office", "fully on", "5 days",
        ]):
            return "onsite"
        # Plain "remote" without "fully" could mean hybrid — call it remote
        if "remote" in text_lower:
            return "remote"
        return "unknown"

    def detect_rate_type(self, text: str) -> str:
        """Infer rate/pay type from rate text or description.

        Args:
            text: Rate text or description.

        Returns:
            One of 'daily', 'hourly', 'annual', or 'unknown'.
        """
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["/day", "per day", "daily", "pd", "p/d"]):
            return "daily"
        if any(kw in text_lower for kw in ["/hour", "/hr", "per hour", "hourly", "ph", "p/h"]):
            return "hourly"
        if any(kw in text_lower for kw in [
            "/year", "per year", "per annum", "p.a.", "pa)", " pa ", "salary",
            "annual", "/annum",
        ]):
            return "annual"
        return "unknown"

    def extract_skills(self, text: str) -> list[str]:
        """Extract common tech skills from free-form text.

        Args:
            text: Job description or title text.

        Returns:
            List of matched skill strings.
        """
        known_skills = [
            "AWS", "Azure", "GCP", "Kubernetes", "Docker", "Terraform",
            "Python", "Java", "TypeScript", "JavaScript", "Go", "Rust",
            "React", "Node.js", "FastAPI", "Django", "Spring Boot",
            "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka",
            "CI/CD", "DevOps", "Agile", "Scrum", "TOGAF", "SABSA",
            "Solutions Architect", "Cloud Architect", "Security Architect",
            "Data Engineer", "Machine Learning", "AI", "LLM",
            "REST", "GraphQL", "gRPC", "Microservices", "Serverless",
            "Linux", "Bash", "PowerShell", "Ansible", "Helm",
            "ArgoCD", "Jenkins", "GitHub Actions", "GitLab CI",
        ]
        found: list[str] = []
        text_lower = text.lower()
        for skill in known_skills:
            if skill.lower() in text_lower and skill not in found:
                found.append(skill)
        return found
