"""Idempotent factual application outcome normalisation."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import Application
from ..models.application_outcome import ApplicationOutcome

STATUS_OUTCOMES = {
    "interview": "interview", "offered": "offer", "accepted": "accepted",
    "rejected": "rejected", "withdrawn": "withdrawn", "declined": "declined",
}


async def record_outcome(db: AsyncSession, application_id: str, outcome_type: str, occurred_at: datetime | None = None, *, source: str, metadata: dict | None = None) -> bool:
    occurred_at = occurred_at or datetime.utcnow()
    existing = await db.scalar(select(ApplicationOutcome).where(
        ApplicationOutcome.application_id == application_id,
        ApplicationOutcome.outcome_type == outcome_type,
    ))
    if existing:
        if occurred_at < existing.occurred_at:
            existing.occurred_at = occurred_at
            existing.source = source
            existing.metadata_json = metadata
            await db.flush()
        return False
    db.add(ApplicationOutcome(application_id=application_id, outcome_type=outcome_type, occurred_at=occurred_at, source=source, metadata_json=metadata))
    await db.flush()
    return True


async def record_status_outcome(db: AsyncSession, application_id: str, status: str, occurred_at: datetime | None = None) -> bool:
    outcome_type = STATUS_OUTCOMES.get(status)
    return False if outcome_type is None else await record_outcome(db, application_id, outcome_type, occurred_at, source="status_transition")


async def backfill_application_outcomes(db: AsyncSession, application_id: str) -> int:
    app = await db.get(Application, application_id)
    if app is None:
        return 0
    created = 0
    if app.response_received:
        created += int(await record_outcome(db, app.id, "recruiter_response", app.response_date or app.updated_at, source="backfill"))
    if app.status in STATUS_OUTCOMES:
        created += int(await record_outcome(db, app.id, STATUS_OUTCOMES[app.status], app.updated_at, source="backfill"))
    return created
