"""Non-secret setup endpoints for easy-install onboarding."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.ai_setup import (
    AISetupIntent,
    ExperienceSetupIntent,
    BACKEND_PROFILES,
    build_hardware_recommendation,
    canonical_provider,
    config_dir,
    load_backend_capabilities,
    load_catalog,
    load_intent,
    load_probe_snapshot,
    load_runtime,
    provider_secret_env,
    recommend_models,
    save_experience_intent,
    save_intent,
)
from ..services.setup_reset import ResetMode, apply_reset, reset_preview
from ..services.onboarding_service import (
    OnboardingFinalizationError,
    OnboardingService,
)
from ..schemas.setup import IntentPatch
from ..services.setup_intent import patch_setup_intent
from ..services.model_discovery import discover_models
from ..services.provider_catalog import (
    provider_catalog,
    test_provider_connection as run_provider_connection_test,
    validate_provider_selection,
)
from ..services.pdf_export import pdf_export_capability

router = APIRouter(prefix="/api/setup", tags=["setup"])


class ResetApplyRequest(BaseModel):
    mode: ResetMode
    confirmation: str
    preserve_profile: bool = False


class OnboardingProgressRequest(BaseModel):
    step_id: str


class OnboardingFinalizeRequest(BaseModel):
    finalization_id: UUID
    profile: dict[str, Any]


def _onboarding_payload(state) -> dict[str, str | None]:
    return {
        "status": state.status,
        "last_completed_step": state.last_completed_step,
    }


@router.patch("/intent")
async def patch_intent(body: IntentPatch) -> dict[str, Any]:
    intent = patch_setup_intent(body)
    return {"intent": intent.model_dump(mode="json")}


@router.post("/onboarding/progress")
async def onboarding_progress(
    body: OnboardingProgressRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        state = await OnboardingService(db).mark_in_progress(body.step_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"onboarding": _onboarding_payload(state)}


@router.post("/onboarding/finalize")
async def finalize_onboarding(
    body: OnboardingFinalizeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        state = await OnboardingService(db).finalize(
            str(body.finalization_id), body.profile
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "profile_invalid",
                "message": "The onboarding profile contains invalid fields.",
                "fields": [".".join(str(part) for part in error["loc"]) for error in exc.errors()],
            },
        ) from exc
    except OnboardingFinalizationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return {"onboarding": _onboarding_payload(state)}


@router.get("/status")
async def setup_status() -> dict[str, Any]:
    runtime = load_runtime()
    intent = load_intent()
    backend = load_backend_capabilities()
    probe = load_probe_snapshot()
    experience = str(intent.get("experience") or _derive_experience(runtime, backend))
    ai_mode = str(intent.get("ai_mode") or runtime.get("ai_mode") or "not_configured")
    provider = canonical_provider(intent.get("provider") or runtime.get("provider"))
    env_name = provider_secret_env(provider)
    configured = False
    healthy = False
    if ai_mode == "local":
        configured = bool(runtime.get("primary_model_id") or intent.get("selected_model_ids"))
        healthy = configured
    elif ai_mode == "cloud":
        configured = bool(provider and env_name and os.getenv(env_name))
        healthy = configured
    action_required = None if healthy else "provider_or_local_model"
    operation = _profile_operation(str(intent.get("backend_profile") or backend["profile"]), backend["profile"])
    hardware = build_hardware_recommendation(probe, experience=experience)
    return {
        "schema_version": 1,
        "onboarding_complete": True,
        "experience": experience,
        "ai": {
            "mode": ai_mode,
            "configured": configured,
            "healthy": healthy,
            "provider": provider or None,
            "model": intent.get("provider_metadata", {}).get("model") or runtime.get("primary_model_id"),
            "action_required": action_required,
        },
        "capabilities": {
            "profile": backend["profile"],
            "enabled": backend["enabled"],
            "available_profiles": ["core", "browser", "local-embeddings", "full"],
            "operation": operation,
        },
        "hardware": hardware,
        "operation": operation,
        "intent": intent,
        "runtime": runtime,
        "restart_required": intent.get("restart_required", False),
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


@router.get("/providers")
async def setup_providers() -> dict[str, Any]:
    catalog = provider_catalog()
    return {
        **catalog,
        "providers": [
            {**provider, "configured": bool(os.getenv(provider["secret_env"]))}
            for provider in catalog["providers"]
        ],
    }


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


@router.get("/models/discovery")
async def model_discovery(force: bool = Query(False)) -> dict[str, Any]:
    snapshot = load_probe_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=409, detail="Run `hatch probe` first.")
    result = await discover_models(snapshot, force=force)
    return result.model_dump(mode="json")


@router.post("/ai-mode")
async def set_ai_mode(payload: AISetupIntent) -> dict[str, Any]:
    try:
        return {"intent": save_intent(payload), "next_command": "hatch apply-ai-config"}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/experience")
async def set_experience(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        intent = save_experience_intent(ExperienceSetupIntent(**payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    current_profile = load_backend_capabilities()["profile"]
    operation = _profile_operation(str(intent.get("backend_profile") or "core"), current_profile)
    return {
        "intent": intent,
        "host_action_required": operation is not None,
        "operation": operation,
        "next_command": operation["command"] if operation else "hatch apply-ai-config",
    }


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
    primary_requested = payload.get("primary_model") or metadata.get("primary_model") or metadata.get("model")
    triage_requested = payload.get("triage_model") or metadata.get("triage_model") or metadata.get("model")
    try:
        primary, triage = validate_provider_selection(
            provider,
            str(primary_requested) if primary_requested else None,
            str(triage_requested) if triage_requested else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    patch_setup_intent(IntentPatch(
        ai_mode="cloud",
        cloud_provider=provider,
        cloud_primary_model=primary,
        cloud_triage_model=triage,
        restart_required=True,
    ))
    return {"intent": load_intent(), "next_command": f"hatch secrets set {provider}"}


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
    metadata = payload.get("provider_metadata") or {}
    primary = payload.get("primary_model") or payload.get("model") or metadata.get("primary_model") or metadata.get("model")
    triage = payload.get("triage_model") or metadata.get("triage_model") or primary
    return await run_provider_connection_test(provider, primary, triage)


@router.post("/skip-ai")
async def skip_ai() -> dict[str, Any]:
    intent = patch_setup_intent(IntentPatch(ai_mode="none", restart_required=True))
    return {"intent": intent.model_dump(mode="json"), "next_command": None}


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


def _derive_experience(runtime: dict[str, Any], backend: dict[str, Any]) -> str:
    if backend.get("profile") == "full":
        return "full_ai"
    if backend.get("profile") != "core":
        return "custom"
    return "essential"


def _profile_operation(target_profile: str, current_profile: str) -> dict[str, Any] | None:
    if target_profile not in BACKEND_PROFILES:
        raise HTTPException(status_code=422, detail="unsupported backend profile")
    if target_profile == current_profile:
        return None
    command = "hatch capabilities disable" if target_profile == "core" else f"hatch capabilities enable {target_profile}"
    return {
        "id": f"backend-profile-{target_profile}",
        "state": "host_action_required",
        "host_action_required": True,
        "command": command,
        "current_profile": current_profile,
        "target_profile": target_profile,
    }
