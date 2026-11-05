"""RED contract for P2: the `add coach interview debriefs` Alembic revision.

Written by Claude Code before implementation (plan §1.5). The full chain from an
empty database fails at a pre-existing revision, so the disposable database is
built from the ORM metadata, the debrief table is removed, and the database is
stamped at the revision's parent before upgrading. All data is synthetic.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.database import Base
from app.models.application import Application, InterviewRound

BACKEND_DIR = Path(__file__).resolve().parents[2]
REVISION_MESSAGE = "add coach interview debriefs"
P1_HEAD = "9a0421e6f32b"
TABLE = "coach_interview_debriefs"
EXPECTED_COLUMNS = {
    "id",
    "interview_round_id",
    "version",
    "status",
    "overall",
    "expectation",
    "questions_json",
    "went_well",
    "do_differently",
    "notes_text",
    "proposals_json",
    "created_at",
    "updated_at",
}


def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))


def _alembic(database: Path, *arguments: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def test_migration_single_head_and_fk_cascade(tmp_path: Path) -> None:
    scripts = _scripts()
    heads = scripts.get_heads()
    assert len(heads) == 1, heads

    matches = [
        revision
        for revision in scripts.walk_revisions()
        if (revision.doc or "").strip().lower() == REVISION_MESSAGE
    ]
    assert len(matches) == 1, f"expected one revision named {REVISION_MESSAGE!r}"
    revision = matches[0]
    assert revision.down_revision == P1_HEAD

    # Disposable database at the parent revision, without the debrief table.
    database = tmp_path / "debrief-migration.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {TABLE}")
        # Core inserts apply the models' Python-side defaults.
        connection.execute(
            Application.__table__.insert().values(
                id="app-m", status="interview", priority="normal"
            )
        )
        connection.execute(
            InterviewRound.__table__.insert().values(
                id="round-m",
                application_id="app-m",
                round_number=1,
                type="behavioural",
                status="completed",
            )
        )
    engine.dispose()
    _alembic(database, "stamp", P1_HEAD)

    _alembic(database, "upgrade", revision.revision)
    connection = sqlite3.connect(database)
    try:
        assert TABLE in _tables(connection)
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({TABLE})")}
        assert EXPECTED_COLUMNS <= columns, EXPECTED_COLUMNS - columns
        notes = [
            row for row in connection.execute(f"PRAGMA table_info({TABLE})")
            if row[1] == "notes_text"
        ]
        assert notes and notes[0][3] == 0, "notes_text must be nullable"

        foreign_keys = connection.execute(
            f"PRAGMA foreign_key_list({TABLE})"
        ).fetchall()
        round_keys = [row for row in foreign_keys if row[3] == "interview_round_id"]
        assert len(round_keys) == 1
        assert round_keys[0][2] == "interview_rounds"
        assert round_keys[0][6].upper() == "CASCADE"

        unique_round = False
        for index in connection.execute(f"PRAGMA index_list({TABLE})"):
            if index[2]:
                cols = [
                    info[2]
                    for info in connection.execute(f"PRAGMA index_info('{index[1]}')")
                ]
                unique_round = unique_round or cols == ["interview_round_id"]
        assert unique_round, "interview_round_id must be unique (one debrief per round)"

        connection.execute("PRAGMA foreign_keys = ON")

        insert = (
            f"INSERT INTO {TABLE} (id, interview_round_id, version, status, overall, "
            "expectation, questions_json, went_well, do_differently, notes_text, "
            "proposals_json, created_at, updated_at) VALUES "
            "(?, ?, 1, 'saved', 4, 'yes', '[]', NULL, NULL, NULL, '[]', "
            "'2026-11-10 12:00:00', '2026-11-10 12:00:00')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(insert, ("orphan", "no-such-round"))
        connection.rollback()

        connection.execute(insert, ("debrief-m", "round-m"))
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(insert, ("second", "round-m"))
        connection.rollback()

        connection.execute("DELETE FROM interview_rounds WHERE id = 'round-m'")
        connection.commit()
        assert connection.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 0
    finally:
        connection.close()

    _alembic(database, "downgrade", P1_HEAD)
    connection = sqlite3.connect(database)
    try:
        assert TABLE not in _tables(connection)
    finally:
        connection.close()

    _alembic(database, "upgrade", revision.revision)
    connection = sqlite3.connect(database)
    try:
        assert TABLE in _tables(connection)
    finally:
        connection.close()
