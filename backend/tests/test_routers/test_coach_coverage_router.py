from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.story import Story


async def _seed(db_session: AsyncSession) -> None:
    db_session.add_all(
        [
            JobPosting(
                id="job-1",
                title="Delivery Lead",
                company="Synthetic Co",
                url="https://example.test/job-1",
                source="synthetic",
                skills=["Python"],
            ),
            JobScore(
                job_id="job-1",
                overall_score=0.5,
                keyword_misses=["Budget ownership"],
                keyword_matches=["Stakeholder management"],
            ),
            Application(id="app-1", job_id="job-1", status="interview", priority="normal"),
            Story(
                id="story-1",
                title="Budget story",
                slug="budget-story",
                tags=["budget", "ownership"],
                result="Cut spend by 18 percent.",
                metrics={"saving": 18},
                strength_score=7.0,
            ),
        ]
    )
    await db_session.flush()


async def test_get_coverage_returns_map(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)

    response = await client.get(
        "/api/coach/readiness/coverage", params={"application_id": "app-1"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["application_id"] == "app-1"
    assert [item["competency"] for item in payload["competencies"]] == [
        "Budget ownership",
        "Stakeholder management",
        "Python",
    ]
    assert payload["competencies"][0]["status"] == "covered"
    assert payload["competencies"][0]["stories"][0]["has_metric"] is True


async def test_get_overview_returns_shared_gaps(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed(db_session)
    db_session.add_all(
        [
            JobPosting(
                id="job-2",
                title="Programme Manager",
                company="Synthetic Co",
                url="https://example.test/job-2",
                source="synthetic",
                skills=["Python"],
            ),
            JobScore(
                job_id="job-2",
                overall_score=0.4,
                keyword_misses=["Budget ownership"],
                keyword_matches=["Stakeholder management"],
            ),
            Application(id="app-2", job_id="job-2", status="interview", priority="normal"),
        ]
    )
    await db_session.flush()

    response = await client.get("/api/coach/readiness/coverage/overview")

    assert response.status_code == 200
    assert {
        item["competency"]: item["application_count"]
        for item in response.json()["gaps"]
    } == {"Python": 2, "Stakeholder management": 2}


async def test_get_coverage_unknown_application_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.get(
        "/api/coach/readiness/coverage", params={"application_id": "missing"}
    )

    assert response.status_code == 404


async def test_flag_off_blocks_override_writes_but_allows_reads(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed(db_session)
    monkeypatch.setattr(settings, "HATCH_COACH_STORY_COVERAGE_ENABLED", False)

    read = await client.get(
        "/api/coach/readiness/coverage", params={"application_id": "app-1"}
    )
    blocked = await client.put(
        "/api/coach/readiness/coverage/app-1/overrides",
        json={
            "overrides": [
                {
                    "original": "Budget ownership",
                    "replacement": "Budget accountability",
                    "hidden": False,
                }
            ]
        },
    )

    assert read.status_code == 200
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "disabled"

    monkeypatch.setattr(settings, "HATCH_COACH_STORY_COVERAGE_ENABLED", True)
    written = await client.put(
        "/api/coach/readiness/coverage/app-1/overrides",
        json={
            "overrides": [
                {
                    "original": "Budget ownership",
                    "replacement": "Budget accountability",
                    "hidden": False,
                }
            ]
        },
    )

    assert written.status_code == 200
    assert written.json()["competencies"][0]["competency"] == "Budget accountability"
