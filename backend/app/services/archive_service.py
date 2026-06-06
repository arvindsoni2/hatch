"""Archive service — auto-archives job postings older than the configured threshold.

Sets is_active=False on jobs whose scraped_at is older than
profile.preferences.archive_after_days. Archived jobs are excluded from normal
listings but remain in the database for historical reference.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job import JobPosting

logger = logging.getLogger(__name__)


async def archive_old_jobs(db: AsyncSession, archive_after_days: int) -> int:
    """Mark active jobs older than *archive_after_days* as inactive.

    Returns the number of rows updated.
    """
    if archive_after_days <= 0:
        return 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=archive_after_days)

    result = await db.execute(
        update(JobPosting)
        .where(
            JobPosting.is_active.is_(True),
            JobPosting.scraped_at < cutoff,
        )
        .values(is_active=False, sync_status="archived")
        .returning(JobPosting.id)
    )
    archived_ids = result.scalars().all()
    await db.commit()

    count = len(archived_ids)
    if count:
        logger.info("Archived %d job(s) older than %d days.", count, archive_after_days)
    return count


async def unarchive_job(db: AsyncSession, job_id: str) -> bool:
    """Manually restore an archived job (sets is_active=True).

    Returns True if the job was found and updated.
    """
    result = await db.execute(
        update(JobPosting)
        .where(JobPosting.id == job_id)
        .values(is_active=True, sync_status="pending")
        .returning(JobPosting.id)
    )
    updated = result.scalar_one_or_none()
    await db.commit()
    return updated is not None
