"""Characterize the current local scoring and persistence result contract."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import select

from app.agents.scorer_agent import ScorerAgent
from app.agents.tools.local_scorer import score_locally
from app.models.job import JobPosting
from app.models.job_score import JobScore


async def test_legacy_score_result_shape_is_persisted(db_session, runtime_fixture) -> None:
    case = runtime_fixture("job_score_cases.json")
    job_data = case["job"]
    profile_data = case["profile"]
    job = JobPosting(
        id=job_data["id"],
        title=job_data["title"],
        company="Synthetic Industries",
        description=job_data["description"],
        location=job_data["location"],
        url="https://example.invalid/synthetic-job-001",
        source="synthetic",
    )
    db_session.add(job)
    await db_session.flush()

    profile = MagicMock()
    profile.candidate.title = profile_data["title"]
    profile.candidate.years_experience = profile_data["years_experience"]
    profile.skills.primary = profile_data["primary_skills"]
    profile.skills.secondary = profile_data["secondary_skills"]
    profile.compensation.min_rate = profile_data["min_rate"]
    profile.compensation.max_rate = profile_data["max_rate"]
    profile.compensation.rate_type = profile_data["rate_type"]
    profile.scoring.weights = SimpleNamespace(
        skill_match=0.35,
        experience_match=0.30,
        rate_match=0.20,
        location_match=0.15,
    )
    profile.search.locations = [
        SimpleNamespace(city="London", country="UK", remote_preference="remote")
    ]

    score = score_locally(job, profile)
    await ScorerAgent()._persist_score(job.id, score, db_session)
    await db_session.commit()
    persisted = (
        await db_session.execute(select(JobScore).where(JobScore.job_id == job.id))
    ).scalar_one()

    characterized = {
        column.name: getattr(persisted, column.name)
        for column in JobScore.__table__.columns
        if column.name not in {"id", "job_id", "scored_at"}
    }
    assert set(characterized) == {
        "skill_match",
        "experience_match",
        "rate_match",
        "location_match",
        "overall_score",
        "reasoning",
        "scoring_method",
        "keyword_matches",
        "keyword_misses",
        "fit_reasoning",
        "strengths",
        "score_gaps",
    }
    assert characterized["scoring_method"] == "local"
    assert characterized["keyword_matches"] == ["AWS", "Terraform", "Python"]
    assert 0.0 <= characterized["overall_score"] <= 1.0
