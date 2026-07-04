#!/usr/bin/env bash
# Hatch — one-command installer for Linux / macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
# Or locally: ./install.sh
set -euo pipefail

MODE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
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
check_cmd python3 "Install Python 3.10 or newer."

# ── Clone or update ────────────────────────────────────────────────

INSTALL_DIR="${HATCH_DIR:-$HOME/.local/share/hatch}"
HATCH_HOME="${HATCH_HOME:-$HOME/.hatch}"
export HATCH_HOME

if [ -d "$INSTALL_DIR/.git" ]; then
  info "Existing install found at $INSTALL_DIR — updating…"
  git -C "$INSTALL_DIR" pull --ff-only
else
  info "Cloning Hatch to $INSTALL_DIR…"
  git clone https://github.com/arvindsoni2/hatch.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Easy-install state + mode ─────────────────────────────────────

mkdir -p "$HATCH_HOME"/{bin,config,models,probe,logs,backups}
chmod 700 "$HATCH_HOME" "$HATCH_HOME"/{bin,config,models,probe,logs,backups}

if [ -z "$MODE" ]; then
  if [ -t 0 ]; then
    printf "AI setup: [1] later (recommended), [2] cloud, [3] local, [4] advanced: "
    read -r MODE_CHOICE
    case "$MODE_CHOICE" in
      2) MODE="cloud" ;;
      3) MODE="local" ;;
      4) MODE="advanced" ;;
      *) MODE="ai-later" ;;
    esac
  else
    MODE="ai-later"
  fi
fi

case "$MODE" in
  ai-later|cloud|local|advanced) ;;
  *) error "Unsupported mode '$MODE'. Use ai-later, cloud, local, or advanced." ;;
esac

cat > "$HATCH_HOME/config/install.json" <<EOF
{
  "schema_version": 1,
  "managed": true,
  "source_dir": "$INSTALL_DIR",
  "installed_mode": "$MODE"
}
EOF
chmod 600 "$HATCH_HOME/config/install.json"

ln -sf "$INSTALL_DIR/hatch" "$HATCH_HOME/bin/hatch"
chmod +x "$INSTALL_DIR/hatch" "$INSTALL_DIR/scripts/hatch_cli.py"

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

info "Building and starting the beginner-safe stack…"
docker compose -f docker-compose.easy.yml up -d --build

if [ "$MODE" = "local" ]; then
  "$HATCH_HOME/bin/hatch" probe
  "$HATCH_HOME/bin/hatch" models install
elif [ "$MODE" = "cloud" ]; then
  info "Choose a provider in Hatch, then run: hatch secrets set <provider>"
fi

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
echo "  Add to PATH: export PATH=\"$HATCH_HOME/bin:\$PATH\""
echo "  Status:  $HATCH_HOME/bin/hatch status"
echo "  Logs:    $HATCH_HOME/bin/hatch logs"
echo "  Stop:    $HATCH_HOME/bin/hatch stop"
echo ""
