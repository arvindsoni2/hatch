"""Readiness brief enhancement jobs (spec §7.5)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import database
from app.config import settings
from app.models.application import Application, InterviewRound
from app.services.ai_setup import load_runtime

from .brief import request_enhancement


async def enhance_upcoming_rounds() -> int:
    if not settings.HATCH_COACH_BRIEF_ENABLED:
        return 0
    if load_runtime().get("ai_mode") not in {"local", "custom"}:
        return 0
    now = datetime.now(UTC)
    async with database.AsyncSessionLocal() as db:
        rounds = (
            await db.execute(
                select(InterviewRound)
                .join(Application, Application.id == InterviewRound.application_id)
                .where(
                    Application.is_active.is_(True),
                    InterviewRound.status.in_(("scheduled", "rescheduled")),
                    InterviewRound.scheduled_at.is_not(None),
                    InterviewRound.scheduled_at >= now.replace(tzinfo=None),
                    InterviewRound.scheduled_at
                    <= (now + timedelta(days=7)).replace(tzinfo=None),
                )
            )
        ).scalars().all()
        for round_row in rounds:
            await request_enhancement(db, round_row.id, now)
        return len(rounds)
