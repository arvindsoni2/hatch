"""Router for polling background LLM jobs."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.async_job_service import AsyncJobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/async-jobs", tags=["async-jobs"])


class AsyncJobRead(BaseModel):
    id: str
    type: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime


def _to_read(job) -> AsyncJobRead:
    result = None
    if job.result_json:
        try:
            result = json.loads(job.result_json)
        except Exception:
            result = job.result_json
    return AsyncJobRead(
        id=job.id,
        type=job.type,
        status=job.status,
        result=result,
        error=job.error,
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=AsyncJobRead)
async def get_async_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> AsyncJobRead:
    """Return the current status and result of a background job."""
    job = await AsyncJobService.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_read(job)


@router.get("", response_model=list[AsyncJobRead])
async def list_async_jobs(
    status: str = Query("done"),
    since: Optional[str] = Query(None, description="ISO-8601 datetime; defaults to 24h ago"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[AsyncJobRead]:
    """List background jobs filtered by status. Used by the notification bell."""
    if since:
        since_dt = datetime.fromisoformat(since)
    else:
        since_dt = datetime.utcnow() - timedelta(hours=24)

    jobs = await AsyncJobService.list_completed_since(db, since_dt, limit=limit)
    return [_to_read(j) for j in jobs]
