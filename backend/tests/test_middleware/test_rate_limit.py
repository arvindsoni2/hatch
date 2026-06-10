"""Tests for per-client rate limiting middleware — SEC-7."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.main import RateLimitMiddleware


def _make_app(limit: int, enabled: bool) -> FastAPI:
    inner = FastAPI()

    @inner.post("/api/mutate")
    async def mutate():
        return {"ok": True}

    @inner.get("/api/read")
    async def read():
        return {"ok": True}

    inner.add_middleware(RateLimitMiddleware, limit_per_minute=limit, enabled=enabled)
    return inner


@pytest.mark.asyncio
async def test_rate_limit_disabled_when_not_enabled() -> None:
    """When enabled=False, no 429 is returned even if limit is exceeded."""
    app = _make_app(limit=2, enabled=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(5):
            r = await ac.post("/api/mutate")
            assert r.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_limit_exceeded() -> None:
    """When enabled, exceeding the per-minute limit returns 429."""
    app = _make_app(limit=3, enabled=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(3):
            r = await ac.post("/api/mutate")
            assert r.status_code == 200
        # 4th request should be blocked
        r = await ac.post("/api/mutate")
        assert r.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_does_not_apply_to_get() -> None:
    """GET requests are not counted against the rate limit."""
    app = _make_app(limit=2, enabled=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(5):
            r = await ac.get("/api/read")
            assert r.status_code == 200
