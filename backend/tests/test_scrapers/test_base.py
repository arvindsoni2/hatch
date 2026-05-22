"""Unit tests for BaseScraper utility methods."""
from __future__ import annotations

import pytest

from app.scrapers.base import BaseScraper
from app.schemas.job import JobPostingCreate


class ConcreteScraper(BaseScraper):
    """Minimal concrete implementation for testing BaseScraper methods."""

    name = "test_scraper"

    async def scrape(self) -> list[JobPostingCreate]:
        return []


@pytest.fixture
def scraper() -> ConcreteScraper:
    return ConcreteScraper()


# ──────────────────────── parse_rate ────────────────────────

class TestParseRate:
    def test_single_value(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("£600/day")
        assert min_r == 600.0
        assert max_r == 600.0

    def test_range_value(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("£500-£700/day")
        assert min_r == 500.0
        assert max_r == 700.0

    def test_value_with_commas(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("£1,000/day")
        assert min_r == 1000.0
        assert max_r == 1000.0

    def test_empty_string(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("")
        assert min_r is None
        assert max_r is None

    def test_no_numbers(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("Competitive salary")
        assert min_r is None
        assert max_r is None

    def test_negotiable_text(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("Negotiable")
        assert min_r is None
        assert max_r is None

    def test_range_picks_correct_min_max(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("£800 to £1000 per day")
        assert min_r == 800.0
        assert max_r == 1000.0

    def test_annual_salary(self, scraper: ConcreteScraper) -> None:
        min_r, max_r = scraper.parse_rate("£60000 per annum")
        assert min_r == 60000.0
        assert max_r == 60000.0


# ──────────────────────── detect_ir35 ────────────────────────

class TestDetectIR35:
    def test_outside_ir35_phrase(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("This role is outside IR35") == "outside"

    def test_outside_of_ir35(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("Contract outside of IR35") == "outside"

    def test_b2b(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("B2B contract, ltd company preferred") == "outside"

    def test_ltd_company(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("Engagement via Ltd company") == "outside"

    def test_inside_ir35(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("This is an inside IR35 contract") == "inside"

    def test_paye_only(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("PAYE only, no Ltd accepted") == "inside"

    def test_unknown_no_keywords(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("Senior Solutions Architect needed") == "unknown"

    def test_case_insensitive(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("OUTSIDE IR35 CONTRACT") == "outside"
        assert scraper.detect_ir35("Inside IR35 engagement") == "inside"

    def test_empty_text(self, scraper: ConcreteScraper) -> None:
        assert scraper.detect_ir35("") == "unknown"


# ──────────────────────── extract_skills ────────────────────────

class TestExtractSkills:
    def test_extracts_aws(self, scraper: ConcreteScraper) -> None:
        skills = scraper.extract_skills("Senior AWS architect needed for cloud migration")
        assert "AWS" in skills

    def test_extracts_multiple(self, scraper: ConcreteScraper) -> None:
        skills = scraper.extract_skills("Experience with Kubernetes, Terraform and Python required")
        assert "Kubernetes" in skills
        assert "Terraform" in skills
        assert "Python" in skills

    def test_no_duplicates(self, scraper: ConcreteScraper) -> None:
        skills = scraper.extract_skills("AWS AWS AWS cloud")
        assert skills.count("AWS") == 1

    def test_empty_text(self, scraper: ConcreteScraper) -> None:
        skills = scraper.extract_skills("")
        assert skills == []

    def test_case_insensitive_matching(self, scraper: ConcreteScraper) -> None:
        skills = scraper.extract_skills("experience with terraform and docker")
        assert "Terraform" in skills
        assert "Docker" in skills


# ──────────────────────── get_random_ua ────────────────────────

class TestGetRandomUA:
    def test_returns_string(self, scraper: ConcreteScraper) -> None:
        ua = scraper.get_random_ua()
        assert isinstance(ua, str)
        assert len(ua) > 20

    def test_returns_valid_browser_ua(self, scraper: ConcreteScraper) -> None:
        ua = scraper.get_random_ua()
        assert "Mozilla" in ua
