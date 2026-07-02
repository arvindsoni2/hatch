#!/usr/bin/env bash
# reset-user-data.sh — wipe local user data and return Hatch to first-run state
# Usage: ./scripts/reset-user-data.sh [--yes] [--keep-profile]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${HATCH_RESET_DATA_DIR:-$PROJECT_DIR/data}"
ASSUME_YES=false
RESET_PROFILE=true

for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=true ;;
    --keep-profile) RESET_PROFILE=false ;;
    --help|-h)
      echo "Usage: $0 [--yes] [--keep-profile]"
      echo "  --yes           Skip the destructive confirmation prompt"
      echo "  --keep-profile  Clear workflow data but retain identity, CV, and saved API keys"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}[hatch]${RESET} $*"; }
ok()    { echo -e "${GREEN}[hatch]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[hatch]${RESET} $*"; }
error() { echo -e "${RED}[hatch]${RESET} $*" >&2; exit 1; }

# ── Detect compose / container runtime ────────────────────────────

COMPOSE=""
if command -v podman-compose &>/dev/null \
  && [ -n "$(docker inspect -f '{{index .Config.Labels "io.podman.compose.project"}}' hatch-backend 2>/dev/null || true)" ]; then
  COMPOSE="podman-compose"
elif docker compose version &>/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE="docker-compose"
fi

backend_running() {
  [[ "${HATCH_RESET_OFFLINE:-0}" != "1" ]] || return 1
  docker ps --format "{{.Names}}" 2>/dev/null | grep -q "hatch-backend"
}

container_exec() {
  docker exec hatch-backend "$@"
}

verify_database_schema() {
  local attempts=30
  local required_tables="alembic_version,applications,async_jobs,job_postings"

  info "Verifying database schema…"
  while (( attempts > 0 )); do
    if container_exec python -c \
      'import sqlite3, sys
db = sqlite3.connect("/app/data/jobpilot.db")
tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = '\''table'\''")}
required = {"alembic_version", "applications", "async_jobs", "job_postings"}
sys.exit(0 if required <= tables else 1)' \
      &>/dev/null; then
      ok "Database schema verified ($required_tables)"
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 2
  done

  error "Backend restarted, but required database tables were not created. Check: docker logs hatch-backend"
}

restart_backend() {
  info "Restarting backend to reinitialise database schema…"

  # Restarting by container name works for Docker Compose, podman-compose, and
  # Docker-compatible Podman. Compose is retained as a fallback for other setups.
  if docker restart hatch-backend &>/dev/null; then
    ok "Backend restarted"
  elif [ -n "$COMPOSE" ] && $COMPOSE restart backend &>/dev/null; then
    ok "Backend restarted via $COMPOSE"
  else
    error "Could not restart hatch-backend. The reset is incomplete; restart it before using Hatch."
  fi

  verify_database_schema
}

# ── Banner ─────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}  Hatch — Reset User Data${RESET}"
echo "  ─────────────────────────────────────────"
echo ""
echo -e "  ${YELLOW}This will permanently delete:${RESET}"
echo "    • All scraped jobs, scores, and decisions"
echo "    • All agent run history and events"
echo "    • Local LangGraph checkpoints"
echo "    • All generated CVs and cover letters"
  echo "    • Coach recordings"
if $RESET_PROFILE; then
  echo "    • profile.yaml → reset to the blank first-run template"
  echo "    • master_cv.json, metadata, and master_resume.*"
  echo "    • data/api_keys.env (keys must be re-entered)"
else
  echo ""
  echo -e "  ${YELLOW}Keeping profile, master CV/resume, and saved API keys.${RESET}"
fi
echo ""

# ── Confirm ────────────────────────────────────────────────────────

CONFIRM=""
if $ASSUME_YES; then
  CONFIRM="yes"
else
  read -r -p "  Type 'yes' to confirm: " CONFIRM
  echo ""
fi

if [[ "$CONFIRM" != "yes" ]]; then
  info "Aborted — no changes made."
  exit 0
fi

# ── Helper: delete a file via container exec or direct/sudo ────────

delete_file() {
  local host_path="$1"
  local container_path="$2"
  local label="$3"

  if ! backend_running && [ ! -e "$host_path" ]; then
    ok "$label was already absent"
    return 0
  fi

  if backend_running; then
    container_exec rm -f "$container_path" 2>/dev/null \
      && ok "Deleted $label" \
      || warn "Could not delete $label inside container (may not exist)"
  elif [ -w "$host_path" ]; then
    rm -f "$host_path" && ok "Deleted $label"
  elif sudo -n true 2>/dev/null; then
    sudo rm -f "$host_path" && ok "Deleted $label (sudo)"
  else
    warn "Cannot delete $label — containers are not running and the file is not writable."
    warn "Run 'docker compose up -d' first, then re-run this script."
    return 1
  fi
}

delete_dir_contents() {
  local host_path="$1"
  local container_path="$2"
  local label="$3"

  if ! backend_running && [ ! -e "$host_path" ]; then
    ok "$label was already absent"
    return 0
  fi

  if backend_running; then
    container_exec sh -c "find '$container_path' -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null; true" \
      && ok "Cleared $label" \
      || warn "Could not clear $label inside container"
  elif [ -w "$host_path" ]; then
    find "${host_path:?}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null
    ok "Cleared $label"
  elif sudo -n true 2>/dev/null; then
    sudo find "${host_path:?}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + 2>/dev/null \
      && ok "Cleared $label (sudo)"
  else
    warn "Cannot clear $label — containers are not running and the directory is not writable."
    return 1
  fi
}

