"""Integration tests for the Hatch v4 two-step assisted-apply endpoints.

New endpoints under test:
  POST /api/jobs/{job_id}/approve          → ready_to_apply + returns package
  GET  /api/applications/{app_id}/package  → package JSON (re-openable)
  POST /api/applications/{app_id}/mark-applied  → applied
  POST /api/applications/{app_id}/reject   → rejected
  POST /api/applications/{app_id}/revert   → ready_to_apply → ready

Iron Law: all tests written RED before any production code added.
test_no_autonomous_submission stays green throughout.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.job import JobPosting
from app.services.assisted_apply import ApplicationPackage


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _insert_job(
    db: AsyncSession,
    url: str | None = None,
) -> JobPosting:
    job = JobPosting(
        id=str(uuid.uuid4()),
        title="Solutions Architect",
        company="Acme Corp",
        location="London",
        url=url or f"https://boards.greenhouse.io/acme/jobs/{uuid.uuid4()}",
        source="reed",
        scraped_at=datetime.utcnow(),
        is_active=True,
        sync_status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def _insert_app(
    db: AsyncSession,
    job_id: str | None = None,
    status: str = "ready",
) -> Application:
    app = Application(
        id=str(uuid.uuid4()),
        job_id=job_id,
        status=status,
        priority="normal",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


def _mock_package(job_id: str = "job-123", job_url: str = "https://greenhouse.io/jobs/1") -> ApplicationPackage:
    return ApplicationPackage(
        job_id=job_id,
        job_url=job_url,
        cv_path="/tmp/cv.docx",
        cover_letter_path="/tmp/cl.docx",
        prefill_map={"name": "Arvind Soni", "email": "arvind@example.com"},
        screening_answers={"work_authorisation": "British Citizen", "notice_period": "Immediately available."},
        paste_map={"First Name": "Arvind", "Last Name": "Soni", "Email Address": "arvind@example.com"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/jobs/{job_id}/approve
# ─────────────────────────────────────────────────────────────────────────────


class TestApproveJobEndpoint:

    @pytest.mark.asyncio
    async def test_approve_returns_202(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST /api/jobs/{job_id}/approve returns 202 (async fire-and-forget)."""
        job = await _insert_job(db_session)

        resp = await client.post(f"/api/jobs/{job.id}/approve")

        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_approve_sets_application_status_to_preparing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST approve immediately moves Application.status to 'preparing'."""

        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready")

        resp = await client.post(f"/api/jobs/{job.id}/approve")

        assert resp.status_code == 202

        # Status is set to 'preparing' synchronously before the 202 is returned.
        await db_session.refresh(app)
        assert app.status == "preparing"

    @pytest.mark.asyncio
    async def test_approve_returns_async_job_fields(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """202 response contains async_job_id, job_id, status, message."""
        job = await _insert_job(db_session)

        resp = await client.post(f"/api/jobs/{job.id}/approve")

        assert resp.status_code == 202
        data = resp.json()
        assert "async_job_id" in data
        assert data["job_id"] == job.id
        assert data["status"] == "preparing"
        assert "message" in data

    @pytest.mark.asyncio
    async def test_approve_returns_404_for_unknown_job(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST /api/jobs/{nonexistent}/approve returns 404."""
        resp = await client.post(f"/api/jobs/{uuid.uuid4()}/approve")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_approve_returns_409_when_package_already_preparing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        job = await _insert_job(db_session)
        await _insert_app(db_session, job_id=job.id, status="preparing")

        resp = await client.post(f"/api/jobs/{job.id}/approve")

        assert resp.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/applications/{app_id}/package
# ─────────────────────────────────────────────────────────────────────────────


