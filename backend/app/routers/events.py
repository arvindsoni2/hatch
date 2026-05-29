"""FastAPI router for agent event management and activity timeline."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.agent_event import AgentEvent
from ..models.cost_tracking import CostTracking
from ..schemas.agent_events import AgentEventList, AgentEventRead

router = APIRouter(prefix="/api/events", tags=["events"])


# ── Activity timeline schemas ─────────────────────────────────────────────────

class ActivityItem(BaseModel):
    id: str
    timestamp: datetime
    agent: str
    event_type: str
    status: str
    title: str
    detail: str | None = None
    job_id: str | None = None
    cost_estimate: float | None = None
    model_used: str | None = None


class ActivityList(BaseModel):
    items: list[ActivityItem]
    total: int


# ── Human-readable event message builders ────────────────────────────────────

def _humanise(event: AgentEvent) -> ActivityItem:
    raw = event.payload or {}
    if isinstance(raw, str):
        import json  # noqa: PLC0415
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    payload: dict[str, Any] = raw
    agent = event.source_agent or "system"
    etype = event.event_type
    job_id: str | None = payload.get("job_id")

    title_map = {
        "job_discovered": lambda p: f"Scout discovered: {p.get('title', 'job')} at {p.get('company', '?')}",
        "scrape_complete": lambda p: (
            f"Scout scrape complete — {p.get('jobs_found', 0)} found, "
            f"{p.get('jobs_new', 0)} new from {p.get('source', '?')}"
        ),
        "scrape_error": lambda p: f"Scout error on {p.get('source', '?')}: {p.get('error', '')}",
        "job_scored": lambda p: (
            f"Scorer evaluated: {p.get('title', payload.get('job_id', '?'))} — "
            f"{round(p.get('score', 0) * 100)}% match"
        ),
        "job_shortlisted": lambda p: f"Shortlisted: score {round(p.get('score', 0) * 100)}% ≥ threshold",
        "cv_tailored": lambda p: f"Tailor generated CV + cover letter — ATS score: {p.get('ats_score', '?')}%",
        "application_approved": lambda p: "Application approved",
        "application_rejected": lambda p: "Application rejected",
    }
    title_fn = title_map.get(etype, lambda p: etype.replace("_", " ").title())
    title = title_fn(payload)

    detail: str | None = None
    if etype == "job_scored" and payload.get("reasoning"):
        detail = payload["reasoning"][:200]
    elif event.error_message:
        detail = event.error_message[:200]

    return ActivityItem(
        id=event.id,
        timestamp=event.created_at,
        agent=agent,
        event_type=etype,
        status=event.status,
        title=title,
        detail=detail,
        job_id=job_id,
        cost_estimate=payload.get("cost_estimate"),
        model_used=payload.get("model_used"),
    )


# ── Activity timeline endpoint ────────────────────────────────────────────────

@router.get("/activity", response_model=ActivityList)
async def get_activity(
    limit: int = Query(20, le=100),
    hours: int = Query(24, le=168),
    db: AsyncSession = Depends(get_db),
) -> ActivityList:
    """Return a human-readable timeline of recent agent actions."""
    since = datetime.utcnow() - timedelta(hours=hours)
    stmt = (
        select(AgentEvent)
        .where(AgentEvent.created_at >= since)
        .order_by(AgentEvent.created_at.desc())
        .limit(limit)
    )
    count_stmt = select(AgentEvent).where(AgentEvent.created_at >= since)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    total = len(rows)

    return ActivityList(items=[_humanise(r) for r in rows], total=total)


# ── Cost summary endpoint ─────────────────────────────────────────────────────

class CostSummary(BaseModel):
    total_cost_usd: float
    by_agent: dict[str, float]
    total_calls: int


@router.get("/costs", response_model=CostSummary)
async def get_cost_summary(
    days: int = Query(30, le=365),
    db: AsyncSession = Depends(get_db),
) -> CostSummary:
    """Return LLM cost summary for the last N days."""
    from sqlalchemy import func
    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(CostTracking.agent_name, func.sum(CostTracking.cost_estimate), func.count())
        .where(CostTracking.created_at >= since)
        .group_by(CostTracking.agent_name)
    )
    by_agent: dict[str, float] = {}
    total_calls = 0
    total_cost = 0.0
    for agent_name, cost, count in result.all():
        by_agent[agent_name] = round(cost or 0.0, 4)
        total_cost += cost or 0.0
        total_calls += count or 0
    return CostSummary(total_cost_usd=round(total_cost, 4), by_agent=by_agent, total_calls=total_calls)


@router.get("", response_model=AgentEventList)
async def list_events(
    event_type: str | None = Query(None),
    status: str | None = Query(None),
    source_agent: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AgentEventList:
    """List agent events with optional filters."""
    from sqlalchemy import func

    stmt = select(AgentEvent).order_by(AgentEvent.created_at.desc())
    count_stmt = select(func.count()).select_from(AgentEvent)

    if event_type:
        stmt = stmt.where(AgentEvent.event_type == event_type)
        count_stmt = count_stmt.where(AgentEvent.event_type == event_type)
    if status:
        stmt = stmt.where(AgentEvent.status == status)
        count_stmt = count_stmt.where(AgentEvent.status == status)
    if source_agent:
        stmt = stmt.where(AgentEvent.source_agent == source_agent)
        count_stmt = count_stmt.where(AgentEvent.source_agent == source_agent)

    total = (await db.execute(count_stmt)).scalar_one() or 0
    result = await db.execute(stmt.limit(limit).offset(offset))
    rows = result.scalars().all()

    return AgentEventList(
        items=[AgentEventRead.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/{event_id}", response_model=AgentEventRead)
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> AgentEventRead:
    """Get a single event by ID."""
    result = await db.execute(select(AgentEvent).where(AgentEvent.id == event_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return AgentEventRead.model_validate(row)


@router.post("/{event_id}/retry")
async def retry_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Reset a failed event to pending so it can be reprocessed."""
    result = await db.execute(select(AgentEvent).where(AgentEvent.id == event_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if row.status != "failed":
        raise HTTPException(status_code=409, detail=f"Event status is '{row.status}', not 'failed'")

    await db.execute(
        update(AgentEvent)
        .where(AgentEvent.id == event_id)
        .values(status="pending", error_message=None, processed_at=None)
    )
    await db.commit()
    return {"event_id": event_id, "status": "pending"}
