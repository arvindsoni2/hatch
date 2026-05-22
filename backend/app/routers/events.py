"""FastAPI router for agent event management."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.agent_event import AgentEvent
from ..schemas.agent_events import AgentEventList, AgentEventRead

router = APIRouter(prefix="/api/events", tags=["events"])


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
