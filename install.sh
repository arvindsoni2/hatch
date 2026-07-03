#!/usr/bin/env bash
# Hatch — one-command installer for Linux / macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
# Or locally: ./install.sh
set -euo pipefail

CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}[hatch]${RESET} $*"; }
ok()    { echo -e "${GREEN}[hatch]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[hatch]${RESET} $*"; }
error() { echo -e "${RED}[hatch]${RESET} $*" >&2; exit 1; }

# ── Prerequisites ──────────────────────────────────────────────────

check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    error "$1 is required but not installed. $2"
  fi
  ok "$1 found: $(command -v "$1")"
}

info "Checking prerequisites…"

check_cmd docker "Install from https://docs.docker.com/get-docker/"

if docker compose version &>/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE="docker-compose"
else
  error "docker compose not found. Install Docker Desktop (https://docs.docker.com/get-docker/) or the Compose plugin."
fi
ok "Compose command: $COMPOSE"

check_cmd git "Install git from https://git-scm.com"

# ── Clone or update ────────────────────────────────────────────────

INSTALL_DIR="${HATCH_DIR:-$HOME/.local/share/hatch}"

if [ -d "$INSTALL_DIR/.git" ]; then
  info "Existing install found at $INSTALL_DIR — updating…"
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning Hatch to $INSTALL_DIR…"
  git clone https://github.com/arvindsoni2/hatch.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Download AI model files ────────────────────────────────────────
# Hatch uses bundled llama.cpp containers — no Ollama, no API key required.
# Two official Qwen GGUF models are downloaded from Hugging Face (public, no auth):
#   Primary:  Qwen3-8B-Q5_K_M.gguf (~5.9 GB)  port 8080
#   Triage:   Qwen3-0.6B-Q8_0.gguf (~639 MB)  port 8081

mkdir -p data/models

PRIMARY_FILE="data/models/Qwen3-8B-Q5_K_M.gguf"
TRIAGE_FILE="data/models/Qwen3-0.6B-Q8_0.gguf"

if [ -f "$PRIMARY_FILE" ] && [ -f "$TRIAGE_FILE" ]; then
  ok "AI model files already present — skipping download."
else
  info "Downloading AI model files (one-time, about 6.5 GB total)…"
  warn "This may take a few minutes on a slow connection."
  if bash scripts/fetch_models.sh; then
    ok "Model files downloaded."
  else
    warn "Model download failed — you can retry later with: bash scripts/fetch_models.sh"
    warn "The llm containers will start in degraded mode without models."
  fi
fi

# ── Data directory + profile.yaml ─────────────────────────────────

if [ ! -f data/profile.yaml ]; then
  if [ -f data/profile.yaml.example ]; then
    info "Creating data/profile.yaml from template…"
    cp data/profile.yaml.example data/profile.yaml
  else
    error "data/profile.yaml.example is missing. Re-clone Hatch before installing."
  fi

  warn "Edit data/profile.yaml with your details (name, target roles, location) before your first agent run."
fi

# ── .env file ──────────────────────────────────────────────────────

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    info "Creating .env from current template…"
    cp .env.example .env
  else
    error ".env.example is missing. Re-clone Hatch before installing."
  fi
fi

# ── Build & start ──────────────────────────────────────────────────

info "Building containers (first run may take 2–3 minutes)…"
$COMPOSE build

info "Starting Hatch…"
$COMPOSE up -d

# ── Optional: systemd user service ────────────────────────────────

SERVICE_FILE="infrastructure/systemd/hatch.service"
if command -v systemctl &>/dev/null && [ -f "$SERVICE_FILE" ]; then
  read -r -p "$(echo -e "${CYAN}[hatch]${RESET} Install systemd user service (auto-start on login)? [y/N] ")" INSTALL_SERVICE
  if [[ "$INSTALL_SERVICE" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/systemd/user"
    sed "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" "$SERVICE_FILE" \
      > "$HOME/.config/systemd/user/hatch.service"
    systemctl --user daemon-reload
    systemctl --user enable hatch.service
    ok "Systemd service installed and enabled."
  fi
fi

# ── Done ───────────────────────────────────────────────────────────

echo ""
ok "Hatch is running!"
echo ""
echo "  Dashboard:  http://localhost:3000"
echo "  API docs:   http://localhost:8000/docs"
echo ""
warn "First run? The onboarding wizard will appear automatically at http://localhost:3000"
echo ""
echo "  Manage:  cd $INSTALL_DIR && $COMPOSE ps"
echo "  Logs:    cd $INSTALL_DIR && $COMPOSE logs -f"
echo "  Stop:    cd $INSTALL_DIR && $COMPOSE down"
echo ""
