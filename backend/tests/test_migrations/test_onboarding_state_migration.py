"""Onboarding state migration compatibility tests."""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import yaml
from sqlalchemy import create_engine

from app.database import Base
import app.models  # noqa: F401 - register the current pre-onboarding schema


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _upgrade(tmp_path: Path, profile: dict | None) -> sqlite3.Connection:
    database = tmp_path / "migration.db"
    profile_path = tmp_path / "profile.yaml"
    if profile is not None:
        profile_path.write_text(yaml.safe_dump(profile), encoding="utf-8")
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
        "PROFILE_PATH": str(profile_path),
        "UV_CACHE_DIR": "/tmp/uv-cache",
    }
    # The historical chain predates a reliable fresh-database baseline. Model
    # an existing installation at the prior head, which is the compatibility
    # boundary this migration owns.
    sync_engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(
        sync_engine,
        tables=[table for table in Base.metadata.sorted_tables if table.name != "onboarding_state"],
    )
    sync_engine.dispose()
    subprocess.run(
        ["uv", "run", "alembic", "stamp", "n1o2p3q4r5s6"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return sqlite3.connect(database)


def test_existing_complete_profile_backfills_complete(tmp_path):
    connection = _upgrade(
        tmp_path,
        {
            "candidate": {"name": "Ada Lovelace"},
            "search": {
                "target_roles": ["Platform Engineer"],
                "locations": [{"city": "London", "country": "GB"}],
            },
        },
    )

    row = connection.execute(
        "SELECT id, status, last_completed_step FROM onboarding_state"
    ).fetchone()

    assert row == (1, "complete", "protect-workspace")


def test_missing_profile_backfills_not_started(tmp_path):
    connection = _upgrade(tmp_path, None)

    row = connection.execute("SELECT id, status FROM onboarding_state").fetchone()

    assert row == (1, "not_started")
