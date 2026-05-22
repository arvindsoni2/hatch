"""FastAPI router for the auto-apply engine endpoints."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..repositories.auto_apply_repository import AutoApplyRepository
from ..services.auto_apply import AutoApplyEngine
from ..services.claude_client import ClaudeClient
from ..database import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auto-apply", tags=["auto-apply"])

# Shared engine instance
_engine: AutoApplyEngine | None = None


def _get_engine() -> AutoApplyEngine:
    global _engine
    if _engine is None:
        _engine = AutoApplyEngine(
            claude_client=ClaudeClient(),
            db_factory=AsyncSessionLocal,
        )
    return _engine


def get_repo(db: AsyncSession = Depends(get_db)) -> AutoApplyRepository:
    return AutoApplyRepository(db)


@router.post("/prepare/{application_id}")
async def prepare_application(
    application_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Stage 1: navigate job URL, detect form, fill fields, generate Q&A.

    Sets attempt status to 'ready_for_review'. Does NOT submit.

    Args:
        application_id: UUID of the parent Application record.

    Returns:
        The ApplicationAttempt as a dict.
    """
    engine = _get_engine()
    try:
        attempt = await engine.prepare_application(application_id, db)
        return {
            "id": attempt.id,
            "application_id": attempt.application_id,
            "job_url": attempt.job_url,
            "apply_url": attempt.apply_url,
            "platform": attempt.platform,
            "status": attempt.status,
            "form_data": attempt.form_data,
            "custom_questions": attempt.custom_questions,
            "screenshot_before": attempt.screenshot_before,
            "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("prepare_application failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/preview/{attempt_id}")
async def get_preview(
    attempt_id: str,
    repo: AutoApplyRepository = Depends(get_repo),
) -> dict:
    """Stage 2 (read-only): return form_data + custom_questions + screenshots.

    Args:
        attempt_id: UUID of the ApplicationAttempt.

    Returns:
        Attempt dict with all fields for user review.
    """
    attempt = await repo.get_attempt(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail=f"Attempt '{attempt_id}' not found.")
    return {
        "id": attempt.id,
        "application_id": attempt.application_id,
        "job_url": attempt.job_url,
        "apply_url": attempt.apply_url,
        "platform": attempt.platform,
        "status": attempt.status,
        "form_data": attempt.form_data,
        "custom_questions": attempt.custom_questions,
        "cv_path": attempt.cv_path,
        "cl_path": attempt.cl_path,
        "screenshot_before": attempt.screenshot_before,
        "screenshot_after": attempt.screenshot_after,
        "error_message": attempt.error_message,
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
    }


@router.patch("/preview/{attempt_id}")
async def update_preview(
    attempt_id: str,
    updates: dict,
    repo: AutoApplyRepository = Depends(get_repo),
) -> dict:
    """User edits form data fields before approving.

    Args:
        attempt_id: UUID of the attempt to update.
        updates: Dict of fields to update (form_data, custom_questions, cv_path, cl_path).

    Returns:
        Updated attempt dict.
    """
    allowed_fields = {"form_data", "custom_questions", "cv_path", "cl_path"}
    safe_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    attempt = await repo.update_attempt(attempt_id, **safe_updates)
    if not attempt:
        raise HTTPException(status_code=404, detail=f"Attempt '{attempt_id}' not found.")
    return await get_preview(attempt_id, repo)


@router.post("/approve/{attempt_id}")
async def approve_attempt(
    attempt_id: str,
    repo: AutoApplyRepository = Depends(get_repo),
) -> dict:
    """Set attempt status to 'approved' — ready for submission.

    Args:
        attempt_id: UUID of the attempt to approve.

    Returns:
        Updated attempt dict.
    """
    attempt = await repo.get_attempt(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail=f"Attempt '{attempt_id}' not found.")
    if attempt.status != "ready_for_review":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve attempt with status '{attempt.status}'. Must be 'ready_for_review'.",
        )
    await repo.update_attempt(attempt_id, status="approved")
    return await get_preview(attempt_id, repo)


@router.post("/submit/{attempt_id}")
async def submit_attempt(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Stage 3: submit the approved application.

    Re-opens the apply page, fills fields, uploads CV/CL, clicks submit.

    Args:
        attempt_id: UUID of the approved attempt.

    Returns:
        Updated attempt dict with status='submitted' or error info.
    """
    engine = _get_engine()
    try:
        attempt = await engine.submit_application(attempt_id, db)
        return {
            "id": attempt.id,
            "status": attempt.status,
            "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
            "screenshot_after": attempt.screenshot_after,
            "error_message": attempt.error_message,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("submit_application failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/screenshot/{attempt_id}/{which}")
async def get_screenshot(
    attempt_id: str,
    which: str,
    repo: AutoApplyRepository = Depends(get_repo),
) -> FileResponse:
    """Serve a screenshot image for an attempt.

    Args:
        attempt_id: UUID of the attempt.
        which: 'before' or 'after'.

    Returns:
        PNG image response.
    """
    attempt = await repo.get_attempt(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail=f"Attempt '{attempt_id}' not found.")

    path_str = attempt.screenshot_before if which == "before" else attempt.screenshot_after
    if not path_str:
        raise HTTPException(status_code=404, detail=f"No {which} screenshot available.")

    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot file not found.")

    return FileResponse(str(path), media_type="image/png")


@router.get("/history")
async def get_history(
    application_id: str | None = None,
    status: str | None = None,
    repo: AutoApplyRepository = Depends(get_repo),
) -> list[dict]:
    """List application attempt history.

    Args:
        application_id: Optional filter by parent application.
        status: Optional filter by attempt status.

    Returns:
        List of attempt dicts ordered by created_at desc.
    """
    attempts = await repo.list_attempts(application_id=application_id, status=status)
    return [
        {
            "id": a.id,
            "application_id": a.application_id,
            "job_url": a.job_url,
            "platform": a.platform,
            "status": a.status,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in attempts
    ]


@router.post("/retry/{attempt_id}")
async def retry_attempt(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
    repo: AutoApplyRepository = Depends(get_repo),
) -> dict:
    """Retry a failed or captcha-blocked attempt.

    Resets status to 'approved' and re-submits.

    Args:
        attempt_id: UUID of the attempt to retry.
    """
    attempt = await repo.get_attempt(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail=f"Attempt '{attempt_id}' not found.")
    if attempt.status not in ("failed", "captcha_blocked", "manual_required"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry attempt with status '{attempt.status}'.",
        )
    await repo.update_attempt(attempt_id, status="approved", error_message=None)
    return await submit_attempt(attempt_id, db)
