"""Easy-install AI setup state, catalogue validation, and recommendations."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

CATALOG_PATH = Path(__file__).parents[1] / "config" / "model_catalog.json"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MODEL_ROLES = {"triage", "combined_capable_primary"}
AI_MODES = {"not_configured", "cloud", "local", "custom"}
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


class AISetupIntent(BaseModel):
    schema_version: int = 1
    ai_mode: str = "not_configured"
    selected_model_ids: list[str] = Field(default_factory=list)
    provider: str | None = None
    provider_metadata: dict[str, str] = Field(default_factory=dict)
    restart_required: bool = False
    hardware_probe_id: str | None = None


def canonical_provider(provider: str | None) -> str:
    value = (provider or "").strip().lower()
    return PROVIDER_ALIASES.get(value, value)


def provider_secret_env(provider: str | None) -> str | None:
    return PROVIDER_SECRET_ENV.get(canonical_provider(provider))


def config_dir() -> Path:
    return Path(os.getenv("HATCH_CONFIG_DIR", "/hatch-home/config"))


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
    return _read_json(config_dir() / "ai_setup_intent.json", AISetupIntent().model_dump())


def save_intent(payload: AISetupIntent) -> dict[str, Any]:
    if payload.ai_mode not in AI_MODES:
        raise ValueError("unsupported AI mode")
    catalog_ids = {entry["id"] for entry in load_catalog()}
    unknown = set(payload.selected_model_ids) - catalog_ids
    if unknown:
        raise ValueError(f"unknown model ids: {', '.join(sorted(unknown))}")
    data = payload.model_dump()
    atomic_write_json(config_dir() / "ai_setup_intent.json", data)
    return data


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
    value = _read_json(config_dir() / "hardware_probe_latest.json", None)
    return value if isinstance(value, dict) and value.get("sanitised") is True else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
