"""Runtime profile loader for agents.

Agents call load_profile() here — never import from profile_service directly.
This module owns the in-process cache so all agents share one loaded copy.
Cache is invalidated when profile.yaml mtime changes.

After loading, locale pack defaults are merged for any fields the user left
at their schema default values — this lets the locale pack act as a regional
baseline without overriding explicit user choices.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ...schemas.profile import Profile
from ...services.ai_setup import load_runtime
from ...services.profile_service import load_profile as _load, get_profile_path

logger = logging.getLogger(__name__)

_cache: Profile | None = None
_cache_mtime: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0  # re-check mtime at most once per minute

_CLOUD_SECRET_ENVS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _apply_runtime_routing(profile: Profile) -> Profile:
    """Overlay applied setup routing onto the persisted user profile."""
    runtime = load_runtime()
    mode = runtime.get("ai_mode")
    routing = runtime.get("effective_routing") or {}
    primary = routing.get("primary")
    triage = routing.get("triage")
    if not primary or not triage:
        return profile
    if mode == "local":
        llm = profile.llm.model_copy(update={
            "provider": "llamacpp",
            "primary_model": primary,
            "triage_model": triage,
            "api_key_env": "",
            "base_url": "http://llm-primary:8080/v1",
            "triage_base_url": "http://llm-triage:8081/v1",
            "track_costs": False,
        })
        return profile.model_copy(update={"llm": llm})
    if mode == "cloud":
        provider = str(runtime.get("provider") or "")
        secret_env = _CLOUD_SECRET_ENVS.get(provider)
        if not secret_env:
            logger.error("Ignoring unsupported applied cloud provider '%s'.", provider)
            return profile
        llm = profile.llm.model_copy(update={
            "provider": provider,
            "primary_model": primary,
            "triage_model": triage,
            "api_key_env": secret_env,
            "base_url": "https://openrouter.ai/api/v1" if provider == "openrouter" else None,
            "triage_base_url": "",
            "track_costs": True,
        })
        return profile.model_copy(update={"llm": llm})
    return profile


def _apply_locale_defaults(profile: Profile) -> Profile:
    """Merge locale pack onboarding_defaults into profile fields that are still at schema defaults.

    Only applies when a field equals the schema default — explicit user values are kept.
    """
    try:
        from ...services.locale_service import get_onboarding_defaults
        defaults = get_onboarding_defaults(profile.locale)
    except Exception:
        return profile  # locale pack missing or malformed — proceed without

    updates: dict[str, Any] = {}

    locale_contract = defaults.get("contract_type")
    if locale_contract and profile.search.contract_type == "any":
        updates["search"] = profile.search.model_copy(update={"contract_type": locale_contract})

    locale_interval = defaults.get("scrape_interval_hours")
    if locale_interval and profile.preferences.scrape_interval_hours == 4:
        updates["preferences"] = profile.preferences.model_copy(
            update={"scrape_interval_hours": locale_interval}
        )

    if updates:
        return profile.model_copy(update=updates)
    return profile


def load_profile() -> Profile:
    """Return the validated Profile, refreshing from disk if modified."""
    global _cache, _cache_mtime

    path = get_profile_path()
    now = time.monotonic()

    if _cache is not None and (now - _cache_mtime) < _CACHE_TTL_SECONDS:
        return _cache

    try:
        mtime = path.stat().st_mtime if path.exists() else 0.0
    except OSError:
        mtime = 0.0

    if _cache is None or mtime != _cache_mtime:
        raw = _load()
        _cache = _apply_runtime_routing(_apply_locale_defaults(raw))
        _cache_mtime = mtime

    return _cache


def invalidate_cache() -> None:
    """Force the next load_profile() call to re-read from disk."""
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = 0.0


def get_profile_dict() -> dict[str, Any]:
    """Return the profile as a plain dict (for prompt building)."""
    return load_profile().model_dump()
