# Release-blocker installer PR 1 implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the managed Linux installer reliable on supported clean machines, deterministic in unattended use, strictly read-only in check-only mode, and safe around Docker privileges and host state.

**Architecture:** Keep `install.sh` as the public orchestrator and move sourceable, side-effect-controlled behavior into focused modules under `scripts/installer/`. Test pure classification and parser behavior directly, then exercise the complete installer through fake host commands and temporary Hatch homes. Preserve the existing developer Compose path; change only the managed easy-install stack and canonical probe reader/writer needed by PR 1.

**Tech stack:** Bash 4+, Python 3, pytest, Docker Compose, existing Hatch host CLI.

## Global constraints

- Implement only PR 1 from `Hatch_Release_Blocker_Installer_Onboarding_AI_Spec_v3.md`.
- Auto-install Docker only on Ubuntu 22.04/24.04, Debian 12/13, and Fedora 43/44.
- Reject whole-installer root invocation with exit `12`.
- Never remove conflicting packages automatically.
- `--yes` never implies Docker-group consent.
- `--check-only` and `--resume` are mutually exclusive; rejection is read-only and JSON uses `operation=check_only`.
- Hardware probe is written to `${HATCH_HOME}/probe/hardware_probe_latest.json` and mounted read-only.
- Browser/backend containers receive no Docker socket.
- Non-interactive Local mode never prompts for or downloads models; healthy Hatch returns warning/0 with model selection action required.
- Preserve current `--mode` and `--backend-profile` compatibility.

---

### Task 1: Shell test harness and argument contract

**Files:**
- Create: `scripts/installer/common.sh`
- Create: `scripts/tests/test_linux_installer.sh`
- Modify: `install.sh`
- Modify: `Makefile`

**Interfaces:**
- Produces: `parse_installer_args "$@"`, `validate_installer_args`, `installer_usage`, `emit_result`, and stable exit-code constants.
- Consumes: environment overrides used only to point detection at controlled fixtures and fake executables.

- [ ] Write failing tests for supported/unknown/missing arguments, mutually exclusive flags, non-interactive requirements, root rejection, and `--check-only --resume` JSON behavior.
- [ ] Run `bash scripts/tests/test_linux_installer.sh`; verify failures identify missing parser behavior.
- [ ] Implement the parser and result fields without performing setup before validation.
- [ ] Run the shell suite and `bash -n install.sh scripts/installer/*.sh` until green.
- [ ] Add the shell suite to `make audit-scripts`.

### Task 2: Platform and consolidated-preflight classification

**Files:**
- Create: `scripts/installer/platform.sh`
- Create: `scripts/installer/preflight.sh`
- Modify: `scripts/tests/test_linux_installer.sh`

**Interfaces:**
- Produces: `detect_platform`, `map_architecture`, `classify_docker_state`, `detect_conflicting_packages`, and a normalized checks collection.
- Consumes: `/etc/os-release` through `HATCH_OS_RELEASE_FILE`, fake `PATH`, and existing installer arguments.

- [ ] Write failing fixture tests for every supported OS/version, Fedora 42, unsupported distributions, `x86_64`/`amd64`/`arm64`/`aarch64`, Docker missing/stopped/permission-denied/healthy, Compose missing, conflicts, ports, disk, Git, Python, and network checks.
- [ ] Verify the tests fail for unimplemented classifiers.
- [ ] Implement read-only detection with no package, service, Docker, repository, directory, or log mutation.
- [ ] Run the shell suite and confirm all fixture cases pass.

### Task 3: Docker repository installation and permission recovery

**Files:**
- Create: `scripts/installer/docker.sh`
- Modify: `scripts/tests/test_linux_installer.sh`

**Interfaces:**
- Produces: `install_docker_engine`, `ensure_docker_daemon`, `configure_docker_access`, and `docker_exec`.
- Consumes: platform fields and consent flags from Tasks 1-2.

- [ ] Write failing tests asserting official apt/dnf repository commands, signed key/repository configuration, package-lock retry classification, no automatic conflict removal, separate group consent, privilege/firewall disclosures, and same-session elevated Docker execution.
- [ ] Verify failures precede implementation.
- [ ] Implement Ubuntu/Debian/Fedora installers using narrowly scoped `sudo`; reject unsupported/manual paths deterministically.
- [ ] Implement daemon start/enable and direct-versus-elevated Docker command abstraction.
- [ ] Run shell tests and syntax checks.

