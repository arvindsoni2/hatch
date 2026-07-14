#!/usr/bin/env bash
# shellcheck disable=SC2034 # This sourced module exports constants and option state.

EXIT_USAGE=2
EXIT_UNSUPPORTED=10
EXIT_PREREQUISITE=11
EXIT_ROOT=12
EXIT_DOCKER_INSTALL=13
EXIT_DOCKER_DAEMON=14
EXIT_DOCKER_PERMISSION=15
EXIT_COMPOSE=16
EXIT_CHECKOUT_OPERATION=17
EXIT_CONFIGURATION=18
EXIT_COMPOSE_START=19
EXIT_HEALTH=20
EXIT_CHECKOUT=21
EXIT_NETWORK=22
EXIT_RESUME=23
EXIT_UNEXPECTED=30

reset_installer_options() {
  MODE=""
  BACKEND_PROFILE=""
  INSTALL_DOCKER=""
  INSTALL_DOCKER_SEEN=false
  NO_INSTALL_DOCKER_SEEN=false
  ALLOW_DOCKER_GROUP=false
  NON_INTERACTIVE=false
  ASSUME_YES=false
  CHECK_ONLY=false
  JSON_MODE=false
  VERBOSE_LOG=false
  RESUME=false
  SHOW_HELP=false
  OPERATION=install
  RESULT_STATUS=success
  EXIT_CODE=0
  ERROR_AREA=""
  ERROR_CODE=""
  ERROR_MESSAGE=""
  ERROR_RETRYABLE=false
  RESULT_EMITTED=false
  ACTIVE_PHASE=""
  LOG_PATH=""
  STATE_PATH=""
  LAST_SAFE_PHASE=""
  CHECKS_JSON='[]'
  PHASES_JSON='[]'
  STARTED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  FINISHED_AT=""
  PLATFORM_OS_ID=""
  PLATFORM_VERSION_ID=""
  PLATFORM_ARCH=""
  PLATFORM_SUPPORTED_AUTO_INSTALL=false
  PREFLIGHT_PREREQUISITE_FAILURES=0
}

installer_usage() {
  cat <<'EOF'
Usage: install.sh [options]
  --mode <ai-later|cloud|local|advanced>
  --backend-profile <core|browser|local-embeddings|full>
  --install-docker | --no-install-docker
  --allow-docker-group
  --non-interactive
  --yes
  --check-only
  --json
  --verbose-log
  --resume
  --help
EOF
}

argument_value() {
  local option=$1 value=${2-}
  if [ -z "$value" ] || [[ "$value" == --* ]]; then
    printf '[hatch] Missing value for %s.\n' "$option" >&2
    return "$EXIT_USAGE"
  fi
  printf '%s' "$value"
}

parse_installer_args() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --mode)
        MODE=$(argument_value "$1" "${2-}") || return "$?"
        shift 2
        ;;
      --backend-profile)
        BACKEND_PROFILE=$(argument_value "$1" "${2-}") || return "$?"
        shift 2
        ;;
      --install-docker) INSTALL_DOCKER=true; INSTALL_DOCKER_SEEN=true; shift ;;
      --no-install-docker) INSTALL_DOCKER=false; NO_INSTALL_DOCKER_SEEN=true; shift ;;
      --allow-docker-group) ALLOW_DOCKER_GROUP=true; shift ;;
      --non-interactive) NON_INTERACTIVE=true; shift ;;
      --yes) ASSUME_YES=true; shift ;;
      --check-only) CHECK_ONLY=true; OPERATION=check_only; shift ;;
      --json) JSON_MODE=true; shift ;;
      --verbose-log) VERBOSE_LOG=true; shift ;;
      --resume) RESUME=true; [ "$CHECK_ONLY" = true ] || OPERATION=resume; shift ;;
      --help) SHOW_HELP=true; shift ;;
      *)
        printf '[hatch] Unknown option: %s\n' "$1" >&2
        return "$EXIT_USAGE"
        ;;
    esac
  done
  if [ "$CHECK_ONLY" = true ]; then
    OPERATION=check_only
  elif [ "$RESUME" = true ]; then
    OPERATION=resume
  fi
}

