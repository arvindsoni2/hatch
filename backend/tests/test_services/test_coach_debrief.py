"""RED contract for P2: debrief status, round mirroring and transitions.

Written by Claude Code before implementation (plan §1.5). Tests go through
``DebriefService`` (spec §10.1) and the existing ``InterviewRepository``.
All data is synthetic.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application, InterviewRound
from app.repositories.interview_repository import InterviewRepository
from app.schemas.interview import InterviewRoundUpdate
from app.services.coach_readiness import debrief as debrief_module
from app.services.coach_readiness.contracts import (
    DebriefQuestion,
    ReadinessError,
    SaveDebriefCommand,
)
from app.services.coach_readiness.debrief import DebriefService

# Fixed clock. Stored round times are naive UTC (spec §7.5); ``now`` is aware UTC.
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _debrief_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)


async def _seed_round(
    db: AsyncSession,
    *,
    round_id: str,
    app_id: str = "app-1",
    status: str = "scheduled",
    starts: datetime | None = None,
    duration_minutes: int | None = None,
) -> None:
    if await db.get(Application, app_id) is None:
        db.add(Application(id=app_id, status="interview", priority="normal"))
        await db.flush()
    db.add(
        InterviewRound(
            id=round_id,
            application_id=app_id,
            round_number=1,
            type="behavioural",
            scheduled_at=_naive_utc(starts) if starts is not None else None,
            duration_minutes=duration_minutes,
            status=status,
        )
    )
    await db.flush()


def _question(qid: str, text: str, *, asked: bool) -> DebriefQuestion:
    return DebriefQuestion(
        id=qid,
        text=text,
        source_ref=None,
        asked=asked,
        rating=None,
        story_id=None,
        note=None,
    )


def _command(
    expected_version: int,
    *,
    overall: int = 4,
    questions: list[DebriefQuestion] | None = None,
    went_well: str | None = None,
) -> SaveDebriefCommand:
    return SaveDebriefCommand(
        expected_version=expected_version,
        overall=overall,
        expectation="unsure",
        questions=questions or [],
        went_well=went_well,
        do_differently=None,
        notes_text=None,
    )


async def _reload_round(db: AsyncSession, round_id: str) -> InterviewRound:
    db.expire_all()
    row = (
        await db.execute(select(InterviewRound).where(InterviewRound.id == round_id))
    ).scalar_one()
    return row


@pytest.mark.asyncio
async def test_debrief_due_when_completed_or_time_passed(db_session: AsyncSession) -> None:
    # Completed round: due even though its scheduled time is still ahead.
    await _seed_round(
        db_session,
        round_id="completed-early",
        status="completed",
        starts=NOW + timedelta(hours=3),
    )
    # Scheduled, no duration: default 60 minutes has passed.
    await _seed_round(
        db_session, round_id="scheduled-default-passed", starts=NOW - timedelta(minutes=61)
    )
    # Scheduled, no duration: still inside the default 60 minutes.
    await _seed_round(
        db_session, round_id="scheduled-default-running", starts=NOW - timedelta(minutes=59)
    )
    # Explicit duration is honoured instead of the default.
    await _seed_round(
        db_session,
        round_id="scheduled-long-running",
        starts=NOW - timedelta(minutes=61),
        duration_minutes=90,
    )
    # Rescheduled rounds become due the same way as scheduled ones.
    await _seed_round(
        db_session,
        round_id="rescheduled-passed",
        status="rescheduled",
        starts=NOW - timedelta(minutes=31),
        duration_minutes=30,
    )
    # Future scheduled round: not due.
    await _seed_round(
        db_session, round_id="scheduled-future", starts=NOW + timedelta(days=2)
    )

    service = DebriefService(db_session)

    for round_id in ("completed-early", "scheduled-default-passed", "rescheduled-passed"):
        read = await service.get_or_due(round_id, NOW)
        assert read is not None, round_id
        assert read.status == "due", round_id

    for round_id in (
        "scheduled-default-running",
        "scheduled-long-running",
        "scheduled-future",
    ):
        assert await service.get_or_due(round_id, NOW) is None, round_id


@pytest.mark.asyncio
async def test_cancelled_round_never_due_saved_debrief_kept(db_session: AsyncSession) -> None:
    await _seed_round(
        db_session,
        round_id="cancelled-past",
        status="cancelled",
        starts=NOW - timedelta(days=1),
    )
    await _seed_round(
        db_session, round_id="saved-then-cancelled", starts=NOW - timedelta(hours=3)
    )
    service = DebriefService(db_session)

    assert await service.get_or_due("cancelled-past", NOW) is None
    with pytest.raises(ReadinessError) as skipped_cancelled:
        await service.skip("cancelled-past", 0, NOW)
    assert skipped_cancelled.value.code == "invalid_state"

    due = await service.get_or_due("saved-then-cancelled", NOW)
    assert due is not None and due.status == "due"
    saved = await service.save(
        "saved-then-cancelled",
        _command(due.version, overall=2, went_well="Clear opening answer."),
        NOW,
    )
    assert saved.status == "saved"
    await db_session.commit()

    await InterviewRepository(db_session).update(
        "saved-then-cancelled", InterviewRoundUpdate(status="cancelled")
    )
    await db_session.commit()
    db_session.expire_all()

    kept = await service.get_or_due("saved-then-cancelled", NOW + timedelta(hours=1))
    assert kept is not None
    assert kept.status == "saved"
    assert kept.overall == 2
    assert kept.went_well == "Clear opening answer."
    assert kept.version == saved.version


@pytest.mark.asyncio
async def test_rescheduled_round_moves_due_time(db_session: AsyncSession) -> None:
    original_start = NOW - timedelta(hours=2)
    await _seed_round(
        db_session, round_id="moved", starts=original_start, duration_minutes=45
    )
    service = DebriefService(db_session)
    assert (await service.get_or_due("moved", NOW)) is not None

    new_start = NOW + timedelta(days=2)
    await InterviewRepository(db_session).update(
        "moved",
        InterviewRoundUpdate(scheduled_at=_naive_utc(new_start), status="rescheduled"),
    )
    await db_session.commit()
    db_session.expire_all()

    # The old end time has passed, but the round now ends later: not due.
    assert await service.get_or_due("moved", NOW) is None
    assert (
        await service.get_or_due("moved", new_start + timedelta(minutes=44)) is None
    )
    due = await service.get_or_due("moved", new_start + timedelta(minutes=46))
    assert due is not None and due.status == "due"


@pytest.mark.asyncio
async def test_save_mirrors_questions_into_round_via_repository(
    db_session: AsyncSession,
) -> None:
    await _seed_round(
        db_session, round_id="mirror", starts=NOW - timedelta(hours=2), duration_minutes=60
    )
    service = DebriefService(db_session)
    due = await service.get_or_due("mirror", NOW)
    assert due is not None

    saved = await service.save(
        "mirror",
        _command(
            due.version,
            questions=[
                _question("q1", "Tell me about a budget you owned.", asked=True),
                _question("q2", "Why this company?", asked=False),
                _question("q3", "Describe a stakeholder conflict.", asked=True),
            ],
        ),
        NOW,
    )
    await db_session.commit()

    assert saved.status == "saved"
    assert [item.text for item in saved.questions] == [
        "Tell me about a budget you owned.",
        "Why this company?",
        "Describe a stakeholder conflict.",
    ]
    round_row = await _reload_round(db_session, "mirror")
    assert round_row.questions_asked == [
        "Tell me about a budget you owned.",
        "Describe a stakeholder conflict.",
    ]
    assert round_row.status == "completed"

    # AC16: the round is written only through the interview repository.
    source = Path(debrief_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names: set[str] = set()
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
    assert "InterviewRound" not in imported_names
    assert "interview_rounds" not in source
    assert any(module.endswith("interview_repository") for module in imported_modules)


@pytest.mark.asyncio
async def test_skip_then_start_later(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    await _seed_round(
        db_session, round_id="skip-me", starts=NOW - timedelta(hours=2), duration_minutes=60
    )
    await _seed_round(
        db_session, round_id="not-yet", starts=NOW + timedelta(days=1), duration_minutes=60
    )
    service = DebriefService(db_session)

    due = await service.get_or_due("skip-me", NOW)
    assert due is not None and due.status == "due"

    skipped = await service.skip("skip-me", due.version, NOW)
    assert skipped.status == "skipped"
    await db_session.commit()
    assert (await service.get_or_due("skip-me", NOW)).status == "skipped"

    # skipped -> skipped is not a transition.
    with pytest.raises(ReadinessError) as twice:
        await service.skip("skip-me", skipped.version, NOW)
    assert twice.value.code == "invalid_state"

    # "Start later": a skipped debrief can still be filled in and saved.
    saved = await service.save("skip-me", _command(skipped.version, overall=3), NOW)
    assert saved.status == "saved"
    assert saved.overall == 3
    await db_session.commit()

    # saved -> skipped is not a transition.
    with pytest.raises(ReadinessError) as after_save:
        await service.skip("skip-me", saved.version, NOW)
    assert after_save.value.code == "invalid_state"

    # A round that is not due cannot be skipped.
    with pytest.raises(ReadinessError) as early:
        await service.skip("not-yet", 0, NOW)
    assert early.value.code == "invalid_state"

    # Over HTTP an illegal transition is 409 invalid_state (spec §12).
    response = await client.post(
        "/api/coach/readiness/rounds/skip-me/debrief/skip",
        json={"expected_version": saved.version},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_state"
