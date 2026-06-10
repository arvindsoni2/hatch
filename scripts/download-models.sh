#!/usr/bin/env bash
# Pull the default Ollama model used by Hatch.
# Run once before 'docker compose up' if Ollama has no models yet.
set -euo pipefail

MODEL="${HATCH_OLLAMA_MODEL:-phi3:mini}"

if ! command -v ollama &>/dev/null; then
  echo "[hatch] ollama not found — install from https://ollama.com/install before running this script."
  exit 1
fi

# Start Ollama if not already running
if ! curl -s --max-time 3 http://localhost:11434/api/tags &>/dev/null; then
  echo "[hatch] Starting Ollama…"
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  sleep 3
fi

# Check if the model is already present
EXISTING=$(curl -s --max-time 3 http://localhost:11434/api/tags \
  | python3 -c "import sys,json; m=json.load(sys.stdin).get('models',[]); print(' '.join(x['name'] for x in m))" 2>/dev/null || echo "")

if echo "$EXISTING" | grep -qF "$MODEL"; then
  echo "[hatch] Model '$MODEL' already present — skipping download."
  exit 0
fi

echo "[hatch] Pulling '$MODEL' via Ollama (~2.3 GB for phi3:mini)…"
echo "[hatch] Set HATCH_OLLAMA_MODEL=<name> to pull a different model."
ollama pull "$MODEL"
echo "[hatch] Done. Run 'docker compose up -d' to start Hatch."
