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

test_noninteractive_resume_loads_selection_from_state() {
  load_modules
  reset_installer_options
  parse_installer_args --resume --non-interactive
  validate_installer_args || fail "non-interactive resume should load selections from state"
  HATCH_HOME=$TEST_TMP/home
  mkdir -p "$HATCH_HOME/config"
  STATE_PATH="$HATCH_HOME/config/install-state.json"
  cat >"$STATE_PATH" <<'JSON'
{"schema_version":1,"last_safe_phase":"wrapper_installed","mode":"cloud","backend_profile":"full","phases":[]}
JSON
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
}

run_test "parse complete non-interactive contract" test_parse_complete_noninteractive_contract
run_test "check-only resume conflict is read-only" test_check_only_resume_is_usage_failure_and_read_only
run_test "non-interactive requires mode and profile" test_noninteractive_requires_mode_and_profile
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
run_test "phase order puts wrapper before probe" test_phase_order_requires_wrapper_before_probe
run_test "non-interactive Local remains pending without download" test_noninteractive_local_integration_is_pending_without_download

printf '1..%d\n' "$PASS_COUNT"
