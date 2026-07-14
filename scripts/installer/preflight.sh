#!/usr/bin/env bash
# shellcheck disable=SC2034 # This sourced module exports consolidated preflight state.

classify_docker_state() {
  local present=$1 info_rc=$2 info_error=${3,,} compose_present=$4
  if [ "$present" != true ]; then
    printf 'missing'
  elif [ "$info_rc" -ne 0 ] && [[ "$info_error" == *permission*denied* || "$info_error" == *docker.sock*permission* ]]; then
    printf 'permission_denied'
  elif [ "$info_rc" -ne 0 ]; then
    printf 'daemon_stopped'
  elif [ "$compose_present" != true ]; then
    printf 'compose_missing'
  else
    printf 'ready'
  fi
}

detect_conflicting_packages() {
  local package
  DETECTED_CONFLICTS=()
  while IFS= read -r package; do
    [ -n "$package" ] || continue
    case "$PLATFORM_OS_ID" in
      ubuntu|debian)
        dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' && DETECTED_CONFLICTS+=("$package")
        ;;
      fedora)
        rpm -q "$package" >/dev/null 2>&1 && DETECTED_CONFLICTS+=("$package")
        ;;
    esac
  done < <(conflicting_package_names "$PLATFORM_OS_ID")
  return 0
}

port_available() {
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}

