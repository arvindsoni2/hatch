#!/usr/bin/env bash
# Compatibility wrapper for the selection-driven Hatch model installer.
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "[fetch_models] No models selected. Run 'hatch models list', then:" >&2
  echo "  hatch models install --primary <model-id> --triage <model-id>" >&2
  exit 2
fi

if command -v hatch >/dev/null 2>&1; then
  exec hatch models install "$@"
fi
exec python3 "$(dirname "$0")/hatch_cli.py" models install "$@"
