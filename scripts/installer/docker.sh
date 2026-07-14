#!/usr/bin/env bash
# shellcheck disable=SC2034 # This sourced module exports Docker execution state.

DOCKER_USE_SUDO=false
DOCKER_GROUP_CHANGED=false

docker_repository_url() {
  case "$1" in
    ubuntu|debian) printf 'https://download.docker.com/linux/%s' "$1" ;;
    fedora) printf 'https://download.docker.com/linux/fedora/docker-ce.repo' ;;
    *) return "$EXIT_UNSUPPORTED" ;;
  esac
}

conflicting_package_names() {
  case "$1" in
    ubuntu|debian)
      printf '%s\n' docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc
      ;;
    fedora)
      printf '%s\n' docker docker-client docker-client-latest docker-common docker-latest \
        docker-latest-logrotate docker-logrotate docker-selinux docker-engine-selinux docker-engine podman-docker containerd runc
      ;;
  esac
}

docker_security_disclosure() {
  cat <<'EOF'
Docker installation adds Docker's official signing key and package repository, installs Engine, CLI, containerd, Buildx, and Compose, and enables the daemon when systemd is available.
Docker creates networking and firewall rules for bridge networks and published ports. Published traffic may bypass normal ufw filtering, and firewalld uses a Docker zone. Hatch will not weaken or rewrite firewall policy.
Membership in the docker group grants root-level privileges on this machine. Group membership requires separate consent.
Conflicting packages are never removed automatically.
EOF
}

run_privileged() {
  sudo "$@"
}

retry_package_command() {
  local attempt=1 max_attempts=${HATCH_PACKAGE_RETRIES:-6}
  while ! run_privileged "$@"; do
    if [ "$attempt" -ge "$max_attempts" ]; then
      return 1
    fi
    printf '[hatch] Package manager is busy; retrying (%d/%d).\n' "$attempt" "$max_attempts" >&2
    sleep "${HATCH_PACKAGE_RETRY_DELAY:-5}"
    attempt=$((attempt + 1))
  done
}

install_docker_engine() {
  case "$PLATFORM_OS_ID" in
    ubuntu|debian)
      local repo
      repo=$(docker_repository_url "$PLATFORM_OS_ID")
      retry_package_command apt-get update
      retry_package_command apt-get install -y ca-certificates curl
      run_privileged install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "$repo/gpg" | run_privileged tee /etc/apt/keyrings/docker.asc >/dev/null
      run_privileged chmod a+r /etc/apt/keyrings/docker.asc
      printf 'Types: deb\nURIs: %s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
        "$repo" "$PLATFORM_VERSION_CODENAME" "$(dpkg --print-architecture)" \
        | run_privileged tee /etc/apt/sources.list.d/docker.sources >/dev/null
      retry_package_command apt-get update
      retry_package_command apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    fedora)
      retry_package_command dnf -y install dnf-plugins-core
      run_privileged dnf config-manager addrepo --from-repofile "$(docker_repository_url fedora)"
      retry_package_command dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
      ;;
    *) return "$EXIT_UNSUPPORTED" ;;
  esac
}

ensure_docker_daemon() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl --version >/dev/null 2>&1; then
    run_privileged systemctl enable --now docker
  fi
  run_privileged docker info >/dev/null 2>&1
}

configure_docker_access() {
  if docker info >/dev/null 2>&1; then
    DOCKER_USE_SUDO=false
    return 0
  fi
  if ! run_privileged docker info >/dev/null 2>&1; then
    return "$EXIT_DOCKER_DAEMON"
  fi
  DOCKER_USE_SUDO=true
  if [ "$ALLOW_DOCKER_GROUP" = true ]; then
    printf '%s\n' "$(docker_security_disclosure)" >&2
    run_privileged usermod -aG docker "$(id -un)"
    DOCKER_GROUP_CHANGED=true
  else
    RESULT_STATUS=warning
    printf '[hatch] Docker requires elevated host commands. To enable direct use later, review Docker privileges and run: sudo usermod -aG docker %s\n' "$(id -un)" >&2
  fi
}

docker_exec() {
  if [ "$DOCKER_USE_SUDO" = true ]; then
    run_privileged docker "$@"
  else
    docker "$@"
  fi
}
