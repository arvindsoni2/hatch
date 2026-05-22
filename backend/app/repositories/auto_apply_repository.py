"""Database access layer for auto-apply application attempts."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.auto_apply import ApplicationAttempt

logger = logging.getLogger(__name__)


class AutoApplyRepository:
    """CRUD operations for ApplicationAttempt records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_attempt(
        self,
        application_id: str,
        job_url: str,
        platform: str | None = None,
        apply_url: str | None = None,
    ) -> ApplicationAttempt:
        """Create a new ApplicationAttempt record.

        Args:
            application_id: FK to the parent Application.
            job_url: URL of the job posting.
            platform: Detected platform (reed, cwjobs, etc.).
            apply_url: Direct apply page URL if known.

        Returns:
            The created ApplicationAttempt ORM object.
        """
        attempt = ApplicationAttempt(
            application_id=application_id,
            job_url=job_url,
            platform=platform,
            apply_url=apply_url,
            status="pending",
        )
        self._session.add(attempt)
        await self._session.flush()
        await self._session.refresh(attempt)
        return attempt

    async def get_attempt(self, attempt_id: str) -> ApplicationAttempt | None:
        """Fetch a single attempt by primary key.

        Args:
            attempt_id: UUID string.

        Returns:
            ApplicationAttempt or None.
        """
        result = await self._session.execute(
            select(ApplicationAttempt).where(ApplicationAttempt.id == attempt_id)
        )
        return result.scalar_one_or_none()

    async def update_attempt(self, attempt_id: str, **fields: object) -> ApplicationAttempt | None:
        """Update fields on an attempt record.

        Args:
            attempt_id: UUID of the attempt to update.
            **fields: Column names and new values.

        Returns:
            Updated ApplicationAttempt or None if not found.
        """
        if not fields:
            return await self.get_attempt(attempt_id)
        await self._session.execute(
            update(ApplicationAttempt)
            .where(ApplicationAttempt.id == attempt_id)
            .values(**fields)
        )
        return await self.get_attempt(attempt_id)

    async def list_attempts(
        self,
        application_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[ApplicationAttempt]:
        """List attempts with optional filters.

        Args:
            application_id: Filter by parent application.
            status: Filter by attempt status.
            limit: Maximum records to return.

        Returns:
            List of ApplicationAttempt ORM objects.
        """
        query = select(ApplicationAttempt)
        if application_id:
            query = query.where(ApplicationAttempt.application_id == application_id)
        if status:
            query = query.where(ApplicationAttempt.status == status)
        query = query.order_by(ApplicationAttempt.created_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_submitted_last_hour(self) -> int:
        """Count attempts submitted in the last hour (for rate limiting).

        Returns:
            Integer count of recently submitted attempts.
        """
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        result = await self._session.execute(
            select(func.count(ApplicationAttempt.id)).where(
                ApplicationAttempt.status == "submitted",
                ApplicationAttempt.submitted_at >= one_hour_ago,
            )
        )
        return result.scalar_one() or 0
