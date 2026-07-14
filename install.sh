#!/usr/bin/env bash
# Hatch managed installer for Linux and macOS.
# Usage: curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
set -euo pipefail

SCRIPT_SOURCE=${BASH_SOURCE[0]:-}
if [ -n "$SCRIPT_SOURCE" ]; then
  SCRIPT_DIR=$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)
else
  SCRIPT_DIR=""
fi
INSTALLER_LIB_BASE_URL=${HATCH_INSTALLER_LIB_BASE_URL:-https://raw.githubusercontent.com/arvindsoni2/hatch/main/scripts/installer}

load_installer_module() {
  local name=$1 local_path=""
  [ -n "$SCRIPT_DIR" ] && local_path="$SCRIPT_DIR/scripts/installer/$1"
  if [ -n "$local_path" ] && [ -r "$local_path" ]; then
    # shellcheck disable=SC1090
    source "$local_path"
  else
    command -v curl >/dev/null 2>&1 || {
      printf '[hatch] curl is required to load installer module %s.\n' "$name" >&2
      exit 11
    }
    # Process substitution keeps piped check-only execution free of file writes.
    # shellcheck disable=SC1090
    source <(curl -fsSL "$INSTALLER_LIB_BASE_URL/$name")
  fi
}

load_installer_module common.sh
load_installer_module platform.sh
load_installer_module docker.sh
load_installer_module preflight.sh
load_installer_module state.sh

INSTALL_DIR=${HATCH_DIR:-$HOME/.local/share/hatch}
HATCH_HOME=${HATCH_HOME:-$HOME/.hatch}
export HATCH_HOME

say() { printf '[hatch] %s\n' "$*" >&2; }
warn() { printf '[hatch] WARNING: %s\n' "$*" >&2; }

finish_failure() {
  if [ -n "${ACTIVE_PHASE:-}" ] && [ -n "${STATE_PATH:-}" ] && json_python_available; then
    mark_phase "$ACTIVE_PHASE" failed || true
  fi
  set_failure "$1" "$2" "$3" "$4" "${5:-false}"
  emit_final_result
  exit "$1"
}

# shellcheck disable=SC2329 # Invoked indirectly by the EXIT trap.
installer_exit_trap() {
  local status=$?
  local final_status=$status
  trap - EXIT
  if [ "$status" -ne 0 ] && [ "${RESULT_EMITTED:-false}" = false ]; then
    if [ -n "${ACTIVE_PHASE:-}" ] && [ -n "${STATE_PATH:-}" ] && json_python_available; then
      mark_phase "$ACTIVE_PHASE" failed || true
    fi
    if [ -z "${ERROR_CODE:-}" ]; then
      set_failure "$EXIT_UNEXPECTED" installer installer.unexpected_failure \
        "Installer stopped unexpectedly. Review the sanitized log and resume state." true
      final_status=$EXIT_UNEXPECTED
    fi
    emit_final_result || true
  fi
  exit "$final_status"
}

prompt_line() {
  local prompt=$1 answer
  if [ "$NON_INTERACTIVE" = true ] || [ ! -r /dev/tty ] || [ ! -w /dev/tty ]; then
    return "$EXIT_USAGE"
  fi
  printf '%s' "$prompt" >/dev/tty
  IFS= read -r answer </dev/tty
  printf '%s' "$answer"
}

prompt_yes() {
  local prompt=$1 answer
  answer=$(prompt_line "$prompt [y/N] ") || return "$?"
  [[ "$answer" =~ ^[Yy]$ ]]
}

choose_mode() {
  [ -n "$MODE" ] && return 0
  local choice
  choice=$(prompt_line 'Generative AI: [1] configure later, [2] cloud, [3] local, [4] advanced: ') || return "$?"
  case "$choice" in
    2) MODE=cloud ;;
    3) MODE=local ;;
    4) MODE=advanced ;;
    *) MODE=ai-later ;;
  esac
}

