"""Background competency extraction writes its cache row (P8 repair cycle 2)."""
from __future__ import annotations

import asyncio

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.models.application import Application
from app.models.coach_readiness import CoachDerivedText
from app.models.job import JobPosting
from app.services.coach_readiness import coverage as coverage_module
from coach_readiness_support import (
    CHAT_COMPLETIONS,
    chat_completion,
    configure_local_ai,
    model_dispatches,
    not_the_test_client,
)


async def _seed(factory) -> None:
    async with factory() as db:
        db.add(JobPosting(
            id="extract-job", title="Delivery Lead", company="Northwind",
            url="https://example.test/extract", source="synthetic",
            description=(
                "We are a friendly company.\n"
                "- Own quarterly planning across four delivery teams.\n"
                "- Keep dependencies visible before the commitment date."
            ),
        ))
        await db.flush()
        db.add(Application(
            id="extract-app", job_id="extract-job", status="interview", priority="normal",
        ))
        await db.commit()


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_background_extraction_persists_the_cache_row(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "HATCH_COACH_STORY_COVERAGE_ENABLED", True)
    monkeypatch.setattr(coverage_module, "_EXTRACT_INFLIGHT", set())
    monkeypatch.setattr(coverage_module, "_EXTRACT_TASKS", set())
    monkeypatch.setattr(coverage_module, "_EXTRACT_FAILED", {})
    await _seed(coach_database)
    httpx_mock.add_callback(
        lambda _request: httpx.Response(
            200, json=chat_completion('{"competencies": ["quarterly planning"]}')
        ),
        method="POST", url=CHAT_COMPLETIONS, is_reusable=True,
    )

    async with coach_database() as db:
        first = await coverage_module.coverage_for_application(db, "extract-app")
    assert first is not None
    assert all(item.label is None for item in first.competencies)

    while coverage_module._EXTRACT_TASKS:
        await asyncio.sleep(0)

    async with coach_database() as db:
        rows = (
            await db.execute(
                select(CoachDerivedText).where(CoachDerivedText.kind == "competency")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].text_json == {"competencies": ["quarterly planning"]}
    assert len(model_dispatches(httpx_mock)) == 1

    async with coach_database() as db:
        second = await coverage_module.coverage_for_application(db, "extract-app")
    assert second is not None
    extracted = [item for item in second.competencies if item.label]
    assert [item.competency for item in extracted] == ["quarterly planning"]
    assert extracted[0].label == "from the job description"
    assert len(model_dispatches(httpx_mock)) == 1