validate_installer_args() {
  if [ "$CHECK_ONLY" = true ] && [ "$RESUME" = true ]; then
    printf '[hatch] --check-only and --resume are mutually exclusive.\n' >&2
    return "$EXIT_USAGE"
  fi
  if [ "$INSTALL_DOCKER_SEEN" = true ] && [ "$NO_INSTALL_DOCKER_SEEN" = true ]; then
    printf '[hatch] --install-docker and --no-install-docker are mutually exclusive.\n' >&2
    return "$EXIT_USAGE"
  fi
  case "$MODE" in
    ""|ai-later|cloud|local|advanced) ;;
    *) printf '[hatch] Unsupported mode: %s\n' "$MODE" >&2; return "$EXIT_USAGE" ;;
  esac
  case "$BACKEND_PROFILE" in
    ""|core|browser|local-embeddings|full) ;;
    *) printf '[hatch] Unsupported backend profile: %s\n' "$BACKEND_PROFILE" >&2; return "$EXIT_USAGE" ;;
  esac
  if [ "$NON_INTERACTIVE" = true ] && [ "$CHECK_ONLY" != true ] && [ "$RESUME" != true ]; then
    [ -n "$MODE" ] || { printf '[hatch] --mode is required with --non-interactive.\n' >&2; return "$EXIT_USAGE"; }
    [ -n "$BACKEND_PROFILE" ] || { printf '[hatch] --backend-profile is required with --non-interactive.\n' >&2; return "$EXIT_USAGE"; }
    [ "$ASSUME_YES" = true ] || { printf '[hatch] --yes is required with --non-interactive installation.\n' >&2; return "$EXIT_USAGE"; }
  fi
}

redact_installer_log() {
  sed -E \
    -e 's/((API_KEY|TOKEN|PASSWORD|SECRET)[A-Za-z0-9_]*=)[^[:space:]]+/\1[REDACTED]/Ig' \
    -e 's/(Authorization:[[:space:]]*Bearer[[:space:]]+)[^[:space:]]+/\1[REDACTED]/Ig'
}

json_python_available() {
  command -v python3 >/dev/null 2>&1 && python3 -c 'import json' >/dev/null 2>&1
}

json_quote() {
  local value=${1-}
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  value=${value//$'\t'/\\t}
  printf '"%s"' "$value"
}

add_check() {
  local id=$1 category=$2 status=$3 message=$4 remediation=${5-} details=${6-'{}'}
  if json_python_available; then
    CHECKS_JSON=$(python3 - "$CHECKS_JSON" "$id" "$category" "$status" "$message" "$remediation" "$details" <<'PY'
import json, sys
items = json.loads(sys.argv[1])
items.append({
    "id": sys.argv[2], "category": sys.argv[3], "status": sys.argv[4],
    "message": sys.argv[5], "remediation": sys.argv[6] or None,
    "details": json.loads(sys.argv[7]),
})
print(json.dumps(items, separators=(",", ":")))
PY
    )
    return
  fi

  local item prefix remediation_json
  remediation_json=null
  [ -n "$remediation" ] && remediation_json=$(json_quote "$remediation")
  item=$(printf '{"id":%s,"category":%s,"status":%s,"message":%s,"remediation":%s,"details":%s}' \
    "$(json_quote "$id")" "$(json_quote "$category")" "$(json_quote "$status")" \
    "$(json_quote "$message")" "$remediation_json" "$details")
  prefix=${CHECKS_JSON%]}
  [ "$prefix" = "[" ] || prefix="$prefix,"
  CHECKS_JSON="$prefix$item]"
}

set_failure() {
  EXIT_CODE=$1
  ERROR_AREA=$2
  ERROR_CODE=$3
  ERROR_MESSAGE=$4
  ERROR_RETRYABLE=${5:-false}
  RESULT_STATUS=failure
}

