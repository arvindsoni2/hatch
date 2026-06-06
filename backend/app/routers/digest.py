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


@router.patch("/settings")
async def update_digest_settings(data: dict[str, object]) -> dict[str, object]:
    """Update digest settings (timezone, send time, frequency, enabled).

    Writes to data/api_keys.env so settings survive container restarts.
    Returns updated digest status.
    """
    import os  # noqa: PLC0415
    import re  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    from ..config import settings  # noqa: PLC0415

    _allowed = {
        "DIGEST_TIMEZONE": str,
        "DIGEST_TIME": str,
        "DIGEST_FREQUENCY": str,
        "DIGEST_ENABLED": str,
    }
    env_file = Path(os.getenv("DATA_DIR", "./data")) / "api_keys.env"
    env_file.parent.mkdir(parents=True, exist_ok=True)

    field_map = {
        "timezone": "DIGEST_TIMEZONE",
        "time": "DIGEST_TIME",
        "frequency": "DIGEST_FREQUENCY",
        "enabled": "DIGEST_ENABLED",
    }

    updates: dict[str, str] = {}
    for field, env_key in field_map.items():
        if field in data:
            updates[env_key] = str(data[field])

    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields provided")

    # Read existing env file
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text().splitlines()

    for env_key, value in updates.items():
        updated = False
        new_lines = []
        for line in lines:
            if re.match(rf"^{re.escape(env_key)}\s*=", line):
                new_lines.append(f"{env_key}={value}")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"{env_key}={value}")
        lines = new_lines
        os.environ[env_key] = value

    env_file.write_text("\n".join(lines) + "\n")

    return {
        "enabled": os.environ.get("DIGEST_ENABLED", str(settings.DIGEST_ENABLED)),
        "time": os.environ.get("DIGEST_TIME", settings.DIGEST_TIME),
        "timezone": os.environ.get("DIGEST_TIMEZONE", settings.DIGEST_TIMEZONE),
        "frequency": os.environ.get("DIGEST_FREQUENCY", settings.DIGEST_FREQUENCY),
        "smtp_configured": bool(settings.SMTP_USER),
        "recipient": settings.NOTIFICATION_EMAIL or None,
    }
