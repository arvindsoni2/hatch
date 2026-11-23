"""Readiness next actions (debrief prompt only in P2)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachInterviewDebrief

from .debrief import _due


async def debrief_next_actions(db: AsyncSession, now: datetime) -> list[dict]:
    rows = (
        await db.execute(
            select(InterviewRound)
            .join(Application, Application.id == InterviewRound.application_id)
            .where(
                Application.is_active.is_(True),
                InterviewRound.status.in_(("completed", "scheduled", "rescheduled")),
            )
            .order_by(InterviewRound.scheduled_at.asc())
        )
    ).scalars().all()
    if not rows:
        rows = []
    saved = {
        item.interview_round_id: item.status
        for item in (
            await db.execute(
                select(CoachInterviewDebrief).where(
                    CoachInterviewDebrief.interview_round_id.in_(
                        [row.id for row in rows]
                    )
                )
            )
        ).scalars().all()
    }
    actions: list[dict] = []
    for row in rows:
        if saved.get(row.id) in {"saved", "skipped"}:
            continue
        if not _due(row, now):
            continue
        actions.append(
            {
                "application_id": row.application_id,
                "round_id": row.id,
                "action": "How did it go?",
                "reason": "Debrief due",
                "urgency": "high",
                "kind": "debrief",
            }
        )
    upcoming = (
        await db.execute(
            select(InterviewRound)
            .join(Application, Application.id == InterviewRound.application_id)
            .where(
                Application.is_active.is_(True),
                InterviewRound.status.in_(("scheduled", "rescheduled")),
                InterviewRound.scheduled_at.is_not(None),
                InterviewRound.scheduled_at > datetime.utcnow(),
            )
            .order_by(InterviewRound.scheduled_at.asc())
        )
    ).scalars().all()
    for row in upcoming:
        days = max(0, (row.scheduled_at - datetime.utcnow()).days)
        if days <= 7:
            actions.append({
                "application_id": row.application_id,
                "round_id": row.id,
                "action": f"Interview in {days} day{'s' if days != 1 else ''} — brief ready",
                "reason": "Pre-interview brief",
                "urgency": "high" if days <= 2 else "normal",
                "kind": "brief",
            })
    with_rounds = {
        row.application_id for row in upcoming
    }
    conditions = [
        Application.is_active.is_(True), Application.status == "interview"
    ]
    if with_rounds:
        conditions.append(~Application.id.in_(with_rounds))
    without_rounds = (
        await db.execute(select(Application).where(*conditions))
    ).scalars().all()
    for application in without_rounds:
        actions.append({
            "application_id": application.id,
            "round_id": "",
            "action": "Add your interview date to get a brief",
            "reason": "No interview round yet",
            "urgency": "normal",
            "kind": "brief",
        })
    return actions
