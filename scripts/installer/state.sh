#!/usr/bin/env bash

installer_phase_order() {
  printf '%s\n' preflight_complete docker_ready repository_ready host_directories_ready \
    install_config_written wrapper_installed probe_complete compose_started health_verified complete
}

init_phase_json() {
  if ! json_python_available; then
    PHASES_JSON='[{"id":"preflight_complete","status":"pending","started_at":null,"finished_at":null},{"id":"docker_ready","status":"pending","started_at":null,"finished_at":null},{"id":"repository_ready","status":"pending","started_at":null,"finished_at":null},{"id":"host_directories_ready","status":"pending","started_at":null,"finished_at":null},{"id":"install_config_written","status":"pending","started_at":null,"finished_at":null},{"id":"wrapper_installed","status":"pending","started_at":null,"finished_at":null},{"id":"probe_complete","status":"pending","started_at":null,"finished_at":null},{"id":"compose_started","status":"pending","started_at":null,"finished_at":null},{"id":"health_verified","status":"pending","started_at":null,"finished_at":null},{"id":"complete","status":"pending","started_at":null,"finished_at":null}]'
    return
  fi
  PHASES_JSON=$(python3 - <<'PY'
import json
ids = "preflight_complete docker_ready repository_ready host_directories_ready install_config_written wrapper_installed probe_complete compose_started health_verified complete".split()
print(json.dumps([{"id": item, "status": "pending", "started_at": None, "finished_at": None} for item in ids], separators=(",", ":")))
PY
  )
}

atomic_write_text() {
  local destination=$1 content=$2 temporary
  temporary=$(mktemp "${destination}.tmp.XXXXXX")
  printf '%s\n' "$content" >"$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$destination"
}

init_mutating_state() {
  local timestamp
  timestamp=$(date -u +"%Y%m%dT%H%M%SZ")
  mkdir -p "$HATCH_HOME/config" "$HATCH_HOME/logs"
  chmod 700 "$HATCH_HOME" "$HATCH_HOME/config" "$HATCH_HOME/logs"
  LOG_PATH="$HATCH_HOME/logs/install-$timestamp.log"
  STATE_PATH="$HATCH_HOME/config/install-state.json"
  : >"$LOG_PATH"
  chmod 600 "$LOG_PATH"
  init_phase_json
}

mark_phase() {
  local phase=$1 status=$2 now
  now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  PHASES_JSON=$(python3 - "$PHASES_JSON" "$phase" "$status" "$now" <<'PY'
import json, sys
items = json.loads(sys.argv[1])
for item in items:
    if item["id"] == sys.argv[2]:
        item["status"] = sys.argv[3]
        if sys.argv[3] == "running": item["started_at"] = sys.argv[4]
        if sys.argv[3] in {"complete", "failed", "skipped"}: item["finished_at"] = sys.argv[4]
print(json.dumps(items, separators=(",", ":")))
PY
  )
  if [ "$status" = complete ]; then
    LAST_SAFE_PHASE=$phase
    persist_resume_state
  fi
}

persist_resume_state() {
  [ -n "$STATE_PATH" ] || return 0
  local payload
  payload=$(python3 - "$LAST_SAFE_PHASE" "$MODE" "$BACKEND_PROFILE" "$PHASES_JSON" <<'PY'
import json, sys
print(json.dumps({
    "schema_version": 1,
    "last_safe_phase": sys.argv[1] or None,
    "mode": sys.argv[2] or None,
    "backend_profile": sys.argv[3] or None,
    "phases": json.loads(sys.argv[4]),
}, indent=2))
PY
  )
  atomic_write_text "$STATE_PATH" "$payload"
}

load_resume_state() {
  [ -r "$STATE_PATH" ] || return "$EXIT_RESUME"
  local values
  values=$(python3 - "$STATE_PATH" <<'PY'
import json, pathlib, sys
try:
    value = json.loads(pathlib.Path(sys.argv[1]).read_text())
    assert value.get("schema_version") == 1
    assert value.get("last_safe_phase") in "preflight_complete docker_ready repository_ready host_directories_ready install_config_written wrapper_installed probe_complete compose_started health_verified complete".split()
except Exception:
    raise SystemExit(23)
print(value.get("last_safe_phase") or "")
print(value.get("mode") or "")
print(value.get("backend_profile") or "")
PY
  ) || return "$?"
  LAST_SAFE_PHASE=$(sed -n '1p' <<<"$values")
  [ -n "$MODE" ] || MODE=$(sed -n '2p' <<<"$values")
  [ -n "$BACKEND_PROFILE" ] || BACKEND_PROFILE=$(sed -n '3p' <<<"$values")
}
