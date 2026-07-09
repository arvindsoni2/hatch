"""Non-secret setup endpoints for easy-install onboarding."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ai_setup import (
    AISetupIntent,
    canonical_provider,
    config_dir,
    load_catalog,
    load_intent,
    load_probe_snapshot,
    load_runtime,
    provider_secret_env,
    recommend_models,
    save_intent,
)
from ..services.setup_reset import ResetMode, apply_reset, reset_preview
from ..services.pdf_export import pdf_export_capability

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


@router.post("/hardware")
async def refresh_hardware_probe() -> dict[str, Any]:
    snapshot = load_probe_snapshot()
    if snapshot is not None:
        return {"started": False, "detected": True, "snapshot": snapshot}
    return {
        "started": False,
        "detected": False,
        "message": "Run hatch probe from the host, then refresh this page.",
        "next_command": "hatch probe",
    }


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
    provider = canonical_provider(provider)
    if provider_secret_env(provider) is None:
        raise HTTPException(status_code=422, detail=f"unsupported provider: {provider}")
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


@router.get("/capabilities")
async def setup_capabilities() -> dict[str, Any]:
    runtime = load_runtime()
    intent = load_intent()
    probe = load_probe_snapshot()
    selected_provider = canonical_provider(intent.get("provider") or runtime.get("provider"))
    pdf_capability = pdf_export_capability()

    def secret_status(provider: str) -> str:
        env_name = provider_secret_env(provider)
        if not env_name:
            return "unavailable"
        if selected_provider != provider:
            return "needs_setup"
        return "available" if os.getenv(env_name) else "needs_setup"

    capabilities = [
        {
            "id": "core_tracking",
            "label": "Application tracking",
            "description": "Track opportunities, applications, follow-ups, and outcomes.",
            "status": "available",
            "installProfile": "lightweight",
            "privacyImpact": "none",
            "costImpact": "free",
            "requiresSecret": False,
            "requiresProbe": False,
        },
        {
            "id": "cv_studio",
            "label": "CV studio",
            "description": "Create and manage CV and cover-letter packages.",
            "status": "available",
            "installProfile": "lightweight",
            "privacyImpact": "local_only",
            "costImpact": "free",
            "requiresSecret": False,
            "requiresProbe": False,
        },
        {
            "id": "local_llm",
            "label": "Local AI",
            "description": "Run bundled local models for AI-assisted Hatch workflows.",
            "status": "available" if runtime.get("ai_mode") == "local" else ("needs_setup" if probe else "unavailable"),
            "installProfile": "lightweight",
            "privacyImpact": "local_only",
            "costImpact": "local_resource",
            "requiresSecret": False,
            "requiresProbe": True,
            "docsCommand": "hatch probe" if probe is None else "hatch models install",
        },
        {
            "id": "cloud_llm",
            "label": "Cloud AI",
            "description": "Use a host-configured cloud provider for AI-assisted workflows.",
            "status": "available" if runtime.get("ai_mode") == "cloud" else "needs_setup",
            "installProfile": "lightweight",
            "privacyImpact": "leaves_device",
            "costImpact": "external_api_cost",
            "requiresSecret": True,
            "requiresProbe": False,
            "docsCommand": "hatch secrets set <provider>",
        },
        {
            "id": "openrouter_provider",
            "label": "OpenRouter",
            "description": "Use OpenRouter's OpenAI-compatible chat API with host-owned secrets.",
            "status": secret_status("openrouter"),
            "installProfile": "lightweight",
            "privacyImpact": "leaves_device",
            "costImpact": "external_api_cost",
            "requiresSecret": True,
            "requiresProbe": False,
            "docsCommand": "hatch secrets set openrouter",
        },
        {
            "id": "job_import_url",
            "label": "Import from URL",
            "description": "Create job records from pasted job-posting URLs.",
            "status": "available",
            "installProfile": "lightweight",
            "privacyImpact": "leaves_device",
            "costImpact": "free",
            "requiresSecret": False,
            "requiresProbe": False,
        },
        {
            "id": "document_generation_docx",
            "label": "DOCX generation",
            "description": "Generate editable DOCX application documents.",
            "status": "available",
            "installProfile": "lightweight",
            "privacyImpact": "local_only",
            "costImpact": "free",
            "requiresSecret": False,
            "requiresProbe": False,
        },
        {
            "id": "document_generation_pdf",
            "label": "PDF export",
            "description": "Preview or download generated documents as local PDF exports.",
            "status": pdf_capability["status"],
            "installProfile": "full",
            "privacyImpact": "local_only",
            "costImpact": "free",
            "requiresSecret": False,
            "requiresProbe": False,
            "message": pdf_capability["message"],
        },
        {
            "id": "diagnostics",
            "label": "Diagnostics",
            "description": "Show setup, probe, and runtime status without exposing secrets.",
            "status": "available",
            "installProfile": "lightweight",
            "privacyImpact": "none",
            "costImpact": "free",
            "requiresSecret": False,
            "requiresProbe": False,
        },
    ]
    return {"capabilities": capabilities}


@router.post("/provider/test")
async def test_provider_connection(payload: dict[str, Any]) -> dict[str, Any]:
    provider = canonical_provider(str(payload.get("provider", "")))
    env_name = provider_secret_env(provider)
    if not env_name:
        raise HTTPException(status_code=422, detail=f"unsupported provider: {provider}")
    secret = os.getenv(env_name, "")
    if not secret:
        return {
            "ok": False,
            "status": "missing_secret",
            "error": f"{env_name} is not configured.",
            "next_command": f"hatch secrets set {provider}",
        }
    if provider != "openrouter":
        return {"ok": False, "status": "configured_not_tested", "error": "Provider test is not available yet."}

    model = str(payload.get("model") or payload.get("provider_metadata", {}).get("model") or "openai/gpt-4o-mini")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {secret}",
                    "Content-Type": "application/json",
                    "X-OpenRouter-Title": "Hatch Setup Test",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 4,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = "invalid_secret" if exc.response.status_code in {401, 403} else "provider_unavailable"
        if exc.response.status_code == 404:
            status = "model_not_found"
        if exc.response.status_code == 429:
            status = "rate_limited"
        return {"ok": False, "status": status, "error": str(exc)}
    except httpx.HTTPError as exc:
        return {"ok": False, "status": "provider_unavailable", "error": str(exc)}
    return {"ok": True, "status": "ready", "provider": provider, "model": model}


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