choose_backend_profile() {
  [ -n "$BACKEND_PROFILE" ] && return 0
  local choice
  choice=$(prompt_line 'Capabilities: [1] core, [2] browser, [3] local embeddings, [4] full: ') || return "$?"
  case "$choice" in
    2) BACKEND_PROFILE=browser ;;
    3) BACKEND_PROFILE=local-embeddings ;;
    4) BACKEND_PROFILE=full ;;
    *) BACKEND_PROFILE=core ;;
  esac
}

backend_enabled_json() {
  case "$1" in
    core) printf '[]' ;;
    browser) printf '["browser"]' ;;
    local-embeddings) printf '["local-embeddings"]' ;;
    full) printf '["browser","local-embeddings","perception","advanced-coach"]' ;;
  esac
}

compose_files() {
  COMPOSE_FILES=(-f docker-compose.easy.yml)
  case "$BACKEND_PROFILE" in
    browser) COMPOSE_FILES+=(-f docker-compose.browser.yml) ;;
    local-embeddings) COMPOSE_FILES+=(-f docker-compose.local-embeddings.yml) ;;
    full) COMPOSE_FILES+=(-f docker-compose.full.yml) ;;
  esac
}

write_install_config() {
  local install_payload capabilities_payload intent_payload
  install_payload=$(python3 - "$INSTALL_DIR" "$MODE" "$BACKEND_PROFILE" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "managed": True, "source_dir": sys.argv[1], "installed_mode": sys.argv[2], "backend_capability_profile": sys.argv[3]}, indent=2))
PY
  ) || return "$?"
  capabilities_payload=$(python3 - "$BACKEND_PROFILE" "$(backend_enabled_json "$BACKEND_PROFILE")" <<'PY'
import datetime, json, sys
print(json.dumps({"schema_version": 1, "profile": sys.argv[1], "enabled": json.loads(sys.argv[2]), "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "updated_by": "install"}, indent=2))
PY
  ) || return "$?"
  atomic_write_text "$HATCH_HOME/config/install.json" "$install_payload" || return "$?"
  atomic_write_text "$HATCH_HOME/config/backend_capabilities.json" "$capabilities_payload" || return "$?"
  if [ "$MODE" = local ]; then
    intent_payload=$(python3 - "$BACKEND_PROFILE" <<'PY'
import json, sys
print(json.dumps({"schema_version": 1, "ai_mode": "local", "experience": "essential", "backend_profile": sys.argv[1], "selected_model_ids": [], "provider": None, "provider_metadata": {}, "restart_required": True}, indent=2))
PY
    ) || return "$?"
    atomic_write_text "$HATCH_HOME/config/ai_setup_intent.json" "$intent_payload" || return "$?"
  fi
}

install_wrapper() {
  local wrapper
  wrapper=$(cat <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec python3 "$INSTALL_DIR/scripts/hatch_cli.py" "\$@"
EOF
  )
  atomic_write_text "$HATCH_HOME/bin/hatch" "$wrapper" || return "$?"
  chmod 700 "$HATCH_HOME/bin/hatch" || return "$?"
}

prepare_checkout() {
  if [ -d "$INSTALL_DIR/.git" ]; then
    if [ -n "$(git -C "$INSTALL_DIR" status --porcelain)" ]; then
      return "$EXIT_CHECKOUT"
    fi
    git -C "$INSTALL_DIR" pull --ff-only >&2 || return "$EXIT_CHECKOUT_OPERATION"
  else
    git clone https://github.com/arvindsoni2/hatch.git "$INSTALL_DIR" >&2 || return "$EXIT_CHECKOUT_OPERATION"
  fi
}

prepare_host_directories() {
  mkdir -p "$HATCH_HOME"/{bin,config,models,probe,logs,backups} || return "$?"
  chmod 700 "$HATCH_HOME" "$HATCH_HOME"/{bin,config,models,probe,logs,backups} || return "$?"
  if [ ! -f "$INSTALL_DIR/data/profile.yaml" ]; then
    cp "$INSTALL_DIR/data/profile.yaml.example" "$INSTALL_DIR/data/profile.yaml" || return "$?"
  fi
  if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env" || return "$?"
  fi
}

resume_artifact_valid() {
  case "$1" in
    repository_ready)
      [ -d "$INSTALL_DIR/.git" ] && [ -z "$(git -C "$INSTALL_DIR" status --porcelain 2>/dev/null)" ]
      ;;
    host_directories_ready)
      [ -d "$HATCH_HOME/bin" ] && [ -d "$HATCH_HOME/config" ] && [ -d "$HATCH_HOME/probe" ] \
        && [ -f "$INSTALL_DIR/data/profile.yaml" ] && [ -f "$INSTALL_DIR/.env" ]
      ;;
    install_config_written)
      validate_install_config_artifacts "$INSTALL_DIR" "$HATCH_HOME" "$MODE" "$BACKEND_PROFILE"
      ;;
    wrapper_installed) validate_wrapper_artifact "$INSTALL_DIR" "$HATCH_HOME" ;;
    probe_complete)
      python3 - "$HATCH_HOME/probe/hardware_probe_latest.json" <<'PY' >/dev/null 2>&1
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value.get("sanitised") is True
PY
      ;;
    compose_started)
      compose_files
      local services
      services=$(docker_exec compose "${COMPOSE_FILES[@]}" ps --status running --services 2>/dev/null) || return 1
      grep -qx backend <<<"$services" && grep -qx frontend <<<"$services"
      ;;
    *) return 1 ;;
  esac
}

