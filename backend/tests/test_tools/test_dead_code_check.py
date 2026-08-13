"""Contract tests for the repository import-graph dead-code gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "dead_code_check",
    ROOT / "scripts" / "dead_code_check.py",
)
assert SPEC and SPEC.loader
dead_code_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dead_code_check)


def test_database_setup_is_allowlisted_as_an_operational_entrypoint() -> None:
    """The startup and Makefile module is reachable without a Python import."""
    assert dead_code_check._is_allowlisted("database_setup")
