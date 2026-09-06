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


def _table_sql(database: Path, table: str) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
    assert row is not None
    return row[0]


def test_runtime_migration_has_one_head() -> None:
    scripts = _alembic_scripts()
    assert scripts.get_heads() == ["z3a4b5c6d7e8"]
    head = scripts.get_revision("z3a4b5c6d7e8")
    assert head is not None
    assert head.down_revision == "y2z3a4b5c6d7"


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
        "capability_id",
        "capability_version",
        "idempotency_class",
        "reconciliation_reference",
        "side_effect_class",
        "execution_intent_active",
    } <= set(attempts.columns.keys())
    runs = Base.metadata.tables["runtime_workflow_runs"]
    assert "max_attempts" in runs.columns
    claims = Base.metadata.tables["runtime_execution_claims"]
    assert {
        "purpose",
        "recovery_not_before",
        "recovery_failure_count",
        "last_recovery_error_code",
    } <= set(claims.columns.keys())
    executions = Base.metadata.tables["runtime_execution_records"]
    assert "parent_execution_id" in executions.columns
    assert {"model_id", "model_version", "provider", "strategy_stage"} <= set(
        executions.columns.keys()
    )
    routing = Base.metadata.tables["runtime_routing_decisions"]
    assert {
        "task_id",
        "task_version",
        "model_version",
        "candidate_snapshot_json",
        "routing_policy_version",
        "evidence_snapshot_id",
    } <= set(routing.columns.keys())
    shadow = Base.metadata.tables["runtime_shadow_comparisons"]
    assert {
        "domain_id_hash",
        "legacy_result_hash",
        "runtime_result_hash",
        "metrics_json",
        "expires_at",
    } <= set(shadow.columns.keys())
    evidence = Base.metadata.tables["runtime_model_evidence"]
    assert {
        "model_version",
        "qualification_id",
        "qualification_version",
        "observation_ids_json",
        "quality_score",
    } <= set(evidence.columns.keys())
    validations = Base.metadata.tables["runtime_validation_results"]
    assert "metrics_json" in validations.columns
    evaluations = Base.metadata.tables["runtime_evaluation_runs"]
    assert {
        "evaluator_type",
        "evaluation_spec_id",
        "evaluation_spec_version",
        "evaluator_model_id",
        "evaluator_model_version",
        "result",
        "scores_json",
        "reason_codes_json",
        "validation_metrics_json",
        "primary_execution_id",
        "repair_execution_id",
        "fallback_execution_id",
        "evaluation_execution_id",
    } <= set(evaluations.columns.keys())
    fk_targets = {
        constraint.name: next(iter(constraint.elements)).target_fullname
        for constraint in evaluations.foreign_key_constraints
        if constraint.name
    }
    assert {
        "fk_runtime_evaluation_runs_primary_execution_id",
        "fk_runtime_evaluation_runs_repair_execution_id",
        "fk_runtime_evaluation_runs_fallback_execution_id",
        "fk_runtime_evaluation_runs_evaluation_execution_id",
    } <= set(fk_targets)
    assert all(
        target == "runtime_execution_records.id" for target in fk_targets.values()
    )


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


def test_evaluation_lineage_migration_has_named_execution_foreign_keys(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evaluation-lineage.db"
    setup = _run_setup(database)
    assert setup.returncode == 0, setup.stderr
    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_evaluation_runs)")
        }
        assert {
            "evaluation_execution_id",
            "primary_execution_id",
            "repair_execution_id",
            "fallback_execution_id",
        } <= columns
        foreign_keys = {
            row[3]: row[2]
            for row in connection.execute(
                "PRAGMA foreign_key_list(runtime_evaluation_runs)"
            )
        }
        assert {
            "evaluation_execution_id",
            "primary_execution_id",
            "repair_execution_id",
            "fallback_execution_id",
        } <= set(foreign_keys)
        assert all(
            foreign_keys[column] == "runtime_execution_records"
            for column in {
                "evaluation_execution_id",
                "primary_execution_id",
                "repair_execution_id",
                "fallback_execution_id",
            }
        )
    downgrade = _run_alembic(database, "downgrade", "y2z3a4b5c6d7")
    assert downgrade.returncode == 0, downgrade.stderr
    reupgrade = _run_alembic(database, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stderr


def test_recovery_disposition_migration_downgrades_and_reupgrades(
    tmp_path: Path,
) -> None:
    database = tmp_path / "reconciliation-binding.db"
    setup = _run_setup(database)
    assert setup.returncode == 0, setup.stderr
    upgraded_columns = {
        "capability_id",
        "capability_version",
        "idempotency_class",
        "reconciliation_reference",
    }
    with sqlite3.connect(database) as connection:
        assert upgraded_columns <= {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_task_attempts)")
        }
        assert "purpose" in {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_execution_claims)")
        }
        assert {
            "recovery_not_before",
            "recovery_failure_count",
            "last_recovery_error_code",
        } <= {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_execution_claims)")
        }

    downgrade = _run_alembic(database, "downgrade", "t7u8v9w0x1y2")
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        assert upgraded_columns <= {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_task_attempts)")
        }
        assert "purpose" in {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_execution_claims)")
        }
        assert not (
            {
                "recovery_not_before",
                "recovery_failure_count",
                "last_recovery_error_code",
            }
            & {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(runtime_execution_claims)"
                )
            }
        )

    reupgrade = _run_alembic(database, "upgrade", "u8v9w0x1y2z3")
    assert reupgrade.returncode == 0, reupgrade.stderr


