#!/usr/bin/env bash
# This script is superseded by scripts/fetch_models.sh (llama.cpp GGUFs).
# See README.md — Hatch now uses bundled llama.cpp containers instead of Ollama.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "[hatch] Redirecting to fetch_models.sh (Ollama is no longer used)…"
exec "$SCRIPT_DIR/fetch_models.sh" "$@"
