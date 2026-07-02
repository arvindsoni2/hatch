"""App-lock API and middleware behaviour."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.app_lock import AppLockConfig, AppLockSession

pytestmark = pytest.mark.app_lock


@pytest.mark.asyncio
async def test_first_run_setup_unlocks_and_protected_api_works(client: AsyncClient) -> None:
    status = await client.get("/api/app-lock/status")
    assert status.status_code == 200
    assert status.json()["configured_source"] == "none"
    assert (await client.get("/api/jobs")).status_code == 423

    setup = await client.post("/api/app-lock/setup", json={"password": "safe-password"})
    assert setup.status_code == 200
    assert setup.json() == {"unlocked": True}
    assert settings.HATCH_APP_SESSION_COOKIE in setup.cookies
    assert (await client.get("/api/jobs")).status_code == 200


@pytest.mark.asyncio
async def test_wrong_password_counts_failures_and_applies_delay(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT", 2)
    await client.post("/api/app-lock/setup", json={"password": "safe-password"})
    await client.post("/api/app-lock/lock")

    first = await client.post("/api/app-lock/unlock", json={"password": "wrong-password"})
    second = await client.post("/api/app-lock/unlock", json={"password": "wrong-password"})
    delayed = await client.post("/api/app-lock/unlock", json={"password": "safe-password"})
    assert first.status_code == second.status_code == 401
    assert delayed.status_code == 429


@pytest.mark.asyncio
async def test_env_password_overrides_database_and_disables_change(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(AppLockConfig(id=1, password_hash="$2b$12$invalid"))
    await db_session.commit()
    monkeypatch.setattr(settings, "HATCH_APP_PASSWORD", "environment-password")

    status = await client.get("/api/app-lock/status")
    assert status.json()["configured_source"] == "env"
    unlocked = await client.post(
        "/api/app-lock/unlock", json={"password": "environment-password"}
    )
    assert unlocked.status_code == 200
    changed = await client.post(
        "/api/app-lock/change-password",
        json={"current_password": "environment-password", "new_password": "new-password"},
    )
    assert changed.status_code == 409


@pytest.mark.asyncio
async def test_change_password_clears_other_sessions(client: AsyncClient, db_session: AsyncSession) -> None:
    await client.post("/api/app-lock/setup", json={"password": "old-password"})
    second = AppLockSession(
        session_hash="f" * 64,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        expires_at=datetime.max,
    )
    db_session.add(second)
    await db_session.commit()

    changed = await client.post(
        "/api/app-lock/change-password",
        json={"current_password": "old-password", "new_password": "new-password"},
    )
    assert changed.status_code == 200
    sessions = (await db_session.execute(select(AppLockSession))).scalars().all()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_disabled_mode_keeps_product_available(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "HATCH_APP_LOCK_ENABLED", False)
    status = await client.get("/api/app-lock/status")
    assert status.json()["enabled"] is False
    assert status.json()["is_unlocked"] is True
    assert (await client.get("/api/jobs")).status_code == 200


@pytest.mark.asyncio
async def test_docs_are_locked(client: AsyncClient) -> None:
    assert (await client.get("/docs")).status_code == 423
    assert (await client.get("/openapi.json")).status_code == 423


@pytest.mark.asyncio
async def test_status_with_session_is_read_only(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup = await client.post("/api/app-lock/setup", json={"password": "safe-password"})
    assert setup.status_code == 200

    cleanup = AsyncMock(side_effect=AssertionError("status must not prune sessions"))
    monkeypatch.setattr(
        "app.services.app_lock_service.AppLockService.cleanup_expired_sessions",
        cleanup,
    )

    status = await client.get("/api/app-lock/status")
    assert status.status_code == 200
    assert status.json()["is_unlocked"] is True
    cleanup.assert_not_awaited()
