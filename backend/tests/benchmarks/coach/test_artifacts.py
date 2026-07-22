from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from benchmarks.coach.artifacts import atomic_write_json, hash_sqlite_state


def test_atomic_json_never_exposes_partial_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "progress.json"
    atomic_write_json(target, {"state": "old"})
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("stop")))
    with pytest.raises(OSError, match="stop"):
        atomic_write_json(target, {"state": "new"})
    assert json.loads(target.read_text()) == {"state": "old"}


def test_sqlite_hash_includes_wal_and_shm(tmp_path: Path) -> None:
    database = tmp_path / "app.db"
    database.write_bytes(b"db")
    first = hash_sqlite_state(database)
    Path(f"{database}-wal").write_bytes(b"wal")
    assert hash_sqlite_state(database) != first
    second = hash_sqlite_state(database)
    Path(f"{database}-shm").write_bytes(b"shm")
    assert hash_sqlite_state(database) != second

