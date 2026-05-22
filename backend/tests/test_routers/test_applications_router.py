"""Integration tests for /api/applications router."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.job import JobPosting


# ──────────────────────── Helpers ────────────────────────


async def _insert_job(db_session: AsyncSession) -> JobPosting:
    """Insert a minimal JobPosting for FK tests."""
    job = JobPosting(
        id=str(uuid.uuid4()),
        title="Solutions Architect",
        company="Test Corp",
        location="London",
        url=f"https://example.com/jobs/{uuid.uuid4()}",
        source="reed",
        scraped_at=datetime.utcnow(),
        is_active=True,
        sync_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


async def _insert_app(
    db_session: AsyncSession,
    status: str = "discovered",
    job_id: str | None = None,
) -> Application:
    """Insert a minimal Application for test setup."""
    app = Application(
        id=str(uuid.uuid4()),
        job_id=job_id,
        status=status,
        priority="normal",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


# ──────────────────────── Tests ────────────────────────


@pytest.mark.asyncio
async def test_create_application_returns_201(client: AsyncClient) -> None:
    """POST /api/applications returns 201 and the new application payload."""
    payload = {"status": "discovered", "priority": "normal", "agency_name": "Acme"}
    response = await client.post("/api/applications/", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "discovered"
    assert data["agency_name"] == "Acme"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_application_404(client: AsyncClient) -> None:
    """GET /api/applications/{id} returns 404 for a non-existent application."""
    fake_id = str(uuid.uuid4())
    response = await client.get(f"/api/applications/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_kanban_returns_grouped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/applications/kanban returns a response with 'columns' and 'stats'."""
    await _insert_app(db_session, status="discovered")
    await _insert_app(db_session, status="applied")

    response = await client.get("/api/applications/kanban")
    assert response.status_code == 200
    data = response.json()
    assert "columns" in data
    assert "stats" in data
    assert "discovered" in data["columns"]
    assert "applied" in data["columns"]


@pytest.mark.asyncio
async def test_track_from_job_returns_201(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """POST /api/applications/from-job/{job_id} creates a discovered application."""
    job = await _insert_job(db_session)
    response = await client.post(f"/api/applications/from-job/{job.id}")

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == job.id
    assert data["status"] == "discovered"


@pytest.mark.asyncio
async def test_track_from_job_duplicate_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tracking the same job twice returns HTTP 400."""
    job = await _insert_job(db_session)
    await _insert_app(db_session, job_id=job.id)

    response = await client.post(f"/api/applications/from-job/{job.id}")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_status_valid_transition(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH /api/applications/{id}/status with a valid transition returns 200."""
    app = await _insert_app(db_session, status="discovered")
    payload = {"status": "shortlisted"}
    response = await client.patch(f"/api/applications/{app.id}/status", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "shortlisted"


@pytest.mark.asyncio
async def test_update_status_invalid_transition_returns_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """PATCH /api/applications/{id}/status with a disallowed transition returns 422."""
    app = await _insert_app(db_session, status="discovered")
    # discovered → interview is not a valid one-step transition
    payload = {"status": "interview"}
    response = await client.patch(f"/api/applications/{app.id}/status", json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_content_type(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /api/applications/export?format=csv returns text/csv content-type."""
    await _insert_app(db_session, status="applied")
    response = await client.get("/api/applications/export?format=csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
