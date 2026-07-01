import importlib.util
import sqlite3
from pathlib import Path


def _load_script():
    path = Path(__file__).resolve().parents[3] / "scripts" / "reset_app_lock.py"
    spec = importlib.util.spec_from_file_location("reset_app_lock", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_reset_clears_only_lock_data(tmp_path: Path) -> None:
    db_path = tmp_path / "hatch.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO jobs VALUES ('preserved')")
        db.execute(
            "CREATE TABLE app_lock_config (password_hash TEXT, failed_attempt_count INTEGER, "
            "last_failed_attempt_at TEXT, last_unlocked_at TEXT, last_password_changed_at TEXT)"
        )
        db.execute("INSERT INTO app_lock_config VALUES ('hash', 4, 'x', 'x', 'x')")
        db.execute("CREATE TABLE app_lock_sessions (id TEXT)")
        db.execute("INSERT INTO app_lock_sessions VALUES ('session')")

    _load_script().reset_database(db_path)

    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT id FROM jobs").fetchall() == [("preserved",)]
        assert db.execute("SELECT * FROM app_lock_sessions").fetchall() == []
        assert db.execute("SELECT password_hash, failed_attempt_count FROM app_lock_config").fetchone() == (None, 0)
