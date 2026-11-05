"""RED contract for P2: debrief deletion cascades (AC17, AC18).

Written by Claude Code before implementation (plan §1.5). File-backed SQLite with
foreign keys on; every assertion reads durable rows from a fresh session.
All data is synthetic.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachCompetencyOverride
from app.models.coach_session import InterviewSession
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.repositories.interview_repository import InterviewRepository
from app.services.coach_privacy import CoachPrivacyService
from app.services.coach_privacy_queue import _process_hard_deletion
from app.services.coach_readiness.contracts import DebriefQuestion, SaveDebriefCommand
from app.services.coach_readiness.debrief import DebriefService
from test_coach_report_privacy_flow import deletion_request, synthetic_session

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _debrief_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)


async def _seed_saved_debrief(factory, *, app_id: str, round_id: str) -> None:
    async with factory() as db:
        db.add(Application(id=app_id, status="interview", priority="normal"))
        await db.flush()
        db.add(
            InterviewRound(
                id=round_id,
                application_id=app_id,
                round_number=1,
                type="behavioural",
                scheduled_at=(NOW - timedelta(hours=3)).replace(tzinfo=None),
                duration_minutes=60,
                status="scheduled",
            )
        )
        await db.commit()

        service = DebriefService(db)
        due = await service.get_or_due(round_id, NOW)
        assert due is not None
        await service.save(
            round_id,
            SaveDebriefCommand(
                expected_version=due.version,
                overall=4,
                expectation="yes",
                questions=[
                    DebriefQuestion(
                        id="q1",
                        text="Walk me through a delivery you rescued.",
                        source_ref=None,
                        asked=True,
                        rating=4,
                        story_id=None,
                        note=None,
                    )
                ],
                went_well="Kept answers short.",
                do_differently="Lead with the result.",
                notes_text=None,
            ),
            NOW,
        )
        await db.commit()


async def _debrief_count(factory, round_id: str | None = None) -> int:
    async with factory() as db:
        if round_id is None:
            result = await db.execute(text("SELECT count(*) FROM coach_interview_debriefs"))
        else:
            result = await db.execute(
                text(
                    "SELECT count(*) FROM coach_interview_debriefs "
                    "WHERE interview_round_id = :round_id"
                ),
                {"round_id": round_id},
            )
        return int(result.scalar_one())


async def test_round_delete_cascades_debrief(coach_database) -> None:
    await _seed_saved_debrief(coach_database, app_id="app-round", round_id="round-1")
    assert await _debrief_count(coach_database, "round-1") == 1

    async with coach_database() as db:
        assert await InterviewRepository(db).delete("round-1") is True
        await db.commit()

    assert await _debrief_count(coach_database, "round-1") == 0
    assert await _debrief_count(coach_database) == 0
    async with coach_database() as db:
        assert await db.get(Application, "app-round") is not None


async def test_application_delete_leaves_no_orphans(coach_database) -> None:
    await _seed_saved_debrief(coach_database, app_id="app-gone", round_id="round-gone")
    async with coach_database() as db:
        db.add(
            CoachCompetencyOverride(
                application_id="app-gone", original="Budget ownership", hidden=True
            )
        )
        await db.commit()

    # Physical deletion of the application row (the soft delete in
    # routers/applications.py removes nothing and is out of scope here).
    async with coach_database() as db:
        application = (
            await db.execute(
                select(Application)
                .options(selectinload(Application.interviews))
                .where(Application.id == "app-gone")
            )
        ).scalar_one()
        await db.delete(application)
        await db.commit()

    assert await _debrief_count(coach_database) == 0
    async with coach_database() as db:
        rounds = await db.execute(
            text("SELECT count(*) FROM interview_rounds WHERE application_id = 'app-gone'")
        )
        overrides = await db.execute(
            text(
                "SELECT count(*) FROM coach_competency_overrides "
                "WHERE application_id = 'app-gone'"
            )
        )
        orphans = await db.execute(
            text(
                "SELECT count(*) FROM coach_interview_debriefs d "
                "LEFT JOIN interview_rounds r ON r.id = d.interview_round_id "
                "WHERE r.id IS NULL"
            )
        )
        assert rounds.scalar_one() == 0
        assert overrides.scalar_one() == 0
        assert orphans.scalar_one() == 0


async def test_practice_session_delete_keeps_debrief(coach_database) -> None:
    await _seed_saved_debrief(coach_database, app_id="app-practice", round_id="round-p")
    async with coach_database() as db:
        db.add(synthetic_session(id="practice-1", application_id="app-practice"))
        await db.commit()
        claim = await CoachPrivacyService(
            ConversationalSessionRepository(db)
        ).claim_hard_deletion("practice-1", deletion_request(), now=datetime.utcnow())
        await db.commit()

    # The real hard-deletion worker, on its own session.
    await _process_hard_deletion(claim)

    async with coach_database() as db:
        assert await db.get(InterviewSession, "practice-1") is None
        service = DebriefService(db)
        kept = await service.get_or_due("round-p", NOW)
        assert kept is not None
        assert kept.status == "saved"
        assert kept.overall == 4
        assert kept.went_well == "Kept answers short."
        assert [item.text for item in kept.questions] == [
            "Walk me through a delivery you rescued."
        ]
    assert await _debrief_count(coach_database, "round-p") == 1
