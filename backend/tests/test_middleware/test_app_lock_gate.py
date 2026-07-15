"""App-lock bootstrap allowlist tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_lock import AppLockConfig
from app.models.onboarding import OnboardingState
from app.services.app_lock_service import AppLockService

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
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    extracted_text = (
        "Jane Doe\njane@example.com\nProfessional Experience\n"
        "2020 - Present Senior Engineer\nExample Ltd\nBuilt reliable systems.\n"
        "Skills\nPython, FastAPI"
    )
    monkeypatch.setattr("app.routers.resume._extract_text_from_pdf", lambda _: extracted_text)
    monkeypatch.setattr("app.routers.resume._data_dir", lambda: tmp_path)
    monkeypatch.setattr("app.services.resume_store.save_resume_text", lambda _: None)

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.pdf", b"synthetic pdf", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "resume.pdf"


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


@pytest.mark.asyncio
async def test_bootstrap_state_error_denies_resume_upload(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_configured_source(_service: AppLockService) -> str:
        raise RuntimeError("bootstrap state unavailable")

    monkeypatch.setattr(AppLockService, "configured_source", fail_configured_source)

    response = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.pdf", b"synthetic pdf", "application/pdf")},
    )

    assert response.status_code == 423
    assert response.json() == {"detail": "Hatch is locked."}
