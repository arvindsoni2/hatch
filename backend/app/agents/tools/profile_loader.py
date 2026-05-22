"""Runtime profile loader for agents.

Agents call load_profile() here — never import from profile_service directly.
This module owns the in-process cache so all agents share one loaded copy.
Cache is invalidated when profile.yaml mtime changes.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from ...schemas.profile import Profile
from ...services.profile_service import load_profile as _load, get_profile_path

_cache: Profile | None = None
_cache_mtime: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0  # re-check mtime at most once per minute


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
        _cache = _load()
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
