"""Integration tests for /api/jobs and /api/health router endpoints."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.job import JobPosting


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    """GET /api/health returns 200 with status ok."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_jobs_returns_200(client: AsyncClient) -> None:
    """GET /api/jobs returns 200 with paginated response."""
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_job_not_found_returns_404(client: AsyncClient) -> None:
    """GET /api/jobs/{id} returns 404 for unknown ID."""
    resp = await client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_returns_200_for_existing_job(
    client: AsyncClient, sample_job: JobPosting
) -> None:
    """GET /api/jobs/{id} returns 200 for a job that exists in the DB."""
    resp = await client.get(f"/api/jobs/{sample_job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_job.id
    assert data["title"] == sample_job.title


@pytest.mark.asyncio
async def test_patch_job_returns_200(
    client: AsyncClient, sample_job: JobPosting
) -> None:
    """PATCH /api/jobs/{id} updates sync_status and returns 200."""
    resp = await client.patch(
        f"/api/jobs/{sample_job.id}",
        json={"sync_status": "approved"},
    )
    assert resp.status_code == 200
    assert resp.json()["sync_status"] == "approved"


@pytest.mark.asyncio
async def test_delete_job_returns_200(
    client: AsyncClient, sample_job: JobPosting
) -> None:
    """DELETE /api/jobs/{id} soft-deletes a job and returns 200."""
    resp = await client.delete(f"/api/jobs/{sample_job.id}")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_jobs_with_status_filter(client: AsyncClient) -> None:
    """GET /api/jobs?sync_status=pending returns 200."""
    resp = await client.get("/api/jobs", params={"sync_status": "pending"})
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_stats_endpoint_returns_200(client: AsyncClient) -> None:
    """GET /api/jobs/stats returns 200 with count fields."""
    resp = await client.get("/api/jobs/stats")
    assert resp.status_code == 200
