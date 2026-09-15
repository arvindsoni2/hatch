"""Best-effort startup and daily maintenance for metadata-only shadow records."""

from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger("jobpilot.runtime.shadow")


async def purge_shadow_comparisons(factory) -> int | None:
    try:
        async with factory.transaction() as uow:
            count = await uow.shadow.purge_expired(now=datetime.utcnow())
            await uow.commit()
        logger.info("shadow_purge_completed deleted_count=%d", count)
        return count
    except Exception:
        # Database/driver exceptions can carry SQL values; retain only a code.
        logger.warning("shadow_purge_failed; next daily run or startup will retry")
        return None


async def install_shadow_retention(scheduler, factory) -> None:
    await purge_shadow_comparisons(factory)
    try:
        scheduler.add_job(
            purge_shadow_comparisons,
            "interval",
            days=1,
            id="runtime-shadow-retention",
            replace_existing=True,
            kwargs={"factory": factory},
            max_instances=1,
            coalesce=True,
        )
    except Exception:
        logger.warning("shadow_purge_schedule_failed; next startup will retry")
