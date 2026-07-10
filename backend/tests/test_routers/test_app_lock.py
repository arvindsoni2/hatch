"""App-lock API and middleware behaviour."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.app_lock import AppLockConfig, AppLockSession

pytestmark = pytest.mark.app_lock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "password",
    [
        "abc123",
        "letters-only-password",
        "123456789012",
        "validpassword1",
        " valid-password-1",
        "valid-password-1 ",
        f"a1{'x' * 127}",
    ],
)
async def test_setup_rejects_passwords_outside_shared_policy(
    client: AsyncClient, password: str
) -> None:
    response = await client.post("/api/app-lock/setup", json={"password": password})
    assert response.status_code == 422
    assert password not in response.text


@pytest.mark.asyncio
async def test_first_run_setup_unlocks_and_protected_api_works(client: AsyncClient) -> None:
    status = await client.get("/api/app-lock/status")
    assert status.status_code == 200
    assert status.json()["configured_source"] == "none"
    assert status.json()["password_policy"] == {
        "min_length": 12,
        "max_length": 128,
        "require_letter": True,
        "require_number": True,
        "require_symbol": True,
        "reject_edge_whitespace": True,
    }
    assert (await client.get("/api/jobs")).status_code == 423

    setup = await client.post("/api/app-lock/setup", json={"password": "safe-password-1"})
    assert setup.status_code == 200
    assert setup.json() == {"unlocked": True}
    assert settings.HATCH_APP_SESSION_COOKIE in setup.cookies
    assert (await client.get("/api/jobs")).status_code == 200


@pytest.mark.asyncio
async def test_locale_metadata_is_available_while_product_data_stays_locked(
    client: AsyncClient,
) -> None:
    assert (await client.get("/api/jobs")).status_code == 423

    locales = await client.get("/api/v2/locales")
    assert locales.status_code == 200
    assert any(locale["id"] == "uk" for locale in locales.json())

    legal_fields = await client.get("/api/v2/locales/uk/legal-fields")
    assert legal_fields.status_code == 200

    boards = await client.get("/api/v2/locales/uk/boards?enabled_only=false")
    assert boards.status_code == 200


@pytest.mark.asyncio
async def test_wrong_password_counts_failures_and_applies_delay(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT", 2)
    await client.post("/api/app-lock/setup", json={"password": "safe-password-1"})
    await client.post("/api/app-lock/lock")

    first = await client.post("/api/app-lock/unlock", json={"password": "wrong-password"})
    second = await client.post("/api/app-lock/unlock", json={"password": "wrong-password"})
    delayed = await client.post("/api/app-lock/unlock", json={"password": "safe-password-1"})
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
    await client.post("/api/app-lock/setup", json={"password": "old-password-1"})
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
        json={"current_password": "old-password-1", "new_password": "new-password-2"},
    )
    assert changed.status_code == 200
    sessions = (await db_session.execute(select(AppLockSession))).scalars().all()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_change_password_rejects_current_value(client: AsyncClient) -> None:
    password = "same-password-1"
    await client.post("/api/app-lock/setup", json={"password": password})
    changed = await client.post(
        "/api/app-lock/change-password",
        json={"current_password": password, "new_password": password},
    )
    assert changed.status_code == 422
    assert changed.json()["detail"] == "New password must be different from the current password."


@pytest.mark.asyncio
async def test_legacy_password_still_unlocks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    legacy_password = "oldpass1"
    db_session.add(
        AppLockConfig(
            id=1,
            password_hash=bcrypt.hashpw(legacy_password.encode(), bcrypt.gensalt()).decode(),
        )
    )
    await db_session.commit()

    unlocked = await client.post(
        "/api/app-lock/unlock",
        json={"password": legacy_password},
    )
    assert unlocked.status_code == 200


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
    setup = await client.post("/api/app-lock/setup", json={"password": "safe-password-1"})
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
