"""Scoring calibration tests — golden test cases for regression prevention.

These run against the LOCAL scorer only (deterministic, no LLM).
They validate that specific job+profile combinations produce sensible scores,
guarding against future regressions in scoring logic.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.agents.tools.local_scorer import score_locally


def _profile(
    title="Delivery Lead",
    years=20,
    primary_skills=None,
    secondary_skills=None,
    min_rate=550,
    max_rate=700,
    rate_type="daily",
    currency="GBP",
    remote_preference="hybrid",
    city="London",
    country="UK",
    preferred_domains=None,
) -> MagicMock:
    p = MagicMock()
    p.locale = "uk"
    p.candidate.title = title
    p.candidate.years_experience = years
    p.skills.primary = primary_skills or ["agile delivery", "stakeholder management", "cloud architecture"]
    p.skills.secondary = secondary_skills or ["python", "devops"]
    p.compensation.min_rate = min_rate
    p.compensation.max_rate = max_rate
    p.compensation.rate_type = rate_type
    p.compensation.currency = currency
    p.scoring.weights.skill_match = 0.35
    p.scoring.weights.experience_match = 0.30
    p.scoring.weights.rate_match = 0.20
    p.scoring.weights.location_match = 0.15
    loc = MagicMock()
    loc.city = city
    loc.country = country
    loc.remote_preference = remote_preference
    p.search.locations = [loc]
    p.domains.preferred = preferred_domains or ["Energy", "Financial Services"]
    return p


def _job(title: str, description: str, location: str = "London, UK") -> MagicMock:
    j = MagicMock()
    j.title = title
    j.description = description
    j.location = location
    return j


class TestScoringCalibration:

    def test_perfect_match_scores_high(self):
        """A job that matches on all four dimensions should score ≥ 0.75."""
        profile = _profile()
        job = _job(
            title="Senior Delivery Lead",
            description=(
                "Senior Delivery Lead required, London hybrid, £550-£650 per day. "
                "Expert in agile delivery, stakeholder management, and cloud architecture. "
                "DevOps background helpful. 10+ years experience preferred."
            ),
        )
        result = score_locally(job, profile)
        assert result.overall_score >= 0.75, (
            f"Perfect match should score ≥ 0.75, got {result.overall_score}. "
            f"Breakdown: skill={result.skill_match} exp={result.experience_match} "
            f"rate={result.rate_match} loc={result.location_match}"
        )

    def test_wrong_seniority_scores_low(self):
        """A junior role for a senior candidate should score ≤ 0.50."""
        profile = _profile(years=20)
        job = _job(
            title="Junior Project Coordinator",
            description=(
                "Entry-level coordinator role. Graduate scheme. "
                "No experience required. Competitive graduate salary."
            ),
        )
        result = score_locally(job, profile)
        assert result.overall_score <= 0.50, (
            f"Junior role for senior candidate should score ≤ 0.50, got {result.overall_score}. "
            f"exp={result.experience_match}"
        )

    def test_wrong_location_lowers_location_match(self):
        """A San Francisco onsite role for a London-only candidate should score low on location."""
        profile = _profile(remote_preference="onsite", city="London", country="UK")
        job = _job(
            title="Senior Delivery Lead",
            description="Senior role based in San Francisco, California. Onsite only. No remote.",
            location="San Francisco, CA",
        )
        result = score_locally(job, profile)
        assert result.location_match <= 0.40, (
            f"SF onsite vs London onsite should give location_match ≤ 0.40, got {result.location_match}"
        )

    def test_missing_skills_lowers_skill_match(self):
        """A job requiring entirely different skills should have skill_match ≤ 0.30."""
        profile = _profile(
            primary_skills=["python", "fastapi", "postgresql"],
            secondary_skills=["docker", "redis"],
        )
        job = _job(
            title="Java Developer",
            description=(
                "Java Spring Boot developer. Expert in Java, Spring, Kotlin, Maven. "
                "Hibernate ORM required. Oracle DB experience essential."
            ),
        )
        result = score_locally(job, profile)
        assert result.skill_match <= 0.30, (
            f"Completely different skills should give skill_match ≤ 0.30, got {result.skill_match}. "
            f"matched={result.keyword_matches}"
        )

    def test_rate_below_minimum_lowers_rate_match(self):
        """A job offering well below the profile's minimum rate should score low on rate."""
        profile = _profile(min_rate=550, max_rate=700, rate_type="daily")
        job = _job(
            title="Delivery Lead",
            description=(
                "Contract Delivery Lead, London. Rate £250-£300 per day. "
                "6-month initial contract."
            ),
        )
        result = score_locally(job, profile)
        assert result.rate_match <= 0.50, (
            f"Rate £250-300/day vs profile min £550/day should give rate_match ≤ 0.50, "
            f"got {result.rate_match}"
        )

    def test_remote_job_matches_remote_preference(self):
        """A fully remote job matches a remote-preference candidate perfectly on location."""
        profile = _profile(remote_preference="remote")
        job = _job(
            title="Senior Cloud Architect",
            description=(
                "Fully remote role. Work from home anywhere in the UK. "
                "Cloud architecture, agile delivery experience needed. £600-700 per day."
            ),
        )
        result = score_locally(job, profile)
        assert result.location_match == 1.0, (
            f"Fully remote job for remote-preference candidate should be 1.0, got {result.location_match}"
        )

    def test_in_range_rate_scores_high(self):
        """A job offering a rate squarely in the candidate's range scores well on rate."""
        profile = _profile(min_rate=500, max_rate=700, rate_type="daily")
        job = _job(
            title="Delivery Lead",
            description="Daily rate £600 outside IR35. Hybrid London.",
        )
        result = score_locally(job, profile)
        assert result.rate_match >= 0.8, (
            f"In-range rate £600 vs £500-700 should give rate_match ≥ 0.8, got {result.rate_match}"
        )

    def test_skill_synonym_improves_match(self):
        """Synonym matching means k8s/ReactJS/ML matches profile skills."""
        profile = _profile(
            primary_skills=["Kubernetes", "React", "machine learning"],
            secondary_skills=["python"],
        )
        job = _job(
            title="Platform Engineer",
            description=(
                "Platform engineer with k8s expertise. ReactJS frontend experience. "
                "ML model deployment knowledge. Python scripting."
            ),
        )
        result = score_locally(job, profile)
        assert result.skill_match >= 0.8, (
            f"Synonym matching should give skill_match ≥ 0.8, got {result.skill_match}. "
            f"matched={result.keyword_matches}"
        )
        assert "Kubernetes" in result.keyword_matches
        assert "React" in result.keyword_matches
        assert "machine learning" in result.keyword_matches
