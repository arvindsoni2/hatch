"""Atomic, privacy-bounded artifact helpers for Coach benchmark runs."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, value: Any) -> None:
    """Replace a JSON target atomically without exposing a partial target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_sqlite_state(path: Path) -> str:
    """Hash SQLite main, WAL, and SHM presence and content deterministically."""
    digest = hashlib.sha256()
    for suffix in ("", "-wal", "-shm"):
        component = Path(f"{path}{suffix}")
        digest.update(suffix.encode())
        if component.is_file():
            digest.update(b"\0present\0")
            digest.update(component.read_bytes())
        else:
            digest.update(b"\0missing\0")
    return digest.hexdigest()


def git_state(cwd: Path) -> dict[str, str | bool]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"

    status = run("status", "--porcelain")
    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current") or "detached",
        "working_tree_clean": status == "" if status != "unknown" else "unknown",
    }


def stable_identity(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
