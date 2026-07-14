#!/usr/bin/env bash
# shellcheck disable=SC2034,SC1091 # The suite sources modules that export shared state.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=""
PASS_COUNT=0

fail() {
  printf 'not ok - %s\n' "$1" >&2
  exit 1
}

assert_eq() {
  local expected=$1 actual=$2 message=$3
  [ "$expected" = "$actual" ] || fail "$message (expected '$expected', got '$actual')"
}

assert_contains() {
  local haystack=$1 needle=$2 message=$3
  [[ "$haystack" == *"$needle"* ]] || fail "$message (missing '$needle')"
}

assert_file_absent() {
  [ ! -e "$1" ] || fail "$2 (unexpected path '$1')"
}

run_test() {
  local name=$1
  shift
  TEST_TMP=$(mktemp -d)
  if "$@"; then
    PASS_COUNT=$((PASS_COUNT + 1))
    printf 'ok %d - %s\n' "$PASS_COUNT" "$name"
  else
    rm -rf "$TEST_TMP"
    fail "$name"
  fi
  rm -rf "$TEST_TMP"
}

load_modules() {
  # shellcheck source=../installer/common.sh
  source "$ROOT/scripts/installer/common.sh"
  # shellcheck source=../installer/platform.sh
  source "$ROOT/scripts/installer/platform.sh"
  # shellcheck source=../installer/preflight.sh
  source "$ROOT/scripts/installer/preflight.sh"
  # shellcheck source=../installer/docker.sh
  source "$ROOT/scripts/installer/docker.sh"
  # shellcheck source=../installer/state.sh
  source "$ROOT/scripts/installer/state.sh"
}

write_resume_fixture() {
  local path=$1 last_safe=$2 mode=$3 profile=$4
  python - "$path" "$last_safe" "$mode" "$profile" <<'PY'
import json, pathlib, sys
phase_ids = "preflight_complete docker_ready repository_ready host_directories_ready install_config_written wrapper_installed probe_complete compose_started health_verified complete".split()
last_index = phase_ids.index(sys.argv[2])
phases = [
    {"id": phase_id, "status": "complete" if index <= last_index else "pending", "started_at": None, "finished_at": "2026-07-14T08:00:00Z" if index <= last_index else None}
    for index, phase_id in enumerate(phase_ids)
]
pathlib.Path(sys.argv[1]).write_text(json.dumps({"schema_version": 1, "last_safe_phase": sys.argv[2], "mode": sys.argv[3], "backend_profile": sys.argv[4], "phases": phases}))
PY
}

test_parse_complete_noninteractive_contract() {
  load_modules
  reset_installer_options
  parse_installer_args --mode local --backend-profile full --install-docker \
    --allow-docker-group --non-interactive --yes --json
  validate_installer_args
  assert_eq local "$MODE" "mode parsed"
  assert_eq full "$BACKEND_PROFILE" "backend profile parsed"
  assert_eq true "$NON_INTERACTIVE" "non-interactive parsed"
  assert_eq true "$JSON_MODE" "JSON parsed"
}

test_check_only_resume_is_usage_failure_and_read_only() {
  local home=$TEST_TMP/home stdout=$TEST_TMP/stdout stderr=$TEST_TMP/stderr status
  mkdir -p "$home"
  set +e
  HOME="$home" HATCH_HOME="$home/.hatch" EUID_OVERRIDE=1000 \
    bash "$ROOT/install.sh" --check-only --resume --json >"$stdout" 2>"$stderr"
  status=$?
  set -e
  assert_eq 2 "$status" "conflicting operation exit"
  [ -s "$stdout" ] || fail "JSON mode produced empty stdout; stderr: $(<"$stderr")"
  python - "$stdout" <<'PY' || fail "installer stdout is not valid result JSON"
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value["operation"] == "check_only"
assert value["exit_code"] == 2
assert value["log_path"] is None
assert value["resume_state"]["state_path"] is None
PY
  assert_file_absent "$home/.hatch" "check-only conflict must not create Hatch home"
}

