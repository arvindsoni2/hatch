#!/usr/bin/env bash
# Downloads Qwen3 14B Q4_K_M GGUF into ./models/
# Run once before first podman-compose up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="${SCRIPT_DIR}/../models"
MODEL_FILE="${MODEL_DIR}/Qwen3-14B-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf"

mkdir -p "${MODEL_DIR}"

if [[ -f "${MODEL_FILE}" ]]; then
  echo "Model already present at ${MODEL_FILE} — skipping download."
  exit 0
fi

MODEL_TMP="${MODEL_FILE}.tmp"
trap 'rm -f "${MODEL_TMP}"' EXIT

echo "Downloading Qwen3-14B-Q4_K_M.gguf (~8.5 GB) from HuggingFace…"
echo "URL: ${MODEL_URL}"
curl -L --progress-bar -o "${MODEL_TMP}" "${MODEL_URL}"
mv "${MODEL_TMP}" "${MODEL_FILE}"

echo ""
echo "Done. Run 'podman-compose up' to start all services."