class TestGetPackageEndpoint:

    @pytest.mark.asyncio
    async def test_get_package_returns_200(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """GET /api/applications/{id}/package returns 200 with package fields."""
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready_to_apply")
        pkg = _mock_package(job_id=job.id, job_url=job.url)

        with patch(
            "app.services.assisted_apply.AssistedApplyService.prepare_application",
            new=AsyncMock(return_value=pkg),
        ):
            resp = await client.get(f"/api/applications/{app.id}/package")

        assert resp.status_code == 200
        data = resp.json()
        assert "job_id" in data
        assert "job_url" in data
        assert "screening_answers" in data
        assert "paste_map" in data

    @pytest.mark.asyncio
    async def test_get_package_returns_404_for_unknown_app(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """GET /api/applications/{nonexistent}/package returns 404."""
        resp = await client.get(f"/api/applications/{uuid.uuid4()}/package")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/applications/{app_id}/mark-applied
# ─────────────────────────────────────────────────────────────────────────────


class TestMarkAppliedEndpoint:

    @pytest.fixture(autouse=True)
    def _mock_coach_queue(self):
        with patch(
            "app.routers.applications.queue_coach_session",
            new_callable=AsyncMock,
        ) as queued:
            queued.return_value = {
                "job_id": "coach-job-id",
                "status": "pending",
                "type": "coach_session",
                "session_id": "coach-session-id",
                "created": True,
            }
            yield queued

    @pytest.mark.asyncio
    async def test_mark_applied_from_ready_to_apply_returns_200(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST mark-applied when status='ready_to_apply' sets status='applied'."""

        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready_to_apply")

        resp = await client.post(f"/api/applications/{app.id}/mark-applied")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "applied"

    @pytest.mark.asyncio
    async def test_mark_applied_sets_applied_date(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """mark-applied sets applied_date to a non-null timestamp."""
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready_to_apply")

        resp = await client.post(f"/api/applications/{app.id}/mark-applied")
        assert resp.status_code == 200

        await db_session.refresh(app)
        assert app.applied_date is not None

    @pytest.mark.asyncio
    async def test_mark_applied_queues_linked_coach_session(
        self, client: AsyncClient, db_session: AsyncSession, _mock_coach_queue
    ) -> None:
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready_to_apply")

        response = await client.post(f"/api/applications/{app.id}/mark-applied")

        assert response.status_code == 200
        request = _mock_coach_queue.await_args.args[0]
        assert request.application_id == app.id
        assert request.company_name == job.company
        assert request.role_title == job.title
        assert _mock_coach_queue.await_args.kwargs["deduplicate_application"] is True

    @pytest.mark.asyncio
    async def test_mark_applied_without_approve_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST mark-applied when status is NOT 'ready_to_apply' returns 422."""
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="discovered")

        resp = await client.post(f"/api/applications/{app.id}/mark-applied")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_mark_applied_returns_404_for_unknown_app(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST mark-applied for nonexistent app returns 404."""
        resp = await client.post(f"/api/applications/{uuid.uuid4()}/mark-applied")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/applications/{app_id}/reject
# ─────────────────────────────────────────────────────────────────────────────


class TestRejectEndpoint:

    @pytest.mark.asyncio
    async def test_reject_sets_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST reject sets Application.status to 'rejected'."""
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready")

        resp = await client.post(f"/api/applications/{app.id}/reject")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_returns_404_for_unknown_app(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST reject for nonexistent app returns 404."""
        resp = await client.post(f"/api/applications/{uuid.uuid4()}/reject")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/applications/{app_id}/revert
# ─────────────────────────────────────────────────────────────────────────────


class TestRevertEndpoint:

    @pytest.mark.asyncio
    async def test_revert_from_ready_to_apply_sets_ready(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST revert from 'ready_to_apply' sets status back to 'ready'."""
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="ready_to_apply")

        resp = await client.post(f"/api/applications/{app.id}/revert")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_revert_from_wrong_status_returns_422(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST revert when not in 'ready_to_apply' returns 422."""
        job = await _insert_job(db_session)
        app = await _insert_app(db_session, job_id=job.id, status="applied")

        resp = await client.post(f"/api/applications/{app.id}/revert")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_revert_returns_404_for_unknown_app(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """POST revert for nonexistent app returns 404."""
        resp = await client.post(f"/api/applications/{uuid.uuid4()}/revert")
        assert resp.status_code == 404
