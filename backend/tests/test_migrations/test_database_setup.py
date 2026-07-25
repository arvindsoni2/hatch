"""Fail-closed coverage for the canonical database setup command."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.database import Base
import app.models  # noqa: F401 - register every ORM table in Base.metadata
from app import database_setup


BACKEND_DIR = Path(__file__).resolve().parents[2]
HEAD_REVISION = "p3q4r5s6t7u8"
PRIOR_HEAD_REVISION = "o2p3q4r5s6t7"


def _environment(database: Path, **overrides: str) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
        "PROFILE_PATH": str(database.with_suffix(".profile.yaml")),
        "UV_CACHE_DIR": "/tmp/uv-cache",
        **overrides,
    }


def _run_setup(database: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.database_setup"],
        cwd=BACKEND_DIR,
        env=_environment(database, **env),
        capture_output=True,
        text=True,
        check=False,
    )


def _run_alembic(database: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=_environment(database),
        capture_output=True,
        text=True,
        check=False,
    )


def _tables(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def _current_revisions(database: Path) -> list[str]:
    with sqlite3.connect(database) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            )
        ]


def _create_version_state(database: Path, *revisions: str) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.executemany(
            "INSERT INTO alembic_version(version_num) VALUES (?)",
            [(revision,) for revision in revisions],
        )


def _create_prior_head_database(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE interview_sessions (
                id VARCHAR(36) PRIMARY KEY,
                status VARCHAR(32),
                completed_at DATETIME
            );
            CREATE TABLE session_questions (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36),
                text TEXT
            );
            CREATE TABLE session_recordings (
                id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36),
                transcript TEXT,
                evaluation_json TEXT,
                created_at DATETIME
            );
            CREATE TABLE alembic_version (
                version_num VARCHAR(32) NOT NULL PRIMARY KEY
            );
            INSERT INTO alembic_version(version_num)
            VALUES ('o2p3q4r5s6t7');
            INSERT INTO interview_sessions(id, status)
            VALUES ('preserved-session', 'active');
            """
        )


def test_truly_empty_database_bootstraps_to_the_sole_head(tmp_path: Path) -> None:
    database = tmp_path / "fresh.db"

    result = _run_setup(database)

    assert result.returncode == 0, result.stderr
    assert _current_revisions(database) == [HEAD_REVISION]
    heads = _run_alembic(database, "heads")
    assert heads.returncode == 0, heads.stderr
    assert heads.stdout.split() == [HEAD_REVISION, "(head)"]


def test_fresh_bootstrap_creates_every_registered_metadata_table(
    tmp_path: Path,
) -> None:
    database = tmp_path / "metadata.db"

    result = _run_setup(database)

    assert result.returncode == 0, result.stderr
    assert _tables(database) == set(Base.metadata.tables) | {"alembic_version"}


def test_fresh_bootstrap_passes_schema_and_sqlite_checks(tmp_path: Path) -> None:
    database = tmp_path / "checked.db"
    result = _run_setup(database)
    assert result.returncode == 0, result.stderr

    check = _run_alembic(database, "check")
    assert check.returncode == 0, check.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_empty_alembic_version_table_is_still_a_fresh_bootstrap(tmp_path: Path) -> None:
    database = tmp_path / "empty-version.db"
    _create_version_state(database)

    result = _run_setup(database)

    assert result.returncode == 0, result.stderr
    assert _current_revisions(database) == [HEAD_REVISION]
    assert _tables(database) == set(Base.metadata.tables) | {"alembic_version"}


def test_current_database_is_a_no_op(tmp_path: Path) -> None:
    database = tmp_path / "current.db"
    first = _run_setup(database)
    assert first.returncode == 0, first.stderr
    before = database.read_bytes()

    second = _run_setup(database)

    assert second.returncode == 0, second.stderr
    assert database.read_bytes() == before


def test_known_prior_head_is_upgraded_and_preserves_data(tmp_path: Path) -> None:
    database = tmp_path / "prior-head.db"
    _create_prior_head_database(database)

    result = _run_setup(database)

    assert result.returncode == 0, result.stderr
    assert _current_revisions(database) == [HEAD_REVISION]
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT id, status FROM interview_sessions"
        ).fetchall() == [("preserved-session", "active")]
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(interview_sessions)")
        }
    assert "report_state" in columns


