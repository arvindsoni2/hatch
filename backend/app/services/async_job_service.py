"""AsyncJobService — create, run, and poll background LLM jobs."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Coroutine

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.async_job import AsyncJob

logger = logging.getLogger(__name__)


class AsyncJobService:
    """Manages background LLM jobs persisted in the async_jobs table."""

    @staticmethod
    async def create(db: AsyncSession, job_type: str) -> AsyncJob:
        """Persist a new pending job and return it.

        Calls flush() (not commit()) so the caller can commit as part of their
        own transaction after getting the job ID.
        """
        job = AsyncJob(type=job_type)
        db.add(job)
        await db.flush()
        return job

    @staticmethod
    def run(job_id: str, coro: Coroutine[Any, Any, None]) -> None:
        """Fire-and-forget: set status=running then await the coroutine."""

        async def _run_and_track() -> None:
            try:
                from ..database import AsyncSessionLocal  # noqa: PLC0415
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(AsyncJob)
                        .where(AsyncJob.id == job_id)
                        .values(status="running", updated_at=datetime.utcnow())
                    )
                    await db.commit()
                await coro
            except Exception as exc:
                logger.exception("Unhandled error in async job %s: %s", job_id, exc)
                await AsyncJobService._finish(job_id, None, str(exc))

        asyncio.create_task(_run_and_track())

    @staticmethod
    async def _finish(
        job_id: str,
        result_json: str | None,
        error: str | None,
        db: AsyncSession | None = None,
    ) -> None:
        """Persist the final status of a background job.

        When *db* is provided the update runs inside the caller's session
        (useful in tests and in coroutines that already hold a session).
        When *db* is None a fresh :data:`AsyncSessionLocal` session is opened —
        the normal path for background coroutines where the request session is
        already closed.
        """
        status = "done" if result_json is not None else "failed"

        async def _apply(session: AsyncSession) -> None:
            await session.execute(
                update(AsyncJob)
                .where(AsyncJob.id == job_id)
                .values(
                    status=status,
                    result_json=result_json,
                    error=error,
                    updated_at=datetime.utcnow(),
                )
            )

        if db is not None:
            await _apply(db)
            await db.commit()
        else:
            from ..database import AsyncSessionLocal  # noqa: PLC0415
            async with AsyncSessionLocal() as session:
                await _apply(session)
                await session.commit()

        logger.info("AsyncJob %s → %s", job_id, status)

    @staticmethod
    async def get(db: AsyncSession, job_id: str) -> AsyncJob | None:
        """Return a job by ID, or None if not found."""
        result = await db.execute(
            select(AsyncJob).where(AsyncJob.id == job_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_status(
        db: AsyncSession, status: str, since: datetime, limit: int = 20
    ) -> list[AsyncJob]:
        """Return jobs with the given status created after `since`, newest first."""
        result = await db.execute(
            select(AsyncJob)
            .where(AsyncJob.status == status, AsyncJob.created_at >= since)
            .order_by(AsyncJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_completed_since(
        db: AsyncSession, since: datetime, limit: int = 20
    ) -> list[AsyncJob]:
        """Return done jobs created after `since`, newest first."""
        result = await db.execute(
            select(AsyncJob)
            .where(AsyncJob.status == "done", AsyncJob.created_at >= since)
            .order_by(AsyncJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
