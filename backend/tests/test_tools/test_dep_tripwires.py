"""Tripwire tests: verify removed dependencies leave no import traces."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.parent.parent / "app"


def test_no_chromadb_import() -> None:
    """chromadb was removed in DW-1; no app module may import it."""
    result = subprocess.run(
        ["grep", "-r", "--include=*.py", "import chromadb", str(APP_DIR)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        f"chromadb import found after DW-1 removal:\n{result.stdout}"
    )
