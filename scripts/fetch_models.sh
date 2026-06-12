#!/usr/bin/env bash
# Idempotent download of the two Qwen3.5 GGUFs used by llm-primary and llm-triage.
# Run once before 'docker compose up'.
# Offline path: manually drop the files into data/models/ and skip this script.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-$(dirname "$0")/../data/models}"
mkdir -p "$MODELS_DIR"

# ── Pinned sources ────────────────────────────────────────────────────────────
# Prefer official Qwen HuggingFace repos. sha256 verified after download.
PRIMARY_REPO="Qwen/Qwen3.5-4B-Instruct-GGUF"
PRIMARY_FILE="Qwen3.5-4B-Instruct-Q4_K_M.gguf"
PRIMARY_SHA256="PLACEHOLDER_VERIFY_AND_FILL_BEFORE_PROD"

TRIAGE_REPO="Qwen/Qwen3.5-0.8B-GGUF"
TRIAGE_FILE="Qwen3.5-0.8B-Q8_0.gguf"
TRIAGE_SHA256="PLACEHOLDER_VERIFY_AND_FILL_BEFORE_PROD"

# ── Helper ────────────────────────────────────────────────────────────────────
download_if_missing() {
  local repo="$1" filename="$2" sha256="$3"
  local dest="$MODELS_DIR/$filename"

  if [[ -f "$dest" ]]; then
    echo "[fetch_models] $filename already present — skipping."
    return
  fi

  echo "[fetch_models] Downloading $filename from $repo …"
  # huggingface-cli is the preferred tool; fall back to wget
  if command -v huggingface-cli &>/dev/null; then
    huggingface-cli download "$repo" "$filename" --local-dir "$MODELS_DIR"
  else
    wget -q --show-progress \
      "https://huggingface.co/${repo}/resolve/main/${filename}" \
      -O "$dest"
  fi

  # sha256 verification (skip if placeholder not filled)
  if [[ "$sha256" != PLACEHOLDER* ]]; then
    echo "[fetch_models] Verifying sha256 for $filename …"
    echo "${sha256}  ${dest}" | sha256sum --check --quiet
    echo "[fetch_models] $filename verified OK."
  else
    echo "[fetch_models] WARNING: sha256 not pinned for $filename — fill in fetch_models.sh before production use."
  fi
}

# ── Download ──────────────────────────────────────────────────────────────────
download_if_missing "$PRIMARY_REPO" "$PRIMARY_FILE" "$PRIMARY_SHA256"
download_if_missing "$TRIAGE_REPO"  "$TRIAGE_FILE"  "$TRIAGE_SHA256"

echo "[fetch_models] Done. Run 'docker compose up -d' to start Hatch."
echo "[fetch_models] Note: the existing Qwen3-14B-Q4_K_M.gguf (previous family) is superseded"
echo "               by Qwen3.5-9B for 16GB+ machines but is still selectable as a custom model."
