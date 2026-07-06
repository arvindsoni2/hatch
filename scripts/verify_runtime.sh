#!/usr/bin/env bash
# Smoke-test the pinned llama.cpp image before committing the tag.
# Usage: ./scripts/verify_runtime.sh [IMAGE_TAG]
# Example: ./scripts/verify_runtime.sh ghcr.io/ggml-org/llama.cpp:server-b5068
set -euo pipefail

IMAGE="${1:-ghcr.io/ggml-org/llama.cpp:server}"
MODELS_DIR="$(dirname "$0")/../data/models"
TRIAGE_MODEL="Qwen_Qwen3.5-0.8B-Q8_0.gguf"

if [[ ! -f "$MODELS_DIR/$TRIAGE_MODEL" ]]; then
  echo "[verify_runtime] $TRIAGE_MODEL not found in $MODELS_DIR."
  echo "  Run scripts/fetch_models.sh first, or drop the file manually."
  exit 1
fi

echo "[verify_runtime] Pulling image: $IMAGE"
docker pull "$IMAGE"

# Print the build number so the caller can pin it
echo "[verify_runtime] Image version:"
docker run --rm "$IMAGE" --version 2>&1 | head -3

echo "[verify_runtime] Starting smoke-test container on :8099 …"
CONTAINER=$(docker run -d --rm \
  -v "$(realpath "$MODELS_DIR"):/models:ro" \
  -p 127.0.0.1:8099:8099 \
  "$IMAGE" \
  --model "/models/$TRIAGE_MODEL" \
  --ctx-size 512 \
  --parallel 1 \
  --host 0.0.0.0 \
  --port 8099)

cleanup() { docker stop "$CONTAINER" 2>/dev/null || true; }
trap cleanup EXIT

echo "[verify_runtime] Waiting for server to start …"
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8099/health &>/dev/null; then
    break
  fi
  sleep 2
done

if ! curl -sf http://127.0.0.1:8099/health &>/dev/null; then
  echo "[verify_runtime] FAIL: server did not start within 60s"
  exit 1
fi

echo "[verify_runtime] Server healthy. Sending test prompt …"
RESPONSE=$(curl -sf http://127.0.0.1:8099/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"Reply with the word OK only."}],"max_tokens":8}')

if echo "$RESPONSE" | grep -qi "content"; then
  echo "[verify_runtime] PASS: model responded."
  echo "Pin this image tag in docker-compose.yml:"
  docker inspect --format='{{index .RepoTags 0}}' "$IMAGE" 2>/dev/null || echo "$IMAGE"
else
  echo "[verify_runtime] FAIL: unexpected response: $RESPONSE"
  exit 1
fi
