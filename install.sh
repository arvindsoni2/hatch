#!/usr/bin/env bash
# JobPilot v2 — one-command installer for Linux / macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/arvindsoni2/jobpilot-v2/main/install.sh | bash
# Or locally: ./install.sh
set -euo pipefail

CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}[jobpilot]${RESET} $*"; }
ok()    { echo -e "${GREEN}[jobpilot]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[jobpilot]${RESET} $*"; }
error() { echo -e "${RED}[jobpilot]${RESET} $*" >&2; exit 1; }

# ── Prerequisites ──────────────────────────────────────────────────

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    error "$1 is required but not installed. $2"
  fi
  ok "$1 found: $(command -v "$1")"
}

info "Checking prerequisites…"

# Docker (or Podman acting as docker)
if command -v podman &>/dev/null; then
  if ! command -v docker &>/dev/null; then
    info "Podman detected — creating docker alias"
    # Podman can act as docker. Alias it if not already done.
    export DOCKER_HOST="unix://$XDG_RUNTIME_DIR/podman/podman.sock"
  fi
else
  check_cmd docker "Install from https://docs.docker.com/get-docker/"
fi

if docker compose version &>/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE="docker-compose"
elif command -v podman-compose &>/dev/null; then
  COMPOSE="podman-compose"
else
  error "docker compose / podman-compose not found. Install Docker Desktop or 'pip install podman-compose'."
fi
ok "Compose command: $COMPOSE"

# ── Clone or update ────────────────────────────────────────────────

INSTALL_DIR="${JOBPILOT_DIR:-$HOME/.local/share/jobpilot}"

if [ -d "$INSTALL_DIR/.git" ]; then
  info "Existing install found at $INSTALL_DIR — updating…"
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning JobPilot v2 to $INSTALL_DIR…"
  git clone https://github.com/arvindsoni2/jobpilot-v2.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Data directory ─────────────────────────────────────────────────

mkdir -p data
if [ ! -f data/profile.yaml ] && [ -f examples/profile_uk_contractor.yaml ]; then
  info "Creating data/profile.yaml from UK contractor example…"
  cp examples/profile_uk_contractor.yaml data/profile.yaml
  warn "Edit data/profile.yaml with your own details before starting."
fi

# ── .env file ──────────────────────────────────────────────────────

if [ ! -f .env ]; then
  info "Creating .env from template…"
  cat > .env <<'ENVEOF'
# LLM provider — uncomment the one you want to use.
# You can also add/update keys via the Settings → AI Provider tab in the UI.
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AIza...
# For Ollama (local, free) — no key needed. Set llm.provider: ollama in profile.yaml.

# Optional tuning
# SCRAPE_INTERVAL_HOURS=4
# SCORE_THRESHOLD=0.75
# LOG_LEVEL=INFO
ENVEOF
  warn ".env created. Add at least one LLM provider key before starting."
  warn "  OR use Settings → AI Provider in the UI after first start."
fi

# ── Build & start ──────────────────────────────────────────────────

info "Building containers (first run may take 2–3 minutes)…"
$COMPOSE build

info "Starting JobPilot…"
$COMPOSE up -d

# ── Optional: systemd service ──────────────────────────────────────

if command -v systemctl &>/dev/null && [ -f jobpilot.service ]; then
  read -r -p "$(echo -e "${CYAN}[jobpilot]${RESET} Install systemd user service (auto-start on login)? [y/N] ")" INSTALL_SERVICE
  if [[ "$INSTALL_SERVICE" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/systemd/user"
    # Patch WorkingDirectory to the actual install path
    sed "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" jobpilot.service \
      > "$HOME/.config/systemd/user/jobpilot.service"
    systemctl --user daemon-reload
    systemctl --user enable jobpilot.service
    ok "Systemd service installed and enabled."
  fi
fi

# ── Done ───────────────────────────────────────────────────────────

echo ""
ok "JobPilot v2 is running!"
echo ""
echo "  Dashboard:  http://localhost:3000"
echo "  API docs:   http://localhost:8000/docs"
echo ""
warn "If this is your first run, the onboarding wizard will appear automatically."
echo ""
echo "  Manage:  cd $INSTALL_DIR && $COMPOSE ps"
echo "  Logs:    cd $INSTALL_DIR && $COMPOSE logs -f"
echo "  Stop:    cd $INSTALL_DIR && $COMPOSE down"
echo ""