def test_execution_intent_migration_downgrades_and_reupgrades(tmp_path: Path) -> None:
    """Would fail if crash-safe intent fields were absent from durable schema."""
    database = tmp_path / "execution-intent.db"
    setup = _run_setup(database)
    assert setup.returncode == 0, setup.stderr
    intent_columns = {"side_effect_class", "execution_intent_active"}
    with sqlite3.connect(database) as connection:
        assert intent_columns <= {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_task_attempts)")
        }

    downgrade = _run_alembic(database, "downgrade", "u8v9w0x1y2z3")
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        assert not (
            intent_columns
            & {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(runtime_task_attempts)"
                )
            }
        )

    reupgrade = _run_alembic(database, "upgrade", "x1y2z3a4b5c6")
    assert reupgrade.returncode == 0, reupgrade.stderr


def test_routing_candidate_snapshot_migration_downgrades_and_reupgrades(
    tmp_path: Path,
) -> None:
    """Would fail if candidate snapshots were folded into unrelated reason codes."""
    database = tmp_path / "routing-snapshot.db"
    setup = _run_setup(database)
    assert setup.returncode == 0, setup.stderr
    snapshot_columns = {
        "task_id",
        "task_version",
        "model_version",
        "candidate_snapshot_json",
        "routing_policy_version",
        "evidence_snapshot_id",
    }
    with sqlite3.connect(database) as connection:
        assert snapshot_columns <= {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(runtime_routing_decisions)"
            )
        }

    downgrade = _run_alembic(database, "downgrade", "v9w0x1y2z3a4")
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        assert not (
            snapshot_columns
            & {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(runtime_routing_decisions)"
                )
            }
        )

    reupgrade = _run_alembic(database, "upgrade", "x1y2z3a4b5c6")
    assert reupgrade.returncode == 0, reupgrade.stderr


def test_evaluation_provenance_migration_downgrades_and_reupgrades(
    tmp_path: Path,
) -> None:
    database = tmp_path / "evaluation-provenance.db"
    setup = _run_setup(database)
    assert setup.returncode == 0, setup.stderr
    columns = {
        "evaluator_type",
        "evaluation_spec_id",
        "evaluation_spec_version",
        "evaluator_model_id",
        "evaluator_model_version",
        "result",
        "scores_json",
        "reason_codes_json",
        "validation_metrics_json",
        "primary_execution_id",
        "repair_execution_id",
        "fallback_execution_id",
    }
    with sqlite3.connect(database) as connection:
        assert columns <= {
            row[1]
            for row in connection.execute("PRAGMA table_info(runtime_evaluation_runs)")
        }
        assert "metrics_json" in {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(runtime_validation_results)"
            )
        }

    downgrade = _run_alembic(database, "downgrade", "y2z3a4b5c6d7")
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(database) as connection:
        assert not (
            columns
            & {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(runtime_evaluation_runs)"
                )
            }
        )

    reupgrade = _run_alembic(database, "upgrade", "z3a4b5c6d7e8")
    assert reupgrade.returncode == 0, reupgrade.stderr
    table_sql = _table_sql(database, "runtime_evaluation_runs")
    for name in (
        "fk_runtime_evaluation_runs_primary_execution_id",
        "fk_runtime_evaluation_runs_repair_execution_id",
        "fk_runtime_evaluation_runs_fallback_execution_id",
    ):
        assert name in table_sql
    foreign_keys = set()
    with sqlite3.connect(database) as connection:
        foreign_keys = {
            (row[2], row[3], row[4])
            for row in connection.execute(
                "PRAGMA foreign_key_list(runtime_evaluation_runs)"
            )
        }
    assert {
        ("runtime_execution_records", "primary_execution_id", "id"),
        ("runtime_execution_records", "repair_execution_id", "id"),
        ("runtime_execution_records", "fallback_execution_id", "id"),
    } <= foreign_keys
