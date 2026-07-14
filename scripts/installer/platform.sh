#!/usr/bin/env bash
# shellcheck disable=SC2034 # This sourced module exports detected platform fields.

map_architecture() {
  case "${1,,}" in
    x86_64|amd64) printf 'x86_64' ;;
    arm64|aarch64) printf 'arm64' ;;
    *) printf 'unsupported' ;;
  esac
}

detect_platform() {
  local os_release=${HATCH_OS_RELEASE_FILE:-/etc/os-release}
  local uname_s uname_m
  uname_s=${HATCH_UNAME_S:-$(uname -s)}
  uname_m=${HATCH_UNAME_M:-$(uname -m)}
  PLATFORM_ARCH=$(map_architecture "$uname_m")
  PLATFORM_OS_ID=""
  PLATFORM_VERSION_ID=""
  PLATFORM_VERSION_CODENAME=""
  PLATFORM_SUPPORTED_AUTO_INSTALL=false

  if [ "$uname_s" = Darwin ]; then
    PLATFORM_OS_ID=macos
    PLATFORM_VERSION_ID=${HATCH_MACOS_VERSION:-$(sw_vers -productVersion 2>/dev/null || true)}
    return 0
  fi
  if [ "$uname_s" != Linux ] || [ ! -r "$os_release" ]; then
    PLATFORM_OS_ID=unsupported
    return 0
  fi

  local ID="" VERSION_ID="" VERSION_CODENAME="" UBUNTU_CODENAME=""
  # shellcheck disable=SC1090
  source "$os_release"
  PLATFORM_OS_ID=${ID,,}
  PLATFORM_VERSION_ID=${VERSION_ID//\"/}
  PLATFORM_VERSION_CODENAME=${UBUNTU_CODENAME:-$VERSION_CODENAME}
  case "$PLATFORM_OS_ID:$PLATFORM_VERSION_ID" in
    ubuntu:22.04|ubuntu:24.04|debian:12|debian:13|fedora:43|fedora:44)
      PLATFORM_SUPPORTED_AUTO_INSTALL=true
      ;;
  esac
}
