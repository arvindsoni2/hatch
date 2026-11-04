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
async def test_soft_deleted_application_never_due(db_session: AsyncSession) -> None:
    await _seed(db_session, active=False)

    service = DebriefService(db_session)

    assert await service.get_or_due("round-1", NOW) is None
    assert await debrief_next_actions(db_session, NOW) == []
