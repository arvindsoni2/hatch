"""Post-commit wake-ups and bounded maintenance for durable deletion claims."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from sqlalchemy import select

from ..config import settings
from ..models.coach_session import InterviewSession
from ..repositories.conversational_session_repository import (
    ConversationalRepositoryError,
    ConversationalSessionRepository,
)
from .async_job_service import AsyncJobService
from .coach_privacy import (
    HardDeletionClaim,
    expire_deletion_receipts,
    run_hard_deletion,
)

logger = logging.getLogger(__name__)


async def _process_hard_deletion(claim: HardDeletionClaim) -> None:
    from ..database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        repository = ConversationalSessionRepository(db)
        try:
            async with asyncio.timeout(
                settings.HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS
            ):
                await run_hard_deletion(claim, repository, now=datetime.utcnow())
                await db.commit()
            logger.info("coach.hard_deletion.completed")
        except BaseException as error:
            await db.rollback()
            try:
                await repository.fail_hard_deletion(
                    claim,
                    "coach_session_deletion_failed",
                    datetime.utcnow(),
                )
                await db.commit()
                logger.warning("coach.hard_deletion.failed")
            except ConversationalRepositoryError:
                await db.rollback()
                logger.info("coach.hard_deletion.stale_claim")
            except Exception:
                await db.rollback()
                # Persisted expiry/reconciliation remains authoritative.
                logger.warning("coach.hard_deletion.failure_finalization_failed")
            if not isinstance(error, Exception):
                raise


def queue_hard_deletion(claim: HardDeletionClaim) -> None:
    worker = _process_hard_deletion(claim)
    try:
        AsyncJobService.run(claim.job_id, worker)
    except Exception:
        worker.close()
        logger.warning("coach.hard_deletion.dispatch_failed")


async def purge_deletion_receipts(session_factory, *, now=None, limit=100) -> int:
    async with session_factory() as db:
        count = await expire_deletion_receipts(
            ConversationalSessionRepository(db),
            now=now or datetime.utcnow(),
            limit=limit,
        )
        await db.commit()
        return count


async def _scheduled_receipt_purge(session_factory) -> None:
    try:
        count = await purge_deletion_receipts(session_factory)
        logger.info("coach.deletion_receipts.purged count=%d", count)
    except Exception:
        logger.warning("coach.deletion_receipts.purge_failed")


async def install_deletion_receipt_retention(scheduler, session_factory) -> None:
    await _scheduled_receipt_purge(session_factory)
    try:
        scheduler.add_job(
            _scheduled_receipt_purge,
            "interval",
            days=1,
            id="coach-deletion-receipt-retention",
            replace_existing=True,
            kwargs={"session_factory": session_factory},
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            reconcile_expired_deletion_claims,
            "interval",
            seconds=60,
            id="coach-deletion-reconciliation",
            replace_existing=True,
            kwargs={"session_factory": session_factory},
            max_instances=1,
            coalesce=True,
        )
    except Exception:
        logger.warning("coach.deletion_receipts.schedule_failed")


async def reconcile_expired_deletion_claims(session_factory) -> int:
    from .coach_reconciliation import reconcile_conversational_session

    try:
        async with session_factory() as db:
            session_ids = list(
                (
                    await db.scalars(
                        select(InterviewSession.id)
                        .where(
                            InterviewSession.experience_version == "conversational_v1",
                            InterviewSession.deletion_state == "deleting",
                            InterviewSession.deletion_claim_expires_at
                            < datetime.utcnow(),
                        )
                        .order_by(InterviewSession.id)
                        .limit(100)
                    )
                ).all()
            )
        recovered = 0
        for session_id in session_ids:
            async with session_factory() as db:
                recovered += await reconcile_conversational_session(db, session_id)
        return recovered
    except Exception:
        logger.warning("coach.hard_deletion.reconciliation_failed")
        return 0