# ── Reset ──────────────────────────────────────────────────────────

info "Resetting job data…"

delete_file \
  "$DATA_DIR/langgraph_checkpoints.db" \
  "/app/data/langgraph_checkpoints.db" \
  "LangGraph checkpoints (langgraph_checkpoints.db)"

delete_file \
  "$DATA_DIR/langgraph_checkpoints.db-shm" \
  "/app/data/langgraph_checkpoints.db-shm" \
  "LangGraph checkpoints WAL shared memory (langgraph_checkpoints.db-shm)"

delete_file \
  "$DATA_DIR/langgraph_checkpoints.db-wal" \
  "/app/data/langgraph_checkpoints.db-wal" \
  "LangGraph checkpoints WAL log (langgraph_checkpoints.db-wal)"

delete_dir_contents \
  "$DATA_DIR/generated" \
  "/app/data/generated" \
  "generated documents (data/generated/)"

delete_dir_contents \
  "$DATA_DIR/recordings" \
  "/app/data/recordings" \
  "Coach recordings (data/recordings/)"

delete_dir_contents \
  "$DATA_DIR/uploads" \
  "/app/data/uploads" \
  "uploaded temporary files (data/uploads/)"

if $RESET_PROFILE; then
  info "Resetting user identity…"

  if [ -f "$DATA_DIR/profile.yaml.example" ]; then
    if backend_running; then
      container_exec sh -c "cp /app/data/profile.yaml.example /app/data/profile.yaml" \
        && ok "Reset profile.yaml from example template"
    elif [ -w "$DATA_DIR" ]; then
      cp "$DATA_DIR/profile.yaml.example" "$DATA_DIR/profile.yaml" \
        && ok "Reset profile.yaml from example template"
    else
      sudo cp "$DATA_DIR/profile.yaml.example" "$DATA_DIR/profile.yaml" \
        && ok "Reset profile.yaml from example template (sudo)"
    fi
  else
    delete_file \
      "$DATA_DIR/profile.yaml" \
      "/app/data/profile.yaml" \
      "profile.yaml"
  fi

  delete_file \
    "$DATA_DIR/master_cv.json" \
    "/app/data/master_cv.json" \
    "master_cv.json"

  delete_file \
    "$DATA_DIR/master_cv.meta.json" \
    "/app/data/master_cv.meta.json" \
    "master_cv.meta.json"

  delete_file \
    "$DATA_DIR/master_resume.txt" \
    "/app/data/master_resume.txt" \
    "master_resume.txt (CV text used for scoring)"

  delete_file \
    "$DATA_DIR/master_resume.pdf" \
    "/app/data/master_resume.pdf" \
    "master_resume.pdf"

  delete_file \
    "$DATA_DIR/master_resume.docx" \
    "/app/data/master_resume.docx" \
    "master_resume.docx"

  warn "Clearing api_keys.env — API keys will need to be re-entered in Settings or onboarding."
  if backend_running; then
    container_exec sh -c "echo '' > /app/data/api_keys.env 2>/dev/null; true" \
      && ok "Cleared api_keys.env"
  elif [ -w "$DATA_DIR/api_keys.env" ]; then
    : > "$DATA_DIR/api_keys.env" && ok "Cleared api_keys.env"
  elif sudo -n true 2>/dev/null; then
    sudo sh -c ": > '$DATA_DIR/api_keys.env'" && ok "Cleared api_keys.env (sudo)"
  else
    warn "Cannot clear api_keys.env — clear it manually to remove old API keys."
  fi
fi

# Delete the live application database last, immediately before restarting the
# backend. This minimises the window in which the running process can connect to
# a newly-created but unmigrated SQLite file.
delete_file \
  "$DATA_DIR/jobpilot.db" \
  "/app/data/jobpilot.db" \
  "database (jobpilot.db)"

delete_file \
  "$DATA_DIR/jobpilot.db-shm" \
  "/app/data/jobpilot.db-shm" \
  "database WAL shared memory (jobpilot.db-shm)"

delete_file \
  "$DATA_DIR/jobpilot.db-wal" \
  "/app/data/jobpilot.db-wal" \
  "database WAL log (jobpilot.db-wal)"

# ── Restart backend so DB schema is recreated ─────────────────────

if backend_running; then
  restart_backend
else
  warn "Backend is not running, so schema recreation is deferred until its next start."
fi

# ── Done ───────────────────────────────────────────────────────────

echo ""
ok "Reset complete."
echo ""
if $RESET_PROFILE; then
  warn "Next: open http://localhost:3000/onboarding to set up the new user."
  warn "Browser tip: clear localStorage for localhost:3000 (DevTools → Application → Storage → Clear site data)"
  warn "  to avoid the previous session's onboarding progress appearing as 'Resume where you left off'."
else
  warn "Next: open http://localhost:3000 — all job data has been cleared, your profile is unchanged."
fi
echo ""
