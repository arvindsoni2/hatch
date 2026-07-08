#!/usr/bin/env bash
# Hatch — one-command installer for Linux / macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
# Or locally: ./install.sh
set -euo pipefail

MODE=""
BACKEND_PROFILE=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) MODE="${2:-}"; shift 2 ;;
    --backend-profile) BACKEND_PROFILE="${2:-}"; shift 2 ;;
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

validate_backend_profile() {
  case "$1" in
    core|browser|local-embeddings|full) ;;
    *) error "Unsupported backend profile '$1'. Use core, browser, local-embeddings, or full." ;;
  esac
}

backend_enabled_json() {
  case "$1" in
    core) printf '[]' ;;
    browser) printf '["browser"]' ;;
    local-embeddings) printf '["local-embeddings"]' ;;
    full) printf '["browser", "local-embeddings", "perception", "advanced-coach"]' ;;
  esac
}

write_backend_capabilities() {
  local profile="$1"
  cat > "$HATCH_HOME/config/backend_capabilities.json" <<EOF
{
  "schema_version": 1,
  "profile": "$profile",
  "enabled": $(backend_enabled_json "$profile"),
  "updated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "updated_by": "install"
}
EOF
  chmod 600 "$HATCH_HOME/config/backend_capabilities.json"
}

compose_files_for_backend_profile() {
  local profile="$1"
  COMPOSE_FILES=(-f docker-compose.easy.yml)
  case "$profile" in
    browser) COMPOSE_FILES+=(-f docker-compose.browser.yml) ;;
    local-embeddings) COMPOSE_FILES+=(-f docker-compose.local-embeddings.yml) ;;
    full) COMPOSE_FILES+=(-f docker-compose.full.yml) ;;
  esac
}

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

if [ -z "$BACKEND_PROFILE" ]; then
  BACKEND_PROFILE="core"
  if [ -t 0 ]; then
    if [ "$MODE" = "advanced" ]; then
      echo ""
      warn "Advanced AI mode can use optional backend capabilities such as browser automation,"
      warn "local embeddings, and perception/advanced coach extras."
      warn "Hatch stays lightweight unless you explicitly enable those packages."
    fi
    echo ""
    echo "Backend capability profile:"
    echo "  [1] Core only - smallest image, recommended"
    echo "  [2] Browser automation - adds Playwright/browser-backed imports"
    echo "  [3] Local embeddings - adds heavier local semantic scoring packages"
    echo "  [4] Full - browser + local embeddings + perception/advanced coach extras"
    printf "Choose backend capability profile [1]: "
    read -r BACKEND_PROFILE_CHOICE
    case "$BACKEND_PROFILE_CHOICE" in
      2) BACKEND_PROFILE="browser" ;;
      3) BACKEND_PROFILE="local-embeddings" ;;
      4) BACKEND_PROFILE="full" ;;
      *) BACKEND_PROFILE="core" ;;
    esac
  fi
fi
validate_backend_profile "$BACKEND_PROFILE"

cat > "$HATCH_HOME/config/install.json" <<EOF
{
  "schema_version": 1,
  "managed": true,
  "source_dir": "$INSTALL_DIR",
  "installed_mode": "$MODE",
  "backend_capability_profile": "$BACKEND_PROFILE"
}
EOF
chmod 600 "$HATCH_HOME/config/install.json"
write_backend_capabilities "$BACKEND_PROFILE"

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
compose_files_for_backend_profile "$BACKEND_PROFILE"
docker compose "${COMPOSE_FILES[@]}" up -d --build

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
