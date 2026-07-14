"""Request-time setup readiness derived from intent and current evidence."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .ai_setup import (
    build_hardware_recommendation,
    load_backend_capabilities,
    load_probe_snapshot,
    load_runtime,
)
from .model_discovery import verification_status
from .onboarding_service import OnboardingService
from .provider_catalog import provider_validation_status
from .setup_intent import load_setup_intent


def _action(action_id: str, label: str, command: str | None, *args: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "executable": "hatch" if command else None,
        "args": list(args),
        "command": command,
    }


def _capability_operation(selected: str, active: str) -> dict[str, Any] | None:
    if selected == active:
        return None
    if selected == "core":
        command = "hatch capabilities disable --all"
        args = ("capabilities", "disable", "--all")
    else:
        command = f"hatch capabilities enable {selected}"
        args = ("capabilities", "enable", selected)
    return {
        "id": "capabilities.apply",
        "label": "Apply the selected capability profile",
        "host_action_required": True,
        "selected_profile": selected,
        "active_profile": active,
        "command": command,
        "executable": "hatch",
        "args": list(args),
    }


async def build_setup_status(db: AsyncSession) -> dict[str, Any]:
    intent = load_setup_intent()
    runtime = load_runtime()
    backend = load_backend_capabilities()
    probe = load_probe_snapshot()
    onboarding = await OnboardingService(db).status()
    actions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    ai_status = "not_configured"
    local_status = "not_selected"
    cloud_status = "not_selected"

    if intent.ai_mode == "none":
        ai_status = "ready"
    elif intent.ai_mode == "local":
        if not intent.local_primary_model or not intent.local_triage_model:
            ai_status = "needs_user_input"
            local_status = "selection_required"
            actions.append(_action("models.select", "Select compatible local models", None))
        else:
            primary_evidence = verification_status(intent.local_primary_model)
            triage_evidence = verification_status(intent.local_triage_model)
            verified = all(
                evidence["status"] == "verified"
                for evidence in (primary_evidence, triage_evidence)
            )
            local_status = "verified" if verified else "installation_required"
            if not verified:
                actions.append(_action(
                    "models.install",
                    "Install and verify the selected local models",
                    (
                        "hatch models install "
                        f"--primary {intent.local_primary_model} "
                        f"--triage {intent.local_triage_model}"
                    ),
                    "models", "install", "--primary", intent.local_primary_model,
                    "--triage", intent.local_triage_model,
                ))
            routing = runtime.get("effective_routing") or {}
            active = (
                runtime.get("ai_mode") == "local"
                and routing.get("primary") == intent.local_primary_model
                and routing.get("triage") == intent.local_triage_model
            )
            if not active:
                actions.append(_action(
                    "ai.apply", "Apply local AI routing", "hatch apply-ai-config",
                    "apply-ai-config",
                ))
            ai_status = "ready" if verified and active else "pending_host_action"
    elif intent.ai_mode == "cloud":
        if not (
            intent.cloud_provider
            and intent.cloud_primary_model
            and intent.cloud_triage_model
        ):
            ai_status = "needs_user_input"
            cloud_status = "selection_required"
        else:
            validation = provider_validation_status(
                intent.cloud_provider,
                intent.cloud_primary_model,
                intent.cloud_triage_model,
            )
            cloud_status = validation["status"]
            if cloud_status == "missing_secret":
                actions.append(_action(
                    "provider.secret",
                    "Configure the provider secret on the host",
                    f"hatch secrets set {intent.cloud_provider}",
                    "secrets", "set", intent.cloud_provider,
                ))
            elif cloud_status != "ready":
                actions.append(_action(
                    "provider.test",
                    "Run the explicit provider connection test",
                    f"hatch provider test {intent.cloud_provider}",
                    "provider", "test", intent.cloud_provider,
                ))
            routing = runtime.get("effective_routing") or {}
            active = (
                runtime.get("ai_mode") == "cloud"
                and runtime.get("provider") == intent.cloud_provider
                and routing.get("primary") == intent.cloud_primary_model
                and routing.get("triage") == intent.cloud_triage_model
            )
            if cloud_status == "ready" and not active:
                actions.append(_action(
                    "ai.apply", "Apply cloud AI routing", "hatch apply-ai-config",
                    "apply-ai-config",
                ))
            ai_status = "ready" if cloud_status == "ready" and active else "pending_host_action"
    elif intent.ai_mode == "custom":
        ai_status = "ready" if runtime.get("ai_mode") == "custom" else "pending_host_action"
    else:
        ai_status = "needs_user_input"

    operation = _capability_operation(intent.backend_profile, backend["profile"])
    if operation:
        actions.append(operation)

    if ai_status == "needs_user_input":
        overall = "needs_user_input"
    elif ai_status != "ready" or operation:
        overall = "pending_host_action"
    else:
        overall = "ready"

    hardware = build_hardware_recommendation(probe, experience=intent.experience)
    intent_data = intent.model_dump(mode="json")
    onboarding_data = {
        "status": onboarding.status,
        "last_completed_step": onboarding.last_completed_step,
    }
    next_command = next(
        (action["command"] for action in actions if action.get("command")), None
    )
    return {
        "schema_version": 2,
        "overall_status": overall,
        "onboarding": onboarding_data,
        "onboarding_complete": onboarding.status == "complete",
        "experience": intent.experience,
        "ai": {
            "mode": intent.ai_mode,
            "configured": intent.ai_mode in {"none", "local", "cloud", "custom"},
            "healthy": ai_status == "ready",
            "status": ai_status,
            "provider": intent.cloud_provider,
            "model": intent.cloud_primary_model or intent.local_primary_model,
            "action_required": actions[0]["id"] if actions else None,
        },
        "local_ai": {
            "status": local_status,
            "primary_model": intent.local_primary_model,
            "triage_model": intent.local_triage_model,
        },
        "cloud_ai": {
            "status": cloud_status,
            "provider": intent.cloud_provider,
            "primary_model": intent.cloud_primary_model,
            "triage_model": intent.cloud_triage_model,
        },
        "capabilities": {
            "profile": backend["profile"],
            "selected_profile": intent.backend_profile,
            "enabled": backend["enabled"],
            "available_profiles": ["core", "browser", "local-embeddings", "full"],
            "operation": operation,
        },
        "hardware": hardware,
        "operation": operation,
        "intent": intent_data,
        "runtime": runtime,
        "restart_required": intent.restart_required,
        "next_actions": actions,
        "next_command": next_command,
        "errors": errors,
    }

