#!/usr/bin/env bash
# reset-user-data.sh — wipe all job/application data to start fresh as a new user
# Usage: ./reset-user-data.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"

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
if docker compose version &>/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE="docker-compose"
fi

backend_running() {
  docker ps --format "{{.Names}}" 2>/dev/null | grep -q "hatch-backend"
}

container_exec() {
  docker exec hatch-backend "$@"
}

# ── Banner ─────────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}  Hatch — Reset User Data${RESET}"
echo "  ─────────────────────────────────────────"
echo ""
echo -e "  ${YELLOW}This will permanently delete:${RESET}"
echo "    • All scraped jobs, scores, and decisions"
echo "    • All agent run history and events"
echo "    • All generated CVs and cover letters"
echo ""
echo -e "  ${YELLOW}If you also reset identity (prompted below):${RESET}"
echo "    • profile.yaml → reset to blank template"
echo "    • master_cv.json / master_resume.txt → deleted"
echo "    • api_keys.env → cleared (keys must be re-entered)"
echo ""

# ── Ask whether to also reset identity files ──────────────────────

RESET_PROFILE="n"
read -r -p "  Also reset profile.yaml and master_cv.json (new user identity)? [y/N] " RESET_PROFILE
echo ""

# ── Confirm ────────────────────────────────────────────────────────

read -r -p "  Type 'yes' to confirm: " CONFIRM
echo ""

if [[ "$CONFIRM" != "yes" ]]; then
  info "Aborted — no changes made."
  exit 0
fi

# ── Helper: delete a file via container exec or direct/sudo ────────

delete_file() {
  local host_path="$1"
  local container_path="$2"
  local label="$3"

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

  if backend_running; then
    container_exec sh -c "rm -rf ${container_path}/* 2>/dev/null; true" \
      && ok "Cleared $label" \
      || warn "Could not clear $label inside container"
  elif [ -w "$host_path" ]; then
    rm -rf "${host_path:?}"/* 2>/dev/null; ok "Cleared $label"
  elif sudo -n true 2>/dev/null; then
    sudo rm -rf "${host_path:?}"/* 2>/dev/null && ok "Cleared $label (sudo)"
  else
    warn "Cannot clear $label — containers are not running and the directory is not writable."
    return 1
  fi
}

# ── Reset ──────────────────────────────────────────────────────────

info "Resetting job data…"

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

delete_dir_contents \
  "$DATA_DIR/generated" \
  "/app/data/generated" \
  "generated documents (data/generated/)"

if [[ "$RESET_PROFILE" =~ ^[Yy]$ ]]; then
  info "Resetting user identity…"

  if [ -f "$DATA_DIR/profile.yaml.example" ]; then
    if backend_running; then
      container_exec sh -c "cp /app/data/profile.yaml.example /app/data/profile.yaml" \
        && ok "Reset profile.yaml from example template"
    elif [ -w "$DATA_DIR/profile.yaml" ]; then
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

# ── Restart backend so DB schema is recreated ─────────────────────

if backend_running && [ -n "$COMPOSE" ]; then
  info "Restarting backend to reinitialise database schema…"
  $COMPOSE restart backend 2>/dev/null && ok "Backend restarted" \
    || warn "Could not restart backend — run '$COMPOSE restart backend' manually"
elif backend_running; then
  warn "Compose not found — restart the backend manually to reinitialise the DB schema."
fi

# ── Done ───────────────────────────────────────────────────────────

echo ""
ok "Reset complete."
echo ""
if [[ "$RESET_PROFILE" =~ ^[Yy]$ ]]; then
  warn "Next: open http://localhost:3000/onboarding to set up the new user."
  warn "Browser tip: clear localStorage for localhost:3000 (DevTools → Application → Storage → Clear site data)"
  warn "  to avoid the previous session's onboarding progress appearing as 'Resume where you left off'."
else
  warn "Next: open http://localhost:3000 — all job data has been cleared, your profile is unchanged."
fi
echo ""