resume_skip_phase() {
  local phase=$1
  [ "$RESUME" = true ] && phase_was_completed "$phase" || return 1
  resume_artifact_valid "$phase" || finish_failure "$EXIT_RESUME" resume resume.inconsistent_artifact \
    "Resume state says $phase completed, but its artifacts are missing or invalid."
  say "Resume validated completed phase: $phase"
  return 0
}

configure_systemd_user_service() {
  local service_file="$INSTALL_DIR/infrastructure/systemd/hatch.service"
  [ "$NON_INTERACTIVE" = false ] || return 0
  command -v systemctl >/dev/null 2>&1 || return 0
  [ -f "$service_file" ] || return 0
  prompt_yes 'Install systemd user service (auto-start on login)?' || return 0
  mkdir -p "$HOME/.config/systemd/user" || return "$?"
  sed "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" "$service_file" \
    >"$HOME/.config/systemd/user/hatch.service" || return "$?"
  systemctl --user daemon-reload || return "$?"
  systemctl --user enable hatch.service || return "$?"
}

health_check() {
  local _attempt
  for _attempt in $(seq 1 "${HATCH_HEALTH_RETRIES:-30}"); do
    if curl -fsS -o /dev/null http://127.0.0.1:8000/api/health \
      && curl -fsS -o /dev/null http://127.0.0.1:3000; then
      return 0
    fi
    sleep "${HATCH_HEALTH_RETRY_DELAY:-2}"
  done
  return "$EXIT_HEALTH"
}

parse_status=0
parse_installer_args "$@" || parse_status=$?
if [ "$parse_status" -ne 0 ]; then
  set_failure "$parse_status" arguments installer.usage "Invalid installer arguments." false
  emit_final_result
  exit "$parse_status"
fi

validate_status=0
validate_installer_args || validate_status=$?
if [ "$validate_status" -ne 0 ]; then
  set_failure "$validate_status" arguments installer.usage "Invalid installer argument combination." false
  emit_final_result
  exit "$validate_status"
fi

trap installer_exit_trap EXIT

if [ "$SHOW_HELP" = true ]; then
  installer_usage
  exit 0
fi

if [ "${EUID_OVERRIDE:-$EUID}" -eq 0 ]; then
  say 'Run the installer as your normal user, without sudo. It requests narrow privileges when required.'
  finish_failure "$EXIT_ROOT" privilege privilege.root_invocation "Whole-installer root invocation is not supported."
fi

if [ "$CHECK_ONLY" = true ]; then
  init_phase_json
  run_consolidated_preflight
  if [ "$PLATFORM_ARCH" = unsupported ]; then
    finish_failure "$EXIT_UNSUPPORTED" platform platform.unsupported_architecture "Unsupported CPU architecture."
  fi
  case "$DOCKER_STATE" in
    ready) ;;
    compose_missing) finish_failure "$EXIT_COMPOSE" docker docker.compose_missing "Docker Compose is unavailable." ;;
    *) finish_failure "$EXIT_PREREQUISITE" docker "docker.$DOCKER_STATE" "Docker requires remediation before installation." ;;
  esac
  if [ "$PREFLIGHT_PREREQUISITE_FAILURES" -gt 0 ]; then
    finish_failure "$EXIT_PREREQUISITE" prerequisite prerequisite.missing "One or more required host prerequisites are unavailable."
  fi
  emit_final_result
  exit 0
