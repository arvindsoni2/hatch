"""FastAPI router for daily digest preview and send endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.digest_service import DigestService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/digest", tags=["digest"])

_digest_service: DigestService | None = None


def _get_service() -> DigestService:
    global _digest_service
    if _digest_service is None:
        _digest_service = DigestService()
    return _digest_service


@router.get("/preview", response_class=HTMLResponse)
async def preview_digest(
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render today's digest as HTML without sending it.

    Returns:
        HTML response with the rendered digest.
    """
    try:
        html = await _get_service().preview_html(db)
        return HTMLResponse(content=html)
    except Exception as exc:
        logger.error("Digest preview failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/send")
async def send_digest(
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Trigger the digest email to be sent now.

    Returns:
        Dict with 'sent' boolean and optional message.
    """
    try:
        sent = await _get_service().send(db)
        return {"sent": sent, "message": "Email sent successfully." if sent else "Skipped — nothing to report or SMTP not configured."}
    except Exception as exc:
        logger.error("Digest send failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/status")
async def digest_status() -> dict[str, object]:
    """Return digest configuration status.

    Returns:
        Dict with enabled flag and configuration.
    """
    from ..config import settings  # noqa: PLC0415
    return {
        "enabled": settings.DIGEST_ENABLED,
        "time": settings.DIGEST_TIME,
        "timezone": settings.DIGEST_TIMEZONE,
        "frequency": settings.DIGEST_FREQUENCY,
        "smtp_configured": bool(settings.SMTP_USER),
        "recipient": settings.NOTIFICATION_EMAIL or None,
    }
