#!/bin/bash
set -e

echo "JobPilot Backend starting..."

# Run Alembic migrations
echo "Running database migrations..."
alembic upgrade head

echo "Migrations complete. Starting FastAPI server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
