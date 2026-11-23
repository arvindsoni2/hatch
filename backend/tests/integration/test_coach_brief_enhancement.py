"""Brief enhancement validation, sources and fingerprint refresh (P7)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, text

from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachDerivedSource, CoachInterviewBrief
from app.models.job import JobPosting
from app.models.job_score import JobScore
from app.models.question_bank import QuestionBankItem
from app.models.story import Story
from app.repositories.story_repository import StoryRepository
from app.schemas.story import StoryUpdate
from app.services.coach_readiness import brief as brief_service
from coach_readiness_support import (
    CHAT_COMPLETIONS,
    chat_completion,
    configure_local_ai,
    fake_llama,
    model_dispatches,
    not_the_test_client,
    seed_pattern_sessions,
)

NOW = datetime.utcnow()


async def _seed(factory):
    async with factory() as db:
        db.add(JobPosting(
            id="enh-job", title="Delivery Lead", company="Northwind",
            url="https://example.test/enh", source="synthetic",
            description="Lead delivery of the billing platform.",
        ))
        await db.flush()
        db.add(Application(id="enh-app", job_id="enh-job", status="interview", priority="normal"))
        db.add(JobScore(
            id="enh-score", job_id="enh-job", overall_score=0.9,
            keyword_matches=["delivery"], keyword_misses=[], scoring_method="local",
        ))
        db.add(InterviewRound(
            id="enh-round", application_id="enh-app", round_number=1,
            type="technical", scheduled_at=NOW + timedelta(days=3),
            duration_minutes=60, status="scheduled",
        ))
        db.add(Story(
            id="enh-story", title="Rescued a late delivery", slug="enh-story",
            situation="Synthetic situation", task="Synthetic task", action="Synthetic action",
            result="Delivered on time", tags=["delivery"], skills=["delivery"],
            metrics={"time": "2 weeks"},
        ))
        db.add(QuestionBankItem(
            id="enh-question", type="behavioural", title="Delivery question",
            question="Tell me about a delivery.", answer_draft="Draft",
            linked_applications=["enh-app"],
        ))
        await db.commit()


async def _wait_state(factory, state: str, timeout: float = 5.0) -> CoachInterviewBrief:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        async with factory() as db:
            row = (await db.execute(
                select(CoachInterviewBrief).where(
                    CoachInterviewBrief.interview_round_id == "enh-round"
                )
            )).scalar_one_or_none()
        if row is not None and row.enhancement_state == state:
            return row
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"brief never became {state}")
        await asyncio.sleep(0.05)


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_bad_enhancement_discarded_skeleton_kept(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)
    fake_llama(httpx_mock, tips=None)
    await seed_pattern_sessions(coach_database)
    await _seed(coach_database)

    async def bad(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=chat_completion(
            json.dumps({"talking_points": [{"story_id": "unknown", "text": "Bad claim."}]})
        ))

    httpx_mock.reset()
    httpx_mock.add_callback(bad, method="POST", url=CHAT_COMPLETIONS, is_reusable=True)

    async with coach_database() as db:
        await brief_service.request_enhancement(db, "enh-round", NOW)
    await _wait_state(coach_database, "unavailable")

    async with coach_database() as db:
        count = await db.scalar(text("SELECT count(*) FROM coach_derived_text"))
        data = await brief_service.build_brief(db, "enh-round", NOW)
    assert count == 0
    assert data["stories"] is not None


@pytest.mark.httpx_mock(should_mock=not_the_test_client)
async def test_successful_enhancement_sources_and_refresh(
    coach_database, httpx_mock, tmp_path, monkeypatch
) -> None:
    configure_local_ai(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)
    await seed_pattern_sessions(coach_database)
    await _seed(coach_database)
    output = {
        "talking_points": [{"story_id": "enh-story", "text": "Delivered on time."}],
        "watch_outs": [],
    }
    httpx_mock.add_callback(
        lambda _request: httpx.Response(200, json=chat_completion(json.dumps(output))),
        method="POST", url=CHAT_COMPLETIONS, is_reusable=True,
    )

    async with coach_database() as db:
        await brief_service.request_enhancement(db, "enh-round", NOW)
    await _wait_state(coach_database, "current")
    assert len(model_dispatches(httpx_mock)) == 1
    async with coach_database() as db:
        kinds = {
            row[0] for row in (await db.execute(
                select(CoachDerivedSource.source_kind)
            )).all()
        }
    assert kinds == {"story", "interview_round", "question_bank_item"}

    async with coach_database() as db:
        data = await brief_service.build_brief(db, "enh-round", NOW)
        assert data["enhancement"]["state"] == "current"
        assert data["stories"][0]["talking_point"] == "Delivered on time."
        await StoryRepository(db).update("enh-story", StoryUpdate(title="Edited story"))
        await db.commit()
        data = await brief_service.build_brief(db, "enh-round", NOW)
        assert data["enhancement"]["state"] == "outdated"
        await brief_service.request_enhancement(db, "enh-round", NOW)
    await _wait_state(coach_database, "current")
    assert len(model_dispatches(httpx_mock)) == 2

    async with coach_database() as db:
        await brief_service.request_enhancement(db, "enh-round", NOW)
    assert len(model_dispatches(httpx_mock)) == 2

    async with coach_database() as db:
        rows = (await db.execute(select(CoachInterviewBrief))).scalars().all()
        assert len(rows) == 1
        rows[0].enhanced_text_id = None
        rows[0].enhancement_state = "current"
        await db.commit()
        data = await brief_service.build_brief(db, "enh-round", NOW)
        assert data["enhancement"]["state"] == "none"
        await brief_service.request_enhancement(db, "enh-round", NOW)
    await _wait_state(coach_database, "current")
