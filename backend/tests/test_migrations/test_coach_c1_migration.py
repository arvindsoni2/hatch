"""Compatibility coverage for the additive Coach C1 migration."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PRIOR_REVISION = "o2p3q4r5s6t7"
COACH_C1_REVISION = "p3q4r5s6t7u8"


def _upgrade(tmp_path: Path) -> sqlite3.Connection:
    database = tmp_path / "coach-c1.db"
    connection = sqlite3.connect(database)
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
        INSERT INTO interview_sessions(id, status) VALUES
            ('active-session', 'active'),
            ('completed-session', 'completed');
        INSERT INTO session_recordings(id, session_id, transcript, evaluation_json) VALUES
            ('skipped', 'active-session', '[SKIPPED]', NULL),
            ('evaluated', 'active-session', 'answer', '{"scores":{"relevance":7},"overall":7}'),
            ('embedded-invalid', 'active-session', '', '{"evaluation_state":"invalid","scores":{},"overall":null}'),
            ('unknown', 'active-session', 'answer', 'not json');
        """
    )
    connection.commit()
    connection.close()

    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "stamp", PRIOR_REVISION],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", COACH_C1_REVISION],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return sqlite3.connect(database)


def test_migration_adds_locked_fields_and_backfills_recording_states(tmp_path: Path) -> None:
    connection = _upgrade(tmp_path)

    session_columns = {
        row[1]: row for row in connection.execute("PRAGMA table_info(interview_sessions)")
    }
    question_columns = {
        row[1]: row for row in connection.execute("PRAGMA table_info(session_questions)")
    }
    recording_columns = {
        row[1]: row for row in connection.execute("PRAGMA table_info(session_recordings)")
    }
    states = dict(
        connection.execute(
            "SELECT id, evaluation_state FROM session_recordings ORDER BY id"
        ).fetchall()
    )

    assert {
        "diagnostics",
        "report_json",
        "report_state",
        "report_job_id",
        "report_started_at",
        "activity_version",
    } <= set(session_columns)
    assert {"requirement_id", "model_answer_diagnostics"} <= set(question_columns)
    assert {"evaluation_state", "async_job_id"} <= set(recording_columns)
    assert states == {
        "embedded-invalid": "invalid",
        "evaluated": "completed",
        "skipped": "skipped",
        "unknown": None,
    }
    defaults = connection.execute(
        "SELECT report_state, activity_version FROM interview_sessions WHERE id='active-session'"
    ).fetchone()
    assert defaults == ("not_started", 0)


def test_migration_downgrades_and_reapplies(tmp_path: Path) -> None:
    connection = _upgrade(tmp_path)
    database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
    connection.close()
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}

    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", PRIOR_REVISION],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    downgraded = sqlite3.connect(database)
    columns = {row[1] for row in downgraded.execute("PRAGMA table_info(interview_sessions)")}
    downgraded.close()
    assert "report_state" not in columns

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", COACH_C1_REVISION],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
