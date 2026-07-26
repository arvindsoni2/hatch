"""Contract tests for the conversational Coach persistence migration."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[2]
SCHEMA_FIXTURE = BACKEND_DIR / "tests/fixtures/coach/p3q4r5s6t7u8_schema.sql"
SOURCE_INTEGRATION_SHA = "52ded582babf684e90325f000233e811914f7710"
SOURCE_REVISION = "p3q4r5s6t7u8"
COACH_REVISION = "q4r5s6t7u8v9"
SCHEMA_FIXTURE_SHA256 = (
    "58a69e0217a71705d06e45588ec254a3f9dd7f8df4eeb4811f76b84d259de2a6"
)
CANONICAL_COMPLETED_EVALUATION_JSON = (
    '{"evaluation_state":"completed","scores":{"relevance":8,'
    '"star_structure":7,"technical_depth":9,"conciseness":6,'
    '"communication":8,"impact_metrics":7},"overall":7.5}'
)

INTEGER_COERCION_VALUES = (
    0,
    1,
    8,
    10,
    11,
    -1,
    0.0,
    1.0,
    8.0,
    8.5,
    True,
    False,
    None,
    "0",
    "1",
    "8",
    "10",
    "11",
    "-1",
    "+1",
    "08",
    "8.0",
    "8.00",
    "8.5",
    "8e0",
    "8E0",
    "1_0",
    "1__0",
    "0__1",
    "1_0.0",
    "1.0_0",
    "0-1",
    "0-0",
    "0-00",
    "0-_0",
    "01-8",
    "+0-1",
    "+0-0",
    "0-1.0",
    "00-0.0",
    "٨",
    " 8 ",
    "8.",
    ".0",
    "",
    "nan",
    "inf",
    10**400,
    {},
    [],
)
INTEGER_COERCION_FIELDS = (
    ("scores", "relevance"),
    ("diagnostic", "attempt_count"),
    ("diagnostic", "repair_count"),
    ("diagnostic", "duration_ms"),
    ("rubric", "dimensions", "relevance", "score"),
    ("rubric", "diagnostic", "attempt_count"),
    ("rubric", "diagnostic", "repair_count"),
    ("rubric", "diagnostic", "duration_ms"),
)
INTEGER_ZERO_GROUP_DECIMAL_VALUES = (
    ("0__0.0", 0),
    ("0___0.0", 0),
    ("00__0.0", 0),
    ("0__00.0", 0),
    ("0__0.00", 0),
    ("0__0_0.0", 0),
    ("0_0__0.0", 0),
    ("00__00.000", 0),
    ("+0__0.0", 0),
    ("-0__0.0", 0),
    ("0__0.1", None),
    ("0__0.0_0", None),
    ("0__0.__0", None),
    ("1__0.0", None),
)
FLOAT_COERCION_VALUES = (
    0,
    10,
    11,
    -1,
    0.0,
    10.0,
    10.5,
    float("nan"),
    float("inf"),
    float("-inf"),
    True,
    False,
    None,
    "0",
    "10",
    "10.0",
    "10e0",
    "1e1",
    "0_.1",
    "1._0",
    "1e_0",
    "0_e1",
    "+_1",
    "._1",
    "0_1",
    "0_1 ",
    " 0_1",
    "0__1",
    "_1",
    "1_",
    "10.5",
    "nan",
    "NaN",
    "inf",
    "Infinity",
    "+infinity",
    "-inf",
    "\t1\n",
    "٠.١",
    "０.１",
    "𝟘.𝟙",
    " 8 ",
    "",
    10**400,
    {},
    [],
)
BOOLEAN_COERCION_VALUES = (
    False,
    True,
    0,
    1,
    -1,
    2,
    0.0,
    1.0,
    -1.0,
    0.5,
    "false",
    "true",
    "f",
    "t",
    "n",
    "y",
    "False",
    "True",
    "F",
    "T",
    "N",
    "Y",
    "0",
    "1",
    "off",
    "on",
    "no",
    "yes",
    " true ",
    "8e0",
    None,
    {},
    [],
)
FLOAT_STRING_FUZZ_ALPHABET = "01+-.eE_ "
RUST_TRIM_WHITESPACE_CODEPOINTS = (
    0x0009,
    0x000A,
    0x000B,
    0x000C,
    0x000D,
    0x0020,
    0x0085,
    0x00A0,
    0x1680,
    *range(0x2000, 0x200B),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)
NON_RUST_TRIM_BOUNDARY_CODEPOINTS = (
    0x0000,
    0x0008,
    0x000E,
    0x001B,
    0x001C,
    0x001D,
    0x001E,
    0x001F,
    0x007F,
    0x180E,
    0x200B,
    0x2060,
    0xFEFF,
)
FLOAT_WHITESPACE_FAMILY_CODEPOINTS = tuple(
    sorted(
        {
            neighbor
            for codepoint in (
                *RUST_TRIM_WHITESPACE_CODEPOINTS,
                *NON_RUST_TRIM_BOUNDARY_CODEPOINTS,
            )
            for neighbor in (codepoint - 1, codepoint, codepoint + 1)
            if 0 <= neighbor <= 0x10FFFF
        }
    )
)
FLOAT_WHITESPACE_CASES = tuple(
    (codepoint, placement)
    for codepoint in FLOAT_WHITESPACE_FAMILY_CODEPOINTS
    for placement in ("prefix", "suffix", "both")
)
MALFORMED_MEMBERSHIP_VALUES = (
    ("object", {}),
    ("list", []),
    ("number", 42),
    ("null", None),
)
MALFORMED_MEMBERSHIP_SITES = (
    "diagnostic.stage",
    "diagnostic.outcome",
    "diagnostic.execution_mode",
    "diagnostic.gate_codes.item",
    "rubric.dimensions.score_band",
)
JSON_SHAPE_FUZZ_VALUES = (
    None,
    False,
    0,
    0.0,
    "",
    [],
    {},
    [None],
    [[]],
    [{}],
    {"nested": None},
    {"nested": []},
    {"nested": {}},
    [None, [], {}],
)


def _coercion_case_id(case: tuple[tuple[str, ...], object]) -> str:
    path, value = case
    rendered = repr(value)
    if len(rendered) > 24:
        rendered = f"<{type(value).__name__}>"
    return f"{'.'.join(path)}={type(value).__name__}:{rendered}"


COERCION_AUTHORITY_CASES = (
    tuple(
        (path, value)
        for path in INTEGER_COERCION_FIELDS
        for value in INTEGER_COERCION_VALUES
    )
    + tuple((("overall",), value) for value in FLOAT_COERCION_VALUES)
    + tuple((("retryable",), value) for value in BOOLEAN_COERCION_VALUES)
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

NEW_TABLE_COLUMN_CONTRACTS: dict[str, dict[str, tuple[bool, str | None]]] = {
    "coach_conversation_command_results": {
        "id": (True, None),
        "session_id": (True, None),
        "command_id": (True, None),
        "command_type": (True, None),
        "request_hash": (True, None),
        "expected_state_version": (True, None),
        "result_state": (True, None),
        "result_json": (False, None),
        "created_at": (True, None),
        "completed_at": (False, None),
    },
    "interview_session_events": {
        "id": (True, None),
        "session_id": (True, None),
        "sequence_number": (True, None),
        "event_type": (True, None),
        "state_before": (False, None),
        "state_after": (False, None),
        "state_version": (True, None),
        "question_id": (False, None),
        "recording_id": (False, None),
        "command_id": (False, None),
        "actor_type": (True, None),
        "payload_json": (False, None),
        "created_at": (True, None),
    },
    "coach_session_evidence_records": {
        "id": (True, None),
        "session_id": (True, None),
        "evidence_id": (True, None),
        "source_type": (True, None),
        "source_record_id": (True, None),
        "source_record_version": (True, None),
        "source_path": (True, None),
        "snapshot_text": (True, None),
        "approval_state": (True, None),
        "content_hash": (True, None),
        "snapshot_hash": (True, None),
        "created_at": (True, None),
    },
    "interview_transcript_versions": {
        "id": (True, None),
        "recording_id": (True, None),
        "version_number": (True, None),
        "transcript": (False, None),
        "source": (True, None),
        "content_hash": (False, None),
        "edit_reason": (False, None),
        "created_by": (True, None),
        "processing_generation": (False, None),
        "created_at": (True, None),
    },
    "interview_attempt_evaluations": {
        "id": (True, None),
        "recording_id": (True, None),
        "transcript_version_id": (False, None),
        "version_number": (True, None),
        "state": (True, None),
        "answer_level": (False, None),
        "rubric_json": (False, None),
        "evidence_findings_json": (False, None),
        "coaching_json": (False, None),
        "follow_up_proposal_json": (False, None),
        "diagnostics_json": (False, None),
        "model_route_json": (False, None),
        "evaluation_contract_version": (True, None),
        "evidence_contract_version": (True, None),
        "follow_up_contract_version": (True, None),
        "async_job_id": (False, None),
        "created_at": (True, None),
        "completed_at": (False, None),
    },
    "interview_attempt_stages": {
        "id": (True, None),
        "recording_id": (True, None),
        "evaluation_version_id": (True, None),
        "stage_name": (True, None),
        "stage_state": (True, None),
        "attempt_count": (True, "0"),
        "repair_count": (True, "0"),
        "job_id": (False, None),
        "claim_token": (False, None),
        "expected_processing_generation": (False, None),
        "source_transcript_version_id": (False, None),
        "reused_from_stage_id": (False, None),
        "job_deadline_at": (False, None),
        "started_at": (False, None),
        "completed_at": (False, None),
        "last_error_code": (False, None),
        "diagnostics_json": (False, None),
    },
    "interview_attempt_uploads": {
        "id": (True, None),
        "attempt_id": (True, None),
        "upload_id": (True, None),
        "request_hash": (True, None),
        "content_sha256": (True, None),
        "byte_size": (True, None),
        "mime_type": (True, None),
        "storage_uri": (True, None),
        "result_state": (True, None),
        "created_at": (True, None),
        "completed_at": (False, None),
    },
    "coach_session_deletion_results": {
        "id": (True, None),
        "session_key_hash": (True, None),
        "command_id": (True, None),
        "request_hash": (True, None),
        "result_state": (True, None),
        "error_code": (False, None),
        "created_at": (True, None),
        "completed_at": (False, None),
        "expires_at": (True, None),
    },
}

ADDED_COLUMN_DEFAULTS = {
    "interview_sessions": {
        "experience_version": "'legacy_v1'",
        "state_version": "0",
        "setup_generation": "0",
        "setup_attempt_count": "0",
        "setup_max_attempts": "3",
        "retention_version": "0",
        "deletion_state": "'not_requested'",
        "deletion_generation": "0",
        "event_version": "0",
        "session_plan_amendment_version": "0",
    },
    "session_questions": {
        "question_kind": "'planned'",
        "follow_up_depth": "0",
        "source_deleted": "0",
        "question_state": "'pending'",
        "attempts_created_count": "0",
        "acceptance_generation": "0",
        "pending_hint_count": "0",
    },
    "session_recordings": {
        "attempt_version": "0",
        "processing_generation": "0",
        "processing_retry_count": "0",
        "processing_retry_limit": "0",
        "hint_count": "0",
    },
}

INDEX_CONTRACTS = {
    "idx_interview_sessions_experience_state": (
        "interview_sessions",
        ("experience_version", "status"),
    ),
    "idx_interview_sessions_conversation_state": (
        "interview_sessions",
        ("conversation_state",),
    ),
    "idx_session_questions_session_asked_sequence": (
        "session_questions",
        ("session_id", "asked_sequence"),
    ),
    "idx_session_questions_root_question": ("session_questions", ("root_question_id",)),
    "idx_session_recordings_question_attempt": (
        "session_recordings",
        ("question_id", "attempt_number"),
    ),
    "idx_session_recordings_async_job_state": (
        "session_recordings",
        ("async_job_id", "attempt_state"),
    ),
    "idx_transcript_versions_recording_version": (
        "interview_transcript_versions",
        ("recording_id", "version_number"),
    ),
    "idx_attempt_evaluations_recording_version": (
        "interview_attempt_evaluations",
        ("recording_id", "version_number"),
    ),
    "idx_attempt_stages_job_state": (
        "interview_attempt_stages",
        ("job_id", "stage_state"),
    ),
    "idx_attempt_uploads_attempt_upload": (
        "interview_attempt_uploads",
        ("attempt_id", "upload_id"),
    ),
    "idx_session_evidence_records_session_evidence": (
        "coach_session_evidence_records",
        ("session_id", "evidence_id"),
    ),
    "idx_session_events_session_sequence": (
        "interview_session_events",
        ("session_id", "sequence_number"),
    ),
    "idx_session_events_session_created": (
        "interview_session_events",
        ("session_id", "created_at"),
    ),
    "idx_session_events_session_type": (
        "interview_session_events",
        ("session_id", "event_type"),
    ),
    "idx_command_results_session_command": (
        "coach_conversation_command_results",
        ("session_id", "command_id"),
    ),
    "idx_command_results_session_created": (
        "coach_conversation_command_results",
        ("session_id", "created_at"),
    ),
}

FOREIGN_KEY_CONTRACTS = {
    "session_questions": {
        ("root_question_id", "session_questions", "id", "SET NULL"),
        ("parent_question_id", "session_questions", "id", "SET NULL"),
        ("follow_up_source_recording_id", "session_recordings", "id", "SET NULL"),
        (
            "follow_up_source_transcript_version_id",
            "interview_transcript_versions",
            "id",
            "SET NULL",
        ),
        ("accepted_recording_id", "session_recordings", "id", "SET NULL"),
    },
    "session_recordings": {
        ("retry_of_recording_id", "session_recordings", "id", "SET NULL"),
        (
            "current_transcript_version_id",
            "interview_transcript_versions",
            "id",
            "SET NULL",
        ),
        (
            "current_evaluation_version_id",
            "interview_attempt_evaluations",
            "id",
            "SET NULL",
        ),
    },
    "coach_conversation_command_results": {
        ("session_id", "interview_sessions", "id", "CASCADE")
    },
    "interview_session_events": {("session_id", "interview_sessions", "id", "CASCADE")},
    "coach_session_evidence_records": {
        ("session_id", "interview_sessions", "id", "CASCADE")
    },
    "interview_transcript_versions": {
        ("recording_id", "session_recordings", "id", "CASCADE")
    },
    "interview_attempt_evaluations": {
        ("recording_id", "session_recordings", "id", "CASCADE"),
        ("transcript_version_id", "interview_transcript_versions", "id", "CASCADE"),
    },
    "interview_attempt_stages": {
        ("recording_id", "session_recordings", "id", "CASCADE"),
        ("evaluation_version_id", "interview_attempt_evaluations", "id", "CASCADE"),
        ("reused_from_stage_id", "interview_attempt_stages", "id", "SET NULL"),
    },
    "interview_attempt_uploads": {
        ("attempt_id", "session_recordings", "id", "CASCADE")
    },
}

CHECK_CONTRACTS = {
    "interview_sessions": {
        "ck_interview_sessions_report_state",
        "ck_interview_sessions_status",
        "ck_interview_sessions_conversation_state",
        "ck_interview_sessions_recoverable_error_scope",
        "ck_interview_sessions_deletion_state",
    },
    "session_questions": {
        "ck_session_questions_follow_up_depth",
        "ck_session_questions_question_kind",
        "ck_session_questions_question_state",
        "ck_session_questions_follow_up_reason",
        "ck_session_questions_attempts_created_count",
        "ck_session_questions_acceptance_generation",
        "ck_session_questions_pending_hint_count",
        "ck_session_questions_kind_depth",
        "ck_session_questions_accepted_generation_order",
        "ck_session_questions_accepted_generation_current",
    },
    "session_recordings": {
        "ck_session_recordings_attempt_number",
        "ck_session_recordings_processing_retry_count",
        "ck_session_recordings_processing_retry_limit",
        "ck_session_recordings_hint_count",
        "ck_session_recordings_attempt_kind",
        "ck_session_recordings_attempt_state",
        "ck_session_recordings_retry_budget",
    },
    "coach_conversation_command_results": {"ck_command_results_state"},
    "interview_session_events": {"ck_session_events_actor_type"},
    "coach_session_evidence_records": {"ck_session_evidence_approval_state"},
    "interview_transcript_versions": {
        "ck_transcript_versions_source",
        "ck_transcript_versions_created_by",
    },
    "interview_attempt_evaluations": {"ck_attempt_evaluations_state"},
    "interview_attempt_stages": {
        "ck_attempt_stages_name",
        "ck_attempt_stages_state",
        "ck_attempt_stages_counts",
    },
    "interview_attempt_uploads": {"ck_attempt_uploads_state"},
    "coach_session_deletion_results": {"ck_deletion_results_state"},
}

UNIQUE_CONTRACTS = {
    "session_questions": {("session_id", "asked_sequence")},
    "session_recordings": {
        ("question_id", "attempt_number"),
        ("session_id", "client_attempt_id"),
    },
    "coach_conversation_command_results": {("session_id", "command_id")},
    "interview_session_events": {("session_id", "sequence_number")},
    "coach_session_evidence_records": {("session_id", "evidence_id")},
    "interview_transcript_versions": {("recording_id", "version_number")},
    "interview_attempt_evaluations": {("recording_id", "version_number")},
    "interview_attempt_stages": {
        ("recording_id", "evaluation_version_id", "stage_name")
    },
    "interview_attempt_uploads": {("attempt_id", "upload_id")},
    "coach_session_deletion_results": {("session_key_hash", "command_id")},
}


class _RecordingBatchOperations:
    def __init__(self, table: str, operations: list[tuple[str, str, object]]) -> None:
        self.table = table
        self.operations = operations

    def __getattr__(self, operation: str):
        def record(*args: object, **kwargs: object) -> None:
            self.operations.append((self.table, operation, (args, kwargs)))

        return record


class _RecordingBatchContext:
    def __init__(self, batch: _RecordingBatchOperations) -> None:
        self.batch = batch

    def __enter__(self) -> _RecordingBatchOperations:
        return self.batch

    def __exit__(self, *_args: object) -> None:
        return None


class _RecordingAlembicOperations:
    def __init__(self) -> None:
        self.operations: list[tuple[str, str, object]] = []

    def batch_alter_table(
        self, table: str, **_kwargs: object
    ) -> _RecordingBatchContext:
        return _RecordingBatchContext(_RecordingBatchOperations(table, self.operations))

    def execute(self, statement: object) -> None:
        self.operations.append(("", "execute", str(statement)))

    def get_bind(self):
        class _EmptyConnection:
            @staticmethod
            def execute(*_args: object, **_kwargs: object) -> list[object]:
                return []

        return _EmptyConnection()

    def create_table(self, table: str, *_args: object, **_kwargs: object) -> None:
        self.operations.append((table, "create_table", None))

    def drop_table(self, table: str, **_kwargs: object) -> None:
        self.operations.append((table, "drop_table", None))


def _load_migration_module():
    path = (
        BACKEND_DIR
        / "alembic/versions/20260725_0001_q4r5s6t7u8v9_add_conversational_coach_foundation.py"
    )
    spec = importlib.util.spec_from_file_location("coach_q4_migration_order", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    evaluation_json: str = CANONICAL_COMPLETED_EVALUATION_JSON,
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
            evaluation_json,
            evaluation_state,
            created_at,
        ),
    )


def _completed_payload_with_contracts() -> dict[str, object]:
    diagnostic = {
        "stage": "answer_evaluation",
        "outcome": "completed",
        "execution_mode": "deterministic",
        "attempt_count": 0,
        "repair_count": 0,
        "gate_codes": [],
        "duration_ms": 0,
    }
    return {
        "evaluation_state": "completed",
        "scores": {
            "relevance": 8,
            "star_structure": 7,
            "technical_depth": 9,
            "conciseness": 6,
            "communication": 8,
            "impact_metrics": 7,
        },
        "overall": 7.5,
        "diagnostic": diagnostic,
        "rubric": {
            "dimensions": {
                "relevance": {
                    "score": 8,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "",
                }
            },
            "diagnostic": diagnostic.copy(),
        },
        "retryable": False,
    }


def _set_malformed_membership_site(
    payload: dict[str, object], site: str, malformed: object
) -> object:
    if site.startswith("diagnostic."):
        diagnostic = payload["diagnostic"]
        assert isinstance(diagnostic, dict)
        field = site.removeprefix("diagnostic.")
        if field == "gate_codes.item":
            diagnostic["gate_codes"] = [malformed]
        else:
            diagnostic[field] = malformed
        return diagnostic

    rubric = payload["rubric"]
    assert isinstance(rubric, dict)
    dimensions = rubric["dimensions"]
    assert isinstance(dimensions, dict)
    relevance = dimensions["relevance"]
    assert isinstance(relevance, dict)
    relevance["score_band"] = malformed
    return rubric


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
    "evaluation_json",
    [
        CANONICAL_COMPLETED_EVALUATION_JSON,
        CANONICAL_COMPLETED_EVALUATION_JSON.replace(
            '"evaluation_state":"completed",', ""
        ),
        CANONICAL_COMPLETED_EVALUATION_JSON.replace('"overall":7.5', '"overall":"7.5"'),
        CANONICAL_COMPLETED_EVALUATION_JSON.replace('"relevance":8', '"relevance":"8"'),
        CANONICAL_COMPLETED_EVALUATION_JSON.replace('"relevance":8', '"relevance":8.5'),
        CANONICAL_COMPLETED_EVALUATION_JSON.replace('"overall":7.5', '"overall":11'),
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1] + ',"feedback":42}',
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1] + ',"strengths":["clear",42]}',
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1] + ',"diagnostic":{}}',
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1]
        + ',"diagnostic":{"stage":"answer_evaluation","outcome":"completed",'
        '"execution_mode":"deterministic","attempt_count":0,"repair_count":0,'
        '"gate_codes":[],"duration_ms":0}}',
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1]
        + ',"diagnostic":{"stage":"answer_evaluation","outcome":"completed",'
        '"execution_mode":"deterministic","attempt_count":0,"repair_count":0,'
        '"gate_codes":["not_a_contract_gate"],"duration_ms":0}}',
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1]
        + ',"rubric":{"dimensions":{"relevance":{"score":12}}}}',
        CANONICAL_COMPLETED_EVALUATION_JSON[:-1] + ',"retryable":{}}',
    ],
)
def test_migration_validity_helper_matches_legacy_canonical_resolver(
    evaluation_json: str,
) -> None:
    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    recording = SimpleNamespace(
        id="recording",
        question_id="question",
        evaluation_state="completed",
        evaluation_json=evaluation_json,
        created_at=datetime(2026, 7, 1),
    )
    assert module._is_valid_legacy_completed_evaluation(
        recording.evaluation_state, recording.evaluation_json
    ) is (_parse_completed(recording) is not None)


@pytest.mark.parametrize("site", MALFORMED_MEMBERSHIP_SITES)
@pytest.mark.parametrize(
    "malformed",
    [value for _, value in MALFORMED_MEMBERSHIP_VALUES],
    ids=[name for name, _ in MALFORMED_MEMBERSHIP_VALUES],
)
def test_malformed_membership_values_are_invalid_without_raising_and_match_resolver(
    site: str, malformed: object
) -> None:
    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    payload = _completed_payload_with_contracts()
    helper_value = _set_malformed_membership_site(payload, site, malformed)
    if site.startswith("diagnostic."):
        assert module._is_valid_diagnostic(helper_value) is False
    else:
        assert module._is_valid_rubric(helper_value) is False

    recording = SimpleNamespace(
        id="recording",
        question_id="question",
        evaluation_state="completed",
        evaluation_json=json.dumps(payload, separators=(",", ":")),
        created_at=datetime(2026, 7, 1),
    )
    assert _parse_completed(recording) is None
    assert (
        module._is_valid_legacy_completed_evaluation(
            recording.evaluation_state, recording.evaluation_json
        )
        is False
    )


def test_bounded_json_shape_fuzz_matches_resolver_without_exceptions() -> None:
    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    paths = (
        ("evaluation_state",),
        ("overall",),
        ("scores",),
        ("feedback",),
        ("strengths",),
        ("follow_up_question",),
        ("diagnostic",),
        ("rubric",),
        ("retryable",),
        ("diagnostic", "stage"),
        ("diagnostic", "outcome"),
        ("diagnostic", "execution_mode"),
        ("diagnostic", "gate_codes"),
        ("rubric", "dimensions", "relevance", "score_band"),
    )
    mismatches: list[str] = []
    for path in paths:
        for shape_index, malformed in enumerate(JSON_SHAPE_FUZZ_VALUES):
            payload = _completed_payload_with_contracts()
            target = payload
            for segment in path[:-1]:
                nested = target[segment]
                assert isinstance(nested, dict)
                target = nested
            target[path[-1]] = malformed
            evaluation_json = json.dumps(payload, separators=(",", ":"))
            recording = SimpleNamespace(
                id="recording",
                question_id="question",
                evaluation_state="completed",
                evaluation_json=evaluation_json,
                created_at=datetime(2026, 7, 1),
            )
            authoritative = _parse_completed(recording) is not None
            try:
                migration_valid = module._is_valid_legacy_completed_evaluation(
                    recording.evaluation_state, recording.evaluation_json
                )
            except Exception as exc:  # pragma: no cover - assertion captures regression
                mismatches.append(
                    f"{'.'.join(path)}[{shape_index}] raised {type(exc).__name__}"
                )
            else:
                if migration_valid is not authoritative:
                    mismatches.append(f"{'.'.join(path)}[{shape_index}] parity")

    assert mismatches == []


@pytest.mark.parametrize(
    ("path", "value"),
    COERCION_AUTHORITY_CASES,
    ids=[_coercion_case_id(case) for case in COERCION_AUTHORITY_CASES],
)
def test_migration_validator_matches_authority_for_every_coercion_field(
    path: tuple[str, ...], value: object
) -> None:
    from app.services.coach_aggregation import _parse_completed

    diagnostic = {
        "stage": "answer_evaluation",
        "outcome": "completed",
        "execution_mode": "deterministic",
        "attempt_count": 0,
        "repair_count": 0,
        "gate_codes": [],
        "duration_ms": 0,
    }
    payload = {
        "evaluation_state": "completed",
        "scores": {
            "relevance": 8,
            "star_structure": 7,
            "technical_depth": 9,
            "conciseness": 6,
            "communication": 8,
            "impact_metrics": 7,
        },
        "overall": 7.5,
        "diagnostic": diagnostic.copy(),
        "rubric": {
            "dimensions": {
                "relevance": {
                    "score": 8,
                    "score_band": "good",
                    "evidence": [],
                    "drill": "",
                }
            },
            "diagnostic": diagnostic.copy(),
        },
        "retryable": False,
    }
    target = payload
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[assignment,index]
    target[path[-1]] = value  # type: ignore[index]
    evaluation_json = json.dumps(payload, separators=(",", ":"))
    recording = SimpleNamespace(
        id="recording",
        question_id="question",
        evaluation_state="completed",
        evaluation_json=evaluation_json,
        created_at=datetime(2026, 7, 1),
    )
    authoritative = _parse_completed(recording) is not None
    module = _load_migration_module()

    assert (
        module._is_valid_legacy_completed_evaluation(
            recording.evaluation_state, recording.evaluation_json
        )
        is authoritative
    )


# These exhaustive grammar comparisons intentionally remain in the ordinary migration
# gate. Their runtime and memory cost is accepted because this migration snapshots
# pydantic-core coercion without importing the application runtime.
def test_migration_validator_matches_authority_for_ascii_float_string_grammar() -> None:
    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    payload = json.loads(CANONICAL_COMPLETED_EVALUATION_JSON)
    recording = SimpleNamespace(
        id="recording",
        question_id="question",
        evaluation_state="completed",
        evaluation_json="",
        created_at=datetime(2026, 7, 1),
    )
    mismatches: list[str] = []
    for length in range(6):
        for characters in itertools.product(FLOAT_STRING_FUZZ_ALPHABET, repeat=length):
            value = "".join(characters)
            payload["overall"] = value
            recording.evaluation_json = json.dumps(payload, separators=(",", ":"))
            authoritative = _parse_completed(recording) is not None
            migration_valid = module._is_valid_legacy_completed_evaluation(
                recording.evaluation_state, recording.evaluation_json
            )
            if migration_valid is not authoritative:
                mismatches.append(value)

    assert mismatches == []


def test_integer_parser_matches_authority_for_ascii_string_grammar_through_length_six() -> (
    None
):
    from pydantic import TypeAdapter, ValidationError

    module = _load_migration_module()
    adapter = TypeAdapter(int)
    mismatches: list[str] = []
    for length in range(7):
        for characters in itertools.product(FLOAT_STRING_FUZZ_ALPHABET, repeat=length):
            value = "".join(characters)
            try:
                authoritative = adapter.validate_python(value)
            except ValidationError:
                authoritative = None
            migration_number = module._coerce_pydantic_integer(value)
            if migration_number != authoritative:
                mismatches.append(value)

    assert mismatches == []


@pytest.mark.parametrize(
    "path",
    INTEGER_COERCION_FIELDS,
    ids=[".".join(path) for path in INTEGER_COERCION_FIELDS],
)
@pytest.mark.parametrize(
    ("value", "expected"),
    INTEGER_ZERO_GROUP_DECIMAL_VALUES,
    ids=[value for value, _ in INTEGER_ZERO_GROUP_DECIMAL_VALUES],
)
def test_repeated_underscore_zero_group_decimals_match_integer_authority_for_every_path(
    path: tuple[str, ...], value: str, expected: int | None
) -> None:
    from pydantic import TypeAdapter, ValidationError

    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    try:
        authoritative_number = TypeAdapter(int).validate_python(value)
    except ValidationError:
        authoritative_number = None
    assert authoritative_number == expected
    assert module._coerce_pydantic_integer(value) == authoritative_number

    diagnostic = {
        "stage": "answer_evaluation",
        "outcome": "completed",
        "execution_mode": "deterministic",
        "attempt_count": 0,
        "repair_count": 0,
        "gate_codes": [],
        "duration_ms": 0,
    }
    payload = {
        "evaluation_state": "completed",
        "scores": {
            "relevance": 8,
            "star_structure": 7,
            "technical_depth": 9,
            "conciseness": 6,
            "communication": 8,
            "impact_metrics": 7,
        },
        "overall": 7.5,
        "diagnostic": diagnostic.copy(),
        "rubric": {
            "dimensions": {"relevance": {"score": 8}},
            "diagnostic": diagnostic.copy(),
        },
        "retryable": False,
    }
    target = payload
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[assignment,index]
    target[path[-1]] = value  # type: ignore[index]
    evaluation_json = json.dumps(payload, separators=(",", ":"))
    recording = SimpleNamespace(
        id="recording",
        question_id="question",
        evaluation_state="completed",
        evaluation_json=evaluation_json,
        created_at=datetime(2026, 7, 1),
    )
    authoritative_valid = _parse_completed(recording) is not None
    assert authoritative_valid is (expected is not None)
    assert (
        module._is_valid_legacy_completed_evaluation(
            recording.evaluation_state, recording.evaluation_json
        )
        is authoritative_valid
    )


@pytest.mark.parametrize(
    ("codepoint", "placement"),
    FLOAT_WHITESPACE_CASES,
    ids=[
        f"U+{codepoint:04X}-{placement}"
        for codepoint, placement in FLOAT_WHITESPACE_CASES
    ],
)
def test_float_whitespace_snapshot_matches_direct_and_whole_resolver_authority(
    codepoint: int, placement: str
) -> None:
    from pydantic import TypeAdapter, ValidationError

    from app.services.coach_aggregation import _parse_completed

    whitespace = chr(codepoint)
    value = {
        "prefix": f"{whitespace}1",
        "suffix": f"1{whitespace}",
        "both": f"{whitespace}1{whitespace}",
    }[placement]
    expected = codepoint in RUST_TRIM_WHITESPACE_CODEPOINTS
    try:
        authoritative_number = TypeAdapter(float).validate_python(value)
    except ValidationError:
        authoritative_number = None

    module = _load_migration_module()
    assert (authoritative_number is not None) is expected
    assert module._parse_pydantic_float_string(value) == authoritative_number

    payload = json.loads(CANONICAL_COMPLETED_EVALUATION_JSON)
    payload["overall"] = value
    recording = SimpleNamespace(
        id="recording",
        question_id="question",
        evaluation_state="completed",
        evaluation_json=json.dumps(payload, separators=(",", ":")),
        created_at=datetime(2026, 7, 1),
    )
    authoritative_valid = _parse_completed(recording) is not None
    assert authoritative_valid is expected
    assert (
        module._is_valid_legacy_completed_evaluation(
            recording.evaluation_state, recording.evaluation_json
        )
        is authoritative_valid
    )


@pytest.mark.parametrize(
    "path",
    INTEGER_COERCION_FIELDS,
    ids=[".".join(path) for path in INTEGER_COERCION_FIELDS],
)
def test_integer_whitespace_snapshot_matches_authority_for_every_integer_path(
    path: tuple[str, ...],
) -> None:
    from pydantic import TypeAdapter, ValidationError

    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    adapter = TypeAdapter(int)
    diagnostic = {
        "stage": "answer_evaluation",
        "outcome": "completed",
        "execution_mode": "deterministic",
        "attempt_count": 0,
        "repair_count": 0,
        "gate_codes": [],
        "duration_ms": 0,
    }
    payload = {
        "evaluation_state": "completed",
        "scores": {
            "relevance": 8,
            "star_structure": 7,
            "technical_depth": 9,
            "conciseness": 6,
            "communication": 8,
            "impact_metrics": 7,
        },
        "overall": 7.5,
        "diagnostic": diagnostic.copy(),
        "rubric": {
            "dimensions": {"relevance": {"score": 8}},
            "diagnostic": diagnostic.copy(),
        },
        "retryable": False,
    }
    target = payload
    for segment in path[:-1]:
        target = target[segment]  # type: ignore[assignment,index]
    mismatches: list[str] = []
    for codepoint, placement in FLOAT_WHITESPACE_CASES:
        boundary = chr(codepoint)
        value = {
            "prefix": f"{boundary}1",
            "suffix": f"1{boundary}",
            "both": f"{boundary}1{boundary}",
        }[placement]
        expected = codepoint in RUST_TRIM_WHITESPACE_CODEPOINTS
        try:
            authoritative_number = adapter.validate_python(value)
        except ValidationError:
            authoritative_number = None
        migration_number = module._coerce_pydantic_integer(value)
        target[path[-1]] = value  # type: ignore[index]
        evaluation_json = json.dumps(payload, separators=(",", ":"))
        recording = SimpleNamespace(
            id="recording",
            question_id="question",
            evaluation_state="completed",
            evaluation_json=evaluation_json,
            created_at=datetime(2026, 7, 1),
        )
        authoritative_valid = _parse_completed(recording) is not None
        migration_valid = module._is_valid_legacy_completed_evaluation(
            recording.evaluation_state, recording.evaluation_json
        )
        if not (
            (authoritative_number is not None) is expected
            and migration_number == authoritative_number
            and authoritative_valid is expected
            and migration_valid is authoritative_valid
        ):
            mismatches.append(f"U+{codepoint:04X}-{placement}")

    assert mismatches == []


def test_boolean_aliases_remain_untrimmed_across_whitespace_family() -> None:
    from pydantic import TypeAdapter, ValidationError

    from app.services.coach_aggregation import _parse_completed

    module = _load_migration_module()
    adapter = TypeAdapter(bool)
    payload = json.loads(CANONICAL_COMPLETED_EVALUATION_JSON)
    mismatches: list[str] = []
    for alias in ("1", "true", "t", "yes"):
        for codepoint, placement in FLOAT_WHITESPACE_CASES:
            boundary = chr(codepoint)
            value = {
                "prefix": f"{boundary}{alias}",
                "suffix": f"{alias}{boundary}",
                "both": f"{boundary}{alias}{boundary}",
            }[placement]
            try:
                adapter.validate_python(value)
                authoritative_boolean = True
            except ValidationError:
                authoritative_boolean = False
            payload["retryable"] = value
            evaluation_json = json.dumps(payload, separators=(",", ":"))
            recording = SimpleNamespace(
                id="recording",
                question_id="question",
                evaluation_state="completed",
                evaluation_json=evaluation_json,
                created_at=datetime(2026, 7, 1),
            )
            authoritative_valid = _parse_completed(recording) is not None
            migration_valid = module._is_valid_legacy_completed_evaluation(
                recording.evaluation_state, recording.evaluation_json
            )
            if (
                authoritative_boolean
                or module._is_pydantic_boolean(value)
                or authoritative_valid
                or migration_valid
            ):
                mismatches.append(f"{alias}-U+{codepoint:04X}-{placement}")

    assert mismatches == []


@pytest.mark.parametrize(
    ("table", "backfill_marker"),
    [
        ("session_questions", "UPDATE session_questions AS question"),
        ("session_recordings", "UPDATE session_recordings AS recording"),
    ],
)
def test_migration_backfills_before_constraints_indexes_and_non_null_enforcement(
    table: str, backfill_marker: str
) -> None:
    module = _load_migration_module()
    recorder = _RecordingAlembicOperations()
    module.op = recorder
    module.upgrade()

    operations = recorder.operations
    backfill_position = next(
        index
        for index, (_, operation, detail) in enumerate(operations)
        if operation == "execute" and backfill_marker in str(detail)
    )
    add_operations = [
        (index, detail)
        for index, (operation_table, operation, detail) in enumerate(operations)
        if operation_table == table and operation == "add_column"
    ]
    assert add_operations
    assert all(index < backfill_position for index, _ in add_operations)
    assert all(
        args[0].nullable is True
        for _, (args, _kwargs) in add_operations
        if args[0].name
        in {
            "question_kind",
            "follow_up_depth",
            "source_deleted",
            "question_state",
            "attempts_created_count",
            "acceptance_generation",
            "pending_hint_count",
            "attempt_version",
            "processing_generation",
            "processing_retry_count",
            "processing_retry_limit",
            "hint_count",
        }
    )
    contract_operations = {
        "alter_column",
        "create_check_constraint",
        "create_foreign_key",
        "create_index",
        "create_unique_constraint",
    }
    positions = [
        index
        for index, (operation_table, operation, _detail) in enumerate(operations)
        if operation_table == table and operation in contract_operations
    ]
    assert positions
    assert min(positions) > backfill_position


def test_attempt_number_backfill_uses_one_materialized_window_ranking() -> None:
    module = _load_migration_module()
    recorder = _RecordingAlembicOperations()
    module.op = recorder
    module.upgrade()
    statement = next(
        str(detail)
        for _, operation, detail in recorder.operations
        if operation == "execute" and "SET attempt_number" in str(detail)
    )

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            """
            CREATE TABLE session_recordings(
                id TEXT PRIMARY KEY,
                question_id TEXT,
                created_at TEXT,
                attempt_number INTEGER,
                attempt_version INTEGER,
                processing_generation INTEGER,
                processing_retry_count INTEGER,
                processing_retry_limit INTEGER,
                hint_count INTEGER
            )
            """
        )
        plan = [row[3] for row in connection.execute(f"EXPLAIN QUERY PLAN {statement}")]

    assert plan.count("MATERIALIZE ranked") == 1
    assert not any("CORRELATED" in step for step in plan)


def test_window_attempt_number_backfill_matches_partitioned_created_at_id_order(
    prior_head_db: Path,
) -> None:
    with sqlite3.connect(prior_head_db) as connection:
        _insert_session(connection, "ranking-session")
        _insert_question(connection, "ranking-session", "question-a")
        _insert_question(connection, "ranking-session", "question-b")
        rows = (
            ("z-a", "question-a", "2026-07-01 10:00:00"),
            ("a-a", "question-a", "2026-07-01 10:00:00"),
            ("m-a", "question-a", "2026-07-01 10:01:00"),
            ("z-b", "question-b", "2026-07-01 09:59:00"),
            ("a-b", "question-b", "2026-07-01 10:02:00"),
        )
        for recording_id, question_id, created_at in rows:
            _insert_recording(
                connection,
                recording_id=recording_id,
                session_id="ranking-session",
                question_id=question_id,
                created_at=created_at,
                evaluation_state="failed",
            )

    _upgrade(prior_head_db)

    with sqlite3.connect(prior_head_db) as connection:
        actual = dict(
            connection.execute(
                "SELECT id, attempt_number FROM session_recordings"
            ).fetchall()
        )
    assert actual == {"a-a": 1, "z-a": 2, "m-a": 3, "z-b": 1, "a-b": 2}


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


@pytest.mark.parametrize(
    "evaluation_json",
    [
        "not-json",
        '{"evaluation_state":"completed","scores":{"relevance":8},"overall":8}',
        (
            '{"evaluation_state":"completed","scores":{"relevance":11,'
            '"star_structure":7,"technical_depth":9,"conciseness":6,'
            '"communication":8,"impact_metrics":7},"overall":8}'
        ),
        (
            '{"evaluation_state":"unavailable","scores":{"relevance":8,'
            '"star_structure":7,"technical_depth":9,"conciseness":6,'
            '"communication":8,"impact_metrics":7},"overall":8}'
        ),
        (
            '{"evaluation_state":"completed","scores":{"relevance":8,'
            '"star_structure":7,"technical_depth":9,"conciseness":6,'
            '"communication":8,"impact_metrics":7},"overall":12}'
        ),
        (
            '{"evaluation_state":"completed","scores":{"relevance":"8e0",'
            '"star_structure":7,"technical_depth":9,"conciseness":6,'
            '"communication":8,"impact_metrics":7},"overall":8}'
        ),
    ],
)
def test_malformed_completed_legacy_evaluations_remain_pending(
    prior_head_db: Path, evaluation_json: str
) -> None:
    with sqlite3.connect(prior_head_db) as connection:
        _insert_session(connection, "malformed-session")
        _insert_question(connection, "malformed-session", "malformed-question")
        _insert_recording(
            connection,
            recording_id="malformed-recording",
            session_id="malformed-session",
            question_id="malformed-question",
            created_at="2026-07-01 10:00:00",
            evaluation_state="completed",
            evaluation_json=evaluation_json,
        )

    _upgrade(prior_head_db)
    with sqlite3.connect(prior_head_db) as connection:
        assert connection.execute(
            "SELECT question_state FROM session_questions WHERE id='malformed-question'"
        ).fetchone() == ("pending",)


def test_upgrade_rejects_all_malformed_membership_shapes_without_partial_state(
    prior_head_db: Path,
) -> None:
    malformed_cases = tuple(
        (site, shape_name, malformed)
        for site in MALFORMED_MEMBERSHIP_SITES
        for shape_name, malformed in MALFORMED_MEMBERSHIP_VALUES
        if shape_name in {"object", "list"}
    )
    with sqlite3.connect(prior_head_db) as connection:
        _insert_session(connection, "malformed-membership-session")
        for index, (site, shape_name, malformed) in enumerate(malformed_cases):
            question_id = f"malformed-membership-question-{index}"
            payload = _completed_payload_with_contracts()
            _set_malformed_membership_site(payload, site, malformed)
            _insert_question(connection, "malformed-membership-session", question_id)
            _insert_recording(
                connection,
                recording_id=f"malformed-membership-recording-{index}",
                session_id="malformed-membership-session",
                question_id=question_id,
                created_at=f"2026-07-01 10:00:{index:02d}",
                evaluation_state="completed",
                evaluation_json=json.dumps(payload, separators=(",", ":")),
            )

    _upgrade(prior_head_db)

    with sqlite3.connect(prior_head_db) as connection:
        states = connection.execute(
            """
            SELECT question_state
            FROM session_questions
            WHERE id LIKE 'malformed-membership-question-%'
            ORDER BY id
            """
        ).fetchall()
        assert states == [("pending",)] * len(malformed_cases)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (COACH_REVISION,)


def test_upgrade_classifies_pydantic_float_string_families(
    prior_head_db: Path,
) -> None:
    cases = (
        ("0_.1", "answered"),
        ("1._0", "answered"),
        ("1e_0", "answered"),
        (" 1 ", "answered"),
        ("0_1 ", "pending"),
        (" 0_1", "pending"),
        ("٠.١", "pending"),
        ("０.１", "pending"),
        ("𝟘.𝟙", "pending"),
        ("nan", "pending"),
        ("inf", "pending"),
    )
    with sqlite3.connect(prior_head_db) as connection:
        for index, (overall, _expected_state) in enumerate(cases):
            session_id = f"float-session-{index}"
            question_id = f"float-question-{index}"
            evaluation = json.loads(CANONICAL_COMPLETED_EVALUATION_JSON)
            evaluation["overall"] = overall
            _insert_session(connection, session_id)
            _insert_question(connection, session_id, question_id)
            _insert_recording(
                connection,
                recording_id=f"float-recording-{index}",
                session_id=session_id,
                question_id=question_id,
                created_at=f"2026-07-01 10:00:{index:02d}",
                evaluation_state="completed",
                evaluation_json=json.dumps(evaluation, separators=(",", ":")),
            )

    _upgrade(prior_head_db)
    with sqlite3.connect(prior_head_db) as connection:
        actual = dict(
            connection.execute(
                """
                SELECT id, question_state
                FROM session_questions
                WHERE id LIKE 'float-question-%'
                """
            ).fetchall()
        )
    assert actual == {
        f"float-question-{index}": expected_state
        for index, (_overall, expected_state) in enumerate(cases)
    }


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

        for result_state in ("permission_denied", "stale_claim"):
            connection.execute(
                """
                INSERT INTO coach_conversation_command_results(
                    id, session_id, command_id, command_type, request_hash,
                    expected_state_version, result_state, created_at
                ) VALUES (?, 'constraint-session', ?, 'start', 'hash', 0, ?,
                          '2026-07-01 10:00:00')
                """,
                (f"valid-{result_state}", result_state, result_state),
            )
        connection.execute(
            "UPDATE session_questions SET follow_up_reason=NULL "
            "WHERE id='constraint-question'"
        )
        connection.execute(
            "UPDATE session_questions SET follow_up_reason='clarify_example' "
            "WHERE id='constraint-question'"
        )
        connection.commit()

        invalid_statements = (
            "UPDATE interview_sessions SET conversation_state='invented' "
            "WHERE id='constraint-session'",
            "UPDATE session_questions SET question_kind='adaptive_follow_up', "
            "follow_up_depth=1 WHERE id='constraint-question'",
            "UPDATE session_questions SET follow_up_reason='invented' "
            "WHERE id='constraint-question'",
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
    with sqlite3.connect(prior_head_db) as connection:
        connection.execute(
            """
            UPDATE interview_sessions
            SET report_state='invalidated',
                report_json='{"stale":"private report"}',
                report_job_id='stale-report-job',
                report_started_at='2026-07-01 11:00:00'
            WHERE id='roundtrip-session'
            """
        )
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
            """
            SELECT report_state, report_json, report_job_id, report_started_at, overall_score
            FROM interview_sessions WHERE id='roundtrip-session'
            """
        ).fetchone() == ("failed", None, None, None, 8.25)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    _upgrade(prior_head_db)
    with sqlite3.connect(prior_head_db) as connection:
        assert connection.execute(
            "SELECT attempt_number, attempt_kind FROM session_recordings"
        ).fetchone() == (1, "primary")
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT report_state, report_json FROM interview_sessions "
            "WHERE id='roundtrip-session'"
        ).fetchone() == ("failed", None)


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
        added_contracts = {
            "interview_sessions": SESSION_COLUMNS,
            "session_questions": QUESTION_COLUMNS,
            "session_recordings": RECORDING_COLUMNS,
        }
        for table, required_columns in added_contracts.items():
            actual = {
                row[1]: (bool(row[3]), row[4])
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert required_columns <= set(actual)
            defaults = ADDED_COLUMN_DEFAULTS[table]
            for column in required_columns:
                assert actual[column] == (
                    column in defaults,
                    defaults.get(column),
                )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert NEW_TABLES <= tables
        for table, expected_columns in NEW_TABLE_COLUMN_CONTRACTS.items():
            actual_columns = {
                row[1]: (bool(row[3]), row[4])
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert actual_columns == expected_columns

        for index, (table, expected_columns) in INDEX_CONTRACTS.items():
            index_row = connection.execute(
                "SELECT tbl_name FROM sqlite_schema WHERE type='index' AND name=?",
                (index,),
            ).fetchone()
            assert index_row == (table,)
            assert (
                tuple(
                    row[2] for row in connection.execute(f"PRAGMA index_info({index})")
                )
                == expected_columns
            )

        for table, expected_uniques in UNIQUE_CONTRACTS.items():
            assert expected_uniques <= _unique_column_sets(connection, table)

        for table, expected_foreign_keys in FOREIGN_KEY_CONTRACTS.items():
            actual_foreign_keys = {
                (row[3], row[2], row[4], row[6])
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")
            }
            assert expected_foreign_keys <= actual_foreign_keys

        for table, expected_checks in CHECK_CONTRACTS.items():
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            assert all(
                f"CONSTRAINT {constraint} CHECK" in table_sql
                for constraint in expected_checks
            )
        command_sql = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name='coach_conversation_command_results'"
        ).fetchone()[0]
        assert "permission_denied" in command_sql
        assert "stale_claim" in command_sql
        question_sql = connection.execute(
            "SELECT sql FROM sqlite_schema WHERE name='session_questions'"
        ).fetchone()[0]
        assert {
            "clarify_example",
            "measurable_result",
            "personal_action",
            "reasoning",
            "role_depth",
            "resolve_ambiguity",
            "evidence_consistency",
        } <= set(re.findall(r"'([a-z_]+)'", question_sql))
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
