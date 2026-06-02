"""Tests for async_jobs router."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.async_job_service import AsyncJobService


@pytest.mark.asyncio
async def test_get_async_job_returns_job(client: AsyncClient, db_session):
    """GET /api/async-jobs/{id} returns the job as JSON."""
    job = await AsyncJobService.create(db_session, "tailor_analyse")
    await db_session.commit()

    response = await client.get(f"/api/async-jobs/{job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job.id
    assert data["type"] == "tailor_analyse"
    assert data["status"] == "pending"
    assert data["result"] is None
    assert data["error"] is None


@pytest.mark.asyncio
async def test_get_async_job_returns_404_for_unknown(client: AsyncClient):
    """GET /api/async-jobs/{id} returns 404 for a non-existent job."""
    response = await client.get("/api/async-jobs/no-such-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_async_jobs_returns_done_jobs(client: AsyncClient, db_session):
    """GET /api/async-jobs?status=done returns completed jobs."""
    job = await AsyncJobService.create(db_session, "email_generate")
    await db_session.commit()
    await AsyncJobService._finish(job.id, '{"subject": "Hi"}', None, db=db_session)

    response = await client.get("/api/async-jobs?status=done&limit=5")

    assert response.status_code == 200
    items = response.json()
    assert any(item["id"] == job.id for item in items)
