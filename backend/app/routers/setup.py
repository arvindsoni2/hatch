"""Non-secret setup endpoints for easy-install onboarding."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ai_setup import (
    AISetupIntent,
    config_dir,
    load_catalog,
    load_intent,
    load_probe_snapshot,
    load_runtime,
    recommend_models,
    save_intent,
)
from ..services.setup_reset import ResetMode, apply_reset, reset_preview

router = APIRouter(prefix="/api/setup", tags=["setup"])


class ResetApplyRequest(BaseModel):
    mode: ResetMode
    confirmation: str
    preserve_profile: bool = False


@router.get("/status")
async def setup_status() -> dict[str, Any]:
    runtime = load_runtime()
    return {
        "intent": load_intent(),
        "runtime": runtime,
        "restart_required": load_intent().get("restart_required", False),
        "next_command": _next_command(runtime),
    }


@router.get("/hardware")
async def setup_hardware() -> dict[str, Any]:
    snapshot = load_probe_snapshot()
    if snapshot is None:
        return {
            "detected": False,
            "message": "Hardware not detected yet.",
            "next_command": "hatch probe",
        }
    return {"detected": True, "snapshot": snapshot}


@router.get("/models/catalog")
async def models_catalog() -> dict[str, Any]:
    return {"models": load_catalog()}


@router.get("/models/recommendations")
async def model_recommendations() -> dict[str, Any]:
    snapshot = load_probe_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=409, detail="Run `hatch probe` first.")
    platform = snapshot.get("platform", {})
    memory = snapshot.get("memory", {})
    storage = snapshot.get("storage", {})
    models_dir = Path(os.getenv("HATCH_MODELS_DIR", "/models"))
    return recommend_models(
        os_family=str(platform.get("os_family", "unknown")),
        arch=str(platform.get("arch", "unknown")),
        total_ram_gb=float(memory.get("total_gb", 0)),
        free_disk_gb=float(storage.get("models_dir_free_gb", 0)),
        models_dir=models_dir,
    )


@router.post("/ai-mode")
async def set_ai_mode(payload: AISetupIntent) -> dict[str, Any]:
    try:
        return {"intent": save_intent(payload), "next_command": "hatch apply-ai-config"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/local-model-selection")
async def select_local_models(payload: dict[str, Any]) -> dict[str, Any]:
    model_ids = payload.get("selected_model_ids", [])
    intent = AISetupIntent(ai_mode="local", selected_model_ids=model_ids, restart_required=True)
    return await set_ai_mode(intent)


@router.post("/cloud-provider")
async def select_cloud_provider(payload: dict[str, Any]) -> dict[str, Any]:
    forbidden = {"api_key", "key", "token", "secret", "key_value"}
    if forbidden & {key.lower() for key in payload}:
        raise HTTPException(status_code=422, detail="API keys must be set with `hatch secrets set`.")
    provider = str(payload.get("provider", "")).strip()
    if not provider:
        raise HTTPException(status_code=422, detail="provider is required")
    metadata = payload.get("provider_metadata", {})
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=422, detail="provider_metadata must be an object")
    intent = AISetupIntent(
        ai_mode="cloud",
        provider=provider,
        provider_metadata={str(k): str(v) for k, v in metadata.items()},
        restart_required=True,
    )
    response = await set_ai_mode(intent)
    response["next_command"] = f"hatch secrets set {provider}"
    return response


@router.post("/skip-ai")
async def skip_ai() -> dict[str, Any]:
    return await set_ai_mode(AISetupIntent(ai_mode="not_configured", restart_required=True))


@router.get("/doctor")
async def setup_doctor() -> dict[str, Any]:
    runtime = load_runtime()
    probe = load_probe_snapshot()
    checks = {
        "config_directory": config_dir().exists(),
        "hardware_probe": probe is not None,
        "ai_configured": runtime.get("ai_mode") != "not_configured",
    }
    return {"healthy": checks["config_directory"], "checks": checks, "secrets": "redacted"}


@router.get("/reset/preview")
async def preview_reset(
    mode: ResetMode = Query(...),
    preserve_profile: bool = Query(False, alias="preserveProfile"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await reset_preview(db, mode, preserve_profile=preserve_profile)


@router.post("/reset/apply")
async def apply_setup_reset(
    payload: ResetApplyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await apply_reset(
            db,
            payload.mode,
            confirmation=payload.confirmation,
            preserve_profile=payload.preserve_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _next_command(runtime: dict[str, Any]) -> str | None:
    if runtime.get("ai_mode") == "not_configured":
        return "hatch apply-ai-config"
    return None
