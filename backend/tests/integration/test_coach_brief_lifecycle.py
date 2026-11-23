"""Brief scheduler lifecycle (spec §7.5)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models.application import Application, InterviewRound
from app.services.coach_readiness import scheduler


@pytest.mark.asyncio
async def test_scheduler_enhances_rounds_in_next_seven_days_only(
    coach_database, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_BRIEF_ENABLED", True)
    now = datetime.utcnow()
    async with coach_database() as db:
        db.add(Application(id="sched-app", status="interview", priority="normal"))
        await db.flush()
        db.add_all(
            [
                InterviewRound(
                    id="soon", application_id="sched-app", round_number=1,
                    type="behavioural", scheduled_at=now + timedelta(days=3),
                    status="scheduled",
                ),
                InterviewRound(
                    id="later", application_id="sched-app", round_number=2,
                    type="behavioural", scheduled_at=now + timedelta(days=15),
                    status="scheduled",
                ),
            ]
        )
        await db.commit()
    calls: list[str] = []

    async def fake(db, round_id, now):
        calls.append(round_id)
        return None

    monkeypatch.setattr(scheduler, "request_enhancement", fake)

    await scheduler.enhance_upcoming_rounds()

    assert calls == ["soon"]
