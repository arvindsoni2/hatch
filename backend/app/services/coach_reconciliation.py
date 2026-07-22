"""Idempotent recovery for abandoned Coach answer and report claims."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.async_job import AsyncJob
from ..models.coach_session import InterviewSession, SessionRecording
from ..repositories.session_repository import SessionRepository
from .coach_contracts import CoachDiagnostic, failed_answer_payload

logger = logging.getLogger(__name__)


def _is_due(
    now: datetime,
    reference: datetime | None,
    *,
    job_status: str | None,
    job_timeout_seconds: int,
) -> bool:
    if reference is None:
        return True
    threshold = settings.HATCH_COACH_STALE_JOB_GRACE_SECONDS
    if job_status in {"pending", "running"}:
        threshold += job_timeout_seconds
    return now - reference >= timedelta(seconds=threshold)


def _recovery_diagnostic(stage: str, gates: list[str]) -> dict:
    return CoachDiagnostic(
        stage=stage,
        outcome="failed",
        execution_mode="deterministic",
        attempt_count=0,
        repair_count=0,
        gate_codes=gates,
        duration_ms=0,
    ).model_dump(mode="json")


async def reconcile_session(
    db: AsyncSession,
    session_id: str,
    *,
    now: datetime | None = None,
) -> int:
    """Recover stale pending attempts and a stale building report for one session."""
    now = now or datetime.utcnow()
    changed = 0
    recordings = list(
        (
            await db.execute(
                select(SessionRecording).where(
                    SessionRecording.session_id == session_id,
                    SessionRecording.evaluation_state == "pending",
                )
            )
        ).scalars()
    )
    repository = SessionRepository(db)
    for recording in recordings:
        job = (
            await db.execute(select(AsyncJob).where(AsyncJob.id == recording.async_job_id))
        ).scalar_one_or_none()
        reference = job.updated_at if job else recording.created_at
        status = job.status if job else None
        if not _is_due(
            now,
            reference,
            job_status=status,
            job_timeout_seconds=settings.HATCH_COACH_TIMEOUT_ANSWER_SUBMIT_JOB_SECONDS,
        ):
            continue
        gates = ["coach_async_job_failed"]
        if status == "done":
            gates.append("coach_persistence_failed")
        payload = failed_answer_payload(reason_code="stale_async_job_recovered")
        payload["diagnostic"]["gate_codes"] = gates
        reconciled = await repository.finalize_answer_attempt(
            recording.id,
            recording.async_job_id or "",
            evaluation_state="failed",
            evaluation_json=json.dumps(payload),
        )
        if reconciled:
            changed += 1
            if job and job.status in {"pending", "running"}:
                await db.execute(
                    update(AsyncJob)
                    .where(
                        AsyncJob.id == job.id,
                        AsyncJob.status.in_(("pending", "running")),
                    )
                    .values(
                        status="failed",
                        error="stale_async_job_recovered",
                        updated_at=now,
                    )
                )

    session = (
        await db.execute(select(InterviewSession).where(InterviewSession.id == session_id))
    ).scalar_one_or_none()
    if session and session.report_state == "building":
        job = (
            await db.execute(select(AsyncJob).where(AsyncJob.id == session.report_job_id))
        ).scalar_one_or_none()
        reference = job.updated_at if job else session.report_started_at
        status = job.status if job else None
        if _is_due(
            now,
            reference,
            job_status=status,
            job_timeout_seconds=settings.HATCH_COACH_TIMEOUT_SESSION_END_JOB_SECONDS,
        ):
            gates = ["coach_async_job_failed"]
            if status == "done":
                gates.append("coach_persistence_failed")
            diagnostic = _recovery_diagnostic("session_report", gates)
            reconciled = await repository.fail_report_claim(
                session.id,
                session.report_job_id or "",
                diagnostic,
                reason_code="stale_async_job_recovered",
            )
            if reconciled:
                changed += 1
                if job and job.status in {"pending", "running"}:
                    await db.execute(
                        update(AsyncJob)
                        .where(
                            AsyncJob.id == job.id,
                            AsyncJob.status.in_(("pending", "running")),
                        )
                        .values(
                            status="failed",
                            error="stale_async_job_recovered",
                            updated_at=now,
                        )
                    )
    if changed:
        await db.commit()
    return changed


async def reconcile_job(db: AsyncSession, job_id: str) -> int:
    """Find and lazily reconcile the Coach session linked to a polled job."""
    recording = (
        await db.execute(
            select(SessionRecording).where(SessionRecording.async_job_id == job_id).limit(1)
        )
    ).scalar_one_or_none()
    if recording:
        return await reconcile_session(db, recording.session_id)
    session_id = (
        await db.execute(
            select(InterviewSession.id)
            .where(InterviewSession.report_job_id == job_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return await reconcile_session(db, session_id) if session_id else 0


async def reconcile_stale_coach_state(batch_size: int = 100) -> int:
    """Run bounded startup recovery using a fresh database session."""
    total = 0
    async with AsyncSessionLocal() as db:
        answer_ids = list(
            (
                await db.execute(
                    select(SessionRecording.session_id)
                    .where(SessionRecording.evaluation_state == "pending")
                    .distinct()
                    .limit(batch_size)
                )
            ).scalars()
        )
        remaining = max(0, batch_size - len(answer_ids))
        report_ids = list(
            (
                await db.execute(
                    select(InterviewSession.id)
                    .where(InterviewSession.report_state == "building")
                    .limit(remaining)
                )
            ).scalars()
        )
        for session_id in dict.fromkeys([*answer_ids, *report_ids]):
            try:
                total += await reconcile_session(db, session_id)
            except Exception:
                await db.rollback()
                logger.exception("Coach stale-state recovery failed for session %s", session_id)
    return total
