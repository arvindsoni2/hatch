"""Schema and Alembic contract tests for the durable runtime foundation."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.database import Base
import app.models  # noqa: F401 - register all ORM tables


BACKEND_DIR = Path(__file__).resolve().parents[2]
RUNTIME_TABLES = {
    "runtime_workflow_runs",
    "runtime_workflow_steps",
    "runtime_task_attempts",
    "runtime_execution_claims",
    "runtime_approvals",
    "runtime_events",
    "runtime_outbox",
    "runtime_outbox_attempts",
    "runtime_policy_decisions",
    "runtime_routing_decisions",
    "runtime_execution_records",
    "runtime_validation_results",
    "runtime_evaluation_runs",
    "runtime_evidence_observations",
    "runtime_model_evidence",
    "runtime_context_packages",
    "runtime_shadow_comparisons",
}


def _alembic_scripts() -> ScriptDirectory:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def _run_alembic(database: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
            "PROFILE_PATH": str(database.with_suffix(".profile.yaml")),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _run_setup(database: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.database_setup"],
        cwd=BACKEND_DIR,
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
            "PROFILE_PATH": str(database.with_suffix(".profile.yaml")),
        },
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


def test_runtime_migration_has_one_head() -> None:
    scripts = _alembic_scripts()
    assert scripts.get_heads() == ["s6t7u8v9w0x"]
    head = scripts.get_revision("s6t7u8v9w0x")
    assert head is not None
    assert head.down_revision == "r5s6t7u8v9w0"


def test_registered_metadata_contains_complete_runtime_schema() -> None:
    assert RUNTIME_TABLES <= set(Base.metadata.tables)
    attempts = Base.metadata.tables["runtime_task_attempts"]
    assert {
        "prior_attempt_id",
        "waiting_reason",
        "not_before",
        "retry_reason",
        "retry_policy_id",
        "retry_policy_version",
        "claim_fencing_token",
        "current_claim_id",
        "context_package_id",
    } <= set(attempts.columns.keys())
    runs = Base.metadata.tables["runtime_workflow_runs"]
    assert "max_attempts" in runs.columns
    executions = Base.metadata.tables["runtime_execution_records"]
    assert "parent_execution_id" in executions.columns
    shadow = Base.metadata.tables["runtime_shadow_comparisons"]
    assert {
        "domain_id_hash",
        "legacy_result_hash",
        "runtime_result_hash",
        "metrics_json",
        "expires_at",
    } <= set(shadow.columns.keys())


def test_runtime_migration_upgrades_and_downgrades_additively(tmp_path: Path) -> None:
    database = tmp_path / "runtime-schema.db"
    setup = _run_setup(database)
    assert setup.returncode == 0, setup.stderr
    prior = _run_alembic(database, "downgrade", "q4r5s6t7u8v9")
    assert prior.returncode == 0, prior.stderr
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO interview_sessions("
            "id, company_name, role_title, status, created_at) "
            "VALUES ('preserved-session', 'Example Ltd', 'Engineer', "
            "'active', CURRENT_TIMESTAMP)"
        )

    upgrade = _run_alembic(database, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    assert RUNTIME_TABLES <= _tables(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    downgrade = _run_alembic(database, "downgrade", "q4r5s6t7u8v9")
    assert downgrade.returncode == 0, downgrade.stderr
    assert not (RUNTIME_TABLES & _tables(database))
    assert "interview_sessions" in _tables(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT id FROM interview_sessions WHERE id = 'preserved-session'"
        ).fetchone() == ("preserved-session",)
