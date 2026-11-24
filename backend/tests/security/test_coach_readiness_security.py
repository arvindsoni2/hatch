"""RED contract for P9: request validation on every readiness write (spec §12).

Written by Claude Code before implementation (plan §1.5). "Request text limits as
stated per feature; unknown fields rejected." Each rejected request must leave
every Phase 2 table unchanged. The memory routes are new in P9: an unknown kind,
or the derived "patterns" row (which has no delete of its own, §7.8), is invalid
input. All data is synthetic.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

sys.path.insert(0, str(Path(__file__).parents[1] / "integration"))

from app import database  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import Base, create_sqlite_engine  # noqa: E402
from app.models.application import Application, InterviewRound  # noqa: E402
from app.models.coach_readiness import CoachFocusArea, CoachPracticePlan  # noqa: E402
from app.models.job import JobPosting  # noqa: E402
from coach_readiness_support import READINESS, client_for  # noqa: E402

PHASE2_TABLES = (
    "coach_pattern_dismissals",
    "coach_focus_areas",
    "coach_practice_plans",
    "coach_interview_briefs",
    "coach_interview_debriefs",
    "coach_derived_text",
    "coach_derived_sources",
    "coach_competency_overrides",
)
FLAGS = (
    "HATCH_COACH_READINESS_ENABLED",
    "HATCH_COACH_BRIEF_ENABLED",
    "HATCH_COACH_DEBRIEF_ENABLED",
    "HATCH_COACH_STORY_COVERAGE_ENABLED",
)

FOCUS = {
    "title": "Make answers specific",
    "dimension": "specificity",
    "criteria": [{"kind": "practice", "count": 1}],
}
DEBRIEF = {"expected_version": 0, "overall": 4}
QUESTION = {"id": "sec-q1", "text": "How do you plan a release?", "asked": True}


@pytest_asyncio.fixture
async def coach_database(tmp_path, monkeypatch):
    """File-backed synthetic database behind the real ``get_db``."""
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'security.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield factory
    finally:
        await engine.dispose()


def _app() -> FastAPI:
    from app.routers.coach_readiness import router

    app = FastAPI()
    app.include_router(router)
    return app


async def _counts(factory) -> dict[str, int]:
    async with factory() as db:
        return {
            table: int((await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())
            for table in PHASE2_TABLES
        }


async def _seed(factory) -> None:
    async with factory() as db:
        db.add(JobPosting(
            id="sec-job", title="Delivery Lead", company="Synthetic Energy",
            url="https://example.test/sec", source="synthetic", description="Lead delivery.",
        ))
        await db.flush()
        db.add(Application(id="sec-app", job_id="sec-job", status="interview", priority="normal"))
        await db.flush()
        db.add(InterviewRound(
            id="sec-round", application_id="sec-app", round_number=1, type="behavioural",
            scheduled_at=datetime.utcnow() - timedelta(days=1), duration_minutes=60,
            status="completed",
        ))
        db.add(CoachFocusArea(
            id="sec-focus", status="active", active_slot=1, title="Synthetic focus",
            dimension="specificity", criteria_json=[{"kind": "practice", "count": 1}],
        ))
        db.add(CoachPracticePlan(
            id="sec-plan", status="draft", minutes=30,
            items_json=[{"id": "sec-item", "type": "practice_session", "status": "todo"}],
        ))
        await db.commit()


# (method, path, json body) → each must be rejected with 422.
UNKNOWN_FIELDS = [
    ("POST", "/focus-areas", {**FOCUS, "unexpected": True}),
    ("POST", "/focus-areas", {**FOCUS, "criteria": [{"kind": "practice", "count": 1, "extra": 1}]}),
    ("PATCH", "/focus-areas/sec-focus", {"expected_version": 1, "title": "New", "owner": "x"}),
    ("POST", "/plans", {"minutes": 30, "unexpected": True}),
    ("PATCH", "/plans/sec-plan/items/sec-item", {"expected_version": 1, "action": "done", "x": 1}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "unexpected": True}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "questions": [{**QUESTION, "extra": 1}]}),
    ("POST", "/rounds/sec-round/debrief/skip", {"expected_version": 0, "unexpected": True}),
    ("PUT", "/coverage/sec-app/overrides", {"overrides": [], "unexpected": True}),
    ("PUT", "/coverage/sec-app/overrides", {"overrides": [{"original": "delivery", "x": 1}]}),
]

OVERSIZE_TEXT = [
    ("POST", "/focus-areas", {**FOCUS, "title": "t" * 81}),
    ("PATCH", "/focus-areas/sec-focus", {"expected_version": 1, "title": "t" * 81}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "notes_text": "n" * 2_501}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "went_well": "w" * 1_001}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "do_differently": "d" * 1_001}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "questions": [{**QUESTION, "text": "q" * 201}]}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "questions": [{**QUESTION, "note": "q" * 201}]}),
    ("PUT", "/rounds/sec-round/debrief", {**DEBRIEF, "questions": [QUESTION] * 21}),
    ("PUT", "/coverage/sec-app/overrides", {"overrides": [{"original": "o" * 201}]}),
    ("PUT", "/coverage/sec-app/overrides", {"overrides": [{"original": "o", "replacement": "r" * 201}]}),
]

BAD_MEMORY_KINDS = ["patterns", "sessions", "everything", "DEBRIEFS"]


async def test_api_rejects_unknown_fields_and_oversize_text(
    coach_database, tmp_path, monkeypatch
) -> None:
    config = tmp_path / "ai-off"
    config.mkdir()
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(config))
    for flag in FLAGS:
        monkeypatch.setattr(settings, flag, True)
    await _seed(coach_database)
    before = await _counts(coach_database)

    async with client_for(_app()) as client:
        for method, path, body in UNKNOWN_FIELDS + OVERSIZE_TEXT:
            response = await client.request(method, f"{READINESS}{path}", json=body)
            assert response.status_code == 422, (method, path, response.status_code, response.text)

        # P9 memory routes: the kind is a closed set (§7.8, §10.1 MemoryKind).
        listing = await client.get(f"{READINESS}/memory")
        assert listing.status_code == 200, listing.text
        for kind in BAD_MEMORY_KINDS:
            response = await client.delete(f"{READINESS}/memory/{kind}")
            assert response.status_code == 422, (kind, response.status_code, response.text)

    assert await _counts(coach_database) == before
