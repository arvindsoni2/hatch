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
# Two small GGUF models are downloaded from HuggingFace (public, no auth):
#   Primary:  Qwen2.5-3B-Instruct-Q4_K_M.gguf  (~721 MB)  port 8080
#   Triage:   Qwen2.5-0.5B-Instruct-Q8_0.gguf  (~507 MB)  port 8081

mkdir -p data/models

PRIMARY_FILE="data/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf"
TRIAGE_FILE="data/models/Qwen2.5-0.5B-Instruct-Q8_0.gguf"

if [ -f "$PRIMARY_FILE" ] && [ -f "$TRIAGE_FILE" ]; then
  ok "AI model files already present — skipping download."
else
  info "Downloading AI model files (one-time, ~1.2 GB total)…"
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
    info "Creating minimal data/profile.yaml…"
    cat > data/profile.yaml <<'PROFILEEOF'
locale: "uk"
candidate:
  name: ""
  title: ""
  years_experience: 0
  summary: ""
search:
  target_roles: []
  locations: []
  contract_type: "any"
compensation:
  min_rate: 0
  max_rate: 0
  rate_type: "daily"
  currency: ""
  legal_preferences: {}
skills:
  primary: []
  secondary: []
  certifications: []
domains:
  preferred: []
  excluded: []
proof_points: []
master_cv_path: "./data/master_cv.json"
job_boards: []
scoring:
  weights:
    skill_match: 0.35
    experience_match: 0.30
    rate_match: 0.20
    location_match: 0.15
  shortlist_threshold: 0.75
llm:
  provider: "llamacpp"
  triage_model: "qwen2.5-0.5b-instruct-q8_0"
  primary_model: "qwen2.5-3b-instruct-q4_k_m"
  base_url: "http://llm-primary:8080/v1"
  triage_base_url: "http://llm-triage:8081/v1"
  api_key_env: ""
  temperature: 0.3
  max_retries: 3
  track_costs: false
  monthly_budget: 0.0
  currency: ""
preferences:
  scrape_interval_hours: 4
  max_tailor_batch: 5
  follow_up_days: [5, 10, 15]
  archive_after_days: 30
PROFILEEOF
  fi

  warn "Edit data/profile.yaml with your details (name, target roles, location) before your first agent run."
fi

# ── .env file ──────────────────────────────────────────────────────

if [ ! -f .env ]; then
  info "Creating .env from template…"
  cat > .env <<'ENVEOF'
# Hatch uses bundled Local AI (llama.cpp) by default — no API key required.
# To use a cloud provider instead, uncomment one of the keys below
# and select the provider during onboarding or in Settings:
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=AIza...

# Optional tuning
# SCRAPE_INTERVAL_HOURS=4
# SCORE_THRESHOLD=0.75
# LOG_LEVEL=INFO
ENVEOF
fi

# ── Build & start ──────────────────────────────────────────────────

info "Building containers (first run may take 2–3 minutes)…"
$COMPOSE build

info "Starting Hatch…"
$COMPOSE up -d

# ── Optional: systemd user service ────────────────────────────────

if command -v systemctl &>/dev/null && [ -f jobpilot.service ]; then
  read -r -p "$(echo -e "${CYAN}[hatch]${RESET} Install systemd user service (auto-start on login)? [y/N] ")" INSTALL_SERVICE
  if [[ "$INSTALL_SERVICE" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/systemd/user"
    sed "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" jobpilot.service \
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
