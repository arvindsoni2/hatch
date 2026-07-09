#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

mkdir -p \
  "$FIXTURE_DIR/generated/job-1" \
  "$FIXTURE_DIR/recordings/session-1" \
  "$FIXTURE_DIR/uploads" \
  "$FIXTURE_DIR/models"

cp "$PROJECT_DIR/data/profile.yaml.example" "$FIXTURE_DIR/profile.yaml.example"
printf 'candidate:\n  name: "Existing User"\n' > "$FIXTURE_DIR/profile.yaml"
printf '{"name":"Existing User"}\n' > "$FIXTURE_DIR/master_cv.json"
printf '{}\n' > "$FIXTURE_DIR/master_cv.meta.json"
printf 'resume text\n' > "$FIXTURE_DIR/master_resume.txt"
printf 'pdf\n' > "$FIXTURE_DIR/master_resume.pdf"
printf 'docx\n' > "$FIXTURE_DIR/master_resume.docx"
printf 'SECRET=value\n' > "$FIXTURE_DIR/api_keys.env"
touch \
  "$FIXTURE_DIR/jobpilot.db" \
  "$FIXTURE_DIR/jobpilot.db-shm" \
  "$FIXTURE_DIR/jobpilot.db-wal" \
  "$FIXTURE_DIR/langgraph_checkpoints.db" \
  "$FIXTURE_DIR/langgraph_checkpoints.db-shm" \
  "$FIXTURE_DIR/langgraph_checkpoints.db-wal" \
  "$FIXTURE_DIR/generated/job-1/cv.docx" \
  "$FIXTURE_DIR/generated/.stale" \
  "$FIXTURE_DIR/recordings/session-1/audio.webm" \
  "$FIXTURE_DIR/uploads/resume.pdf" \
  "$FIXTURE_DIR/models/model.gguf"

HATCH_RESET_DATA_DIR="$FIXTURE_DIR" \
HATCH_RESET_OFFLINE=1 \
  bash "$PROJECT_DIR/scripts/reset-user-data.sh" --yes

test -f "$FIXTURE_DIR/models/model.gguf"
test -f "$FIXTURE_DIR/profile.yaml.example"
cmp -s "$FIXTURE_DIR/profile.yaml.example" "$FIXTURE_DIR/profile.yaml"

test ! -e "$FIXTURE_DIR/jobpilot.db"
test ! -e "$FIXTURE_DIR/jobpilot.db-shm"
test ! -e "$FIXTURE_DIR/jobpilot.db-wal"
test ! -e "$FIXTURE_DIR/langgraph_checkpoints.db"
test ! -e "$FIXTURE_DIR/langgraph_checkpoints.db-shm"
test ! -e "$FIXTURE_DIR/langgraph_checkpoints.db-wal"
test ! -e "$FIXTURE_DIR/generated/job-1/cv.docx"
test ! -e "$FIXTURE_DIR/generated/.stale"
test ! -e "$FIXTURE_DIR/recordings/session-1/audio.webm"
test ! -e "$FIXTURE_DIR/uploads/resume.pdf"
test ! -e "$FIXTURE_DIR/master_cv.json"
test ! -e "$FIXTURE_DIR/master_cv.meta.json"
test ! -e "$FIXTURE_DIR/master_resume.txt"
test ! -e "$FIXTURE_DIR/master_resume.pdf"
test ! -e "$FIXTURE_DIR/master_resume.docx"
test -f "$FIXTURE_DIR/api_keys.env"
grep -q "SECRET=value" "$FIXTURE_DIR/api_keys.env"

printf 'SECRET=delete-me\n' > "$FIXTURE_DIR/api_keys.env"
touch "$FIXTURE_DIR/jobpilot.db"

HATCH_RESET_DATA_DIR="$FIXTURE_DIR" \
HATCH_RESET_OFFLINE=1 \
  bash "$PROJECT_DIR/scripts/reset-user-data.sh" --yes --delete-secrets

test -f "$FIXTURE_DIR/api_keys.env"
test ! -s "$FIXTURE_DIR/api_keys.env"

printf 'candidate:\n  name: "Retained User"\n' > "$FIXTURE_DIR/profile.yaml"
printf '{"name":"Retained User"}\n' > "$FIXTURE_DIR/master_cv.json"
printf 'SECRET=retained\n' > "$FIXTURE_DIR/api_keys.env"
touch "$FIXTURE_DIR/jobpilot.db"
mkdir -p "$FIXTURE_DIR/recordings/session-2"
touch "$FIXTURE_DIR/recordings/session-2/.hidden-recording"

HATCH_RESET_DATA_DIR="$FIXTURE_DIR" \
HATCH_RESET_OFFLINE=1 \
  bash "$PROJECT_DIR/scripts/reset-user-data.sh" --yes --keep-profile

grep -q "Retained User" "$FIXTURE_DIR/profile.yaml"
test -f "$FIXTURE_DIR/master_cv.json"
grep -q "SECRET=retained" "$FIXTURE_DIR/api_keys.env"
test ! -e "$FIXTURE_DIR/jobpilot.db"
test ! -e "$FIXTURE_DIR/recordings/session-2/.hidden-recording"

echo "reset-user-data isolated test passed"
