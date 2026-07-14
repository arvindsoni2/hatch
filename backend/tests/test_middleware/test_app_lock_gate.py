"""App-lock bootstrap allowlist tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

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