run_consolidated_preflight() {
  PREFLIGHT_PREREQUISITE_FAILURES=0
  detect_platform
  add_check platform.support platform "$([ "$PLATFORM_SUPPORTED_AUTO_INSTALL" = true ] && printf pass || printf warn)" \
    "$PLATFORM_OS_ID $PLATFORM_VERSION_ID on $PLATFORM_ARCH" \
    "$([ "$PLATFORM_SUPPORTED_AUTO_INSTALL" = true ] && printf '' || printf 'Use a documented manual Docker installation path.')" '{}'

  add_check privilege.effective_user privilege pass \
    "Installer is running as non-root user $(id -un)" "" '{}'

  if command -v sudo >/dev/null 2>&1; then
    add_check privilege.sudo privilege pass "sudo is available" "" '{}'
  else
    add_check privilege.sudo privilege fail "sudo is unavailable" "Install sudo or arrange supported administrator access." '{}'
  fi
  if command -v git >/dev/null 2>&1; then
    add_check prerequisite.git prerequisite pass "Git is available" "" '{}'
  else
    add_check prerequisite.git prerequisite fail "Git is unavailable" "Install Git." '{}'
    PREFLIGHT_PREREQUISITE_FAILURES=$((PREFLIGHT_PREREQUISITE_FAILURES + 1))
  fi
  if json_python_available; then
    local python_version
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    if python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
      add_check prerequisite.python prerequisite pass "Python $python_version is supported" "" '{}'
    else
      add_check prerequisite.python prerequisite fail "Python $python_version is too old" "Install Python 3.10 or newer." '{}'
      PREFLIGHT_PREREQUISITE_FAILURES=$((PREFLIGHT_PREREQUISITE_FAILURES + 1))
    fi
  else
    add_check prerequisite.python prerequisite fail "Python 3 is unavailable or unusable" "Install Python 3.10 or newer." '{}'
    PREFLIGHT_PREREQUISITE_FAILURES=$((PREFLIGHT_PREREQUISITE_FAILURES + 1))
  fi

  local package_manager=""
  case "$PLATFORM_OS_ID" in
    ubuntu|debian) package_manager=apt-get ;;
    fedora) package_manager=dnf ;;
  esac
  if [ -n "$package_manager" ] && command -v "$package_manager" >/dev/null 2>&1; then
    add_check package_manager.ready prerequisite pass "$package_manager is available" "" '{}'
  elif [ -n "$package_manager" ]; then
    add_check package_manager.ready prerequisite fail "$package_manager is unavailable" "Repair the operating-system package manager." '{}'
  else
    add_check package_manager.ready prerequisite skipped "Automatic package management is not supported on this platform" "Install Docker manually." '{}'
  fi

  local repository_url="https://download.docker.com/"
  if curl -fsSI --connect-timeout 5 "$repository_url" >/dev/null 2>&1; then
    add_check network.docker_repository network pass "Docker's package host is reachable" "" '{}'
  else
    add_check network.docker_repository network warn "Docker's package host could not be reached" "Check DNS, proxy, and internet access." '{}'
  fi

  local docker_present=false info_rc=1 info_error="" compose_present=false docker_state
  if command -v docker >/dev/null 2>&1; then
    docker_present=true
    set +e
    info_error=$(docker info 2>&1 >/dev/null)
    info_rc=$?
    set -e
    docker compose version >/dev/null 2>&1 && compose_present=true
  fi
  docker_state=$(classify_docker_state "$docker_present" "$info_rc" "$info_error" "$compose_present")
  DOCKER_STATE=$docker_state
  case "$docker_state" in
    ready) add_check docker.runtime docker pass "Docker Engine and Compose are ready" "" '{}' ;;
    missing) add_check docker.runtime docker action_required "Docker Engine is not installed" "Approve installation or install Docker manually." '{}' ;;
    daemon_stopped) add_check docker.runtime docker action_required "Docker daemon is not running" "Start the Docker service." '{}' ;;
    permission_denied) add_check docker.runtime docker action_required "Current user cannot access Docker" "Approve Docker-group access or use elevated host commands." '{}' ;;
    compose_missing) add_check docker.runtime docker fail "Docker Compose plugin is unavailable" "Install docker-compose-plugin." '{}' ;;
  esac

  if id -nG 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    add_check docker.group docker warn "Current user belongs to the docker group, which grants root-level privileges" "Review Docker daemon security." '{}'
  else
    add_check docker.group docker pass "Current user is not a member of the docker group" "" '{}'
  fi

  local firewall_manager=none
  if command -v ufw >/dev/null 2>&1; then
    firewall_manager=ufw
  elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall_manager=firewalld
  elif command -v nft >/dev/null 2>&1; then
    firewall_manager=nftables
  elif command -v iptables >/dev/null 2>&1; then
    firewall_manager=iptables
  fi
  add_check firewall.manager network warn "Detected firewall manager: $firewall_manager; Docker published ports create host rules" \
    "Review published ports and host firewall policy; Hatch will not change it." '{}'

  if [ "$PLATFORM_OS_ID" = ubuntu ] || [ "$PLATFORM_OS_ID" = debian ] || [ "$PLATFORM_OS_ID" = fedora ]; then
    detect_conflicting_packages
    if [ "${#DETECTED_CONFLICTS[@]}" -gt 0 ]; then
      add_check docker.conflicts docker fail "Conflicting packages: ${DETECTED_CONFLICTS[*]}" "Remove conflicts manually after reviewing Docker's distribution instructions." '{}'
    else
      add_check docker.conflicts docker pass "No conflicting Docker packages detected" "" '{}'
    fi
  fi

  local port
  for port in 3000 8000; do
    if port_available "$port"; then
      add_check "port.$port" network pass "Port $port is available on 127.0.0.1" "" '{}'
    else
      add_check "port.$port" network warn "Port $port is already in use" "Stop the conflicting service or inspect the existing Hatch stack." '{}'
    fi
  done

  local disk_root available_kb
  disk_root=$HOME
  [ -e "${INSTALL_DIR:-}" ] && disk_root=$INSTALL_DIR
  available_kb=$(df -Pk "$disk_root" | awk 'NR==2 {print $4}')
  if [ "${available_kb:-0}" -ge 5242880 ]; then
    add_check storage.free storage pass "At least 5 GB is available for the managed installation" "" '{}'
  else
    add_check storage.free storage warn "Less than 5 GB is available" "Free disk space before building images or downloading models." '{}'
  fi

  if [ -d "${INSTALL_DIR:-}/.git" ]; then
    if [ -n "$(git -C "$INSTALL_DIR" status --porcelain 2>/dev/null)" ]; then
      add_check checkout.state checkout fail "Managed checkout is dirty" "Commit, stash, or remove local changes manually." '{}'
    else
      add_check checkout.state checkout pass "Managed checkout is clean" "" '{}'
    fi
  else
    add_check checkout.state checkout pass "No existing managed checkout was found" "" '{}'
  fi

  local discovered_state="$HATCH_HOME/config/install-state.json"
  if [ -r "$discovered_state" ]; then
    if python3 - "$discovered_state" <<'PY' >/dev/null 2>&1
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert value.get("schema_version") == 1
PY
    then
      STATE_PATH=$(cd "$(dirname "$discovered_state")" && pwd -P)/$(basename "$discovered_state")
      add_check resume.state installer warn "An installer state file is available" "Use --resume to continue after reviewing preflight." '{}'
    else
      add_check resume.state installer fail "Installer state is invalid" "Remove it only after reviewing the interrupted installation." '{}'
    fi
  else
    [ "$CHECK_ONLY" = true ] && STATE_PATH=""
    add_check resume.state installer pass "No incomplete installer state was found" "" '{}'
  fi

  if [ "$docker_present" = true ]; then
    local container_count
    container_count=$(docker ps --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
    add_check docker.containers docker "$([ "$container_count" -gt 0 ] && printf warn || printf pass)" \
      "$container_count running Docker container(s) detected" "Review existing containers for port or project conflicts." '{}'
  else
    add_check docker.containers docker skipped "Docker is unavailable, so containers were not inspected" "" '{}'
  fi
  return 0
}
