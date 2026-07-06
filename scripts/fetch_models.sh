#!/usr/bin/env bash
# Idempotent download of the two Qwen3.5 GGUFs used by llm-primary and llm-triage.
# Source: pinned bartowski quantizations of the official Qwen models.
# Run once before 'docker compose up'.
# Offline path: manually drop the files into data/models/ and skip this script.
set -euo pipefail

MODELS_DIR="$(realpath -m "${MODELS_DIR:-$(dirname "$0")/../data/models}")"
mkdir -p "$MODELS_DIR"

if ! command -v wget &>/dev/null && ! command -v curl &>/dev/null; then
  echo "[fetch_models] ERROR: install curl or wget before downloading models." >&2
  exit 1
fi

# ── Pinned sources ────────────────────────────────────────────────────────────
# Public GGUF quantizations — no HF token required.
PRIMARY_URL="https://huggingface.co/bartowski/Qwen_Qwen3.5-4B-GGUF/resolve/4168f45a16a1290d65a4ec0fa312ae917a4c15d6/Qwen_Qwen3.5-4B-Q4_K_M.gguf"
PRIMARY_FILE="Qwen_Qwen3.5-4B-Q4_K_M.gguf"
PRIMARY_SHA256="13c16f426047e2de38cd075bdade4a7bcbc8c774384876f677740cda65f8a983"

TRIAGE_URL="https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/resolve/f36b1ea49a332ede8fe5f389bbf5b3575ef71f48/Qwen_Qwen3.5-0.8B-Q8_0.gguf"
TRIAGE_FILE="Qwen_Qwen3.5-0.8B-Q8_0.gguf"
TRIAGE_SHA256="7182e2362766bb9569209bbc24cf1a4cdfbb8ab161babdb2080c84fa62c08c2f"

# ── Helper ────────────────────────────────────────────────────────────────────
download_if_missing() {
  local url="$1" filename="$2" expected_sha256="$3"
  local dest="$MODELS_DIR/$filename"
  local tmp="$dest.part"

  if [[ -s "$dest" ]]; then
    if echo "$expected_sha256  $dest" | sha256sum --check --status; then
      echo "[fetch_models] $filename already present and verified — skipping."
      return
    fi
    echo "[fetch_models] $filename has the wrong checksum — replacing it."
    rm -f "$dest"
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
  if ! echo "$expected_sha256  $tmp" | sha256sum --check --status; then
    rm -f "$tmp"
    echo "[fetch_models] ERROR: checksum verification failed for $filename." >&2
    return 1
  fi

  mv "$tmp" "$dest"
  echo "[fetch_models] $filename downloaded and verified."
}

# ── Download ──────────────────────────────────────────────────────────────────
download_if_missing "$PRIMARY_URL" "$PRIMARY_FILE" "$PRIMARY_SHA256"
download_if_missing "$TRIAGE_URL"  "$TRIAGE_FILE" "$TRIAGE_SHA256"

# Remove only the two superseded defaults, and only after both replacements
# have been downloaded and checksum-verified.
rm -f \
  "$MODELS_DIR/Qwen3-8B-Q5_K_M.gguf" \
  "$MODELS_DIR/Qwen3-0.6B-Q8_0.gguf"

echo "[fetch_models] Done. Run 'docker compose up -d' to start Hatch."
