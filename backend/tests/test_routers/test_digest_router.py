from __future__ import annotations

import pytest

from app.config import settings
from app.routers.digest import digest_status


@pytest.mark.asyncio
async def test_digest_status_requires_full_smtp_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", "sender@example.com")
    monkeypatch.setattr(settings, "SMTP_PASS", "")

    status = await digest_status()

    assert status["smtp_configured"] is False
