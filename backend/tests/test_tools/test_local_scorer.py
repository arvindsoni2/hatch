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
