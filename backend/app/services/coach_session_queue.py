"""Queue Coach session generation while exposing a session stub immediately."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.coach_session import InterviewSession
from ..models.application import Application
from ..observability import get_telemetry
from ..observability.attributes import ASYNC_JOB_ID, COACH_SESSION_ID
from ..repositories.session_repository import SessionRepository
from ..schemas.coach import CreateSessionRequest
from .async_job_service import AsyncJobService
from .coach_service import CoachService
from .coach_contracts import CoachDiagnostic, run_with_stage_deadline
from .coach_session_plan import (
    SessionPlanBuilder,
    SessionPlanError,
    claim_session_setup,
    fail_session_setup,
    finalise_session_setup,
    load_claim_planning_request,
    load_session_plan_sources,
)
from .coach_conversational_contracts import ERROR_REGISTRY

logger = logging.getLogger(__name__)


async def queue_coach_session(
    request: CreateSessionRequest,
    db: AsyncSession,
    service: CoachService | None = None,
    *,
    deduplicate_application: bool = False,
) -> dict:
    """Create a visible setup session and generate its content in the background."""
    if request.experience_version == "conversational_v1":
        if not settings.HATCH_COACH_CONVERSATIONAL_ENABLED:
            raise SessionPlanError("coach_conversation_not_enabled")
        return await queue_conversational_session_setup(
            request,
            db,
            deduplicate_application=deduplicate_application,
        )
    return await queue_legacy_coach_session(
        request,
        db,
        service,
        deduplicate_application=deduplicate_application,
    )


async def queue_legacy_coach_session(
    request: CreateSessionRequest,
    db: AsyncSession,
    service: CoachService | None = None,
    *,
    deduplicate_application: bool = False,
) -> dict:
    """Preserve the legacy-v1 asynchronous creation path unchanged."""
    if deduplicate_application and request.application_id:
        result = await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.application_id == request.application_id,
                InterviewSession.experience_version == "legacy_v1",
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


async def queue_conversational_session_setup(
    request: CreateSessionRequest,
    db: AsyncSession,
    *,
    deduplicate_application: bool = False,
) -> dict:
    """Persist a fenced planning claim before dispatching its worker."""
    if deduplicate_application and request.application_id:
        # SQLite has no row-level SELECT FOR UPDATE. A harmless write to the
        # linked application serializes competing creators until this transaction
        # commits, so the second request observes the first session.
        await db.execute(
            update(Application)
            .where(Application.id == request.application_id)
            .values(updated_at=Application.updated_at)
        )
        result = await db.execute(
            select(InterviewSession)
            .where(
                InterviewSession.application_id == request.application_id,
                InterviewSession.experience_version == "conversational_v1",
                InterviewSession.status != "abandoned",
            )
            .order_by(InterviewSession.created_at.desc())
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return {
                "job_id": existing.setup_job_id,
                "status": existing.status,
                "type": "coach_session",
                "session_id": existing.id,
                "created": False,
                "experience_version": existing.experience_version,
            }

    normalized_request = await load_claim_planning_request(db, request=request)
    stub = InterviewSession(
        application_id=normalized_request.application_id,
        company_name=normalized_request.company_name,
        role_title=normalized_request.role_title,
        config={},
        status="setup",
        experience_version="conversational_v1",
    )
    db.add(stub)
    await db.flush()
    claim = await claim_session_setup(
        db, session_id=stub.id, request=normalized_request
    )
    trace_context = get_telemetry().capture_trace_context()
    await db.commit()

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415

        async with AsyncSessionLocal() as job_db:
            try:
                reconstructed = await load_claim_planning_request(job_db, claim=claim)
                sources = await load_session_plan_sources(
                    job_db, reconstructed, claim=claim
                )
                build = SessionPlanBuilder.build(reconstructed, sources)
                finalised = await finalise_session_setup(
                    job_db,
                    claim=claim,
                    build=build,
                )
                if finalised:
                    await job_db.commit()
                else:
                    await job_db.rollback()
            except asyncio.CancelledError:
                await job_db.rollback()
                if await fail_session_setup(
                    job_db,
                    claim=claim,
                    error_code="coach_setup_claim_expired",
                    retryable=True,
                ):
                    await job_db.commit()
                else:
                    await job_db.rollback()
                raise
            except TimeoutError:
                await job_db.rollback()
                if await fail_session_setup(
                    job_db,
                    claim=claim,
                    error_code="coach_setup_claim_expired",
                    retryable=True,
                ):
                    await job_db.commit()
                else:
                    await job_db.rollback()
            except Exception as exc:
                logger.error(
                    "Conversational Coach setup job %s failed: %s",
                    claim.job_id,
                    type(exc).__name__,
                )
                await job_db.rollback()
                error_code = (
                    exc.code
                    if isinstance(exc, SessionPlanError)
                    else "coach_contract_unsupported"
                )
                if await fail_session_setup(
                    job_db,
                    claim=claim,
                    error_code=error_code,
                    retryable=ERROR_REGISTRY[error_code].retryable,
                ):
                    await job_db.commit()
                else:
                    await job_db.rollback()

    AsyncJobService.run(
        claim.job_id,
        _work(),
        trace_context=trace_context,
        trace_attributes={
            COACH_SESSION_ID: claim.session_id,
            ASYNC_JOB_ID: claim.job_id,
        },
        telemetry_operation="session_create",
    )
    return {
        "job_id": claim.job_id,
        "status": "pending",
        "type": "coach_session",
        "session_id": claim.session_id,
        "created": True,
        "experience_version": "conversational_v1",
    }