def test_non_empty_unversioned_database_fails_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "unversioned.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('keep me')")
    before = database.read_bytes()

    result = _run_setup(database)

    assert result.returncode != 0
    assert "non-empty unversioned" in result.stderr.lower()
    assert database.read_bytes() == before


def test_unversioned_view_fails_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "unversioned-view.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE VIEW sentinel AS SELECT 'keep me' AS value")
    before = database.read_bytes()

    result = _run_setup(database)

    assert result.returncode != 0
    assert "non-empty unversioned" in result.stderr.lower()
    assert database.read_bytes() == before


def test_reserved_version_view_fails_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "reserved-version-view.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE VIEW alembic_version AS "
            "SELECT CAST(NULL AS TEXT) AS version_num WHERE 0"
        )
    before = database.read_bytes()

    result = _run_setup(database)

    assert result.returncode != 0
    assert "non-empty unversioned" in result.stderr.lower()
    assert database.read_bytes() == before


def test_partial_a70_database_fails_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "partial-a70.db"
    _create_version_state(database, "a70e739c5a23")
    with sqlite3.connect(database) as connection:
        # c30577e861e2 creates these two tables before its first missing-table
        # failure, while Alembic leaves the version at a70e739c5a23.
        connection.execute(
            "CREATE TABLE application_attempts (id VARCHAR(36) PRIMARY KEY)"
        )
        connection.execute(
            "CREATE TABLE recruiter_contacts (id VARCHAR(36) PRIMARY KEY)"
        )
    before = database.read_bytes()

    result = _run_setup(database)

    assert result.returncode != 0
    assert "migration preflight failed" in result.stderr.lower()
    assert database.read_bytes() == before


def test_unknown_revision_fails_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "unknown.db"
    _create_version_state(database, "not-a-revision")
    before = database.read_bytes()

    result = _run_setup(database)

    assert result.returncode != 0
    assert "unknown revision" in result.stderr.lower()
    assert database.read_bytes() == before


def test_known_non_ancestor_revision_fails_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "non-ancestor.db"
    _create_version_state(database, "detached-revision")
    before = database.read_bytes()
    scripts = SimpleNamespace(
        get_heads=lambda: (HEAD_REVISION,),
        get_revision=lambda _revision: SimpleNamespace(revision="detached-revision"),
        walk_revisions=lambda **_bounds: (
            SimpleNamespace(revision=HEAD_REVISION),
            SimpleNamespace(revision=PRIOR_HEAD_REVISION),
        ),
    )
    monkeypatch.setattr(
        database_setup.ScriptDirectory,
        "from_config",
        staticmethod(lambda _config: scripts),
    )

    with pytest.raises(database_setup.DatabaseSetupError, match="not an ancestor"):
        database_setup.setup_database(f"sqlite+aiosqlite:///{database}")

    assert database.read_bytes() == before


def test_multiple_database_heads_fail_without_mutation(tmp_path: Path) -> None:
    database = tmp_path / "multiple-heads.db"
    _create_version_state(database, PRIOR_HEAD_REVISION, HEAD_REVISION)
    before = database.read_bytes()

    result = _run_setup(database)

    assert result.returncode != 0
    assert "multiple database heads" in result.stderr.lower()
    assert database.read_bytes() == before


def test_schema_creation_failure_never_stamps(tmp_path: Path) -> None:
    database = tmp_path / "create-failure.db"
    injection_dir = tmp_path / "injection"
    injection_dir.mkdir()
    (injection_dir / "sitecustomize.py").write_text(
        """
from sqlalchemy.sql.schema import MetaData

def fail_create_all(self, *args, **kwargs):
    raise RuntimeError("deliberate-create-all-failure")

MetaData.create_all = fail_create_all
""",
        encoding="utf-8",
    )
    python_path = os.pathsep.join(
        [str(injection_dir), os.environ.get("PYTHONPATH", "")]
    )

    result = _run_setup(database, PYTHONPATH=python_path)

    assert result.returncode != 0
    assert "deliberate-create-all-failure" in result.stderr
    assert "alembic_version" not in _tables(database)