fi

if [ "$RESUME" != true ]; then
  choose_mode || finish_failure "$EXIT_USAGE" arguments installer.mode_required "An explicit AI mode is required when no terminal is available."
  choose_backend_profile || finish_failure "$EXIT_USAGE" arguments installer.profile_required "An explicit backend profile is required when no terminal is available."
fi

init_mutating_state
exec 3>&2
exec 2> >(redact_installer_log | tee -a "$LOG_PATH" >&3)
[ "$VERBOSE_LOG" = true ] && set -x
say "Installer operation: $OPERATION; mode: $MODE; backend profile: $BACKEND_PROFILE"

if [ "$RESUME" = true ]; then
  load_resume_state || finish_failure "$EXIT_RESUME" resume resume.invalid_state "Installer resume state is missing or invalid."
  [ -n "$MODE" ] && [ -n "$BACKEND_PROFILE" ] \
    || finish_failure "$EXIT_RESUME" resume resume.incomplete_state "Resume state does not contain the required mode and backend profile."
fi

mark_phase preflight_complete running
run_consolidated_preflight
if [ "$PLATFORM_ARCH" = unsupported ]; then
  mark_phase preflight_complete failed
  finish_failure "$EXIT_UNSUPPORTED" platform platform.unsupported_architecture "Unsupported CPU architecture."
fi
mark_phase preflight_complete complete

if [ "$PREFLIGHT_PREREQUISITE_FAILURES" -gt 0 ]; then
  finish_failure "$EXIT_PREREQUISITE" prerequisite prerequisite.missing "One or more required host prerequisites are unavailable."
fi

if [ "${#DETECTED_CONFLICTS[@]}" -gt 0 ] && [ "$DOCKER_STATE" != ready ]; then
  finish_failure "$EXIT_PREREQUISITE" docker docker.conflicting_packages \
    "Conflicting packages must be reviewed and removed manually: ${DETECTED_CONFLICTS[*]}"
fi

mark_phase docker_ready running
if [ "$DOCKER_STATE" = missing ]; then
  if [ "$PLATFORM_SUPPORTED_AUTO_INSTALL" != true ]; then
    finish_failure "$EXIT_PREREQUISITE" docker docker.manual_install_required "Install Docker manually on this platform, then rerun Hatch."
  fi
  if [ "$NON_INTERACTIVE" = true ] && [ -z "$INSTALL_DOCKER" ]; then
    finish_failure "$EXIT_PREREQUISITE" docker docker.install_choice_required "Use --install-docker or --no-install-docker."
  fi
  if [ "$INSTALL_DOCKER" = false ]; then
    finish_failure "$EXIT_PREREQUISITE" docker docker.install_forbidden "Docker is absent and installation was forbidden."
  fi
  if [ "$INSTALL_DOCKER" != true ]; then
    printf '%s\n' "$(docker_security_disclosure)" >&2
    prompt_yes 'Install Docker Engine from Docker official packages?' || finish_failure "$EXIT_PREREQUISITE" docker docker.install_declined "Docker installation was not approved."
  else
    printf '%s\n' "$(docker_security_disclosure)" >&2
  fi
  install_docker_engine || finish_failure "$EXIT_DOCKER_INSTALL" docker docker.install_failed "Docker package installation failed." true
fi

ensure_docker_daemon || finish_failure "$EXIT_DOCKER_DAEMON" docker docker.daemon_unavailable "Docker daemon is unavailable." true
if ! docker info >/dev/null 2>&1 && [ "$NON_INTERACTIVE" != true ] && [ "$ALLOW_DOCKER_GROUP" != true ]; then
  printf '%s\n' "$(docker_security_disclosure)" >&2
  prompt_yes 'Add your user to the docker group?' && ALLOW_DOCKER_GROUP=true
