from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachInterviewDebrief
from app.services.coach_readiness.contracts import (
    DebriefQuestion,
    ReadinessError,
    SaveDebriefCommand,
)
from app.services.coach_readiness.debrief import DebriefService
from app.services.coach_readiness.next_actions import debrief_next_actions

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)


async def _seed(db: AsyncSession, *, active: bool = True) -> None:
    db.add(Application(id="app-1", status="interview", priority="normal", is_active=active))
    await db.flush()
    db.add(
        InterviewRound(
            id="round-1",
            application_id="app-1",
            round_number=1,
            type="behavioural",
            scheduled_at=(NOW - timedelta(hours=2)).replace(tzinfo=None),
            duration_minutes=60,
            status="scheduled",
        )
    )
    await db.flush()


def _question(index: int, text: str | None = None) -> DebriefQuestion:
    return DebriefQuestion(
        id=f"q{index}",
        text=text or f"Question {index}?",
        source_ref={"kind": "question_bank_item", "id": f"qb-{index}"},
        asked=index % 2 == 0,
        rating=3,
        story_id="story-1",
        note="One line.",
    )


@pytest.mark.asyncio
async def test_questions_capped_and_text_limits(db_session: AsyncSession) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    due = await service.get_or_due("round-1", NOW)
    assert due is not None

    with pytest.raises(ReadinessError) as too_many:
        await service.save(
            "round-1",
            SaveDebriefCommand(
                expected_version=due.version,
                overall=4,
                questions=[_question(index) for index in range(21)],
            ),
            NOW,
        )
    assert too_many.value.code == "invalid_input"

    with pytest.raises(ReadinessError):
        await service.save(
            "round-1",
            SaveDebriefCommand(
                expected_version=due.version,
                overall=4,
                questions=[_question(1, "x" * 201)],
            ),
            NOW,
        )
    with pytest.raises(ReadinessError):
        await service.save(
            "round-1",
            SaveDebriefCommand(
                expected_version=due.version,
                overall=4,
                went_well="x" * 1_001,
            ),
            NOW,
        )
    with pytest.raises(ReadinessError):
        await service.save(
            "round-1",
            SaveDebriefCommand(
                expected_version=due.version,
                overall=4,
                notes_text="x" * 2_501,
            ),
            NOW,
        )


@pytest.mark.asyncio
async def test_questions_json_item_shape(db_session: AsyncSession) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    due = await service.get_or_due("round-1", NOW)
    assert due is not None

    await service.save(
        "round-1",
        SaveDebriefCommand(
            expected_version=due.version,
            overall=4,
            questions=[_question(1)],
        ),
        NOW,
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(CoachInterviewDebrief).where(
                CoachInterviewDebrief.interview_round_id == "round-1"
            )
        )
    ).scalar_one()

    assert row.questions_json == [
        {
            "id": "q1",
            "text": "Question 1?",
            "source_ref": {"kind": "question_bank_item", "id": "qb-1"},
            "asked": False,
            "rating": 3,
            "story_id": "story-1",
            "note": "One line.",
        }
    ]


@pytest.mark.asyncio
async def test_save_merges_asked_questions_into_round(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    round_row = await db_session.get(InterviewRound, "round-1")
    round_row.questions_asked = ["Existing question"]
    await db_session.flush()

    service = DebriefService(db_session)
    due = await service.get_or_due("round-1", NOW)
    assert due is not None
    saved = await service.save(
        "round-1",
        SaveDebriefCommand(
            expected_version=due.version,
            overall=4,
            questions=[
                _question(0, "A"),
                _question(2, "existing  QUESTION"),
            ],
        ),
        NOW,
    )
    await db_session.flush()
    db_session.expire_all()
    round_row = await db_session.get(InterviewRound, "round-1")

    assert round_row.questions_asked == ["Existing question", "A"]

    await service.save(
        "round-1",
        SaveDebriefCommand(
            expected_version=saved.version,
            overall=4,
            questions=[],
        ),
        NOW,
    )
    await db_session.flush()
    db_session.expire_all()
    round_row = await db_session.get(InterviewRound, "round-1")

    assert round_row.questions_asked == ["Existing question", "A"]


@pytest.mark.asyncio
async def test_stale_edit_is_a_version_conflict(db_session: AsyncSession) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    due = await service.get_or_due("round-1", NOW)
    assert due is not None
    await service.save(
        "round-1",
        SaveDebriefCommand(expected_version=due.version, overall=4),
        NOW,
    )
    await db_session.flush()

    with pytest.raises(ReadinessError) as conflict:
        await service.save(
            "round-1",
            SaveDebriefCommand(expected_version=due.version, overall=5),
            NOW,
        )

    assert conflict.value.code == "version_conflict"


@pytest.mark.asyncio
async def test_concurrent_first_save_is_a_version_conflict(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(db_session)
    service = DebriefService(db_session)
    due = await service.get_or_due("round-1", NOW)
    assert due is not None
    await service.save(
        "round-1",
        SaveDebriefCommand(expected_version=due.version, overall=4),
        NOW,
    )
    await db_session.flush()

    async def no_row(_round_id: str):
        return None

    monkeypatch.setattr(service, "_row", no_row)
    with pytest.raises(ReadinessError) as conflict:
        await service.save(
            "round-1",
            SaveDebriefCommand(expected_version=0, overall=5),
            NOW,
        )

    assert conflict.value.code == "version_conflict"


@pytest.mark.asyncio
async def test_soft_deleted_application_never_due(db_session: AsyncSession) -> None:
    await _seed(db_session, active=False)

    service = DebriefService(db_session)

    assert await service.get_or_due("round-1", NOW) is None
    assert await debrief_next_actions(db_session, NOW) == []
