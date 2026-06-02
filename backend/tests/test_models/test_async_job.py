"""Tests for AsyncJob model."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.async_job import AsyncJob


@pytest.mark.asyncio
async def test_async_job_created_with_pending_status(db_session):
    """AsyncJob defaults to status=pending on creation."""
    job = AsyncJob(type="tailor_analyse")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.id is not None
    assert job.status == "pending"
    assert job.result_json is None
    assert job.error is None
    assert job.created_at is not None
    assert job.updated_at is not None


@pytest.mark.asyncio
async def test_async_job_type_stored_correctly(db_session):
    """AsyncJob.type is persisted and retrieved correctly."""
    job = AsyncJob(type="coach_session")
    db_session.add(job)
    await db_session.commit()

    result = await db_session.execute(select(AsyncJob).where(AsyncJob.id == job.id))
    fetched = result.scalar_one()
    assert fetched.type == "coach_session"
