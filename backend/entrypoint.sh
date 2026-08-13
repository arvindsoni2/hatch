#!/bin/bash
set -e

echo "JobPilot Backend starting..."

python -m app.database_setup

echo "Database ready. Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
