"""Post-commit wake-up for frozen conversational report ownership."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from ..repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from .async_job_service import AsyncJobService
from .coach_conversational_report import run_conversational_report

logger = logging.getLogger(__name__)


async def _process_conversational_report(job_id: str) -> None:
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        repository = ConversationalSessionRepository(db)
        claim = None
        try:
            claim = await repository.load_report_build_claim(job_id)
            if claim is None:
                logger.info("coach.report.stale_claim")
                return
            remaining = (claim.deadline_at - datetime.utcnow()).total_seconds()
            async with asyncio.timeout(max(0, remaining)):
                await run_conversational_report(claim, repository)
                await db.commit()
        except BaseException as error:
            await db.rollback()
            if claim is not None:
                try:
                    await repository.fail_conversational_report(
                        claim,
                        now=datetime.utcnow(),
                        error_code="coach_report_worker_failed",
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.warning("coach.report.failure_finalization_failed")
            logger.warning("coach.report.worker_failed")
            if not isinstance(error, Exception):
                raise


def queue_conversational_report(job_id: str) -> None:
    worker = _process_conversational_report(job_id)
    try:
        AsyncJobService.run(job_id, worker)
    except Exception:
        worker.close()
        logger.warning("coach.report.dispatch_failed")
