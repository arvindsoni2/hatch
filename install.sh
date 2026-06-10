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

check_cmd python3 "Install Python 3.8+ from https://python.org"
check_cmd git     "Install git from https://git-scm.com"

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

# ── Ollama (default LLM — free, local, no API key) ─────────────────

# Two models are used by Hatch:
#   primary (gemma4:e2b) — CV / cover-letter generation, JD analysis
#   triage  (phi3:mini)  — fast job classification, runs in background
# Both are pulled automatically on first install when no models are present.
DEFAULT_PRIMARY_MODEL="gemma4:e2b"
DEFAULT_TRIAGE_MODEL="phi3:mini"

setup_ollama() {
  # 1. Install Ollama if missing
  if ! command -v ollama &>/dev/null; then
    info "Installing Ollama (local LLM — free, no API key needed)…"
    if command -v curl &>/dev/null; then
      curl -fsSL https://ollama.com/install.sh | sh
    else
      error "curl is required to install Ollama. Install it first and re-run."
    fi
  else
    ok "Ollama found: $(command -v ollama)"
  fi

  # 2. Start the Ollama service if it is not already running
  if ! curl -s --max-time 3 http://localhost:11434/api/tags &>/dev/null; then
    info "Starting Ollama…"
    if command -v systemctl &>/dev/null && systemctl list-unit-files ollama.service &>/dev/null 2>&1; then
      systemctl --user start ollama 2>/dev/null || sudo systemctl start ollama 2>/dev/null || true
    else
      # Fallback: background process
      nohup ollama serve > /tmp/ollama.log 2>&1 &
    fi
    # Wait up to 10 s for Ollama to come up
    for i in $(seq 1 10); do
      sleep 1
      curl -s --max-time 1 http://localhost:11434/api/tags &>/dev/null && break
      [ "$i" -eq 10 ] && warn "Ollama did not start within 10 s — you can start it manually with 'ollama serve'."
    done
  fi
  ok "Ollama is running."

  # 3. Configure Ollama to listen on all interfaces so containers can reach it.
  #    Requires sudo — skipped gracefully if not available.
  local needs_config=false
  if command -v systemctl &>/dev/null && systemctl is-active --quiet ollama 2>/dev/null; then
    if ! systemctl show ollama --property=Environment 2>/dev/null | grep -q "OLLAMA_HOST=0.0.0.0"; then
      needs_config=true
    fi
  fi

  if $needs_config; then
    info "Configuring Ollama to listen on all interfaces (needed for container access)…"
    if sudo -n true 2>/dev/null; then
      sudo mkdir -p /etc/systemd/system/ollama.service.d
      printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\n' \
        | sudo tee /etc/systemd/system/ollama.service.d/env.conf > /dev/null
      sudo systemctl daemon-reload
      sudo systemctl restart ollama
      sleep 3
      ok "Ollama configured to listen on all interfaces."
    else
      warn "Cannot configure Ollama network binding without sudo."
      warn "Run these commands once to allow containers to reach Ollama:"
      warn "  sudo mkdir -p /etc/systemd/system/ollama.service.d"
      warn "  echo -e '[Service]\\nEnvironment=\"OLLAMA_HOST=0.0.0.0:11434\"' | sudo tee /etc/systemd/system/ollama.service.d/env.conf"
      warn "  sudo systemctl daemon-reload && sudo systemctl restart ollama"
    fi
  fi

  # 4. Pull default models if none are installed
  local model_count
  model_count=$(curl -s --max-time 3 http://localhost:11434/api/tags \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('models',[])))" 2>/dev/null || echo "0")

  if [ "$model_count" -eq 0 ]; then
    info "No Ollama models found — pulling default models…"
    warn "One-time download of two models (several GB). This may take a few minutes on a slow connection."
    warn "  • ${DEFAULT_PRIMARY_MODEL}  — primary model for CV/CL generation and JD analysis"
    warn "  • ${DEFAULT_TRIAGE_MODEL}   — fast triage model for background job classification"

    info "Pulling ${DEFAULT_PRIMARY_MODEL}…"
    ollama pull "$DEFAULT_PRIMARY_MODEL"
    ok "${DEFAULT_PRIMARY_MODEL} ready."

    info "Pulling ${DEFAULT_TRIAGE_MODEL}…"
    ollama pull "$DEFAULT_TRIAGE_MODEL"
    ok "${DEFAULT_TRIAGE_MODEL} ready."
  else
    # Models already present — report what's there
    local model_list
    model_list=$(curl -s --max-time 3 http://localhost:11434/api/tags \
      | python3 -c "import sys,json; m=json.load(sys.stdin).get('models',[]); print(', '.join(x['name'] for x in m))" 2>/dev/null || echo "unknown")
    ok "Ollama models already available: ${model_list}"

    # Warn if the expected models are missing so the user knows to pull them
    for model in "$DEFAULT_PRIMARY_MODEL" "$DEFAULT_TRIAGE_MODEL"; do
      if ! ollama list 2>/dev/null | grep -qF "$model"; then
        warn "Model '${model}' not found — pull it with: ollama pull ${model}"
      fi
    done
  fi
}

setup_ollama

# ── Data directory + profile.yaml ─────────────────────────────────

mkdir -p data

if [ ! -f data/profile.yaml ]; then
  if [ -f data/profile.yaml.example ]; then
    info "Creating data/profile.yaml from template…"
    cp data/profile.yaml.example data/profile.yaml
  else
    # Minimal bootstrap so containers can start
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
  provider: "ollama"
  triage_model: ""
  primary_model: ""
  base_url: "http://host.docker.internal:11434"
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

  # Inject Ollama model names and correct base_url into profile.yaml
  python3 - <<'PYEOF'
import yaml, pathlib, urllib.request, json, sys

p = pathlib.Path("data/profile.yaml")
d = yaml.safe_load(p.read_text())

# Always point at Ollama for zero-config start
d.setdefault("llm", {})
d["llm"]["provider"] = "ollama"
d["llm"]["base_url"] = "http://host.docker.internal:11434"
d["llm"]["api_key_env"] = ""
d["llm"]["track_costs"] = False
d["llm"]["monthly_budget"] = 0.0

# Preferred models matching the two roles Hatch uses:
#   primary — CV/CL generation and JD analysis (larger, instruction-tuned)
#   triage  — fast background job classification
PREFERRED_PRIMARY = "gemma4:e2b"
PREFERRED_TRIAGE  = "phi3:mini"

try:
    resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
    models = json.loads(resp.read()).get("models", [])
    names = [m["name"] for m in models]

    if names:
        # Use preferred models when available; fall back to the first installed model
        primary = PREFERRED_PRIMARY if PREFERRED_PRIMARY in names else names[0]
        triage  = PREFERRED_TRIAGE  if PREFERRED_TRIAGE  in names else names[0]
        d["llm"]["primary_model"] = primary
        d["llm"]["triage_model"]  = triage
        print(f"[hatch] Profile: primary_model='{primary}', triage_model='{triage}'")
    else:
        print("[hatch] Warning: no Ollama models found — set primary_model/triage_model in data/profile.yaml after pulling one.")
except Exception as e:
    print(f"[hatch] Could not auto-detect Ollama models: {e}")

p.write_text(yaml.dump(d, default_flow_style=False, allow_unicode=True))
PYEOF

  warn "Edit data/profile.yaml with your details (name, target roles, location) before your first agent run."
fi

# ── .env file ──────────────────────────────────────────────────────

if [ ! -f .env ]; then
  info "Creating .env from template…"
  cat > .env <<'ENVEOF'
# LLM provider — Ollama (local, free) is the default and needs no key.
# Uncomment to use a cloud provider instead:
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

if command -v systemctl &>/dev/null && [ -f hatch.service ]; then
  read -r -p "$(echo -e "${CYAN}[hatch]${RESET} Install systemd user service (auto-start on login)? [y/N] ")" INSTALL_SERVICE
  if [[ "$INSTALL_SERVICE" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/systemd/user"
    sed "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" hatch.service \
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
warn "Ollama models available: $(curl -s --max-time 2 http://localhost:11434/api/tags | python3 -c "import sys,json; m=json.load(sys.stdin).get('models',[]); print(', '.join(x['name'] for x in m) if m else 'none')" 2>/dev/null)"
echo ""
echo "  Manage:  cd $INSTALL_DIR && $COMPOSE ps"
echo "  Logs:    cd $INSTALL_DIR && $COMPOSE logs -f"
echo "  Stop:    cd $INSTALL_DIR && $COMPOSE down"
echo ""
