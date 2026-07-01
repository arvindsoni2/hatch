#!/usr/bin/env bash
# Idempotent download of the two Qwen3 GGUFs used by llm-primary and llm-triage.
# Source: official Qwen quantizations on Hugging Face (public, no auth required).
# Run once before 'docker compose up'.
# Offline path: manually drop the files into data/models/ and skip this script.
set -euo pipefail

MODELS_DIR="$(realpath -m "${MODELS_DIR:-$(dirname "$0")/../data/models}")"
mkdir -p "$MODELS_DIR"

# ── Pinned sources ────────────────────────────────────────────────────────────
# Official Qwen quantizations — no HF token required.
PRIMARY_URL="https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q5_K_M.gguf"
PRIMARY_FILE="Qwen3-8B-Q5_K_M.gguf"

TRIAGE_URL="https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf"
TRIAGE_FILE="Qwen3-0.6B-Q8_0.gguf"

# ── Helper ────────────────────────────────────────────────────────────────────
download_if_missing() {
  local url="$1" filename="$2"
  local dest="$MODELS_DIR/$filename"
  local tmp="$dest.part"

  if [[ -s "$dest" ]]; then
    echo "[fetch_models] $filename already present — skipping."
    return
  fi

  if [[ -f "$dest" ]]; then
    echo "[fetch_models] $filename exists but is empty — replacing it."
    rm -f "$dest"
  fi

  echo "[fetch_models] Downloading $filename …"
  rm -f "$tmp"
  if command -v wget &>/dev/null; then
    wget -q --show-progress "$url" -O "$tmp"
  else
    curl -L --progress-bar "$url" -o "$tmp"
  fi

  if [[ ! -s "$tmp" ]]; then
    rm -f "$tmp"
    echo "[fetch_models] ERROR: downloaded $filename, but the file is empty." >&2
    return 1
  fi

  mv "$tmp" "$dest"
  echo "[fetch_models] $filename downloaded."
}

# ── Download ──────────────────────────────────────────────────────────────────
download_if_missing "$PRIMARY_URL" "$PRIMARY_FILE"
download_if_missing "$TRIAGE_URL"  "$TRIAGE_FILE"

echo "[fetch_models] Done. Run 'docker compose up -d' to start Hatch."
