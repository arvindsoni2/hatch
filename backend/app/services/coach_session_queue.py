"""Queue Coach session generation while exposing a session stub immediately."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coach_session import InterviewSession
from ..repositories.session_repository import SessionRepository
from ..schemas.coach import CreateSessionRequest
from .async_job_service import AsyncJobService
from .coach_service import CoachService

logger = logging.getLogger(__name__)


async def queue_coach_session(
    request: CreateSessionRequest,
    db: AsyncSession,
    service: CoachService | None = None,
    *,
    deduplicate_application: bool = False,
) -> dict:
    """Create a visible setup session and generate its content in the background."""
    if deduplicate_application and request.application_id:
        result = await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.application_id == request.application_id,
                InterviewSession.status != "abandoned",
            )
            .order_by(InterviewSession.created_at.desc())
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return {
                "job_id": None,
                "status": existing.status,
                "type": "coach_session",
                "session_id": existing.id,
                "created": False,
            }

    session_repo = SessionRepository(db)
    config = request.config.model_dump()
    if request.interview_date:
        config["interview_date"] = request.interview_date
    stub = await session_repo.create_session(
        application_id=request.application_id,
        company_name=request.company_name,
        role_title=request.role_title,
        config=config,
    )
    async_job = await AsyncJobService.create(db, "coach_session")
    await db.commit()

    coach = service or CoachService()

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415

        async with AsyncSessionLocal() as job_db:
            try:
                generated = await coach.create_session(request, job_db, session_id=stub.id)
                await AsyncJobService._finish(
                    async_job.id,
                    generated.model_dump_json(),
                    None,
                )
            except Exception as exc:
                logger.error("Coach session job %s failed: %s", async_job.id, exc)
                try:
                    await SessionRepository(job_db).update_session_status(stub.id, "abandoned")
                    await job_db.commit()
                except Exception:
                    logger.exception("Could not mark Coach session %s abandoned", stub.id)
                await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {
        "job_id": async_job.id,
        "status": "pending",
        "type": "coach_session",
        "session_id": stub.id,
        "created": True,
    }