test_noninteractive_requires_mode_and_profile() {
  load_modules
  reset_installer_options
  parse_installer_args --non-interactive --no-install-docker
  set +e
  validate_installer_args >/dev/null 2>&1
  local status=$?
  set -e
  assert_eq 2 "$status" "missing mode/profile is usage failure"
}

test_noninteractive_install_requires_yes() {
  load_modules
  reset_installer_options
  parse_installer_args --non-interactive --no-install-docker --mode ai-later --backend-profile core
  set +e
  validate_installer_args >/dev/null 2>&1
  local status=$?
  set -e
  assert_eq 2 "$status" "unattended mutation requires explicit yes"
}

test_noninteractive_resume_loads_selection_from_state() {
  load_modules
  reset_installer_options
  parse_installer_args --resume --non-interactive
  validate_installer_args || fail "non-interactive resume should load selections from state"
  HATCH_HOME=$TEST_TMP/home
  mkdir -p "$HATCH_HOME/config"
  STATE_PATH="$HATCH_HOME/config/install-state.json"
  write_resume_fixture "$STATE_PATH" wrapper_installed cloud full
  load_resume_state
  assert_eq cloud "$MODE" "resume restores mode"
  assert_eq full "$BACKEND_PROFILE" "resume restores profile"
}

test_root_invocation_is_rejected_before_writes() {
  local home=$TEST_TMP/home stdout=$TEST_TMP/stdout stderr=$TEST_TMP/stderr status
  mkdir -p "$home"
  set +e
  HOME="$home" HATCH_HOME="$home/.hatch" EUID_OVERRIDE=0 \
    bash "$ROOT/install.sh" --mode ai-later --backend-profile core --check-only --json >"$stdout" 2>"$stderr"
  status=$?
  set -e
  assert_eq 12 "$status" "root invocation exit"
  python - "$stdout" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value["exit_code"] == 12
assert value["error"]["code"] == "privilege.root_invocation"
assert value["log_path"] is None
PY
  assert_contains "$(<"$stderr")" "normal user" "root remediation"
  assert_file_absent "$home/.hatch" "root failure must not create Hatch home"
}

test_check_only_needs_no_mode_and_creates_nothing() {
  local home=$TEST_TMP/home fakebin=$TEST_TMP/bin os_release=$TEST_TMP/os-release stdout=$TEST_TMP/stdout stderr=$TEST_TMP/stderr status
  mkdir -p "$home" "$fakebin"
  printf 'ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n' >"$os_release"
  cat >"$fakebin/docker" <<'SH'
#!/usr/bin/env bash
case "$*" in
  info|"compose version") exit 0 ;;
  "ps --format "*) exit 0 ;;
  *) exit 0 ;;
