#!/usr/bin/env python3
"""Clear only Hatch app-lock configuration and sessions."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def reset_database(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute("DELETE FROM app_lock_sessions")
        db.execute(
            "UPDATE app_lock_config SET password_hash=NULL, failed_attempt_count=0, "
            "last_failed_attempt_at=NULL, last_unlocked_at=NULL, last_password_changed_at=NULL"
        )


def main() -> int:
    print("This clears the app-lock password and active sessions. User data is preserved.")
    if input("Type RESET_APP_LOCK to continue: ").strip() != "RESET_APP_LOCK":
        print("Reset cancelled.")
        return 1
    db_path = Path(__file__).resolve().parents[1] / "data" / "jobpilot.db"
    reset_database(db_path)
    print("App lock reset. Restart Hatch and open /unlock to set a new app password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
