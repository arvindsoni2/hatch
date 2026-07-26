"""Contract tests for the conversational Coach persistence migration."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
SCHEMA_FIXTURE = BACKEND_DIR / "tests/fixtures/coach/p3q4r5s6t7u8_schema.sql"
SOURCE_INTEGRATION_SHA = "52ded582babf684e90325f000233e811914f7710"
SOURCE_REVISION = "p3q4r5s6t7u8"
COACH_REVISION = "q4r5s6t7u8v9"
SCHEMA_FIXTURE_SHA256 = (
    "58a69e0217a71705d06e45588ec254a3f9dd7f8df4eeb4811f76b84d259de2a6"
)

SESSION_COLUMNS = {
    "experience_version",
    "conversation_state",
    "state_version",
    "resume_state",
    "active_question_id",
    "active_recording_id",
    "active_root_question_id",
    "last_activity_at",
    "paused_at",
    "recoverable_error_code",
    "recoverable_error_scope",
    "recoverable_error_context_json",
    "setup_generation",
    "setup_job_id",
    "setup_claim_token",
    "setup_claimed_at",
    "setup_claim_expires_at",
    "setup_started_at",
    "setup_completed_at",
    "setup_attempt_count",
    "setup_max_attempts",
    "retention_version",
    "deletion_state",
    "deletion_generation",
    "deletion_job_id",
    "deletion_command_id",
    "deletion_claim_token",
    "deletion_claim_expires_at",
    "deletion_started_at",
    "deletion_failed_at",
    "deletion_error_code",
    "event_version",
    "planning_request_json",
    "session_plan_json",
    "session_plan_contract_version",
    "evaluation_contract_version",
    "report_contract_version",
    "compatibility_key",
    "retention_policy_json",
    "session_plan_amendment_version",
    "report_build_reason",
}

QUESTION_COLUMNS = {
    "question_kind",
    "root_question_id",
    "parent_question_id",
    "follow_up_depth",
    "follow_up_reason",
    "follow_up_target_dimension",
    "follow_up_aggregation_role",
    "follow_up_source_recording_id",
    "follow_up_source_transcript_version_id",
    "follow_up_context_json",
    "follow_up_generation_json",
    "source_deleted",
    "question_state",
    "accepted_recording_id",
    "attempts_created_count",
    "acceptance_generation",
    "last_accepted_generation",
    "question_category_contract_version",
    "pending_hint_count",
    "pending_hint_types_json",
    "question_contract_version",
    "asked_sequence",
}

RECORDING_COLUMNS = {
    "attempt_number",
    "attempt_kind",
    "retry_of_recording_id",
    "attempt_state",
    "attempt_version",
    "processing_generation",
    "processing_retry_count",
    "processing_retry_limit",
    "current_transcript_version_id",
    "current_evaluation_version_id",
    "accepted_at",
    "submitted_at",
    "processing_started_at",
    "processing_completed_at",
    "audio_retention_policy",
    "audio_retention_state",
    "audio_deleted_at",
    "audio_content_hash",
    "client_attempt_id",
    "hint_count",
    "self_assessment_json",
    "self_assessment_updated_at",
}

NEW_TABLES = {
    "coach_conversation_command_results",
    "interview_session_events",
    "coach_session_evidence_records",
    "interview_transcript_versions",
    "interview_attempt_evaluations",
    "interview_attempt_stages",
    "interview_attempt_uploads",
    "coach_session_deletion_results",
}

REQUIRED_INDEXES = {
    "idx_interview_sessions_experience_state",
    "idx_interview_sessions_conversation_state",
    "idx_session_questions_session_asked_sequence",
    "idx_session_questions_root_question",
    "idx_session_recordings_question_attempt",
    "idx_session_recordings_async_job_state",
    "idx_transcript_versions_recording_version",
    "idx_attempt_evaluations_recording_version",
    "idx_attempt_stages_job_state",
    "idx_attempt_uploads_attempt_upload",
    "idx_session_evidence_records_session_evidence",
    "idx_session_events_session_sequence",
    "idx_command_results_session_command",
}


def _run_alembic(database: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _schema_blocks(sql: str) -> list[tuple[str, str, str]]:
    matches = list(re.finditer(r"(?m)^-- (index|table|trigger|view): ([^\n]+)\n", sql))
    blocks: list[tuple[str, str, str]] = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(sql)
        statement = sql[match.end() : end].strip()
        blocks.append((match.group(1), match.group(2), statement))
    return blocks


def _create_template(path: Path) -> None:
    fixture_bytes = SCHEMA_FIXTURE.read_bytes()
    assert hashlib.sha256(fixture_bytes).hexdigest() == SCHEMA_FIXTURE_SHA256
    sql = fixture_bytes.decode("utf-8")
    assert "\r" not in sql
    assert f"-- Source integration SHA: {SOURCE_INTEGRATION_SHA}" in sql
    assert f"-- Alembic revision: {SOURCE_REVISION}" in sql

    blocks = _schema_blocks(sql)
    assert [(kind, name) for kind, name, _ in blocks] == sorted(
        (kind, name) for kind, name, _ in blocks
    )
    assert all(statement.endswith(";") for _, _, statement in blocks)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for kind in ("table", "index", "trigger", "view"):
            for object_kind, _, statement in blocks:
                if object_kind == kind:
                    connection.executescript(statement)
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES (?)", (SOURCE_REVISION,)
        )
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        assert revision == (SOURCE_REVISION,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


@pytest.fixture(scope="session")
def prior_head_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("coach-p3-template") / "p3.sqlite"
    _create_template(path)
    return path


@pytest.fixture
def prior_head_db(prior_head_template: Path, tmp_path: Path) -> Iterator[Path]:
    database = tmp_path / "coach-p3-copy.sqlite"
    shutil.copy2(prior_head_template, database)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (SOURCE_REVISION,)
    yield database


def _insert_session(connection: sqlite3.Connection, session_id: str) -> None:
    connection.execute(
        """
        INSERT INTO interview_sessions(
            id, company_name, role_title, status, overall_score, created_at,
            report_json, report_state, activity_version
        ) VALUES (?, 'Hatch', 'Engineer', 'completed', 8.25,
                  '2026-07-01 10:00:00', ?, 'completed', 7)
        """,
        (session_id, '{"summary":"legacy byte contract","scores":[8,7]}'),
    )


def _insert_question(
    connection: sqlite3.Connection,
    session_id: str,
    question_id: str,
    category: str = "Technical",
) -> None:
    connection.execute(
        """
        INSERT INTO session_questions(
            id, session_id, question_num, text, category, difficulty, order_in_session
        ) VALUES (?, ?, 1, 'Legacy question?', ?, 'medium', 1)
        """,
        (question_id, session_id, category),
    )


def _insert_recording(
    connection: sqlite3.Connection,
    *,
    recording_id: str,
    session_id: str,
    question_id: str,
    created_at: str,
    evaluation_state: str | None,
    transcript: str = "legacy answer",
) -> None:
    connection.execute(
        """
        INSERT INTO session_recordings(
            id, session_id, question_id, recording_type, transcript,
            speech_metrics, evaluation_json, evaluation_state, created_at
        ) VALUES (?, ?, ?, 'text', ?, ?, ?, ?, ?)
        """,
        (
            recording_id,
            session_id,
            question_id,
            transcript,
            '{"wpm":123,"filler_count":2}',
            '{"scores":{"relevance":7.5},"overall":7.5}',
            evaluation_state,
            created_at,
        ),
    )


def _upgrade(database: Path) -> None:
    _run_alembic(database, "upgrade", "head")
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (COACH_REVISION,)


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _unique_column_sets(
    connection: sqlite3.Connection, table: str
) -> set[tuple[str, ...]]:
    result: set[tuple[str, ...]] = set()
    for row in connection.execute(f"PRAGMA index_list({table})"):
        if row[2]:
            result.add(
                tuple(
                    item[2]
                    for item in connection.execute(f"PRAGMA index_info({row[1]})")
                )
            )
    return result


def test_fixture_is_hash_locked_complete_prior_head(prior_head_template: Path) -> None:
    with sqlite3.connect(prior_head_template) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert {
            "alembic_version",
            "interview_sessions",
            "session_questions",
            "session_recordings",
        } <= names
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (SOURCE_REVISION,)


def test_revision_is_the_only_alembic_head() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    head_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert head_lines == [f"{COACH_REVISION} (head)"]


@pytest.mark.parametrize(
    ("recordings", "expected_state", "expected_numbers", "expected_kinds"),
    [
        ([], "pending", [], []),
        (
            [("r1", "2026-07-01 10:01:00", "completed", "answer")],
            "answered",
            [1],
            ["primary"],
        ),
        (
            [("r1", "2026-07-01 10:01:00", "failed", "answer")],
            "pending",
            [1],
            ["primary"],
        ),
        (
            [
                ("r1", "2026-07-01 10:01:00", "completed", "answer"),
                ("r2", "2026-07-01 10:02:00", "failed", "answer"),
                ("r3", "2026-07-01 10:03:00", "completed", "answer"),
            ],
            "answered",
            [1, 2, 3],
            ["primary", "retry", "retry"],
        ),
        (
            [
                ("a-recording", "2026-07-01 10:01:00", "completed", "answer"),
                ("z-recording", "2026-07-01 10:01:00", "skipped", "[SKIPPED]"),
            ],
            "skipped",
            [1, 2],
            ["primary", "retry"],
        ),
    ],
)
def test_upgrade_backfills_legacy_vectors_without_mutating_content(
    prior_head_db: Path,
    recordings: list[tuple[str, str, str, str]],
    expected_state: str,
    expected_numbers: list[int],
    expected_kinds: list[str],
) -> None:
    with sqlite3.connect(prior_head_db) as connection:
        _insert_session(connection, "legacy-session")
        _insert_question(
            connection, "legacy-session", "legacy-question", "Unmapped Legacy"
        )
        for recording_id, created_at, state, transcript in recordings:
            _insert_recording(
                connection,
                recording_id=recording_id,
                session_id="legacy-session",
                question_id="legacy-question",
                created_at=created_at,
                evaluation_state=state,
                transcript=transcript,
            )
        before = connection.execute(
            """
            SELECT report_json, overall_score, activity_version
            FROM interview_sessions WHERE id='legacy-session'
            """
        ).fetchone()
        recording_content = connection.execute(
            """
            SELECT id, transcript, speech_metrics, evaluation_json
            FROM session_recordings ORDER BY id
            """
        ).fetchall()

    _upgrade(prior_head_db)

    with sqlite3.connect(prior_head_db) as connection:
        session = connection.execute(
            """
            SELECT experience_version, conversation_state, state_version, event_version,
                   report_json, overall_score, activity_version
            FROM interview_sessions WHERE id='legacy-session'
            """
        ).fetchone()
        assert session[:4] == ("legacy_v1", None, 0, 0)
        assert session[4:] == before
        question = connection.execute(
            """
            SELECT category, question_kind, follow_up_depth, question_state,
                   accepted_recording_id
            FROM session_questions WHERE id='legacy-question'
            """
        ).fetchone()
        assert question == ("Unmapped Legacy", "planned", 0, expected_state, None)
        attempts = connection.execute(
            """
            SELECT attempt_number, attempt_kind
            FROM session_recordings ORDER BY created_at, id
            """
        ).fetchall()
        assert [row[0] for row in attempts] == expected_numbers
        assert [row[1] for row in attempts] == expected_kinds
        assert (
            connection.execute(
                """
            SELECT id, transcript, speech_metrics, evaluation_json
            FROM session_recordings ORDER BY id
            """
            ).fetchall()
            == recording_content
        )
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        for table in (
            "interview_transcript_versions",
            "interview_attempt_evaluations",
            "interview_session_events",
            "coach_session_evidence_records",
        ):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone() == (
                0,
            )


def test_upgrade_adds_exact_foundation_schema_constraints_and_indexes(
    prior_head_db: Path,
) -> None:
    _upgrade(prior_head_db)
    with sqlite3.connect(prior_head_db) as connection:
        assert SESSION_COLUMNS <= _column_names(connection, "interview_sessions")
        assert QUESTION_COLUMNS <= _column_names(connection, "session_questions")
        assert RECORDING_COLUMNS <= _column_names(connection, "session_recordings")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert NEW_TABLES <= tables
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='index' AND name IS NOT NULL"
            )
        }
        assert REQUIRED_INDEXES <= indexes
        assert ("question_id", "attempt_number") in _unique_column_sets(
            connection, "session_recordings"
        )
        assert ("session_id", "client_attempt_id") in _unique_column_sets(
            connection, "session_recordings"
        )
        assert ("session_id", "asked_sequence") in _unique_column_sets(
            connection, "session_questions"
        )
        expected_uniques = {
            "coach_conversation_command_results": ("session_id", "command_id"),
            "interview_session_events": ("session_id", "sequence_number"),
            "coach_session_evidence_records": ("session_id", "evidence_id"),
            "interview_transcript_versions": ("recording_id", "version_number"),
            "interview_attempt_evaluations": ("recording_id", "version_number"),
            "interview_attempt_stages": (
                "recording_id",
                "evaluation_version_id",
                "stage_name",
            ),
            "interview_attempt_uploads": ("attempt_id", "upload_id"),
            "coach_session_deletion_results": ("session_key_hash", "command_id"),
        }
        for table, columns in expected_uniques.items():
            assert columns in _unique_column_sets(connection, table)
        session_sql = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE type='table' AND name='interview_sessions'"
        ).fetchone()[0]
        assert "invalidated" in session_sql
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_upgrade_enforces_conversational_state_allowlists(prior_head_db: Path) -> None:
    _upgrade(prior_head_db)
    with sqlite3.connect(prior_head_db) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_session(connection, "constraint-session")
        _insert_question(connection, "constraint-session", "constraint-question")
        _insert_recording(
            connection,
            recording_id="constraint-recording",
            session_id="constraint-session",
            question_id="constraint-question",
            created_at="2026-07-01 10:00:00",
            evaluation_state="completed",
        )
        connection.commit()

        invalid_statements = (
            "UPDATE interview_sessions SET conversation_state='invented' "
            "WHERE id='constraint-session'",
            "UPDATE session_questions SET question_kind='adaptive_follow_up', "
            "follow_up_depth=1 WHERE id='constraint-question'",
            "UPDATE session_recordings SET attempt_state='invented' "
            "WHERE id='constraint-recording'",
            """
            INSERT INTO coach_conversation_command_results(
                id, session_id, command_id, command_type, request_hash,
                expected_state_version, result_state, created_at
            ) VALUES (
                'bad-command', 'constraint-session', 'command-1', 'start',
                'hash', 0, 'invented', '2026-07-01 10:00:00'
            )
            """,
            """
            INSERT INTO interview_transcript_versions(
                id, recording_id, version_number, source, created_by, created_at
            ) VALUES (
                'bad-transcript', 'constraint-recording', 1, 'invented',
                'candidate', '2026-07-01 10:00:00'
            )
            """,
            """
            INSERT INTO interview_attempt_evaluations(
                id, recording_id, version_number, state,
                evaluation_contract_version, evidence_contract_version,
                follow_up_contract_version, created_at
            ) VALUES (
                'bad-evaluation', 'constraint-recording', 1, 'invented',
                'evaluation-v1', 'evidence-v1', 'follow-up-v1',
                '2026-07-01 10:00:00'
            )
            """,
            """
            INSERT INTO interview_attempt_uploads(
                id, attempt_id, upload_id, request_hash, content_sha256,
                byte_size, mime_type, storage_uri, result_state, created_at
            ) VALUES (
                'bad-upload', 'constraint-recording', 'upload-1', 'hash',
                'content-hash', 1, 'audio/webm', 'owned://uri', 'invented',
                '2026-07-01 10:00:00'
            )
            """,
        )
        for statement in invalid_statements:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
            connection.rollback()


def test_upgrade_current_check_downgrade_and_reupgrade(prior_head_db: Path) -> None:
    with sqlite3.connect(prior_head_db) as connection:
        _insert_session(connection, "roundtrip-session")
        _insert_question(connection, "roundtrip-session", "roundtrip-question")
        _insert_recording(
            connection,
            recording_id="roundtrip-recording",
            session_id="roundtrip-session",
            question_id="roundtrip-question",
            created_at="2026-07-01 10:00:00",
            evaluation_state="completed",
        )

    _upgrade(prior_head_db)
    assert COACH_REVISION in _run_alembic(prior_head_db, "current").stdout
    assert "No new upgrade operations detected" in (
        _run_alembic(prior_head_db, "check").stdout
        + _run_alembic(prior_head_db, "check").stderr
    )
    _run_alembic(prior_head_db, "downgrade", SOURCE_REVISION)

    with sqlite3.connect(prior_head_db) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (SOURCE_REVISION,)
        assert "experience_version" not in _column_names(
            connection, "interview_sessions"
        )
        assert connection.execute(
            "SELECT report_json, overall_score FROM interview_sessions WHERE id='roundtrip-session'"
        ).fetchone() == ('{"summary":"legacy byte contract","scores":[8,7]}', 8.25)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    _upgrade(prior_head_db)
    with sqlite3.connect(prior_head_db) as connection:
        assert connection.execute(
            "SELECT attempt_number, attempt_kind FROM session_recordings"
        ).fetchone() == (1, "primary")
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_supported_fresh_install_matches_new_head_metadata(tmp_path: Path) -> None:
    database = tmp_path / "coach-fresh-install.sqlite"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import asyncio\n"
                "import app.models\n"
                "from app.database import Base, engine\n"
                "async def main():\n"
                " async with engine.begin() as connection:\n"
                "  await connection.run_sync(Base.metadata.create_all)\n"
                " await engine.dispose()\n"
                "asyncio.run(main())"
            ),
        ],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    _run_alembic(database, "stamp", COACH_REVISION)
    assert COACH_REVISION in _run_alembic(database, "current").stdout
    check_result = _run_alembic(database, "check")
    assert (
        "No new upgrade operations detected"
        in check_result.stdout + check_result.stderr
    )
    with sqlite3.connect(database) as connection:
        assert SESSION_COLUMNS <= _column_names(connection, "interview_sessions")
        assert QUESTION_COLUMNS <= _column_names(connection, "session_questions")
        assert RECORDING_COLUMNS <= _column_names(connection, "session_recordings")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert NEW_TABLES <= tables
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
