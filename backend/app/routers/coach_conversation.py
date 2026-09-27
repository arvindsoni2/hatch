"""Strict HTTP boundary for the conversational Coach experience."""

from __future__ import annotations

import uuid
from pathlib import Path
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.coach_session import InterviewSession
from ..repositories.conversational_session_repository import (
    ConversationalRepositoryError,
    ConversationalSessionRepository,
)
from ..schemas.coach_conversation import (
    AttemptAudioUploadRead,
    ConversationCommandRequest,
    ConversationCommandResult,
    ConversationErrorResponse,
    ConversationLiveView,
    ConversationalProgressRead,
    ConversationalReportRead,
    DeletionCommandResult,
    HardDeletionCommandRequest,
    ReportExportRequest,
    SupportDiagnosticsRead,
)
from ..services.coach_conversation_commands import (
    ConversationCommandError,
    ConversationCommandService,
)
from ..services.coach_service import CoachService
from ..services.coach_reconciliation import reconcile_session
from ..services.coach_conversational_contracts import ERROR_REGISTRY, REPORT_CONTRACT
from ..services.coach_live_view import CoachLiveViewError, CoachLiveViewService
from ..services.coach_media_storage import (
    CoachMediaError,
    StagedAudio,
    cleanup_staged_audio,
    coach_upload_temp_dir,
    resolve_owned_audio_path,
    stream_audio_upload,
)
from ..services.coach_conversational_progress import (
    ConversationalProgressService,
    ProgressSelector,
)
from ..services.coach_privacy import CoachPrivacyService, HardDeletionClaim
from ..services.coach_privacy_queue import queue_hard_deletion
from ..services.coach_report_export import export_report
from ..services.coach_support_diagnostics import build_support_diagnostics
from .coach import _require_safe_id

router = APIRouter(prefix="/api/coach", tags=["coach"])

CANONICAL_ERROR_RESPONSES = {
    status: {"model": ConversationErrorResponse}
    for status in sorted({definition.http_status for definition in ERROR_REGISTRY.values()})
}


def conversation_error_response(
    code: str,
    *,
    current_state: str | None = None,
    current_state_version: int | None = None,
) -> JSONResponse:
    """Render only registry-backed conversational errors at the HTTP boundary."""
    if code not in ERROR_REGISTRY:
        code = "coach_conversation_invalid_state"
    definition = ERROR_REGISTRY[code]
    try:
        payload = ConversationErrorResponse.model_validate(
            {
                "error": {
                    "code": code,
                    "current_state": current_state,
                    "current_state_version": current_state_version,
                    "correlation_id": uuid.uuid4().hex,
                    "details": {},
                }
            }
        )
    except ValueError:
        payload = ConversationErrorResponse.model_validate(
            {
                "error": {
                    "code": "coach_conversation_invalid_state",
                    "correlation_id": uuid.uuid4().hex,
                    "details": {},
                }
            }
        )
        definition = ERROR_REGISTRY["coach_conversation_invalid_state"]
    return JSONResponse(
        status_code=definition.http_status,
        content=payload.model_dump(mode="json"),
    )


def require_safe_conversation_session_id(session_id: str) -> JSONResponse | None:
    """Apply the shared ID semantics without exposing legacy validation details."""
    try:
        _require_safe_id(session_id, "session_id")
    except HTTPException:
        return conversation_error_response("coach_contract_unsupported")
    return None


