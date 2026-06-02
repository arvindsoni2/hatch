"""Profile service — read, write, and validate profile.yaml.

The profile lives at data/profile.yaml (relative to the project root).
Agents must never call this directly; they use profile_loader.py instead
so caching is centralised.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..schemas.profile import Profile

def _find_default_profile_path() -> Path:
    """Resolve the default profile path without depending on CWD.

    Walks up from this module file looking for the first ``data/profile.yaml``
    that exists, checking up to 5 levels.  This works for both:

    * Docker (WORKDIR=/app, module at /app/app/services/…, data at /app/data/)
    * Local dev (module at backend/app/services/…, data at project-root/data/)

    The ``PROFILE_PATH`` env var always wins when set.
    """
    if env_path := os.getenv("PROFILE_PATH"):
        return Path(env_path)

    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "data" / "profile.yaml"
        if candidate.exists():
            return candidate

    # Fallback: sibling data/ of the package root (3 levels up from this file)
    return here.parent.parent.parent / "data" / "profile.yaml"


_DEFAULT_PROFILE_PATH = _find_default_profile_path()


def get_profile_path() -> Path:
    return _DEFAULT_PROFILE_PATH


def profile_exists() -> bool:
    return get_profile_path().exists()


def load_profile_raw() -> dict[str, Any]:
    """Load profile.yaml as a raw dict without Pydantic validation."""
    path = get_profile_path()
    if not path.exists():
        return {}
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def load_profile() -> Profile:
    """Load and validate profile.yaml. Raises ValidationError on schema mismatch."""
    raw = load_profile_raw()
    return Profile.model_validate(raw)


def save_profile(profile: Profile) -> None:
    """Serialise and write profile to disk. Creates data/ dir if needed."""
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        yaml.safe_dump(profile.model_dump(exclude_none=True), fh, sort_keys=False, allow_unicode=True)


def save_profile_raw(data: dict[str, Any]) -> Profile:
    """Validate raw dict, write to disk, return validated Profile."""
    profile = Profile.model_validate(data)
    save_profile(profile)
    return profile


def validate_profile_data(data: dict[str, Any]) -> list[str]:
    """Return a list of validation error messages (empty = valid)."""
    try:
        Profile.model_validate(data)
        return []
    except ValidationError as exc:
        return [f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()]
