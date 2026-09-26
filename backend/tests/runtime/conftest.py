"""Synthetic fixture loading for runtime characterization and workflow tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from workflow_test_support import workflow_runtime  # noqa: F401


_FIXTURE_ROOT = Path(__file__).parent / "fixtures"


@pytest.fixture
def runtime_fixture() -> Any:
    """Load a named synthetic JSON fixture from the runtime fixture directory."""

    def _load(name: str) -> Any:
        return json.loads((_FIXTURE_ROOT / name).read_text(encoding="utf-8"))

    return _load
