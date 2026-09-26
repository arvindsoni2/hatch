"""Config package — master profile loader + settings re-export.

Python resolves `app.config` to this package (takes precedence over config.py).
We load settings from the sibling config.py using importlib so all existing
`from app.config import settings` imports continue to work.
"""
from __future__ import annotations

import functools
import importlib.util
import os
from pathlib import Path
from typing import Any

import yaml

# ──────────────────────── Settings re-export ────────────────────────

_config_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.py")
_spec = importlib.util.spec_from_file_location("app._config_module", _config_py)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
Settings = _mod.Settings
settings = _mod.settings

# ──────────────────────── Master profile ────────────────────────

_PROFILE_DIR = Path(__file__).parent
_PROFILE_PATH = _PROFILE_DIR / "master_profile.yaml"
_PROFILE_EXAMPLE_PATH = _PROFILE_DIR / "master_profile.example.yaml"


@functools.lru_cache(maxsize=1)
def load_master_profile() -> dict[str, Any]:
    """Load and cache the master profile YAML, falling back to the example."""
    path = _PROFILE_PATH if _PROFILE_PATH.exists() else _PROFILE_EXAMPLE_PATH
    with path.open() as fh:
        return yaml.safe_load(fh)
