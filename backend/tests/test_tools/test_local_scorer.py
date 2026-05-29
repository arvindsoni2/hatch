"""Tests for local keyword-based job scorer."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from app.agents.tools.local_scorer import score_locally, LocalScoreResult


def _make_profile(
    primary_skills=None,
    secondary_skills=None,
    min_rate=500,
    max_rate=700,
    rate_type="daily",
    years_exp=15,
    title="Cloud Architect",
    locations=None,
) -> MagicMock:
    profile = MagicMock()
    profile.candidate.title = title
    profile.candidate.years_experience = years_exp
    profile.skills.primary = primary_skills or ["cloud architecture", "aws", "terraform"]
    profile.skills.secondary = secondary_skills or ["python", "devops"]
    profile.compensation.min_rate = min_rate
    profile.compensation.max_rate = max_rate
    profile.compensation.rate_type = rate_type
    profile.compensation.currency = "GBP"
    profile.scoring.weights.skill_match = 0.35
    profile.scoring.weights.experience_match = 0.30
    profile.scoring.weights.rate_match = 0.20
    profile.scoring.weights.location_match = 0.15

    loc = MagicMock()
    loc.city = "London"
    loc.country = "UK"
    loc.remote_preference = "hybrid"
    profile.search.locations = locations or [loc]
    return profile


def _make_job(description: str, title: str = "Cloud Architect", location: str = "London, UK") -> MagicMock:
    job = MagicMock()
    job.title = title
    job.location = location
    job.description = description
    return job


class TestLocalScorer:

    # ── New correctness tests (should fail until scorer is fixed) ──────

    def test_rate_match_ignores_non_salary_numbers(self):
        """Numbers not near currency indicators must not be treated as rates."""
        profile = _make_profile(min_rate=500, max_rate=700, rate_type="daily")
        # 500 = team size, 1998 = founded year — neither is a rate
        job = _make_job(
            "We are a team of 500 engineers, founded in 1998. Great culture.",
            title="Delivery Lead",
        )
        result = score_locally(job, profile)
        # Should return neutral (0.6), not a match or penalty
        assert 0.5 <= result.rate_match <= 0.7, (
            f"Expected neutral rate_match 0.5-0.7, got {result.rate_match}"
        )

    def test_rate_match_handles_annual_salary(self):
        """Annual salary stated in JD should match annual rate_type profile."""
        profile = _make_profile(min_rate=70000, max_rate=90000, rate_type="annual")
        job = _make_job("Salary £75,000 per annum plus benefits.", title="Senior Engineer")
        result = score_locally(job, profile)
        assert result.rate_match >= 0.8, (
            f"Expected rate_match >= 0.8 for in-range annual salary, got {result.rate_match}"
        )

    def test_rate_match_parses_ranges(self):
        """Rate range in JD should match profile range when overlapping."""
        profile = _make_profile(min_rate=550, max_rate=700, rate_type="daily")
        job = _make_job("Rate: £550 - £650 per day, outside IR35.", title="Delivery Lead")
        result = score_locally(job, profile)
        assert result.rate_match >= 0.8, (
            f"Expected rate_match >= 0.8 for overlapping rate range, got {result.rate_match}"
        )

    def test_experience_match_ignores_mentor_junior_in_description(self):
        """'junior' in context 'mentor junior engineers' should NOT penalise a senior candidate."""
        profile = _make_profile(years_exp=10, title="Senior Delivery Lead")
        job = _make_job(
            "Senior Delivery Lead required. You will mentor junior engineers and manage delivery.",
            title="Senior Delivery Lead",
        )
        result = score_locally(job, profile)
        assert result.experience_match >= 0.7, (
            f"Expected experience_match >= 0.7 (senior role), got {result.experience_match}"
        )

    def test_skill_match_handles_react_variants(self):
        """profile skill 'React' should match JD text containing 'ReactJS' or 'React.js'."""
        profile = _make_profile(primary_skills=["React", "TypeScript", "CSS"])
        job = _make_job("We use ReactJS and TypeScript for our frontend. CSS-in-JS experience helpful.")
        result = score_locally(job, profile)
        assert "React" in result.keyword_matches, (
            f"Expected 'React' to match 'ReactJS' in JD. keyword_matches={result.keyword_matches}"
        )

    def test_skill_match_handles_kubernetes_synonym(self):
        """profile skill 'Kubernetes' should match JD text containing 'k8s'."""
        profile = _make_profile(primary_skills=["Kubernetes", "Docker", "Terraform"])
        job = _make_job("Experience with k8s required. Docker and Terraform experience helpful.")
        result = score_locally(job, profile)
        assert "Kubernetes" in result.keyword_matches, (
            f"Expected 'Kubernetes' to match 'k8s' synonym. keyword_matches={result.keyword_matches}"
        )

    def test_skill_match_handles_ml_synonym(self):
        """profile skill 'machine learning' should match JD containing 'ML'."""
        profile = _make_profile(primary_skills=["machine learning", "python"])
        job = _make_job("Strong ML background required. Python experience essential.")
        result = score_locally(job, profile)
        assert "machine learning" in result.keyword_matches, (
            f"Expected 'machine learning' to match 'ML'. keyword_matches={result.keyword_matches}"
        )

    # ── Existing tests ─────────────────────────────────────────────────

    def test_scores_matching_skills_correctly(self):
        """Job with 3 out of 5 profile skills in description scores above 0.5 for skill_match."""
        profile = _make_profile(
            primary_skills=["aws", "terraform", "cloud architecture"],
            secondary_skills=["python", "devops"],
        )
        # Include 3 of the 5 skills in job description
        job = _make_job("We need aws and terraform experience. DevOps background helpful.")

        result = score_locally(job, profile)

        assert isinstance(result, LocalScoreResult)
        assert result.skill_match > 0.3
        assert "aws" in result.keyword_matches
        assert "terraform" in result.keyword_matches

    def test_remote_location_scores_max(self):
        """Job with 'remote' in description scores location_match = 1.0 for remote-preference profile."""
        loc = MagicMock()
        loc.city = "London"
        loc.country = "UK"
        loc.remote_preference = "remote"
        profile = _make_profile(locations=[loc])

        job = _make_job("Fully remote role, work from anywhere in the UK.")

        result = score_locally(job, profile)

        assert result.location_match == 1.0

    def test_returns_scoring_method_local_keyword(self):
        """score_locally() always sets reasoning = 'local-keyword'."""
        profile = _make_profile()
        job = _make_job("Senior cloud architect role.")

        result = score_locally(job, profile)

        assert result.reasoning == "local-keyword"
        assert isinstance(result.overall_score, float)
        assert 0.0 <= result.overall_score <= 1.0
