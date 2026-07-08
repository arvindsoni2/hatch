"""Backend capability profile status for read-only diagnostics."""
from __future__ import annotations

import importlib.util
import os
from typing import Any

from .ai_setup import load_runtime

BACKEND_PROFILES = {"core", "browser", "local-embeddings", "full"}


def _env_enabled(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _backend_profile() -> str:
    profile = os.getenv("HATCH_BACKEND_PROFILE", "core").strip().lower()
    return profile if profile in BACKEND_PROFILES else "core"


def _profile_configured(profile: str, capability: str) -> bool:
    if capability == "browser_automation":
        return profile in {"browser", "full"}
    if capability == "local_embeddings":
        return profile in {"local-embeddings", "full"}
    if capability == "perception_advanced_coach":
        return profile == "full"
    return False


def _configured(profile: str, capability: str, env_name: str) -> bool:
    explicit = _env_enabled(env_name)
    if explicit is not None:
        return explicit
    return _profile_configured(profile, capability)


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _optional_capability(
    *,
    configured: bool,
    installed: bool,
    not_configured_reason: str,
    not_installed_reason: str,
    enable_command: str,
) -> dict[str, Any]:
    available = configured and installed
    reason = None
    if not configured:
        reason = not_configured_reason
    elif not installed:
        reason = not_installed_reason
    return {
        "configured": configured,
        "installed": installed,
        "available": available,
        "reason": reason,
        "enable_command": None if available else enable_command,
    }


def build_backend_capability_status() -> dict[str, Any]:
    profile = _backend_profile()
    browser_configured = _configured(
        profile,
        "browser_automation",
        "HATCH_BROWSER_AUTOMATION_ENABLED",
    )
    local_embeddings_configured = _configured(
        profile,
        "local_embeddings",
        "HATCH_LOCAL_EMBEDDINGS_ENABLED",
    )
    perception_configured = (
        _configured(profile, "perception_advanced_coach", "HATCH_PERCEPTION_ENABLED")
        or _configured(profile, "perception_advanced_coach", "HATCH_ADVANCED_COACH_ENABLED")
    )

    capabilities = {
        "core_backend": {
            "configured": True,
            "installed": True,
            "available": True,
            "reason": None,
            "enable_command": None,
        },
        "browser_automation": _optional_capability(
            configured=browser_configured,
            installed=_module_available("playwright"),
            not_configured_reason="Browser automation profile is not enabled.",
            not_installed_reason="Browser automation dependencies are not installed in this backend image.",
            enable_command="hatch capabilities enable browser",
        ),
        "local_embeddings": _optional_capability(
            configured=local_embeddings_configured,
            installed=_module_available("sentence_transformers"),
            not_configured_reason="Local embeddings profile is not enabled.",
            not_installed_reason="Local embeddings dependencies are not installed in this backend image.",
            enable_command="hatch capabilities enable local-embeddings",
        ),
        "perception_advanced_coach": _optional_capability(
            configured=perception_configured,
            installed=_module_available("faster_whisper"),
            not_configured_reason="Full backend capability profile is not enabled.",
            not_installed_reason="Perception and advanced coach dependencies are not installed in this backend image.",
            enable_command="hatch capabilities enable full",
        ),
    }

    return {
        "backend_profile": profile,
        "ai_mode": load_runtime().get("ai_mode", "not_configured"),
        "capabilities": capabilities,
    }
