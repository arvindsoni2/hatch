"""Central store for the master CV — single source of truth for all tailoring services."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "./data/master_cv.json"
_cached_mtime: float | None = None
_cached_cv: dict[str, Any] | None = None


class MasterCVMissingError(Exception):
    """Raised when no confirmed master CV exists at the expected path."""


def resolve_master_cv_path() -> Path:
    """Return the absolute path to the master CV.

    Precedence: DATA_DIR env var > profile.master_cv_path > ./data/master_cv.json default.
    Relative paths are resolved relative to /app (Docker working dir).
    """
    from ..agents.tools.profile_loader import load_profile  # noqa: PLC0415

    try:
        profile = load_profile()
        raw_path = getattr(profile, "master_cv_path", None) or _DEFAULT_PATH
    except Exception:
        raw_path = _DEFAULT_PATH

    path = Path(raw_path)
    if not path.is_absolute():
        data_dir = os.environ.get("DATA_DIR")
        if data_dir:
            path = Path(data_dir) / path.name
        else:
            path = Path("/app") / path.relative_to(".")

    return path


def load_master_cv() -> dict[str, Any]:
    """Load the master CV, with mtime-based cache so re-uploads take effect immediately.

    Raises:
        MasterCVMissingError: when no CV has been uploaded yet.
    """
    global _cached_mtime, _cached_cv

    cv_path = resolve_master_cv_path()

    if not cv_path.exists():
        raise MasterCVMissingError(
            "No master CV found. Upload your CV in Settings → Resume before tailoring."
        )

    try:
        mtime = cv_path.stat().st_mtime
    except OSError:
        raise MasterCVMissingError(
            "No master CV found. Upload your CV in Settings → Resume before tailoring."
        )

    if _cached_cv is not None and _cached_mtime == mtime:
        return _cached_cv

    try:
        with cv_path.open() as fh:
            data = json.load(fh)
    except Exception as exc:
        raise MasterCVMissingError(
            f"Master CV could not be read ({exc}). Re-upload your CV in Settings → Resume."
        ) from exc

    _cached_mtime = mtime
    _cached_cv = data
    logger.debug("Master CV loaded from %s (mtime=%s)", cv_path, mtime)
    return data


def invalidate_cache() -> None:
    """Invalidate the in-process cache — call after /resume/confirm persists a new CV."""
    global _cached_mtime, _cached_cv
    _cached_mtime = None
    _cached_cv = None
