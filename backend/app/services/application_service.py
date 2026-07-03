"""ApplicationService — orchestrates application lifecycle with state machine."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import HTTPException

from ..repositories.application_repository import ApplicationRepository
from ..repositories.interview_repository import InterviewRepository
from ..schemas.application import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
)
from ..schemas.interview import FollowUpCreate

logger = logging.getLogger(__name__)

STATUS_TRANSITIONS: dict[str, list[str]] = {
    "saved":       ["discovered", "rejected", "withdrawn"],
    # Users may record a submission directly when they applied outside Hatch.
    "discovered":  ["shortlisted", "applied", "rejected", "withdrawn"],
    "shortlisted": ["applied", "rejected", "withdrawn"],
    "parked":      ["applied", "rejected", "withdrawn"],
    "ready":       ["applied", "rejected", "withdrawn"],
    "approved":    ["preparing", "rejected", "withdrawn"],
    "preparing":   ["ready_to_apply", "rejected", "withdrawn"],
    "ready_to_apply": ["applied", "rejected", "withdrawn"],
    "applied":     ["interview", "rejected", "withdrawn"],
    "interview":   ["offered", "rejected", "withdrawn"],
    "offered":     ["accepted", "declined", "withdrawn"],
    "accepted":    [],
    "rejected":    [],
    "withdrawn":   [],
    "declined":    [],
}


class ApplicationService:
    """Orchestrates application lifecycle: creation, status transitions, and side effects."""

    def __init__(
        self,
        app_repo: ApplicationRepository,
        interview_repo: InterviewRepository,
    ) -> None:
        self._repo = app_repo
        self._interview_repo = interview_repo

    def validate_transition(self, current_status: str, next_status: str) -> None:
        """Validate that a status transition is permitted by the state machine.

        Args:
            current_status: Current application status.
            next_status: Target status to move to.

        Raises:
            HTTPException 422: If the transition is not allowed.
        """
        allowed = STATUS_TRANSITIONS.get(current_status, [])
        if next_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot transition from '{current_status}' to '{next_status}'. "
                    f"Allowed transitions: {allowed}"
                ),
            )

    async def create_application(self, data: ApplicationCreate) -> ApplicationRead:
        """Create a new application record and log the creation event.

        Args:
            data: ApplicationCreate schema.

        Returns:
            ApplicationRead with the new record.
        """
        app = await self._repo.create(data)
        await self._repo.log_activity(app.id, action="created", detail=f"status={app.status}")
        if app.status == "applied":
            from .application_snapshot_service import create_snapshot
            from .outcome_learning_service import recompute_active_jobs
            await create_snapshot(self._repo._session, app.id)
            await recompute_active_jobs(self._repo._session)
        elif app.status in {"interview", "offered", "accepted", "rejected", "withdrawn", "declined"}:
            from .outcome_event_service import record_status_outcome
            await record_status_outcome(self._repo._session, app.id, app.status)
        logger.info("Application created: %s (status=%s)", app.id, app.status)
        return app

    async def update_status(
        self, app_id: str, status_update: ApplicationStatusUpdate
    ) -> ApplicationRead:
        """Update application status with state machine validation and side effects.

        Sets applied_date when transitioning to 'applied'. Creates automatic
        follow-up tasks on certain transitions. Logs the status change.

        Args:
            app_id: UUID of the application.
            status_update: New status and optional note.

        Returns:
            Updated ApplicationRead.

        Raises:
            HTTPException 404: If application not found.
            HTTPException 422: If transition is not allowed by the state machine.
        """
        current = await self._repo.get_by_id(app_id)
        if current is None:
            raise HTTPException(
                status_code=404, detail=f"Application '{app_id}' not found."
            )

        self.validate_transition(current.status, status_update.status)

        update_data = ApplicationUpdate(status=status_update.status)

        # Side effect: record the date the application was submitted
        if status_update.status == "applied" and current.applied_date is None:
            update_data.applied_date = datetime.utcnow()

        updated = await self._repo.update(app_id, update_data)
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail=f"Application '{app_id}' not found after update.",
            )

        db = self._repo._session
        if status_update.status == "applied":
            from .application_snapshot_service import create_snapshot
            await create_snapshot(db, app_id)
        from .outcome_event_service import record_status_outcome
        outcome_created = await record_status_outcome(db, app_id, status_update.status)
        if status_update.status == "applied" or outcome_created:
            from .outcome_learning_service import recompute_active_jobs
            await recompute_active_jobs(db)

        # Create automatic follow-up tasks based on new status
        await self._create_status_follow_ups(app_id, status_update.status)

        # Audit trail
        await self._repo.log_activity(
            app_id,
            action="status_change",
            old_value=current.status,
            new_value=status_update.status,
        )

        # Append optional note provided with the status update
        if status_update.notes:
            await self.add_note(app_id, status_update.notes)

        # Re-fetch with relations to include auto-created follow-ups in response
        updated = await self._repo.get_by_id(app_id, load_relations=True)
        return updated

    async def _create_status_follow_ups(self, app_id: str, new_status: str) -> None:
        """Create automatic follow-up tasks based on status transitions.

        Args:
            app_id: UUID of the application.
            new_status: The newly assigned status.
        """
        now = datetime.utcnow()
        follow_up: FollowUpCreate | None = None

        if new_status == "applied":
            follow_up = FollowUpCreate(
                application_id=app_id,
                due_date=now + timedelta(days=5),
                type="check_in",
                note="Follow up on application status.",
            )
        elif new_status == "interview":
            # Try to schedule the thank-you note for the day after the first interview
            upcoming = await self._interview_repo.get_upcoming(days=30)
            app_interviews = [i for i in upcoming if i.application_id == app_id]
            if app_interviews and app_interviews[0].scheduled_at:
                due = app_interviews[0].scheduled_at + timedelta(days=1)
            else:
                due = now + timedelta(days=2)
            follow_up = FollowUpCreate(
                application_id=app_id,
                due_date=due,
                type="thank_you",
                note="Send thank-you note after interview.",
            )
        elif new_status == "offered":
            follow_up = FollowUpCreate(
                application_id=app_id,
                due_date=now + timedelta(days=2),
                type="negotiation",
                note="Review offer details and negotiate if needed.",
            )

        if follow_up:
            await self._interview_repo.create_follow_up(follow_up)
            await self._repo.log_activity(
                app_id,
                action="follow_up_created",
                detail=f"type={follow_up.type}",
            )

    async def add_note(self, app_id: str, note_text: str) -> ApplicationRead:
        """Append a timestamped note to the application's notes field.

        Args:
            app_id: UUID of the application.
            note_text: Text content to append.

        Returns:
            Updated ApplicationRead.

        Raises:
            HTTPException 404: If application not found.
        """
        current = await self._repo.get_by_id(app_id)
        if current is None:
            raise HTTPException(
                status_code=404, detail=f"Application '{app_id}' not found."
            )

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        separator = "\n\n---\n"
        new_entry = f"**{timestamp}**\n{note_text}"
        updated_notes = (
            f"{current.notes}{separator}{new_entry}" if current.notes else new_entry
        )
        updated = await self._repo.update(app_id, ApplicationUpdate(notes=updated_notes))
        await self._repo.log_activity(app_id, action="note_added", detail=note_text[:200])
        return updated

    async def track_from_job(self, job_id: str) -> ApplicationRead:
        """Create a 'discovered' application from a job listing.

        Args:
            job_id: UUID of the job posting to track.

        Returns:
            New ApplicationRead with status 'discovered'.

        Raises:
            HTTPException 400: If already tracking this job.
        """
        existing = await self._repo.get_by_job_id(job_id)
        if existing is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Already tracking job '{job_id}'. "
                    f"Application id: {existing.id}"
                ),
            )
        return await self.create_application(
            ApplicationCreate(job_id=job_id, status="discovered")
        )

    async def get_next_actions(self, app_id: str) -> list[dict[str, str]]:
        """Return suggested next actions for a single application.

        Args:
            app_id: UUID of the application.

        Returns:
            List of action dicts, each with 'action' and 'reason' keys.
            Returns empty list if application not found.
        """
        current = await self._repo.get_by_id(app_id)
        if current is None:
            return []

        actions: list[dict[str, str]] = []

        # Highlight overdue follow-ups for this application
        overdue = await self._repo.get_overdue_follow_ups()
        app_overdue = [f for f in overdue if f.application_id == app_id]
        for fu in app_overdue:
            actions.append(
                {
                    "action": f"Complete overdue follow-up: {fu.type}",
                    "reason": "Overdue",
                }
            )

        # Suggest valid forward transitions (excluding terminal negative states)
        transitions = STATUS_TRANSITIONS.get(current.status, [])
        for t in transitions:
            if t not in ("rejected", "withdrawn"):
                actions.append(
                    {
                        "action": f"Move to {t}",
                        "reason": f"Next step from {current.status}",
                    }
                )

        return actions
