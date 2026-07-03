#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSUME_YES=false

case "${1:-}" in
  --help|-h|--database|--database=*)
    exec python3 "$SCRIPT_DIR/reset_app_lock.py" "$@"
    ;;
  --yes)
    ASSUME_YES=true
    shift
    ;;
  "")
    ;;
  *)
    exec python3 "$SCRIPT_DIR/reset_app_lock.py" "$@"
    ;;
esac

if (($# > 0)); then
  exec python3 "$SCRIPT_DIR/reset_app_lock.py" ${ASSUME_YES:+--yes} "$@"
fi

backend_running() {
  command -v docker &>/dev/null \
    && docker ps --format "{{.Names}}" 2>/dev/null | grep -qx "hatch-backend"
}

if backend_running; then
  echo "This clears the app-lock password and active sessions. User data is preserved."
  if ! $ASSUME_YES; then
    read -r -p "Type RESET_APP_LOCK to continue: " CONFIRM
    if [[ "$CONFIRM" != "RESET_APP_LOCK" ]]; then
      echo "Reset cancelled."
      exit 1
    fi
  fi

  docker exec hatch-backend python -c '
import sqlite3
db = sqlite3.connect("/app/data/jobpilot.db")
tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='\''table'\''")}
required = {"app_lock_config", "app_lock_sessions"}
if not required <= tables:
    raise SystemExit("Database does not contain the app-lock tables. Start Hatch once so migrations can complete.")
with db:
    db.execute("DELETE FROM app_lock_sessions")
    db.execute(
        "UPDATE app_lock_config SET password_hash=NULL, failed_attempt_count=0, "
        "last_failed_attempt_at=NULL, last_unlocked_at=NULL, "
        "last_password_changed_at=NULL"
    )
db.close()
'
  echo "App lock reset. Restart Hatch and open /unlock to set a new app password."
else
  exec python3 "$SCRIPT_DIR/reset_app_lock.py" "$@"
fi
