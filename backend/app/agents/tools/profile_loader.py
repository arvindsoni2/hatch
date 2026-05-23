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
from ...services.profile_service import load_profile as _load, get_profile_path

logger = logging.getLogger(__name__)

_cache: Profile | None = None
_cache_mtime: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0  # re-check mtime at most once per minute


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
        _cache = _apply_locale_defaults(raw)
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
