"""Canonical, fail-closed database bootstrap and migration command."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

from .config import settings
from .database import Base
from . import models as _models  # noqa: F401 - register all metadata tables


BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSION_TABLE = "alembic_version"


class DatabaseSetupError(RuntimeError):
    """Raised when database state cannot be changed safely."""


def _sync_url(database_url: str) -> URL:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        raise DatabaseSetupError("Only file-backed SQLite databases are supported.")
    if url.database == ":memory:":
        raise DatabaseSetupError("In-memory databases cannot be bootstrapped.")
    return url.set(drivername="sqlite")


def _async_url_for_path(database: Path) -> str:
    return URL.create(
        "sqlite+aiosqlite", database=str(database.resolve())
    ).render_as_string(hide_password=False)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["database_url"] = database_url
    return config


def _copy_sqlite_database(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)


def _preflight_upgrade(database: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hatch-database-setup-") as directory:
        candidate = Path(directory) / "migration-preflight.db"
        _copy_sqlite_database(database, candidate)
        candidate_config = _alembic_config(_async_url_for_path(candidate))
        try:
            command.upgrade(candidate_config, "head")
        except Exception as exc:
            raise DatabaseSetupError(
                "Migration preflight failed; database left unchanged."
            ) from exc


def setup_database(database_url: str | None = None) -> None:
    """Create a verified-empty database or safely upgrade a known ancestor."""
    configured_url = database_url or settings.DATABASE_URL
    sync_url = _sync_url(configured_url)
    database = Path(sync_url.database).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    config = _alembic_config(configured_url)
    scripts = ScriptDirectory.from_config(config)
    script_heads = scripts.get_heads()
    if len(script_heads) != 1:
        raise DatabaseSetupError(
            f"Expected exactly one migration head; found {len(script_heads)}."
        )
    head = script_heads[0]

    engine = create_engine(sync_url)
    try:
        with engine.connect() as connection:
            schema_objects = {
                (row[0], row[1])
                for row in connection.exec_driver_sql(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%'"
                )
            }
            current_heads = MigrationContext.configure(connection).get_current_heads()

        if len(current_heads) > 1:
            raise DatabaseSetupError("Multiple database heads are not supported.")

        if not current_heads:
            application_objects = schema_objects - {("table", VERSION_TABLE)}
            if application_objects:
                raise DatabaseSetupError(
                    "Non-empty unversioned database cannot be bootstrapped."
                )
            Base.metadata.create_all(engine)
            command.stamp(config, "head")
            return

        current = current_heads[0]
        if current == head:
            return

        try:
            scripts.get_revision(current)
        except CommandError as exc:
            raise DatabaseSetupError(
                f"Unknown revision {current!r}; database left unchanged."
            ) from exc

        ancestors = {
            revision.revision
            for revision in scripts.walk_revisions(base="base", head=head)
        }
        if current not in ancestors:
            raise DatabaseSetupError(
                f"Revision {current!r} is not an ancestor of head; "
                "database left unchanged."
            )

        _preflight_upgrade(database)
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def main() -> int:
    """Run database setup using the configured application database URL."""
    try:
        setup_database()
    except DatabaseSetupError as exc:
        print(f"Database setup refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