esac
SH
  cat >"$fakebin/curl" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  chmod +x "$fakebin"/*
  set +e
  PATH="$fakebin:$PATH" HOME="$home" HATCH_HOME="$home/.hatch" EUID_OVERRIDE=1000 \
    HATCH_OS_RELEASE_FILE="$os_release" HATCH_UNAME_S=Linux HATCH_UNAME_M=x86_64 \
    bash "$ROOT/install.sh" --check-only --json >"$stdout" 2>/dev/null
  status=$?
  set -e
  assert_eq 0 "$status" "healthy check-only exit"
  python - "$stdout" <<'PY' || fail "check-only output is invalid"
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value["operation"] == "check_only"
assert value["mode"] is None
assert value["backend_profile"] is None
assert value["log_path"] is None
PY
  assert_file_absent "$home/.hatch" "check-only must not create Hatch state"
}

test_piped_check_only_loads_modules_without_file_writes() {
  local home=$TEST_TMP/home fakebin=$TEST_TMP/bin os_release=$TEST_TMP/os-release stdout=$TEST_TMP/stdout stderr=$TEST_TMP/stderr status
  mkdir -p "$home" "$fakebin"
  printf 'ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n' >"$os_release"
  cat >"$fakebin/docker" <<'SH'
#!/usr/bin/env bash
exit 0
SH
  cat >"$fakebin/curl" <<'SH'
#!/usr/bin/env bash
if [[ "$*" == *"file://"* ]]; then
  source_path=${*: -1}
  command cat "${source_path#file://}"
  exit 0
fi
exit 0
SH
  chmod +x "$fakebin"/*
  set +e
  cat "$ROOT/install.sh" | PATH="$fakebin:$PATH" HOME="$home" HATCH_HOME="$home/.hatch" EUID_OVERRIDE=1000 \
    HATCH_INSTALLER_LIB_BASE_URL="file://$ROOT/scripts/installer" \
    HATCH_OS_RELEASE_FILE="$os_release" HATCH_UNAME_S=Linux HATCH_UNAME_M=x86_64 \
    bash -s -- --check-only --json >"$stdout" 2>"$stderr"
  status=$?
  set -e
  [ "$status" -eq 0 ] || printf 'piped stderr:\n%s\n' "$(<"$stderr")" >&2
  assert_eq 0 "$status" "piped check-only exit"
  python - "$stdout" <<'PY' || fail "piped check-only output is invalid"
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value["operation"] == "check_only"
assert value["log_path"] is None
PY
  assert_file_absent "$home/.hatch" "piped check-only must not create Hatch state"
}

test_missing_python_still_emits_json_without_writes() {
  local home=$TEST_TMP/home fakebin=$TEST_TMP/bin os_release=$TEST_TMP/os-release stdout=$TEST_TMP/stdout stderr=$TEST_TMP/stderr status
  mkdir -p "$home" "$fakebin"
  printf 'ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n' >"$os_release"
  printf '#!/usr/bin/env bash\nexit 127\n' >"$fakebin/python3"
  printf '#!/usr/bin/env bash\nexit 0\n' >"$fakebin/docker"
  printf '#!/usr/bin/env bash\nexit 0\n' >"$fakebin/curl"
  chmod +x "$fakebin"/*
  set +e
  PATH="$fakebin:$PATH" HOME="$home" HATCH_HOME="$home/.hatch" EUID_OVERRIDE=1000 \
    HATCH_OS_RELEASE_FILE="$os_release" HATCH_UNAME_S=Linux HATCH_UNAME_M=x86_64 \
    bash "$ROOT/install.sh" --check-only --json >"$stdout" 2>"$stderr"
  status=$?
  set -e
  assert_eq 11 "$status" "missing Python prerequisite exit"
  python - "$stdout" <<'PY' || fail "fallback stdout is not valid result JSON"
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value["operation"] == "check_only"
assert value["exit_code"] == 11
assert value["error"]["code"] == "prerequisite.missing"
assert any(item["id"] == "prerequisite.python" and item["status"] == "fail" for item in value["checks"])
assert value["log_path"] is None
PY
  assert_file_absent "$home/.hatch" "missing-Python check-only must not create Hatch state"
}

test_platform_support_matrix() {
  load_modules
  local fixture=$TEST_TMP/os-release
  printf 'ID=fedora\nVERSION_ID="44"\n' >"$fixture"
  HATCH_OS_RELEASE_FILE=$fixture detect_platform
  assert_eq fedora "$PLATFORM_OS_ID" "Fedora detected"
  assert_eq true "$PLATFORM_SUPPORTED_AUTO_INSTALL" "Fedora 44 supported"
  printf 'ID=fedora\nVERSION_ID="42"\n' >"$fixture"
  HATCH_OS_RELEASE_FILE=$fixture detect_platform
  assert_eq false "$PLATFORM_SUPPORTED_AUTO_INSTALL" "Fedora 42 manual"
  printf 'ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n' >"$fixture"
  HATCH_OS_RELEASE_FILE=$fixture detect_platform
  assert_eq true "$PLATFORM_SUPPORTED_AUTO_INSTALL" "Ubuntu 24.04 supported"
}

test_architecture_mapping() {
  load_modules
  assert_eq x86_64 "$(map_architecture amd64)" "amd64 maps to x86_64"
  assert_eq arm64 "$(map_architecture aarch64)" "aarch64 maps to arm64"
  assert_eq unsupported "$(map_architecture riscv64)" "unknown arch rejected"
}

test_docker_state_classification() {
  load_modules
  assert_eq missing "$(classify_docker_state false 1 '' false)" "missing Docker"
  assert_eq daemon_stopped "$(classify_docker_state true 1 'cannot connect to the Docker daemon' true)" "stopped daemon"
  assert_eq permission_denied "$(classify_docker_state true 1 'permission denied /var/run/docker.sock' true)" "socket permission"
  assert_eq compose_missing "$(classify_docker_state true 0 '' false)" "missing Compose"
  assert_eq ready "$(classify_docker_state true 0 '' true)" "ready Docker"
}

test_result_json_schema() {
  load_modules
  reset_installer_options
  JSON_MODE=true
  OPERATION=check_only
  RESULT_STATUS=warning
  EXIT_CODE=0
  MODE=local
  BACKEND_PROFILE=core
  PLATFORM_OS_ID=ubuntu
  PLATFORM_VERSION_ID=24.04
  PLATFORM_ARCH=x86_64
  PLATFORM_SUPPORTED_AUTO_INSTALL=true
  add_check local.model_selection ai action_required "Select local models" "Open onboarding" '{}'
  local result
  result=$(emit_result_json)
  python -c 'import json,sys; v=json.load(sys.stdin); assert v["schema_version"]=="1.0"; assert v["checks"][0]["status"]=="action_required"' <<<"$result"
}

test_docker_repository_and_conflict_contract() {
  load_modules
  assert_eq "https://download.docker.com/linux/ubuntu" "$(docker_repository_url ubuntu)" "Ubuntu official repo"
  assert_eq "https://download.docker.com/linux/debian" "$(docker_repository_url debian)" "Debian official repo"
  assert_eq "https://download.docker.com/linux/fedora/docker-ce.repo" "$(docker_repository_url fedora)" "Fedora official repo"
  assert_contains "$(conflicting_package_names ubuntu)" "podman-docker" "apt conflict list"
  assert_contains "$(conflicting_package_names fedora)" "docker-client" "Fedora conflict list"
  assert_contains "$(docker_security_disclosure)" "root-level privileges" "group warning"
  assert_contains "$(docker_security_disclosure)" "firewall" "firewall warning"
}

test_elevated_docker_preserves_explicit_home_contract() {
  load_modules
  reset_installer_options
  local log=$TEST_TMP/sudo-args
  HATCH_HOME=$TEST_TMP/custom-hatch-home
  HOME=$TEST_TMP/custom-user-home
  DOCKER_USE_SUDO=true
  # shellcheck disable=SC2329 # docker_exec invokes this test double indirectly.
  sudo() { printf '%s\n' "$*" >"$log"; }

  docker_exec compose version

  assert_eq "env HATCH_HOME=$HATCH_HOME HOME=$HOME docker compose version" "$(<"$log")" \
    "elevated Docker receives the installer home paths"
}

test_resume_restores_phases_and_rejects_inconsistent_state() {
  load_modules
  reset_installer_options
  HATCH_HOME=$TEST_TMP/home
  mkdir -p "$HATCH_HOME/config"
  STATE_PATH="$HATCH_HOME/config/install-state.json"
  write_resume_fixture "$STATE_PATH" wrapper_installed cloud core

  load_resume_state

  assert_contains "$PHASES_JSON" '"id":"wrapper_installed"' "resume restores phase data"
  assert_eq true "$(phase_was_completed wrapper_installed && printf true || printf false)" "completed phase is recognized"

  python - "$STATE_PATH" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
value = json.loads(path.read_text())
value["last_safe_phase"] = "probe_complete"
path.write_text(json.dumps(value))
PY
  set +e
  load_resume_state >/dev/null 2>&1
  local status=$?
  set -e
  assert_eq 23 "$status" "last safe phase must agree with completed phases"
}

test_python_310_configuration_contract() {
  assert_contains "$(<"$ROOT/install.sh")" "datetime.timezone.utc" "installer configuration supports Python 3.10"
}

test_atomic_write_failure_propagates() {
  load_modules
  reset_installer_options
  local destination=$TEST_TMP/missing/config.json
  set +e
  atomic_write_text "$destination" '{}' >/dev/null 2>&1
  local status=$?
  set -e
  [ "$status" -ne 0 ] || fail "atomic write unexpectedly succeeded"
  assert_file_absent "$destination" "failed atomic write must not create destination"
}

test_resume_payload_generation_failure_propagates() {
  load_modules
  reset_installer_options
  STATE_PATH=$TEST_TMP/install-state.json
  PHASES_JSON='[]'
  # shellcheck disable=SC2329 # persist_resume_state invokes this test double indirectly.
  python3() { return 42; }
  set +e
  persist_resume_state >/dev/null 2>&1
  local status=$?
  set -e
  unset -f python3
  assert_eq 42 "$status" "resume payload generation failure propagates"
  assert_file_absent "$STATE_PATH" "failed resume payload must not be written"
}

test_docker_group_failure_propagates_without_success_flag() {
  load_modules
  reset_installer_options
  ALLOW_DOCKER_GROUP=true
  # shellcheck disable=SC2329 # configure_docker_access invokes this test double indirectly.
  docker() { return 1; }
  # shellcheck disable=SC2329 # configure_docker_access invokes this test double indirectly.
  run_privileged() {
    [ "$1" = docker ] && return 0
    [ "$1" = usermod ] && return 7
    return 0
  }
  set +e
  configure_docker_access >/dev/null 2>&1
  local status=$?
  set -e
  unset -f docker run_privileged
  assert_eq 7 "$status" "usermod failure propagates"
  assert_eq false "$DOCKER_GROUP_CHANGED" "failed group change is not reported as complete"
}

test_resume_artifacts_validate_content_not_just_presence() {
  load_modules
  reset_installer_options
  INSTALL_DIR=$TEST_TMP/install
  HATCH_HOME=$TEST_TMP/home
  MODE=cloud
  BACKEND_PROFILE=core
  mkdir -p "$INSTALL_DIR/scripts" "$HATCH_HOME/config" "$HATCH_HOME/bin"
  printf '{"schema_version":1,"managed":true,"source_dir":"%s","installed_mode":"cloud","backend_capability_profile":"core"}\n' "$INSTALL_DIR" \
    >"$HATCH_HOME/config/install.json"
  printf '{"schema_version":1,"profile":"core","enabled":[]}\n' >"$HATCH_HOME/config/backend_capabilities.json"
  printf '#!/usr/bin/env bash\nexec python3 "%s/scripts/hatch_cli.py" "$@"\n' "$INSTALL_DIR" >"$HATCH_HOME/bin/hatch"
  chmod 700 "$HATCH_HOME/bin/hatch"

  validate_install_config_artifacts "$INSTALL_DIR" "$HATCH_HOME" "$MODE" "$BACKEND_PROFILE"
  validate_wrapper_artifact "$INSTALL_DIR" "$HATCH_HOME"

  printf '{"schema_version":1,"managed":true,"source_dir":"/stale","installed_mode":"cloud","backend_capability_profile":"core"}\n' \
    >"$HATCH_HOME/config/install.json"
  set +e
  validate_install_config_artifacts "$INSTALL_DIR" "$HATCH_HOME" "$MODE" "$BACKEND_PROFILE" >/dev/null 2>&1
  local status=$?
  set -e
  [ "$status" -ne 0 ] || fail "stale installer config was accepted"

  printf '#!/usr/bin/env bash\nexec python3 "/stale/scripts/hatch_cli.py" "$@"\n' >"$HATCH_HOME/bin/hatch"
  set +e
  validate_wrapper_artifact "$INSTALL_DIR" "$HATCH_HOME" >/dev/null 2>&1
  status=$?
  set -e
  [ "$status" -ne 0 ] || fail "stale wrapper target was accepted"
}

test_log_redaction_contract() {
  load_modules
  local redacted
  redacted=$(printf 'API_KEY=secret-token password=hunter2 Authorization: Bearer abc123\n' | redact_installer_log)
  [[ "$redacted" != *secret-token* ]] || fail "API key was not redacted"
  [[ "$redacted" != *hunter2* ]] || fail "password was not redacted"
  [[ "$redacted" != *abc123* ]] || fail "bearer token was not redacted"
}

test_phase_order_requires_wrapper_before_probe() {
  load_modules
  local phases
  phases=$(installer_phase_order)
  python - "$phases" <<'PY'
import sys
items = sys.argv[1].split()
assert items.index("wrapper_installed") < items.index("probe_complete") < items.index("compose_started")
assert items[-1] == "complete"
PY
}

test_noninteractive_local_integration_is_pending_without_download() {
  local home=$TEST_TMP/home install=$TEST_TMP/install fakebin=$TEST_TMP/bin log=$TEST_TMP/commands os_release=$TEST_TMP/os-release
  mkdir -p "$home" "$install/.git" "$install/scripts" "$install/data" "$fakebin"
  cp "$ROOT/hatch" "$install/hatch"
  cat >"$install/scripts/hatch_cli.py" <<'PY'
#!/usr/bin/env python3
import json, os, pathlib, sys
with open(os.environ["HATCH_FAKE_LOG"], "a", encoding="utf-8") as handle:
    handle.write("hatch " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1:] == ["probe"]:
    target = pathlib.Path(os.environ["HATCH_HOME"]) / "probe" / "hardware_probe_latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"schema_version": 1, "sanitised": True}) + "\n")
PY
  chmod +x "$install/hatch" "$install/scripts/hatch_cli.py"
  printf 'candidate:\n  name: ""\n' >"$install/data/profile.yaml.example"
  printf 'AUTO_APPROVE=false\n' >"$install/.env.example"
  touch "$install/docker-compose.easy.yml" "$install/docker-compose.full.yml"
  mkdir -p "$install/infrastructure/systemd"
  printf '[Service]\nWorkingDirectory=/stale\n' >"$install/infrastructure/systemd/hatch.service"
  printf 'ID=ubuntu\nVERSION_ID="24.04"\nVERSION_CODENAME=noble\n' >"$os_release"
  cat >"$fakebin/git" <<'SH'
#!/usr/bin/env bash
case "$*" in
  *status*--porcelain*) exit 0 ;;
  *) exit 0 ;;
esac
SH
  cat >"$fakebin/docker" <<'SH'
#!/usr/bin/env bash
printf 'docker %s\n' "$*" >>"$HATCH_FAKE_LOG"
case "$*" in
  info|"compose version"|"compose config --quiet"*) exit 0 ;;
  "compose"*"ps"*) printf 'backend running\nfrontend running\n'; exit 0 ;;
  *) exit 0 ;;
esac
SH
  cat >"$fakebin/systemctl" <<'SH'
#!/usr/bin/env bash
printf 'systemctl %s\n' "$*" >>"$HATCH_FAKE_LOG"
exit 0
SH
cat >"$fakebin/curl" <<'SH'
#!/usr/bin/env bash
printf 'curl %s\n' "$*" >>"$HATCH_FAKE_LOG"
exit 0
SH
  chmod +x "$fakebin"/*

  local stdout=$TEST_TMP/stdout stderr=$TEST_TMP/stderr status
  set +e
  PATH="$fakebin:$PATH" HOME="$home" HATCH_HOME="$home/.hatch" HATCH_DIR="$install" \
    HATCH_OS_RELEASE_FILE="$os_release" HATCH_UNAME_S=Linux HATCH_UNAME_M=x86_64 \
    HATCH_FAKE_LOG="$log" EUID_OVERRIDE=1000 \
    bash "$ROOT/install.sh" --non-interactive --yes --no-install-docker \
      --mode local --backend-profile core --json >"$stdout" 2>"$stderr"
  status=$?
  set -e
  if [ "$status" -ne 0 ]; then
    printf 'installer stderr:\n%s\ninstaller stdout:\n%s\n' "$(<"$stderr")" "$(<"$stdout")" >&2
  fi
  assert_eq 0 "$status" "pending Local installation remains usable"
  [ -s "$stdout" ] || fail "JSON mode produced empty stdout; stderr: $(<"$stderr")"
  python - "$stdout" <<'PY' || fail "installer stdout is not valid result JSON"
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value["status"] == "warning"
assert value["exit_code"] == 0
assert any(item["id"] == "local.model_selection" and item["status"] == "action_required" for item in value["checks"])
check_ids = {item["id"] for item in value["checks"]}
required = {
    "platform.support", "privilege.effective_user", "privilege.sudo",
    "package_manager.ready", "network.docker_repository", "prerequisite.git",
    "prerequisite.python", "docker.runtime", "docker.group", "firewall.manager",
    "port.3000", "port.8000", "storage.free", "checkout.state",
    "resume.state", "docker.containers",
}
assert required <= check_ids, required - check_ids
ids = [item["id"] for item in value["phases"] if item["status"] == "complete"]
assert ids.index("wrapper_installed") < ids.index("probe_complete") < ids.index("compose_started")
PY
  assert_contains "$(<"$log")" "hatch probe" "probe runs"
  [[ "$(<"$log")" != *"models install"* ]] || fail "non-interactive Local downloaded models"
  [[ "$(<"$log")" != *"systemctl --user"* ]] || fail "non-interactive install prompted for or enabled systemd"
  assert_file_absent "$home/.hatch/config/install-state.json" "successful install retires resume state"
}

run_test "parse complete non-interactive contract" test_parse_complete_noninteractive_contract
run_test "check-only resume conflict is read-only" test_check_only_resume_is_usage_failure_and_read_only
run_test "non-interactive requires mode and profile" test_noninteractive_requires_mode_and_profile
run_test "non-interactive install requires yes" test_noninteractive_install_requires_yes
run_test "non-interactive resume restores selection" test_noninteractive_resume_loads_selection_from_state
run_test "root invocation is rejected before writes" test_root_invocation_is_rejected_before_writes
run_test "check-only needs no mode and creates nothing" test_check_only_needs_no_mode_and_creates_nothing
run_test "piped check-only loads modules without writes" test_piped_check_only_loads_modules_without_file_writes
run_test "missing Python still returns read-only JSON" test_missing_python_still_emits_json_without_writes
run_test "platform support matrix" test_platform_support_matrix
run_test "architecture mapping" test_architecture_mapping
run_test "Docker state classification" test_docker_state_classification
run_test "JSON result schema" test_result_json_schema
run_test "Docker repository and conflict contract" test_docker_repository_and_conflict_contract
run_test "elevated Docker preserves explicit home" test_elevated_docker_preserves_explicit_home_contract
run_test "resume restores and validates phase data" test_resume_restores_phases_and_rejects_inconsistent_state
run_test "Python 3.10 configuration contract" test_python_310_configuration_contract
run_test "atomic write failures propagate" test_atomic_write_failure_propagates
run_test "resume payload failures propagate" test_resume_payload_generation_failure_propagates
run_test "Docker group failures propagate" test_docker_group_failure_propagates_without_success_flag
run_test "resume artifacts validate content" test_resume_artifacts_validate_content_not_just_presence
run_test "installer logs redact secrets" test_log_redaction_contract
run_test "phase order puts wrapper before probe" test_phase_order_requires_wrapper_before_probe
run_test "non-interactive Local remains pending without download" test_noninteractive_local_integration_is_pending_without_download

printf '1..%d\n' "$PASS_COUNT"
