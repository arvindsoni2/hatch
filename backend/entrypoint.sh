#!/bin/bash
set -e

echo "JobPilot Backend starting..."

# Resolve DB file path from DATABASE_URL
# e.g. sqlite+aiosqlite:///./data/jobpilot.db  →  ./data/jobpilot.db
DB_PATH="${DATABASE_URL#sqlite+aiosqlite:///}"

# Detect fresh vs existing install.
# Fresh = DB file doesn't exist OR has no user tables yet.
# On fresh: stamp Alembic to head WITHOUT running migrations (migrations 1-3
# are no-ops; migration 4 would fail trying to ALTER tables that don't exist
# in a clean DB). FastAPI lifespan calls init_db() → create_all() instead.
# On existing: run normal incremental migrations.
is_fresh() {
    if [ ! -f "$DB_PATH" ]; then
        return 0
    fi
    TABLE_COUNT=$(python3 -c "
import sqlite3, sys
try:
    con = sqlite3.connect('$DB_PATH')
    n = con.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table' AND name != 'alembic_version'\").fetchone()[0]
    print(n)
except Exception:
    print(0)
")
    [ "$TABLE_COUNT" -eq 0 ]
}

if is_fresh; then
    echo "Fresh database — stamping Alembic to head (schema created by init_db on startup)..."
    alembic stamp head
else
    echo "Existing database — running Alembic migrations..."
    alembic upgrade head
fi

echo "Database ready. Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