### Task 4: Logging, phases, resume, JSON, and strict check-only

**Files:**
- Create: `scripts/installer/state.sh`
- Modify: `scripts/installer/common.sh`
- Modify: `scripts/tests/test_linux_installer.sh`

**Interfaces:**
- Produces: ordered phase transitions, atomic resume-state writes, sanitized log creation, and schema `1.0` JSON.
- Consumes: normalized checks and stable failures from earlier tasks.

- [ ] Write failing tests for phase order, resume revalidation, invalid state exit `23`, atomic state writes, one-object JSON stdout, stderr diagnostics, nullable early/check-only paths, warning/0 rules, redaction, and no mutation in check-only.
- [ ] Verify the tests fail for absent state/result implementation.
- [ ] Implement log/state handling only after mutating mode is confirmed.
- [ ] Implement one exit funnel so process exit equals JSON `exit_code`.
- [ ] Run shell tests and parse emitted JSON with Python.

### Task 5: Managed install orchestration and non-interactive Local behavior

**Files:**
- Modify: `install.sh`
- Modify: `scripts/tests/test_linux_installer.sh`

**Interfaces:**
- Consumes all installer modules.
- Produces a managed checkout, wrapper, probe, selected easy Compose profile, and verified health.

- [ ] Write failing mocked integration tests for clean install, update, piped `/dev/tty`, dirty checkout rejection, probe-before-Compose phase order, stopped daemon recovery, missing user socket access, profile selection, and non-interactive Local warning without `models install`.
- [ ] Verify failures correspond to missing orchestration.
- [ ] Rewrite orchestration around the locked phase sequence and `docker_exec`.
- [ ] Ensure prompts use `/dev/tty`, unattended mode never prompts, and systemd-user-service prompting obeys non-interactive mode.
- [ ] Run the full mocked integration suite.

### Task 6: Canonical probe path and read-only backend mount

**Files:**
- Modify: `scripts/hatch_cli.py`
- Modify: `scripts/tests/test_hatch_cli.py`
- Modify: `backend/app/services/ai_setup.py`
- Modify: `backend/tests/test_services/test_ai_setup.py`
- Modify: `docker-compose.easy.yml`

**Interfaces:**
- Produces: canonical `${HATCH_HOME}/probe/hardware_probe_latest.json` writer and `/hatch-home/probe` read-only consumer.
- Preserves: temporary config-directory fallback for existing installs.

- [ ] Write failing pytest cases for canonical write/read, legacy fallback, canonical precedence, and no new legacy write.
- [ ] Run targeted tests and verify expected failures.
- [ ] Update host CLI and backend lookup; add `HATCH_PROBE_DIR` and read-only Compose mount.
- [ ] Run targeted pytest and easy/local Compose config checks.

### Task 7: Documentation and release evidence contract

**Files:**
- Modify: `README.md`
- Modify: `docs/getting-started/INSTALLATION.md`
- Modify: `docs/operations/OPERATIONS.md`
- Modify: `docs/operations/RELEASE_CHECKLIST.md`
- Modify: `scripts/tests/test_hatch_cli.py` or docs contract tests as appropriate.

**Interfaces:**
- Documents exact supported platforms, flags, security warnings, probe path, manual macOS/Fedora 42 handling, and pending Local behavior.

- [ ] Add failing documentation-contract assertions for required commands and warnings.
- [ ] Run targeted tests and confirm missing copy fails.
- [ ] Update documentation without changing README installer URLs from `main`.
- [ ] Run `python scripts/check_readme_contract.py` and `python scripts/check_docs.py`.

### Task 8: Final verification and review

**Files:**
- Review all branch changes.

- [ ] Run `bash -n install.sh scripts/installer/*.sh scripts/tests/test_linux_installer.sh`.
- [ ] Run `shellcheck install.sh scripts/installer/*.sh scripts/tests/test_linux_installer.sh` when ShellCheck is available; otherwise record the missing tool.
- [ ] Run `bash scripts/tests/test_linux_installer.sh`.
- [ ] Run targeted Python tests for Hatch CLI and AI setup.
- [ ] Run `make lint`, `make test`, and standalone easy/local Compose validation.
- [ ] Run docs validators and inspect `git diff --check` plus `git status`.
- [ ] Record that Ubuntu 24.04 and Fedora 44 clean-VM evidence remains a merge gate unless suitable VMs are available in this environment.