fi
configure_docker_access || finish_failure "$EXIT_DOCKER_PERMISSION" docker docker.permission_failed "Docker access could not be established." true
docker_exec compose version >/dev/null || finish_failure "$EXIT_COMPOSE" docker docker.compose_missing "Docker Compose is unavailable."
mark_phase docker_ready complete

if ! resume_skip_phase repository_ready; then
  mark_phase repository_ready running
  prepare_checkout || {
    status=$?
    if [ "$status" -eq "$EXIT_CHECKOUT" ]; then
      finish_failure "$EXIT_CHECKOUT" checkout checkout.dirty "Managed checkout has uncommitted changes."
    else
      finish_failure "$EXIT_CHECKOUT_OPERATION" checkout checkout.update_failed "Repository clone or update failed." true
    fi
  }
  mark_phase repository_ready complete
fi
cd "$INSTALL_DIR"

if ! resume_skip_phase host_directories_ready; then
  mark_phase host_directories_ready running
  prepare_host_directories || finish_failure "$EXIT_CONFIGURATION" configuration configuration.host_directories "Could not prepare Hatch files."
  mark_phase host_directories_ready complete
fi

if ! resume_skip_phase install_config_written; then
  mark_phase install_config_written running
  write_install_config || finish_failure "$EXIT_CONFIGURATION" configuration configuration.write_failed "Could not write installer configuration."
  mark_phase install_config_written complete
fi

if ! resume_skip_phase wrapper_installed; then
  mark_phase wrapper_installed running
  install_wrapper || finish_failure "$EXIT_CONFIGURATION" configuration wrapper.install_failed "Could not install the Hatch wrapper."
  mark_phase wrapper_installed complete
fi

if ! resume_skip_phase probe_complete; then
  mark_phase probe_complete running
  "$HATCH_HOME/bin/hatch" probe >&2 || finish_failure "$EXIT_CONFIGURATION" probe probe.failed "Hardware probe failed." true
  mark_phase probe_complete complete
fi

compose_files
if ! resume_skip_phase compose_started; then
  mark_phase compose_started running
  docker_exec compose "${COMPOSE_FILES[@]}" config --quiet >&2 \
    || finish_failure "$EXIT_COMPOSE_START" compose compose.invalid "Selected Compose profile is invalid."
  docker_exec compose "${COMPOSE_FILES[@]}" up -d --build >&2 \
    || finish_failure "$EXIT_COMPOSE_START" compose compose.start_failed "Hatch containers failed to start." true
  mark_phase compose_started complete
fi

if [ "$MODE" = local ]; then
  RESULT_STATUS=warning
  add_check local.model_selection ai action_required "Select local model IDs before Local AI can become ready." \
    "Continue in onboarding or Settings, or run hatch models install with explicit catalog IDs." '{}'
fi
if [ "$MODE" = cloud ]; then
  RESULT_STATUS=warning
  add_check cloud.secret ai action_required "Configure the provider secret on the host." "Run hatch secrets set <provider>." '{}'
fi

mark_phase health_verified running
health_check || {
  docker_exec compose "${COMPOSE_FILES[@]}" logs --tail 50 >&2 || true
  finish_failure "$EXIT_HEALTH" health health.verification_failed "Backend or frontend health verification failed." true
}
mark_phase health_verified complete
configure_systemd_user_service \
  || finish_failure "$EXIT_CONFIGURATION" configuration systemd.user_service_failed "Could not configure the systemd user service."
mark_phase complete running
mark_phase complete complete
clear_resume_state || finish_failure "$EXIT_CONFIGURATION" configuration resume.cleanup_failed "Could not retire completed installer state."

if [ "$DOCKER_GROUP_CHANGED" = true ]; then
  warn 'Docker-group membership grants root-level privileges. Sign out and back in, then run: docker info'
fi
if [ "$RESULT_STATUS" = success ]; then
  say 'Hatch is running at http://localhost:3000'
else
  say 'Hatch is running; one or more setup actions remain.'
fi
emit_final_result
exit 0
