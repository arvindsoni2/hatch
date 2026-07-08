#!/usr/bin/env bash
set -euo pipefail

BACKEND_IMAGE="${BACKEND_IMAGE:-hatch-backend:latest}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-hatch-frontend:latest}"

echo "== Hatch image sizes =="
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}' \
  | awk 'NR == 1 || $1 ~ /^hatch-/'

echo
echo "== Running container writable sizes =="
docker ps --size --filter "name=hatch-" \
  --format 'table {{.Names}}\t{{.Image}}\t{{.Size}}\t{{.Status}}'

echo
echo "== Backend image layer history: ${BACKEND_IMAGE} =="
docker history --human "${BACKEND_IMAGE}" || true

echo
echo "== Frontend image layer history: ${FRONTEND_IMAGE} =="
docker history --human "${FRONTEND_IMAGE}" || true
