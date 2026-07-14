"""Easy-install AI setup state, catalogue validation, and recommendations."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CATALOG_PATH = Path(__file__).parents[1] / "config" / "model_catalog.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MODEL_ROLES = {"triage", "combined_capable_primary"}
AI_MODES = {"not_configured", "none", "cloud", "local", "custom"}
EXPERIENCES = {"essential", "full_ai", "custom"}
BACKEND_PROFILES = {"core", "browser", "local-embeddings", "full"}
PROVIDER_SECRET_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
PROVIDER_ALIASES = {
    "google": "google_genai",
    "google_gemini": "google_genai",
}
LOGGER = logging.getLogger(__name__)


class AISetupIntent(BaseModel):
    schema_version: int = 1
    ai_mode: str = "not_configured"
    experience: str = "essential"
    backend_profile: str = "core"
    selected_model_ids: list[str] = Field(default_factory=list)
    provider: str | None = None
    provider_metadata: dict[str, str] = Field(default_factory=dict)
    restart_required: bool = False
    hardware_probe_id: str | None = None


class ExperienceSetupIntent(BaseModel):
    schema_version: int = 1
    experience: str = "essential"
    ai_mode: str = "not_configured"
    backend_profile: str = "core"
    provider: str | None = None
    provider_metadata: dict[str, str] = Field(default_factory=dict)
    selected_model_ids: list[str] = Field(default_factory=list)
    acknowledgement: bool = False
    restart_required: bool = True


def canonical_provider(provider: str | None) -> str:
    value = (provider or "").strip().lower()
    return PROVIDER_ALIASES.get(value, value)


def provider_secret_env(provider: str | None) -> str | None:
    return PROVIDER_SECRET_ENV.get(canonical_provider(provider))


def config_dir() -> Path:
    return Path(os.getenv("HATCH_CONFIG_DIR", "/hatch-home/config"))


def probe_dir() -> Path:
    return Path(os.getenv("HATCH_PROBE_DIR", "/hatch-home/probe"))


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_catalog() -> list[dict[str, Any]]:
    catalog = _read_json(CATALOG_PATH, [])
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: Any) -> None:
    if not isinstance(catalog, list) or not catalog:
        raise ValueError("model catalogue must be a non-empty list")
    seen: set[str] = set()
    required = {
        "id", "display_name", "role", "format", "supported_os",
        "supported_arch", "repo_id", "filename", "download_url_template",
        "source_revision", "sha256", "download_size_gb", "disk_required_gb",
        "min_ram_gb", "recommended_ram_gb", "license", "source_trust",
    }
    for model in catalog:
        missing = required - set(model)
        if missing:
            raise ValueError(f"catalogue entry missing: {', '.join(sorted(missing))}")
        if model["id"] in seen:
            raise ValueError(f"duplicate model id: {model['id']}")
        seen.add(model["id"])
        if model["format"] != "gguf" or model["role"] not in MODEL_ROLES:
            raise ValueError(f"invalid format or role for {model['id']}")
        if not COMMIT_RE.fullmatch(model["source_revision"]):
            raise ValueError(f"invalid source revision for {model['id']}")
        if not re.fullmatch(r"[0-9a-f]{64}", model["sha256"]):
            raise ValueError(f"invalid sha256 for {model['id']}")
        if "{source_revision}" not in model["download_url_template"]:
            raise ValueError(f"download URL is not revision-pinned for {model['id']}")
        if model["min_ram_gb"] > model["recommended_ram_gb"]:
            raise ValueError(f"invalid RAM thresholds for {model['id']}")


def recommend_models(
    *,
    os_family: str,
    arch: str,
    total_ram_gb: float,
    free_disk_gb: float,
    models_dir: Path | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "recommended": [], "compatible": [], "not_recommended": [], "warnings": [],
    }
    aliases = {"aarch64": "arm64", "amd64": "x86_64"}
    normalized_arch = aliases.get(arch.lower(), arch.lower())
    for model in load_catalog():
        supported_arch = {aliases.get(value, value) for value in model["supported_arch"]}
        reasons: list[str] = []
        if os_family.lower() not in model["supported_os"]:
            reasons.append("Host operating system is unsupported.")
        if normalized_arch not in supported_arch:
            reasons.append("Host architecture is unsupported.")
        if total_ram_gb < model["min_ram_gb"]:
            reasons.append(f"Requires at least {model['min_ram_gb']} GB total RAM.")
        if free_disk_gb < model["disk_required_gb"]:
            reasons.append(f"Requires {model['disk_required_gb']} GB free model storage.")
        downloaded = bool(models_dir and (models_dir / model["filename"]).is_file())
        item = {"model_id": model["id"], "already_downloaded": downloaded}
        if reasons:
            result["not_recommended"].append({**item, "reasons": reasons})
        elif total_ram_gb >= model["recommended_ram_gb"]:
            result["recommended"].append(item)
        else:
            result["compatible"].append(item)
    return result


def load_intent() -> dict[str, Any]:
    from .setup_intent import load_setup_intent

    intent = load_setup_intent()
    data = intent.model_dump(mode="json")
    data.update({
        "provider": intent.cloud_provider,
        "provider_metadata": {
            "model": intent.cloud_primary_model,
            "primary_model": intent.cloud_primary_model,
            "triage_model": intent.cloud_triage_model,
        } if intent.cloud_provider else {},
        "selected_model_ids": [
            model_id
            for model_id in (intent.local_triage_model, intent.local_primary_model)
            if model_id
        ],
    })
    return data


def save_intent(payload: AISetupIntent) -> dict[str, Any]:
    if payload.ai_mode not in AI_MODES:
        raise ValueError("unsupported AI mode")
    if payload.experience not in EXPERIENCES:
        raise ValueError("unsupported experience")
    if payload.backend_profile not in BACKEND_PROFILES:
        raise ValueError("unsupported backend profile")
    catalog_ids = {entry["id"] for entry in load_catalog()}
    unknown = set(payload.selected_model_ids) - catalog_ids
    if unknown:
        raise ValueError(f"unknown model ids: {', '.join(sorted(unknown))}")
    from ..schemas.setup import IntentPatch
    from .setup_intent import patch_setup_intent

    primary = next((value for value in payload.selected_model_ids if "primary" in value), None)
    triage = next((value for value in payload.selected_model_ids if "triage" in value), None)
    metadata = payload.provider_metadata
    patch = IntentPatch(
        ai_mode=payload.ai_mode,
        experience=payload.experience,
        backend_profile=payload.backend_profile,
        local_primary_model=primary,
        local_triage_model=triage,
        cloud_provider=canonical_provider(payload.provider) or None,
        cloud_primary_model=metadata.get("primary_model") or metadata.get("model"),
        cloud_triage_model=metadata.get("triage_model") or metadata.get("model"),
        restart_required=payload.restart_required,
        hardware_probe_id=payload.hardware_probe_id,
    )
    patch_setup_intent(patch)
    return load_intent()


def load_backend_capabilities() -> dict[str, Any]:
    default = {
        "schema_version": 1,
        "profile": "core",
        "enabled": [],
        "updated_at": None,
        "updated_by": "default",
    }
    value = _read_json(config_dir() / "backend_capabilities.json", default)
    profile = str(value.get("profile") or "core")
    if profile not in BACKEND_PROFILES:
        return default
    enabled_by_profile = {
        "core": [],
        "browser": ["browser"],
        "local-embeddings": ["local-embeddings"],
        "full": ["browser", "local-embeddings", "perception", "advanced-coach"],
    }
    return {
        "schema_version": 1,
        "profile": profile,
        "enabled": enabled_by_profile[profile],
        "updated_at": value.get("updated_at"),
        "updated_by": value.get("updated_by", "unknown"),
    }


def save_experience_intent(payload: ExperienceSetupIntent) -> dict[str, Any]:
    if payload.experience not in EXPERIENCES:
        raise ValueError("unsupported experience")
    if payload.ai_mode not in {"not_configured", "cloud", "local", "custom", "ai-later"}:
        raise ValueError("unsupported AI mode")
    if payload.backend_profile not in BACKEND_PROFILES:
        raise ValueError("unsupported backend profile")
    ai_mode = "not_configured" if payload.ai_mode == "ai-later" else payload.ai_mode
    intent = AISetupIntent(
        ai_mode=ai_mode,
        experience=payload.experience,
        backend_profile=payload.backend_profile,
        provider=canonical_provider(payload.provider) if payload.provider else None,
        provider_metadata=payload.provider_metadata,
        selected_model_ids=payload.selected_model_ids,
        restart_required=payload.restart_required,
    )
    return save_intent(intent)


def build_hardware_recommendation(snapshot: dict[str, Any] | None, *, experience: str) -> dict[str, Any]:
    if snapshot is None:
        return {
            "status": "unknown",
            "last_checked_at": None,
            "recommendation": {
                "experience": experience,
                "readiness": "unknown",
                "reasons": [{
                    "id": "probe.missing",
                    "severity": "warning",
                    "message": "Run hatch probe to check this computer.",
                }],
                "recommended_ai_modes": ["cloud", "ai-later"],
                "local_ai_recommended": False,
            },
        }
    memory = snapshot.get("memory", {})
    storage = snapshot.get("storage", {})
    total_ram = float(memory.get("total_gb", 0) or 0)
    free_disk = float(storage.get("models_dir_free_gb", 0) or 0)
    reasons: list[dict[str, str]] = []
    local_ok = total_ram >= 24 and free_disk >= 20
    readiness = "recommended" if local_ok else "supported_with_limitations"
    if total_ram < 24:
        reasons.append({
            "id": "memory.below_recommended",
            "severity": "warning",
            "message": "Full AI can run, but local generation may be slow.",
        })
    if free_disk < 20:
        reasons.append({
            "id": "disk.below_recommended",
            "severity": "warning",
            "message": "Local models may need additional storage.",
        })
    if not reasons:
        reasons.append({
            "id": "hardware.ready",
            "severity": "info",
            "message": "This computer is suitable for the selected experience.",
        })
    return {
        "status": readiness,
        "last_checked_at": snapshot.get("captured_at") or snapshot.get("created_at"),
        "recommendation": {
            "experience": experience,
            "readiness": readiness,
            "reasons": reasons,
            "recommended_ai_modes": ["local", "cloud", "ai-later"] if local_ok else ["cloud", "ai-later"],
            "local_ai_recommended": local_ok,
        },
    }


def load_runtime() -> dict[str, Any]:
    default = {
        "schema_version": 1,
        "ai_mode": "not_configured",
        "quality_mode": "not_configured",
        "primary_model_id": None,
        "triage_model_id": None,
        "effective_routing": {"primary": None, "triage": None},
        "provider": None,
        "feature_gates": {
            "cv_tailoring": False,
            "cover_letter_generation": False,
            "coach_interview_prep": False,
        },
        "warnings": [],
    }
    path = config_dir() / "ai_runtime.json"
    if path.exists():
        return _read_json(path, default)
    # The existing developer stack does not set HATCH_CONFIG_DIR. Preserve its
    # profile.yaml-driven LLM behavior until easy-install runtime state exists.
    if "HATCH_CONFIG_DIR" not in os.environ:
        return {
            **default,
            "ai_mode": "custom",
            "quality_mode": "custom",
            "feature_gates": {
                "cv_tailoring": True,
                "cover_letter_generation": True,
                "coach_interview_prep": True,
            },
        }
    return default


def feature_enabled(name: str) -> bool:
    return bool(load_runtime().get("feature_gates", {}).get(name, False))


def load_probe_snapshot() -> dict[str, Any] | None:
    canonical = _read_json(probe_dir() / "hardware_probe_latest.json", None)
    if isinstance(canonical, dict) and canonical.get("sanitised") is True:
        return canonical
    legacy = _read_json(config_dir() / "hardware_probe_latest.json", None)
    if isinstance(legacy, dict) and legacy.get("sanitised") is True:
        LOGGER.warning("Using legacy hardware probe path; run hatch probe to migrate it.")
        return legacy
    return None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
