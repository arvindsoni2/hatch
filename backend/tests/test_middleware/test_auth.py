"""Tests for optional bearer-token AuthMiddleware — SEC-1."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.main import AuthMiddleware


def _make_app(token: str) -> FastAPI:
    inner = FastAPI()

    @inner.get("/api/health")
    async def health():
        return {"status": "ok"}

    @inner.get("/api/protected")
    async def protected():
        return {"secret": "data"}

    @inner.get("/non-api")
    async def non_api():
        return {"public": True}

    inner.add_middleware(AuthMiddleware, token=token)
    return inner


@pytest.mark.asyncio
async def test_auth_disabled_when_token_empty() -> None:
    """When HATCH_AUTH_TOKEN is empty, all requests pass without a token."""
    app = _make_app(token="")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_rejects_missing_token() -> None:
    """When token is set, requests without Authorization header get 401."""
    app = _make_app(token="supersecret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_auth_accepts_correct_bearer() -> None:
    """When token is set and correct Bearer is provided, request passes."""
    app = _make_app(token="supersecret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected", headers={"Authorization": "Bearer supersecret"})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_rejects_wrong_bearer() -> None:
    """Wrong token returns 401."""
    app = _make_app(token="supersecret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/protected", headers={"Authorization": "Bearer wrongtoken"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_health_always_reachable() -> None:
    """/api/health is exempt from auth even when token is set."""
    app = _make_app(token="supersecret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_options_always_passes() -> None:
    """OPTIONS (CORS preflight) bypasses auth check."""
    app = _make_app(token="supersecret")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.options("/api/protected")
    # FastAPI returns 405 for OPTIONS on non-OPTIONS routes, not 401 — auth did NOT block it
    assert r.status_code != 401


@pytest.mark.asyncio
async def test_cors_allow_credentials_false() -> None:
    """The CORS middleware must NOT send Allow-Credentials: true (bearer auth, not cookies)."""
    from app.main import app as real_app
    async with AsyncClient(transport=ASGITransport(app=real_app), base_url="http://test") as ac:
        r = await ac.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.headers.get("access-control-allow-credentials", "false").lower() != "true"
