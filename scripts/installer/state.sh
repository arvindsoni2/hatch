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
  temporary=$(mktemp "${destination}.tmp.XXXXXX") || return "$?"
  printf '%s\n' "$content" >"$temporary" || { rm -f "$temporary"; return 1; }
  chmod 600 "$temporary" || { rm -f "$temporary"; return 1; }
  mv -f "$temporary" "$destination" || { rm -f "$temporary"; return 1; }
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
  ) || return "$?"
  if [ "$status" = running ]; then
    ACTIVE_PHASE=$phase
  elif [ "$ACTIVE_PHASE" = "$phase" ]; then
    ACTIVE_PHASE=""
  fi
  if [ "$status" = complete ]; then
    LAST_SAFE_PHASE=$(python3 - "$PHASES_JSON" <<'PY'
import json, sys
last = ""
for item in json.loads(sys.argv[1]):
    if item.get("status") != "complete":
        break
    last = item.get("id", "")
print(last)
PY
    ) || return "$?"
    persist_resume_state || return "$?"
  elif [ "$status" = failed ]; then
    persist_resume_state || return "$?"
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
  ) || return "$?"
  atomic_write_text "$STATE_PATH" "$payload"
}

validate_install_config_artifacts() {
  python3 - "$1" "$2" "$3" "$4" <<'PY'
import json, pathlib, sys
install_dir, hatch_home, mode, profile = sys.argv[1:]
config_dir = pathlib.Path(hatch_home) / "config"
install = json.loads((config_dir / "install.json").read_text())
capabilities = json.loads((config_dir / "backend_capabilities.json").read_text())
assert install.get("schema_version") == 1
assert install.get("managed") is True
assert install.get("source_dir") == install_dir
assert install.get("installed_mode") == mode
assert install.get("backend_capability_profile") == profile
assert capabilities.get("schema_version") == 1
assert capabilities.get("profile") == profile
assert isinstance(capabilities.get("enabled"), list)
PY
}

validate_wrapper_artifact() {
  local expected
  expected="exec python3 \"$1/scripts/hatch_cli.py\" \"\$@\""
  [ -x "$2/bin/hatch" ] && grep -Fqx "$expected" "$2/bin/hatch"
}

load_resume_state() {
  [ -r "$STATE_PATH" ] || return "$EXIT_RESUME"
  local values
  values=$(python3 - "$STATE_PATH" <<'PY'
import json, pathlib, sys
phase_ids = "preflight_complete docker_ready repository_ready host_directories_ready install_config_written wrapper_installed probe_complete compose_started health_verified complete".split()
try:
    value = json.loads(pathlib.Path(sys.argv[1]).read_text())
    assert value.get("schema_version") == 1
    last_safe = value.get("last_safe_phase")
    assert last_safe in phase_ids
    provided = value.get("phases")
    assert isinstance(provided, list)
    by_id = {item.get("id"): item for item in provided if isinstance(item, dict)}
    assert by_id.get(last_safe, {}).get("status") == "complete"
    last_index = phase_ids.index(last_safe)
    assert all(by_id.get(phase_id, {}).get("status") == "complete" for phase_id in phase_ids[:last_index + 1])
    assert not any(by_id.get(phase_id, {}).get("status") == "complete" for phase_id in phase_ids[last_index + 1:])
    phases = []
    for phase_id in phase_ids:
        item = by_id.get(phase_id, {})
        status = item.get("status", "pending")
        assert status in {"pending", "running", "complete", "failed", "skipped"}
        phases.append({
            "id": phase_id,
            "status": "pending" if status == "running" else status,
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
        })
except Exception:
    raise SystemExit(23)
print(value.get("last_safe_phase") or "")
print(value.get("mode") or "")
print(value.get("backend_profile") or "")
print(json.dumps(phases, separators=(",", ":")))
PY
  ) || return "$?"
  LAST_SAFE_PHASE=$(sed -n '1p' <<<"$values")
  [ -n "$MODE" ] || MODE=$(sed -n '2p' <<<"$values")
  [ -n "$BACKEND_PROFILE" ] || BACKEND_PROFILE=$(sed -n '3p' <<<"$values")
  PHASES_JSON=$(sed -n '4p' <<<"$values")
}

phase_was_completed() {
  python3 - "$PHASES_JSON" "$1" <<'PY'
import json, sys
raise SystemExit(0 if any(item.get("id") == sys.argv[2] and item.get("status") == "complete" for item in json.loads(sys.argv[1])) else 1)
PY
}

clear_resume_state() {
  [ -n "$STATE_PATH" ] || return 0
  rm -f "$STATE_PATH" || return "$?"
  STATE_PATH=""
  LAST_SAFE_PHASE=""
}
