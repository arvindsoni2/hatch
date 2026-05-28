"""Tests for ApplicationService — state machine, notes, and activity logging."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.job import JobPosting
from app.repositories.application_repository import ApplicationRepository
from app.repositories.interview_repository import InterviewRepository
from app.schemas.application import ApplicationCreate, ApplicationStatusUpdate
from app.services.application_service import ApplicationService


# ──────────────────────── Helpers ────────────────────────


def make_service(db_session: AsyncSession) -> ApplicationService:
    """Build an ApplicationService from a test session."""
    app_repo = ApplicationRepository(db_session)
    interview_repo = InterviewRepository(db_session)
    return ApplicationService(app_repo, interview_repo)


async def _insert_app(
    db_session: AsyncSession,
    status: str = "discovered",
    job_id: str | None = None,
) -> Application:
    """Insert a raw Application ORM object directly for test setup."""
    app = Application(
        id=str(uuid.uuid4()),
        job_id=job_id,
        status=status,
        priority="normal",
        agency_name="Test Agency",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(app)
    await db_session.commit()
    await db_session.refresh(app)
    return app


# ──────────────────────── TestCreateApplication ────────────────────────


class TestCreateApplication:
    @pytest.mark.asyncio
    async def test_create_with_job_id(self, db_session: AsyncSession) -> None:
        """Application is created and linked to a job_id."""
        service = make_service(db_session)
        job_id = str(uuid.uuid4())
        # Repository validates job existence before creating application
        job = JobPosting(id=job_id, title="Test Role", company="Test Co",
                         url="https://example.com/job/1", source="test",
                         ir35_status="unknown", employment_type="unknown",
                         working_pattern="unknown", rate_type="unknown",
                         created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db_session.add(job)
        await db_session.commit()
        data = ApplicationCreate(job_id=job_id, status="discovered", agency_name="Acme")
        result = await service.create_application(data)

        assert result.id is not None
        assert result.job_id == job_id
        assert result.status == "discovered"
        assert result.agency_name == "Acme"

    @pytest.mark.asyncio
    async def test_create_without_job_id(self, db_session: AsyncSession) -> None:
        """Application can be created without a linked job posting (manual entry)."""
        service = make_service(db_session)
        data = ApplicationCreate(status="discovered", agency_name="Direct")
        result = await service.create_application(data)

        assert result.id is not None
        assert result.job_id is None
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_track_from_job_duplicate_raises_400(
        self, db_session: AsyncSession
    ) -> None:
        """Calling track_from_job for a job already being tracked raises HTTP 400."""
        service = make_service(db_session)
        job_id = str(uuid.uuid4())
        # Insert an existing application linked to this job
        await _insert_app(db_session, job_id=job_id)

        with pytest.raises(HTTPException) as exc_info:
            await service.track_from_job(job_id)

        assert exc_info.value.status_code == 400
        assert job_id in exc_info.value.detail


# ──────────────────────── TestStatusTransitions ────────────────────────


class TestStatusTransitions:
    @pytest.mark.asyncio
    async def test_valid_transition_discovered_to_shortlisted(
        self, db_session: AsyncSession
    ) -> None:
        """discovered → shortlisted is a valid transition."""
        service = make_service(db_session)
        app = await _insert_app(db_session, status="discovered")
        result = await service.update_status(
            app.id, ApplicationStatusUpdate(status="shortlisted")
        )
        assert result.status == "shortlisted"

    @pytest.mark.asyncio
    async def test_valid_transition_applied_sets_applied_date(
        self, db_session: AsyncSession
    ) -> None:
        """Transitioning to 'applied' auto-sets applied_date when not already set."""
        service = make_service(db_session)
        app = await _insert_app(db_session, status="shortlisted")
        result = await service.update_status(
            app.id, ApplicationStatusUpdate(status="applied")
        )
        assert result.status == "applied"
        assert result.applied_date is not None

    @pytest.mark.asyncio
    async def test_invalid_transition_raises_422(
        self, db_session: AsyncSession
    ) -> None:
        """Skipping a stage (discovered → applied) raises HTTP 422."""
        service = make_service(db_session)
        app = await _insert_app(db_session, status="discovered")

        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(
                app.id, ApplicationStatusUpdate(status="applied")
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_terminal_state_cannot_transition(
        self, db_session: AsyncSession
    ) -> None:
        """A rejected application cannot transition to any other status."""
        service = make_service(db_session)
        app = await _insert_app(db_session, status="rejected")

        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(
                app.id, ApplicationStatusUpdate(status="shortlisted")
            )

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_applied_transition_creates_check_in_follow_up(
        self, db_session: AsyncSession
    ) -> None:
        """Transitioning to 'applied' automatically creates a check_in follow-up."""
        from sqlalchemy import select
        from app.models.application import FollowUp

        service = make_service(db_session)
        app = await _insert_app(db_session, status="shortlisted")
        await service.update_status(app.id, ApplicationStatusUpdate(status="applied"))

        result = await db_session.execute(
            select(FollowUp).where(
                FollowUp.application_id == app.id,
                FollowUp.type == "check_in",
            )
        )
        follow_up = result.scalar_one_or_none()
        assert follow_up is not None
        assert follow_up.completed is False

    @pytest.mark.asyncio
    async def test_offered_transition_creates_negotiation_follow_up(
        self, db_session: AsyncSession
    ) -> None:
        """Transitioning to 'offered' automatically creates a negotiation follow-up."""
        from sqlalchemy import select
        from app.models.application import FollowUp

        service = make_service(db_session)
        app = await _insert_app(db_session, status="interview")
        await service.update_status(app.id, ApplicationStatusUpdate(status="offered"))

        result = await db_session.execute(
            select(FollowUp).where(
                FollowUp.application_id == app.id,
                FollowUp.type == "negotiation",
            )
        )
        follow_up = result.scalar_one_or_none()
        assert follow_up is not None


# ──────────────────────── TestAddNote ────────────────────────


class TestAddNote:
    @pytest.mark.asyncio
    async def test_add_note_creates_entry_with_timestamp(
        self, db_session: AsyncSession
    ) -> None:
        """Adding a note prepends a timestamp header to the notes field."""
        service = make_service(db_session)
        app = await _insert_app(db_session, status="discovered")
        result = await service.add_note(app.id, "Initial note text")

        assert result.notes is not None
        assert "Initial note text" in result.notes
        assert "UTC" in result.notes  # timestamp suffix

    @pytest.mark.asyncio
    async def test_add_note_appends_to_existing(self, db_session: AsyncSession) -> None:
        """Calling add_note twice appends the second note after a separator."""
        service = make_service(db_session)
        app = await _insert_app(db_session, status="discovered")
        await service.add_note(app.id, "First note")
        result = await service.add_note(app.id, "Second note")

        assert "First note" in result.notes
        assert "Second note" in result.notes
        assert "---" in result.notes  # separator present


# ──────────────────────── TestActivityLog ────────────────────────


class TestActivityLog:
    @pytest.mark.asyncio
    async def test_status_change_is_logged(self, db_session: AsyncSession) -> None:
        """A status transition writes an activity log entry with old and new values."""
        from sqlalchemy import select
        from app.models.activity import ActivityLog

        service = make_service(db_session)
        app = await _insert_app(db_session, status="discovered")
        await service.update_status(
            app.id, ApplicationStatusUpdate(status="shortlisted")
        )

        result = await db_session.execute(
            select(ActivityLog).where(
                ActivityLog.application_id == app.id,
                ActivityLog.action == "status_change",
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.old_value == "discovered"
        assert log.new_value == "shortlisted"

    @pytest.mark.asyncio
    async def test_note_added_is_logged(self, db_session: AsyncSession) -> None:
        """Adding a note writes an activity log entry with action='note_added'."""
        from sqlalchemy import select
        from app.models.activity import ActivityLog

        service = make_service(db_session)
        app = await _insert_app(db_session, status="discovered")
        await service.add_note(app.id, "A test note for logging")

        result = await db_session.execute(
            select(ActivityLog).where(
                ActivityLog.application_id == app.id,
                ActivityLog.action == "note_added",
            )
        )
        log = result.scalar_one_or_none()
        assert log is not None
        assert "A test note for logging" in (log.detail or "")
