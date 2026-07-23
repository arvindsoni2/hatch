"""Queue Coach session generation while exposing a session stub immediately."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.coach_session import InterviewSession
from ..observability import get_telemetry
from ..observability.attributes import ASYNC_JOB_ID, COACH_SESSION_ID
from ..repositories.session_repository import SessionRepository
from ..schemas.coach import CreateSessionRequest
from .async_job_service import AsyncJobService
from .coach_service import CoachService
from .coach_contracts import CoachDiagnostic, run_with_stage_deadline

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
    if request.jd_text:
        config["jd_text"] = request.jd_text
    stub = await session_repo.create_session(
        application_id=request.application_id,
        company_name=request.company_name,
        role_title=request.role_title,
        config=config,
    )
    async_job = await AsyncJobService.create(db, "coach_session")
    trace_context = get_telemetry().capture_trace_context()
    await db.commit()

    request_data = request.model_dump(mode="json")
    session_id = stub.id
    job_id = async_job.id

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415

        async with AsyncSessionLocal() as job_db:
            try:
                reconstructed = CreateSessionRequest.model_validate(request_data)
                generated = await run_with_stage_deadline(
                    CoachService().create_session(
                        reconstructed, job_db, session_id=session_id
                    ),
                    settings.HATCH_COACH_TIMEOUT_SESSION_CREATE_JOB_SECONDS,
                )
                await AsyncJobService._finish(
                    job_id,
                    generated.model_dump_json(),
                    None,
                    db=job_db,
                )
            except TimeoutError:
                await job_db.rollback()
                diagnostic = CoachDiagnostic(
                    stage="question_generation",
                    outcome="failed",
                    execution_mode="deterministic",
                    attempt_count=0,
                    repair_count=0,
                    gate_codes=["coach_job_timeout"],
                    duration_ms=settings.HATCH_COACH_TIMEOUT_SESSION_CREATE_JOB_SECONDS
                    * 1000,
                )
                repository = SessionRepository(job_db)
                await repository.update_stage_diagnostics(
                    session_id,
                    "question_generation",
                    {
                        "initial": None,
                        "repair": None,
                        "final": diagnostic.model_dump(mode="json"),
                    },
                )
                await repository.update_session_status(session_id, "failed")
                await job_db.commit()
                await AsyncJobService._finish(
                    job_id, None, "coach_job_timeout", db=job_db
                )
            except Exception as exc:
                logger.error("Coach session job %s failed: %s", job_id, exc)
                try:
                    # Keep generation failures distinct from user deletion.
                    # The default session list hides only abandoned sessions,
                    # while failed sessions remain visible and retryable.
                    await SessionRepository(job_db).update_session_status(
                        session_id, "failed"
                    )
                    await job_db.commit()
                except Exception:
                    logger.exception(
                        "Could not mark Coach session %s failed", session_id
                    )
                await AsyncJobService._finish(job_id, None, str(exc), db=job_db)

    AsyncJobService.run(
        job_id,
        _work(),
        trace_context=trace_context,
        trace_attributes={
            COACH_SESSION_ID: session_id,
            ASYNC_JOB_ID: job_id,
        },
        telemetry_operation="session_create",
    )
    return {
        "job_id": async_job.id,
        "status": "pending",
        "type": "coach_session",
        "session_id": stub.id,
        "created": True,
    }
