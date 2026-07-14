"""Cloud provider setup API tests."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.routers import setup


@pytest.mark.asyncio
async def test_provider_catalog_endpoint_never_returns_secret_values(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-never-return-this")

    response = await client.get("/api/setup/providers")

    assert response.status_code == 200
    assert "sk-never-return-this" not in response.text
    assert any(item["id"] == "openai" for item in response.json()["providers"])


@pytest.mark.asyncio
async def test_setup_status_poll_does_not_call_provider(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_spy = AsyncMock()
    monkeypatch.setattr(setup, "run_provider_connection_test", provider_spy)

    response = await client.get("/api/setup/status")

    assert response.status_code == 200
    provider_spy.assert_not_awaited()
