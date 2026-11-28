"""Settings router — API key management and environment configuration."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from ..agents.tools.profile_loader import invalidate_cache, load_profile
from ..services.profile_service import load_profile_raw, save_profile_raw

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/settings", tags=["settings"])

# Detect provider from env var name
_KEY_PROVIDER_MAP: dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic",
    "OPENAI_API_KEY": "openai",
    "GOOGLE_API_KEY": "google_genai",
    "AZURE_OPENAI_API_KEY": "azure_openai",
    "GOOGLE_GENAI_API_KEY": "google_genai",
    "OPENROUTER_API_KEY": "openrouter",
}

# Known free-tier models per provider
_PROVIDER_MODELS: dict[str, list[str]] = {
    "anthropic": ["claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-7"],
    "openai": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
    "google_genai": [
        "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro",
        "gemini-2.5-flash-lite",
    ],
    "azure_openai": ["gpt-4o-mini", "gpt-4o"],
    "openrouter": ["openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-3.5-sonnet"],
    "ollama": [],  # dynamically populated from /api/v2/settings/ollama-models
}

_FREE_TIER_PROVIDERS = {"google_genai", "ollama"}

_DIGEST_ENV_KEYS = (
    "DIGEST_TIMEZONE",
    "DIGEST_TIME",
    "DIGEST_FREQUENCY",
    "DIGEST_ENABLED",
)
_ALLOWED_ENV_KEYS = frozenset({*_KEY_PROVIDER_MAP, *_DIGEST_ENV_KEYS})


def _api_keys_file() -> Path:
    return Path(os.getenv("DATA_DIR", "./data")) / "api_keys.env"


def write_env_values(updates: dict[str, str]) -> None:
    """Atomically replace allow-listed keys in data/api_keys.env."""
    unknown = set(updates) - _ALLOWED_ENV_KEYS
    if unknown:
        raise ValueError(f"Unsupported env key: {sorted(unknown)[0]}")
    for value in updates.values():
        if not isinstance(value, str) or any(char in value for char in "\r\n\x00"):
            raise ValueError("Env values must be strings without CR, LF or NUL")

    path = _api_keys_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    written: set[str] = set()
    lines: list[str] = []
    for line in existing:
        key = line.partition("=")[0].strip()
        if key in updates:
            if key not in written:
                lines.append(f"{key}={updates[key]}")
                written.add(key)
        else:
            lines.append(line)
    for key, value in updates.items():
        if key not in written:
            lines.append(f"{key}={value}")
    payload = "\n".join(lines) + "\n" if lines else ""

    descriptor, temporary = tempfile.mkstemp(
        prefix=".api_keys.env.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_env_file() -> None:
    """Load only allow-listed keys from data/api_keys.env."""
    path = _api_keys_file()
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in _ALLOWED_ENV_KEYS:
            logger.warning("Ignoring unrecognized key in api_keys.env: %s", key)
            continue
        value = value.strip()
        if any(char in value for char in "\r\n\x00"):
            logger.warning("Ignoring invalid value for api_keys.env key: %s", key)
            continue
        os.environ[key] = value


# Load persisted keys at module import time
_load_env_file()


@router.put("/env")
async def save_api_key(data: dict[str, Any]) -> dict[str, Any]:
    """Reject browser/API secret writes; v1 secrets are host-CLI owned."""
    del data
    raise HTTPException(
        status_code=410,
        detail="API key writes moved to the host CLI. Run `hatch secrets set <provider>`.",
    )


@router.get("/env/status")
async def get_env_status() -> dict[str, Any]:
    """Return which providers have API keys configured and the current provider.

    Never returns key values — only presence and validity metadata.
    """
    # Load persisted keys first (in case process restarted)
    _load_env_file()

    configured: dict[str, dict] = {}
    for env_var, provider in _KEY_PROVIDER_MAP.items():
        value = os.environ.get(env_var, "")
        if value:
            configured[provider] = {
                "env_var": env_var,
                "configured": True,
            }

    # Add Ollama — no key needed
    configured["ollama"] = {"env_var": None, "configured": True}

    # Current provider from profile
    current_provider = "unknown"
    current_tier = "unknown"
    try:
        from ..services.profile_service import load_profile  # noqa: PLC0415
        profile = load_profile()
        current_provider = profile.llm.provider
        current_tier = "free" if current_provider in _FREE_TIER_PROVIDERS else "paid"
    except Exception:
        pass

    return {
        "configured_providers": configured,
        "current_provider": current_provider,
        "tier": current_tier,
    }


@router.get("/ollama-models")
async def list_ollama_models() -> dict[str, Any]:
    """Return models currently installed in Ollama by querying its /api/tags endpoint.

    Falls back gracefully if Ollama is unreachable (returns empty list + error).
    """
    base_url = "http://host.containers.internal:11434"
    try:
        profile = load_profile()
        base_url = profile.llm.base_url or base_url
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{base_url}/api/tags")
            r.raise_for_status()
            data = r.json()
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models, "base_url": base_url}
    except Exception as exc:
        logger.warning("Could not reach Ollama at %s: %s", base_url, exc)
        return {"models": [], "base_url": base_url, "error": str(exc)}


@router.put("/ollama-model")
async def set_ollama_model(data: dict[str, Any]) -> dict[str, Any]:
    """Persist primary_model (and optionally triage_model) for Ollama in profile.yaml."""
    primary = (data.get("primary_model") or "").strip()
    triage = (data.get("triage_model") or "").strip()
    if not primary:
        raise HTTPException(status_code=400, detail="primary_model is required")
    try:
        raw = load_profile_raw()
        if "llm" not in raw:
            raw["llm"] = {}
        raw["llm"]["primary_model"] = primary
        if triage:
            raw["llm"]["triage_model"] = triage
        save_profile_raw(raw)
        invalidate_cache()
        saved_triage = triage or raw["llm"].get("triage_model", "")
        return {"saved": True, "primary_model": primary, "triage_model": saved_triage}
    except Exception as exc:
        logger.error("Failed to save Ollama model: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
