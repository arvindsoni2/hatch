"""Repository for Application, FollowUp, and ActivityLog database access."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.application import Application, FollowUp, InterviewRound
from ..models.activity import ActivityLog
from ..models.document import GeneratedDocument
from ..models.job import JobPosting
from ..models.job_score import JobScore
from ..schemas.application import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationRead,
    ApplicationUpdate,
    FollowUpRead,
)
from ..schemas.interview import (
    InterviewRoundRead,
)
from ..schemas.analytics import KanbanStats

logger = logging.getLogger(__name__)


class ApplicationRepository:
    """All database operations for applications, follow-ups, and activity logs.

    Uses SQLAlchemy async session. Returns Pydantic schemas, never raw ORM models
    outside this class.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: ApplicationCreate) -> ApplicationRead:
        """Insert a new application record.

        Args:
            data: Validated ApplicationCreate schema.

        Returns:
            The created application as ApplicationRead.

        Raises:
            ValueError: If job_id is provided but the referenced job does not exist.
        """
        if data.job_id is not None:
            job_exists = await self._session.execute(
                select(JobPosting.id).where(JobPosting.id == data.job_id)
            )
            if job_exists.scalar_one_or_none() is None:
                raise ValueError(f"Job {data.job_id} not found — cannot create orphaned application")
        db_obj = Application(**data.model_dump())
        self._session.add(db_obj)
        await self._session.flush()
        await self._session.refresh(db_obj)
        return self._to_read(db_obj)

    async def get_by_id(
        self, app_id: str, load_relations: bool = False
    ) -> ApplicationRead | None:
        """Fetch a single application by primary key.

        Args:
            app_id: UUID of the application.
            load_relations: When True, eagerly load interviews, follow-ups, and activity.

        Returns:
            ApplicationRead if found and active, None otherwise.
        """
        if load_relations:
            result = await self._session.execute(
                select(Application, JobPosting)
                .outerjoin(JobPosting, Application.job_id == JobPosting.id)
                .options(
                    selectinload(Application.interviews),
                    selectinload(Application.follow_ups),
                )
                .where(Application.id == app_id, Application.is_active)
            )
            row = result.one_or_none()
            if row is None:
                return None
            app_row, job_row = row
            # Load activity separately to avoid multi-level eager load complexity
            act_result = await self._session.execute(
                select(ActivityLog)
                .where(ActivityLog.application_id == app_id)
                .order_by(ActivityLog.created_at.desc())
                .limit(50)
            )
            activity_rows = act_result.scalars().all()
            app_dict: dict[str, Any] = {
                **{c.key: getattr(app_row, c.key) for c in Application.__table__.columns},
                "interviews": app_row.interviews,
                "follow_ups": app_row.follow_ups,
                "activity": activity_rows,
                "job": job_row if job_row is not None else None,
            }
            return ApplicationRead.model_validate(app_dict)
        else:
            result = await self._session.execute(
                select(Application).where(
                    Application.id == app_id, Application.is_active
                )
            )
            row = result.scalar_one_or_none()
            return self._to_read(row) if row else None

    async def get_by_job_id(self, job_id: str) -> ApplicationListItem | None:
        """Fetch a lightweight application record by linked job_id.

        Args:
            job_id: UUID of the job posting.

        Returns:
            ApplicationListItem if found and active, None otherwise.
        """
        result = await self._session.execute(
            select(Application).where(
                Application.job_id == job_id, Application.is_active
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return self._to_list_item(row, None)

    async def list_all(
        self,
        status: str | None = None,
        priority: str | None = None,
        search: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApplicationListItem], int]:
        """List active applications with optional filters and pagination.

        Performs a left outer join to job_postings so job fields are available
        on the returned ApplicationListItem objects.

        Args:
            status: Filter by application status.
            priority: Filter by priority level.
            search: Search agency, recruiter, notes, job title, and company.
            skip: Pagination offset.
            limit: Maximum records to return.

        Returns:
            Tuple of (list of ApplicationListItem, total count).
        """
        latest_cv_ats_score = self._latest_cv_ats_score_subquery()
        query = (
            select(Application, JobPosting, JobScore, latest_cv_ats_score)
            .outerjoin(JobPosting, Application.job_id == JobPosting.id)
            .outerjoin(JobScore, Application.job_id == JobScore.job_id)
            .where(Application.is_active)
        )
        if status:
            query = query.where(Application.status == status)
        if priority:
            query = query.where(Application.priority == priority)
        if search:
            term = f"%{search}%"
            query = query.where(
                Application.agency_name.ilike(term)
                | Application.recruiter_name.ilike(term)
                | Application.notes.ilike(term)
                | JobPosting.title.ilike(term)
                | JobPosting.company.ilike(term)
            )

        count_result = await self._session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar_one()

        query = query.order_by(Application.updated_at.desc()).offset(skip).limit(limit)
        result = await self._session.execute(query)
        rows = result.all()
        items = [self._to_list_item(app, job, score, cv_ats_score) for app, job, score, cv_ats_score in rows]
        return items, total

    async def get_kanban(self) -> dict[str, list[ApplicationListItem]]:
        """Fetch all active applications grouped by status for Kanban view.

        Single query approach — groups in Python to avoid N+1 per status.

        Returns:
            Dict mapping status string to list of ApplicationListItem.
        """
        result = await self._session.execute(
            select(Application, JobPosting, JobScore, self._latest_cv_ats_score_subquery())
            .outerjoin(JobPosting, Application.job_id == JobPosting.id)
            .outerjoin(JobScore, Application.job_id == JobScore.job_id)
            .where(Application.is_active)
            .order_by(Application.updated_at.desc())
        )
        rows = result.all()
        grouped: dict[str, list[ApplicationListItem]] = {}
        for app, job, score, cv_ats_score in rows:
            item = self._to_list_item(app, job, score, cv_ats_score)
            grouped.setdefault(app.status, []).append(item)
        return grouped

    async def update(self, app_id: str, data: ApplicationUpdate) -> ApplicationRead | None:
        """Partially update an application record.

        Args:
            app_id: UUID of the application to update.
            data: Fields to update (only non-None values applied).

        Returns:
            Updated ApplicationRead, or None if not found.
        """
        update_data = data.model_dump(exclude_none=True)
        if not update_data:
            return await self.get_by_id(app_id)
        update_data["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(Application).where(Application.id == app_id).values(**update_data)
        )
        await self._session.flush()
        return await self.get_by_id(app_id)

    async def soft_delete(self, app_id: str) -> bool:
        """Mark an application as inactive (soft delete).

        Args:
            app_id: UUID of the application.

        Returns:
            True if found and deactivated, False if not found.
        """
        result = await self._session.execute(
            update(Application)
            .where(Application.id == app_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await self._session.flush()
        return (result.rowcount or 0) > 0

    async def get_overdue_follow_ups(self) -> list[FollowUpRead]:
        """Fetch all incomplete follow-ups whose due_date has passed.

        Returns:
            List of FollowUpRead ordered by due_date ascending.
        """
        now = datetime.utcnow()
        result = await self._session.execute(
            select(FollowUp)
            .where(~FollowUp.completed, FollowUp.due_date < now)
            .order_by(FollowUp.due_date.asc())
        )
        rows = result.scalars().all()
        return [FollowUpRead.model_validate(r) for r in rows]

    async def get_upcoming_interviews(self, days: int = 7) -> list[InterviewRoundRead]:
        """Fetch scheduled interviews within the next N days.

        Args:
            days: Look-ahead window in days.

        Returns:
            List of InterviewRoundRead ordered by scheduled_at ascending.
        """
        from datetime import timedelta

        now = datetime.utcnow()
        cutoff = now + timedelta(days=days)
        result = await self._session.execute(
            select(InterviewRound)
            .where(
                InterviewRound.scheduled_at >= now,
                InterviewRound.scheduled_at <= cutoff,
                InterviewRound.status == "scheduled",
            )
            .order_by(InterviewRound.scheduled_at.asc())
        )
        rows = result.scalars().all()
        return [InterviewRoundRead.model_validate(r) for r in rows]

    async def log_activity(
        self,
        app_id: str,
        action: str,
        old_value: str | None = None,
        new_value: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Append an immutable activity log entry.

        Args:
            app_id: UUID of the application this log belongs to.
            action: Short action label (e.g. 'status_change', 'note_added').
            old_value: Previous value for the changed field, if applicable.
            new_value: New value for the changed field, if applicable.
            detail: Free-text detail for additional context.
        """
        log = ActivityLog(
            application_id=app_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            detail=detail,
        )
        self._session.add(log)
        await self._session.flush()

    async def get_kanban_stats(self) -> KanbanStats:
        """Compute summary statistics for the Kanban board header.

        Returns:
            KanbanStats with active count, applied count, response rate, and overdue count.
        """
        result = await self._session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.is_active)
            .group_by(Application.status)
        )
        counts: dict[str, int] = dict(result.all())

        # "discovered" is a raw Scout-found job, not an application the user is pursuing
        active_statuses = {"shortlisted", "applied", "interview", "offered"}
        active_count = sum(counts.get(s, 0) for s in active_statuses)
        applied_count = (
            counts.get("applied", 0)
            + counts.get("interview", 0)
            + counts.get("offered", 0)
        )
        total_applied = (
            applied_count
            + counts.get("accepted", 0)
            + counts.get("rejected", 0)
            + counts.get("declined", 0)
        )
        interview_plus = (
            counts.get("interview", 0)
            + counts.get("offered", 0)
            + counts.get("accepted", 0)
        )
        response_rate = (interview_plus / max(total_applied, 1)) * 100.0

        overdue_result = await self._session.execute(
            select(func.count(FollowUp.id)).where(
                ~FollowUp.completed,
                FollowUp.due_date < datetime.utcnow(),
            )
        )
        overdue_count = overdue_result.scalar_one() or 0

        return KanbanStats(
            active_count=active_count,
            applied_count=applied_count,
            response_rate=round(response_rate, 1),
            overdue_count=overdue_count,
        )

    def _to_read(self, app: Application) -> ApplicationRead:
        """Build an ApplicationRead from an ORM object without accessing lazy relationships.

        Relationship fields (interviews, follow_ups, activity) are set to empty lists
        because lazy-loading is not safe outside a greenlet context. Use
        get_by_id(load_relations=True) when the full nested payload is needed.

        Args:
            app: Application ORM object (column data already loaded).

        Returns:
            ApplicationRead with empty nested lists.
        """
        return ApplicationRead(
            id=app.id,
            job_id=app.job_id,
            status=app.status,
            priority=app.priority,
            applied_date=app.applied_date,
            cv_version=app.cv_version,
            cover_letter_version=app.cover_letter_version,
            notes=app.notes,
            recruiter_name=app.recruiter_name,
            recruiter_email=app.recruiter_email,
            recruiter_phone=app.recruiter_phone,
            agency_name=app.agency_name,
            salary_offered=app.salary_offered,
            rejection_reason=app.rejection_reason,
            is_active=app.is_active,
            created_at=app.created_at,
            updated_at=app.updated_at,
            interviews=[],
            follow_ups=[],
            activity=[],
        )

    def _to_list_item(
        self,
        app: Application,
        job: JobPosting | None,
        score: JobScore | None = None,
        latest_cv_ats_score: int | None = None,
    ) -> ApplicationListItem:
        """Build an ApplicationListItem from an ORM Application and optional JobPosting.

        Args:
            app: Application ORM object.
            job: JobPosting ORM object if available via join, otherwise None.
            score: JobScore ORM object if available via join, otherwise None.

        Returns:
            ApplicationListItem with job_* fields populated when job is not None.
        """
        return ApplicationListItem(
            id=app.id,
            job_id=app.job_id,
            status=app.status,
            priority=app.priority,
            applied_date=app.applied_date,
            recruiter_name=app.recruiter_name,
            agency_name=app.agency_name,
            salary_offered=app.salary_offered,
            is_active=app.is_active,
            created_at=app.created_at,
            updated_at=app.updated_at,
            job_title=job.title if job else None,
            job_company=job.company if job else None,
            job_location=job.location if job else None,
            job_rate_text=job.rate_text if job else None,
            job_rate_min=job.rate_min if job else None,
            job_source=job.source if job else None,
            job_url=job.url if job else None,
            agent_score=score.overall_score if score else None,
            latest_cv_ats_score=latest_cv_ats_score,
            agent_created=getattr(app, "agent_created", False),
            approval_status=getattr(app, "approval_status", None),
        )

    @staticmethod
    def _latest_cv_ats_score_subquery():
        """Return the newest ATS score for the generated CV attached to each app."""
        return (
            select(GeneratedDocument.ats_score)
            .where(
                GeneratedDocument.application_id == Application.id,
                GeneratedDocument.document_type == "cv",
                GeneratedDocument.ats_score.isnot(None),
            )
            .order_by(GeneratedDocument.created_at.desc())
            .limit(1)
            .scalar_subquery()
        )
