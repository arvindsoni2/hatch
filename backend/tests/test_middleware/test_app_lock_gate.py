"""App-lock bootstrap allowlist tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_lock import AppLockConfig
from app.models.onboarding import OnboardingState

pytestmark = pytest.mark.app_lock


@pytest.mark.asyncio
async def test_locked_bootstrap_can_read_setup_status(client: AsyncClient) -> None:
    response = await client.get("/api/setup/status")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_locked_bootstrap_can_save_non_secret_ai_intent(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path / "config"))

    response = await client.post("/api/setup/ai-mode", json={"ai_mode": "not_configured"})

    assert response.status_code == 200
    assert response.json()["intent"]["ai_mode"] == "not_configured"


@pytest.mark.asyncio
async def test_locked_bootstrap_cannot_write_profile(client: AsyncClient) -> None:
    response = await client.put("/api/v2/profile", json={})

    assert response.status_code == 423


@pytest.mark.asyncio
async def test_unconfigured_incomplete_onboarding_can_reach_resume_upload(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.txt", b"resume", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Only PDF and DOCX files are supported."


@pytest.mark.asyncio
async def test_completed_onboarding_cannot_bootstrap_resume_upload(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(OnboardingState(id=1, status="complete"))
    await db_session.commit()

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.txt", b"resume", "text/plain")},
    )

    assert response.status_code == 423
    assert response.json() == {"detail": "Hatch is locked."}


@pytest.mark.asyncio
async def test_configured_incomplete_onboarding_cannot_bootstrap_resume_upload(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(AppLockConfig(id=1, password_hash="hash"))
    await db_session.commit()

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.txt", b"resume", "text/plain")},
    )

    assert response.status_code == 423
    assert response.json() == {"detail": "Hatch is locked."}
