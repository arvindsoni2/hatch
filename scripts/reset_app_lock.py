#!/usr/bin/env python3
"""Clear only Hatch app-lock configuration and sessions."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def reset_database(db_path: Path) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as db:
        tables = {
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        required = {"app_lock_config", "app_lock_sessions"}
        if not required <= tables:
            raise RuntimeError(
                "Database does not contain the app-lock tables. "
                "Start Hatch once so migrations can complete."
            )
        db.execute("DELETE FROM app_lock_sessions")
        db.execute(
            "UPDATE app_lock_config SET password_hash=NULL, failed_attempt_count=0, "
            "last_failed_attempt_at=NULL, last_unlocked_at=NULL, last_password_changed_at=NULL"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clear Hatch app-lock configuration and sessions without deleting user data."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "jobpilot.db",
        help="Path to jobpilot.db (defaults to the repository data directory)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the RESET_APP_LOCK confirmation prompt",
    )
    args = parser.parse_args()

    print("This clears the app-lock password and active sessions. User data is preserved.")
    if not args.yes and input("Type RESET_APP_LOCK to continue: ").strip() != "RESET_APP_LOCK":
        print("Reset cancelled.")
        return 1

    try:
        reset_database(args.database.resolve())
    except (FileNotFoundError, RuntimeError, sqlite3.Error, PermissionError) as exc:
        print(f"App lock reset failed: {exc}", file=sys.stderr)
        return 1

    print("App lock reset. Restart Hatch and open /unlock to set a new app password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