emit_result_json() {
  FINISHED_AT=${FINISHED_AT:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}
  if json_python_available; then
    python3 - "$STARTED_AT" "$FINISHED_AT" "$OPERATION" "$RESULT_STATUS" "$EXIT_CODE" \
    "$MODE" "$BACKEND_PROFILE" "$PLATFORM_OS_ID" "$PLATFORM_VERSION_ID" \
    "$PLATFORM_ARCH" "$PLATFORM_SUPPORTED_AUTO_INSTALL" "$CHECKS_JSON" "$PHASES_JSON" \
    "$STATE_PATH" "$LAST_SAFE_PHASE" "$LOG_PATH" "$ERROR_AREA" "$ERROR_CODE" \
    "$ERROR_MESSAGE" "$ERROR_RETRYABLE" <<'PY'
import json, os, sys
(
    started, finished, operation, status, exit_code, mode, profile, os_id,
    version_id, arch, auto_install, checks, phases, state_path,
    last_safe_phase, log_path, error_area, error_code, error_message,
    retryable,
) = sys.argv[1:]
error = None
if error_code:
    error = {
        "area": error_area, "code": error_code, "message": error_message,
        "retryable": retryable == "true",
    }
result = {
    "schema_version": "1.0",
    "installer_version": os.getenv("HATCH_INSTALLER_VERSION", "working-tree"),
    "operation": operation,
    "status": status,
    "exit_code": int(exit_code),
    "started_at": started,
    "finished_at": finished,
    "mode": mode or None,
    "backend_profile": profile or None,
    "platform": {
        "os_id": os_id or None, "version_id": version_id or None,
        "architecture": arch or None,
        "supported_auto_install": auto_install == "true",
    },
    "checks": json.loads(checks),
    "phases": json.loads(phases),
    "resume_state": {
        "available": bool(state_path), "state_path": state_path or None,
        "last_safe_phase": last_safe_phase or None,
    },
    "log_path": log_path or None,
    "error": error,
}
print(json.dumps(result, separators=(",", ":")))
PY
    return
  fi

  local error_json=null state_available=false
  [ -n "$STATE_PATH" ] && state_available=true
  if [ -n "$ERROR_CODE" ]; then
    error_json=$(printf '{"area":%s,"code":%s,"message":%s,"retryable":%s}' \
      "$(json_quote "$ERROR_AREA")" "$(json_quote "$ERROR_CODE")" \
      "$(json_quote "$ERROR_MESSAGE")" "$ERROR_RETRYABLE")
  fi
  printf '{"schema_version":"1.0","installer_version":%s,"operation":%s,"status":%s,"exit_code":%d,"started_at":%s,"finished_at":%s,"mode":%s,"backend_profile":%s,"platform":{"os_id":%s,"version_id":%s,"architecture":%s,"supported_auto_install":%s},"checks":%s,"phases":%s,"resume_state":{"available":%s,"state_path":%s,"last_safe_phase":%s},"log_path":%s,"error":%s}\n' \
    "$(json_quote "${HATCH_INSTALLER_VERSION:-working-tree}")" "$(json_quote "$OPERATION")" \
    "$(json_quote "$RESULT_STATUS")" "$EXIT_CODE" "$(json_quote "$STARTED_AT")" \
    "$(json_quote "$FINISHED_AT")" "$([ -n "$MODE" ] && json_quote "$MODE" || printf null)" \
    "$([ -n "$BACKEND_PROFILE" ] && json_quote "$BACKEND_PROFILE" || printf null)" \
    "$([ -n "$PLATFORM_OS_ID" ] && json_quote "$PLATFORM_OS_ID" || printf null)" \
    "$([ -n "$PLATFORM_VERSION_ID" ] && json_quote "$PLATFORM_VERSION_ID" || printf null)" \
    "$([ -n "$PLATFORM_ARCH" ] && json_quote "$PLATFORM_ARCH" || printf null)" \
    "$PLATFORM_SUPPORTED_AUTO_INSTALL" "$CHECKS_JSON" "$PHASES_JSON" "$state_available" \
    "$([ -n "$STATE_PATH" ] && json_quote "$STATE_PATH" || printf null)" \
    "$([ -n "$LAST_SAFE_PHASE" ] && json_quote "$LAST_SAFE_PHASE" || printf null)" \
    "$([ -n "$LOG_PATH" ] && json_quote "$LOG_PATH" || printf null)" "$error_json"
}

emit_final_result() {
  [ "$RESULT_EMITTED" = false ] || return 0
  RESULT_EMITTED=true
  if [ "$JSON_MODE" = true ]; then
    emit_result_json
  fi
}

reset_installer_options
