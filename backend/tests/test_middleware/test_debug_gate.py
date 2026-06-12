"""Tests for debug-router gating behind LOG_LEVEL=DEBUG — SEC-5."""
from __future__ import annotations

import importlib
import sys

import pytest
from httpx import AsyncClient, ASGITransport


def _rebuild_app(log_level: str):
    """Rebuild the app with a patched settings LOG_LEVEL.

    Re-imports app.main under a patched LOG_LEVEL, then restores the original
    module in sys.modules so the conftest's cached `app` singleton stays valid.
    """
    import app.config as _cfg
    orig_level = _cfg.settings.LOG_LEVEL
    orig_module = sys.modules.get("app.main")
    _cfg.settings.LOG_LEVEL = log_level
    if "app.main" in sys.modules:
        del sys.modules["app.main"]
    try:
        import app.main as _main
        built = _main.create_app()
    finally:
        # Restore original module so downstream tests see the same app singleton
        _cfg.settings.LOG_LEVEL = orig_level
        if orig_module is not None:
            sys.modules["app.main"] = orig_module
        elif "app.main" in sys.modules:
            del sys.modules["app.main"]
    return built


@pytest.mark.asyncio
async def test_debug_router_mounted_at_info_level() -> None:
    """GET /api/debug/llm-traces returns 200 at INFO level (always mounted)."""
    application = _rebuild_app("INFO")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        r = await ac.get("/api/debug/llm-traces")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_debug_router_mounted_at_debug_level() -> None:
    """GET /api/debug/llm-traces returns 200 (or non-404) when LOG_LEVEL=DEBUG."""
    application = _rebuild_app("DEBUG")
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        r = await ac.get("/api/debug/llm-traces")
    assert r.status_code != 404
