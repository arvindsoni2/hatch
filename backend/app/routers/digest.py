"""FastAPI router for daily digest preview and send endpoints."""
from __future__ import annotations

import logging
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.digest_service import DigestService
from .settings import write_env_values

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/digest", tags=["digest"])

_digest_service: DigestService | None = None


def _smtp_configured() -> bool:
    from ..config import settings  # noqa: PLC0415

    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASS)


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
    from ..services.locale_service import get_digest_timezone  # noqa: PLC0415
    tz = settings.DIGEST_TIMEZONE or get_digest_timezone(settings.LOCALE)
    return {
        "enabled": settings.DIGEST_ENABLED,
        "time": settings.DIGEST_TIME,
        "timezone": tz,
        "frequency": settings.DIGEST_FREQUENCY,
        "smtp_configured": _smtp_configured(),
        "recipient": settings.NOTIFICATION_EMAIL or None,
    }


_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_ALLOWED_FREQUENCIES = frozenset({"daily"})
_FIELD_MAP = {
    "timezone": "DIGEST_TIMEZONE",
    "time": "DIGEST_TIME",
    "frequency": "DIGEST_FREQUENCY",
    "enabled": "DIGEST_ENABLED",
}


def _invalid(field: str) -> HTTPException:
    return HTTPException(status_code=422, detail=f"Invalid digest {field}")


def _validated_updates(data: dict[str, object]) -> dict[str, str]:
    updates: dict[str, str] = {}
    for field, env_key in _FIELD_MAP.items():
        if field not in data:
            continue
        value = data[field]
        if field == "enabled":
            if not isinstance(value, bool):
                raise _invalid(field)
            updates[env_key] = "true" if value else "false"
        elif field == "time":
            if not isinstance(value, str) or not _TIME_RE.fullmatch(value):
                raise _invalid(field)
            updates[env_key] = value
        elif field == "timezone":
            if not isinstance(value, str):
                raise _invalid(field)
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError):
                raise _invalid(field) from None
            updates[env_key] = value
        elif field == "frequency":
            if not isinstance(value, str) or value not in _ALLOWED_FREQUENCIES:
                raise _invalid(field)
            updates[env_key] = value
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided")
    return updates


@router.patch("/settings")
async def update_digest_settings(data: dict[str, object]) -> dict[str, object]:
    """Update digest settings (timezone, send time, frequency, enabled).

    Validates before writing to data/api_keys.env so an invalid request cannot
    change the file. Returns updated digest status.
    """
    from ..config import settings  # noqa: PLC0415

    updates = _validated_updates(data)
    write_env_values(updates)
    for env_key, value in updates.items():
        os.environ[env_key] = value

    return {
        "enabled": os.environ.get("DIGEST_ENABLED", str(settings.DIGEST_ENABLED)),
        "time": os.environ.get("DIGEST_TIME", settings.DIGEST_TIME),
        "timezone": os.environ.get("DIGEST_TIMEZONE", settings.DIGEST_TIMEZONE),
        "frequency": os.environ.get("DIGEST_FREQUENCY", settings.DIGEST_FREQUENCY),
        "smtp_configured": _smtp_configured(),
        "recipient": settings.NOTIFICATION_EMAIL or None,
    }
