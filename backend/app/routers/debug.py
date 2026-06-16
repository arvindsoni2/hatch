"""Debug endpoints — LLM call traces and latency inspection."""
from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/llm-traces")
async def list_llm_traces() -> list[dict]:
    """Return the last 100 LLM calls with latency, token counts, and response preview."""
    from ..agents.tools.llm_factory import get_llm_traces  # noqa: PLC0415
    return get_llm_traces()


@router.delete("/llm-traces")
async def clear_llm_traces() -> dict:
    """Clear the in-memory LLM trace buffer."""
    from ..agents.tools.llm_factory import clear_llm_traces  # noqa: PLC0415
    clear_llm_traces()
    return {"cleared": True}


async def _probe_service(name: str, url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        latency_ms = round((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "status": "online" if response.status_code < 500 else "degraded",
            "detail": f"HTTP {response.status_code}",
            "latency_ms": latency_ms,
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000)
        return {
            "name": name,
            "status": "offline",
            "detail": exc.__class__.__name__,
            "latency_ms": latency_ms,
        }


@router.get("/runtime-status")
async def runtime_status() -> dict[str, Any]:
    """Return lightweight runtime health for the app and bundled LLM services."""
    services = [
        {"name": "backend", "status": "online", "detail": "API responding", "latency_ms": 0},
        await _probe_service("llm-primary", "http://llm-primary:8080/health"),
        await _probe_service("llm-triage", "http://llm-triage:8081/health"),
    ]
    return {"services": services, "checked_at": time.time()}
