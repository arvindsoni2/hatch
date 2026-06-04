"""Debug endpoints — LLM call traces and latency inspection."""
from __future__ import annotations

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
