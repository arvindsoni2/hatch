"""Read-only system status endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..services.backend_capabilities import build_backend_capability_status

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/capabilities")
async def get_system_capabilities() -> dict[str, Any]:
    return build_backend_capability_status()
