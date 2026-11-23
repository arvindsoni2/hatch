"""Readiness brief scheduler gates (spec §7.5)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import database
from app.config import settings
from app.database import Base, create_sqlite_engine
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachInterviewBrief
from app.services import coach_reconciliation
from app.services.coach_readiness import brief as brief_service
from app.services.coach_readiness import scheduler


@pytest_asyncio.fixture
async def factory(tmp_path, monkeypatch):
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'scheduler.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(coach_reconciliation, "AsyncSessionLocal", session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield session_factory
    finally:
        await engine.dispose()


async def _seed(factory):
    now = datetime.utcnow()
    async with factory() as db:
        db.add(Application(id="app", status="interview", priority="normal"))
        await db.flush()
        db.add_all([
            InterviewRound(id="soon", application_id="app", round_number=1,
                           type="behavioural", scheduled_at=now + timedelta(days=3),
                           status="scheduled"),
            InterviewRound(id="later", application_id="app", round_number=2,
                           type="behavioural", scheduled_at=now + timedelta(days=15),
                           status="scheduled"),
        ])
        await db.commit()


@pytest.mark.asyncio
async def test_scheduler_enhances_rounds_in_next_seven_days_only(
    factory, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)
    await _seed(factory)
    calls: list[str] = []

    async def fake(_db, round_id, _now):
        calls.append(round_id)

    monkeypatch.setattr(scheduler, "request_enhancement", fake)
    await scheduler.enhance_upcoming_rounds()
    assert calls == ["soon"]


@pytest.mark.asyncio
async def test_scheduler_skips_when_flag_or_ai_is_off(factory, monkeypatch) -> None:
    await _seed(factory)
    calls: list[str] = []

    async def fake(_db, round_id, _now):
        calls.append(round_id)

    monkeypatch.setattr(scheduler, "request_enhancement", fake)
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", False)
    await scheduler.enhance_upcoming_rounds()
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)
    monkeypatch.setattr(scheduler, "load_runtime", lambda: {"ai_mode": "none"})
    await scheduler.enhance_upcoming_rounds()
    assert calls == []


@pytest.mark.asyncio
async def test_scheduler_requeues_stale_enhancing_row(factory, monkeypatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)
    await _seed(factory)
    async with factory() as db:
        db.add(CoachInterviewBrief(
            interview_round_id="soon", enhancement_state="enhancing",
        ))
        await db.commit()
    # A restart left the row enhancing with nothing in flight.
    monkeypatch.setattr(brief_service, "_INFLIGHT", set())
    monkeypatch.setattr(scheduler, "load_runtime", lambda: {"ai_mode": "local"})
    monkeypatch.setattr(brief_service, "load_runtime", lambda: {"ai_mode": "local"})
    started: list[str] = []

    async def fake_run(round_id, context, key):
        started.append(round_id)

    monkeypatch.setattr(brief_service, "_run_enhancement", fake_run)

    await scheduler.enhance_upcoming_rounds()

    assert started == ["soon"]
