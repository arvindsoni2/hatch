"""Repository for InterviewRound and FollowUp CRUD."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.application import FollowUp, InterviewRound
from ..schemas.interview import (
    FollowUpCreate,
    FollowUpRead,
    FollowUpUpdate,
    InterviewRoundCreate,
    InterviewRoundRead,
    InterviewRoundUpdate,
)


class InterviewRepository:
    """All database operations for interview rounds and follow-up tasks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: InterviewRoundCreate) -> InterviewRoundRead:
        """Create a new interview round.

        Args:
            data: Validated InterviewRoundCreate schema.

        Returns:
            The created round as InterviewRoundRead.
        """
        db_obj = InterviewRound(id=str(uuid.uuid4()), **data.model_dump())
        self._session.add(db_obj)
        await self._session.flush()
        await self._session.refresh(db_obj)
        return InterviewRoundRead.model_validate(db_obj)

    async def update(
        self, interview_id: str, data: InterviewRoundUpdate
    ) -> InterviewRoundRead | None:
        """Partially update an interview round.

        Args:
            interview_id: UUID of the interview round.
            data: Fields to update (only non-None values applied).

        Returns:
            Updated InterviewRoundRead, or None if not found.
        """
        update_data = data.model_dump(exclude_none=True)
        update_data["updated_at"] = datetime.utcnow()
        await self._session.execute(
            update(InterviewRound)
            .where(InterviewRound.id == interview_id)
            .values(**update_data)
        )
        await self._session.flush()
        result = await self._session.execute(
            select(InterviewRound).where(InterviewRound.id == interview_id)
        )
        row = result.scalar_one_or_none()
        return InterviewRoundRead.model_validate(row) if row else None

    async def delete(self, interview_id: str) -> bool:
        """Hard-delete an interview round.

        Args:
            interview_id: UUID of the interview round.

        Returns:
            True if found and deleted, False otherwise.
        """
        result = await self._session.execute(
            select(InterviewRound).where(InterviewRound.id == interview_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True

    async def list_by_application(self, app_id: str) -> list[InterviewRoundRead]:
        """List all interview rounds for a given application, ordered by round number.

        Args:
            app_id: UUID of the application.

        Returns:
            List of InterviewRoundRead ordered by round_number ascending.
        """
        result = await self._session.execute(
            select(InterviewRound)
            .where(InterviewRound.application_id == app_id)
            .order_by(InterviewRound.round_number.asc())
        )
        rows = result.scalars().all()
        return [InterviewRoundRead.model_validate(r) for r in rows]

    async def get_upcoming(self, days: int = 7) -> list[InterviewRoundRead]:
        """Fetch scheduled interviews within the next N days.

        Args:
            days: Look-ahead window in days.

        Returns:
            List of InterviewRoundRead ordered by scheduled_at ascending.
        """
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

    async def create_follow_up(self, data: FollowUpCreate) -> FollowUpRead:
        """Create a new follow-up task.

        Args:
            data: Validated FollowUpCreate schema.

        Returns:
            The created follow-up as FollowUpRead.
        """
        db_obj = FollowUp(id=str(uuid.uuid4()), **data.model_dump())
        self._session.add(db_obj)
        await self._session.flush()
        await self._session.refresh(db_obj)
        return FollowUpRead.model_validate(db_obj)

    async def update_follow_up(
        self, follow_up_id: str, data: FollowUpUpdate
    ) -> FollowUpRead | None:
        """Partially update a follow-up task.

        Args:
            follow_up_id: UUID of the follow-up.
            data: Fields to update (only non-None values applied).

        Returns:
            Updated FollowUpRead, or None if not found.
        """
        update_data = data.model_dump(exclude_none=True)
        await self._session.execute(
            update(FollowUp).where(FollowUp.id == follow_up_id).values(**update_data)
        )
        await self._session.flush()
        result = await self._session.execute(
            select(FollowUp).where(FollowUp.id == follow_up_id)
        )
        row = result.scalar_one_or_none()
        return FollowUpRead.model_validate(row) if row else None

    async def get_overdue_follow_ups(self) -> list[FollowUpRead]:
        """Fetch all incomplete follow-ups whose due_date has passed.

        Returns:
            List of FollowUpRead ordered by due_date ascending.
        """
        now = datetime.utcnow()
        result = await self._session.execute(
            select(FollowUp)
            .where(FollowUp.completed == False, FollowUp.due_date < now)
            .order_by(FollowUp.due_date.asc())
        )
        rows = result.scalars().all()
        return [FollowUpRead.model_validate(r) for r in rows]
