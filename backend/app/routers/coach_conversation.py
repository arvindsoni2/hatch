"""Strict HTTP boundary for the conversational Coach experience."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas.coach_conversation import (
    ConversationCommandRequest,
    ConversationCommandResult,
    ConversationErrorResponse,
    ConversationLiveView,
)
from ..services.coach_conversation_commands import (
    ConversationCommandError,
    ConversationCommandService,
)
from ..services.coach_conversational_contracts import ERROR_REGISTRY
from ..services.coach_live_view import CoachLiveViewError, CoachLiveViewService
from .coach import _require_safe_id

router = APIRouter(prefix="/api/coach", tags=["coach"])


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


@router.post(
    "/sessions/{session_id}/commands",
    response_model=ConversationCommandResult,
    responses={409: {"model": ConversationErrorResponse}},
)
async def execute_command(
    session_id: str,
    request: ConversationCommandRequest,
    db: AsyncSession = Depends(get_db),
) -> ConversationCommandResult | JSONResponse:
    """Execute one version-fenced conversational command."""
    _require_safe_id(session_id, "session_id")
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
    responses={409: {"model": ConversationErrorResponse}},
)
async def get_live(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConversationLiveView | JSONResponse:
    """Return the reconciled, privacy-bounded live conversational projection."""
    _require_safe_id(session_id, "session_id")
    try:
        return await CoachLiveViewService(db).get_live_view(
            user_id="local", session_id=session_id
        )
    except CoachLiveViewError as error:
        return conversation_error_response(error.code)