@router.post(
    "/sessions/{session_id}/commands",
    response_model=ConversationCommandResult,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def execute_command(
    session_id: str,
    request: ConversationCommandRequest,
    db: AsyncSession = Depends(get_db),
) -> ConversationCommandResult | JSONResponse:
    """Execute one version-fenced conversational command."""
    safe_id_error = require_safe_conversation_session_id(session_id)
    if safe_id_error is not None:
        return safe_id_error
    try:
        return await ConversationCommandService(db).execute(
            user_id="local", session_id=session_id, request=request
        )
    except ConversationCommandError as error:
        return conversation_error_response(
            error.code,
            current_state=error.current_state,
            current_state_version=error.current_state_version,
        )


@router.get(
    "/sessions/{session_id}/live",
    response_model=ConversationLiveView,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def get_live(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConversationLiveView | JSONResponse:
    """Return the reconciled, privacy-bounded live conversational projection."""
    safe_id_error = require_safe_conversation_session_id(session_id)
    if safe_id_error is not None:
        return safe_id_error
    try:
        return await CoachLiveViewService(db).get_live_view(
            user_id="local", session_id=session_id
        )
    except CoachLiveViewError as error:
        return conversation_error_response(error.code)


@router.get(
    "/sessions/{session_id}/report",
    response_model=None,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def get_conversational_report(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> ConversationalReportRead | JSONResponse:
    safe_id_error = require_safe_conversation_session_id(session_id)
    if safe_id_error is not None:
        return safe_id_error
    session = await db.get(InterviewSession, session_id)
    if session is not None and session.experience_version != "conversational_v1":
        await reconcile_session(db, session_id)
        return await CoachService().get_report(session_id, db)
    if (
        session is None
        or session.experience_version != "conversational_v1"
        or session.deletion_state != "not_requested"
        or session.report_state not in {"completed", "fallback"}
        or not isinstance(session.report_json, dict)
    ):
        return conversation_error_response("coach_report_unavailable")
    report = dict(session.report_json)
    report.pop("retention_summary", None)
    report.update(
        {
            "session_id": session.id,
            "report_state": session.report_state,
            "activity_version": session.activity_version,
            "retention_version": session.retention_version,
            "retention_summary": (
                dict(session.retention_policy_json)
                if isinstance(session.retention_policy_json, dict)
                else None
            ),
            "contract_version": REPORT_CONTRACT,
        }
    )
    try:
        return ConversationalReportRead.model_validate(report)
    except ValueError:
        return conversation_error_response("coach_report_unavailable")


@router.get(
    "/conversational-progress",
    response_model=ConversationalProgressRead,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def get_conversational_progress(
    session_id: str | None = Query(default=None),
    application_id: str | None = Query(default=None),
    compatibility_key: str | None = Query(default=None),
    company_name: str | None = Query(default=None),
    role_title: str | None = Query(default=None),
    group_limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ConversationalProgressRead | JSONResponse:
    try:
        selector = ProgressSelector(
            mode="exact" if session_id is not None else "filtered",
            session_id=session_id,
            application_id=application_id,
            compatibility_key=compatibility_key,
            company_name=company_name,
            role_title=role_title,
        )
    except ValueError:
        return conversation_error_response("coach_progress_selector_conflict")
    result = await ConversationalProgressService(
        ConversationalSessionRepository(db)
    ).get_progress(selector, group_limit)
    return result


@router.post(
    "/sessions/{session_id}/exports",
    response_model=None,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def export_conversational_report(
    session_id: str,
    request: ReportExportRequest,
    db: AsyncSession = Depends(get_db),
) -> Response | JSONResponse:
    safe_id_error = require_safe_conversation_session_id(session_id)
    if safe_id_error is not None:
        return safe_id_error
    try:
        payload = await export_report(
            session_id, request, ConversationalSessionRepository(db)
        )
    except ValueError as error:
        code = str(error)
        if code not in ERROR_REGISTRY:
            code = "coach_report_unavailable"
        return conversation_error_response(code)
    return Response(payload.body, media_type=payload.media_type, headers=payload.headers())


@router.post(
    "/sessions/{session_id}/deletion-commands",
    response_model=DeletionCommandResult,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def request_hard_deletion(
    session_id: str,
    request: HardDeletionCommandRequest,
    db: AsyncSession = Depends(get_db),
) -> DeletionCommandResult | JSONResponse:
    safe_id_error = require_safe_conversation_session_id(session_id)
    if safe_id_error is not None:
        return safe_id_error
    try:
        result = await CoachPrivacyService(
            ConversationalSessionRepository(db)
        ).claim_hard_deletion(session_id, request, now=datetime.utcnow())
        if isinstance(result, HardDeletionClaim):
            await db.commit()
            queue_hard_deletion(result)
            return DeletionCommandResult(
                command_id=request.command_id,
                result_state="processing",
                contract_version=request.contract_version,
            )
        await db.commit()
        return result
    except ConversationalRepositoryError as error:
        await db.rollback()
        code = str(error)
        if code not in ERROR_REGISTRY:
            code = "coach_session_deletion_failed"
        return conversation_error_response(code)


@router.get(
    "/sessions/{session_id}/diagnostics",
    response_model=SupportDiagnosticsRead,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def get_conversational_diagnostics(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> SupportDiagnosticsRead | JSONResponse:
    safe_id_error = require_safe_conversation_session_id(session_id)
    if safe_id_error is not None:
        return safe_id_error
    session = await db.get(InterviewSession, session_id)
    if (
        session is None
        or session.experience_version != "conversational_v1"
        or session.deletion_state != "not_requested"
    ):
        return conversation_error_response("coach_report_unavailable")
    return build_support_diagnostics(
        session, error_code=session.recoverable_error_code
    )


@router.post(
    "/sessions/{session_id}/attempts/{attempt_id}/audio",
    response_model=AttemptAudioUploadRead,
    responses=CANONICAL_ERROR_RESPONSES,
)
async def upload_attempt_audio(
    session_id: str,
    attempt_id: str,
    upload_id: Annotated[str, Form(min_length=1, max_length=64)],
    content_sha256: Annotated[str, Form(pattern=r"^[0-9a-f]{64}$")],
    audio: UploadFile = File(),
    db: AsyncSession = Depends(get_db),
) -> AttemptAudioUploadRead | JSONResponse:
    """Stream and persist one idempotent, attempt-owned browser recording."""
    staged: StagedAudio | None = None
    audio_closed = False
    try:
        for value, field in (
            (session_id, "session_id"),
            (attempt_id, "attempt_id"),
            (upload_id, "upload_id"),
        ):
            _require_safe_id(value, field)
        storage_root = Path(settings.HATCH_COACH_MEDIA_ROOT)
        staged = await stream_audio_upload(
            audio,
            max_bytes=settings.HATCH_COACH_MAX_AUDIO_BYTES,
            temp_dir=coach_upload_temp_dir(storage_root),
        )
        try:
            await audio.close()
            audio_closed = True
        except BaseException as error:
            if not isinstance(error, Exception):
                raise
            try:
                cleanup_staged_audio(staged)
            except CoachMediaError:
                pass
            return conversation_error_response("coach_attempt_upload_conflict")
        destination = resolve_owned_audio_path(
            storage_root, session_id, attempt_id, upload_id, ".webm"
        )
        repository = ConversationalSessionRepository(db)
        result = await repository.persist_audio_upload(
            session_id=session_id,
            attempt_id=attempt_id,
            upload_id=upload_id,
            declared_sha256=content_sha256,
            staged=staged,
            destination=destination,
        )
        await repository.commit_audio_upload()
        return result
    except HTTPException:
        return conversation_error_response("coach_attempt_upload_conflict")
    except (CoachMediaError, ConversationalRepositoryError) as error:
        code = str(error)
        if code not in ERROR_REGISTRY:
            code = "coach_attempt_upload_conflict"
        return conversation_error_response(code)
    finally:
        if staged is not None:
            try:
                cleanup_staged_audio(staged)
            except CoachMediaError:
                pass
        if not audio_closed:
            try:
                await audio.close()
            except Exception:
                pass
