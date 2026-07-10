---
title: Backend Capability Profile CLI Implementation Plan
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# Backend Capability Profile CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement PR 1 from `docs/Hatch_Backend_Capability_Profile_UX_CLI_Spec_v2.md`: host-side backend capability profile management for easy install and Hatch CLI.

**Architecture:** `scripts/hatch_cli.py` becomes the single source of truth for persisted backend capability config and profile-aware Compose resolution. Linux and Windows installers persist the same config schema before first startup and start with the selected profile. README documents the normal user path; backend API and frontend UX remain out of scope for PR 1.

**Tech Stack:** Python host CLI, Bash installer, PowerShell installer, Docker Compose, pytest/static script tests.

## Global Constraints

- Scope only PR 1: installer, CLI, persisted backend capability profile config, profile-aware Compose resolution, docs, and tests.
- Do not implement backend API or frontend UX in this PR.
- Default backend profile is `core`.
- `advanced` install mode recommends optional/full capabilities but does not force them.
- `install.sh` gets `--backend-profile`.
- `install.ps1` gets `-BackendProfile`.
- `hatch capabilities enable <profile>` recreates backend only by default with profile-aware `docker compose ... up -d --build backend`.
- Add `--restart-all` and `--no-restart`; they are mutually exclusive.
- `start`, `restart`, `update`, `status`, `logs`, and `uninstall` must use the same profile-aware `compose_files()` resolver.
- Missing `backend_capabilities.json` means `core`.
- Existing users must not break.

---

### Task 1: Host CLI Capability Config and Compose Resolver

**Files:**
- Modify: `scripts/hatch_cli.py`
- Modify/Test: `scripts/tests/test_hatch_cli.py`

**Interfaces:**
- Produces: `BACKEND_CAPABILITIES_PATH`, `BackendProfile` constants/dicts, `read_backend_capabilities() -> dict[str, Any]`, `write_backend_capabilities(profile: str, *, updated_by: str) -> None`, `enabled_capabilities_for_profile(profile: str) -> list[str]`, `compose_files(local: bool | None = None, backend_profile: str | None = None) -> list[str]`.
- Consumes: existing `read_json()`, `write_json()`, `RUNTIME_PATH`, and `ROOT`.

- [ ] Write failing tests for missing config defaulting to `core`, valid profile loading, invalid JSON falling back for read-only loads, canonical writes, enabled list derivation, and compose file matrices.
- [ ] Run `pytest -q scripts/tests/test_hatch_cli.py` and verify the new tests fail because the functions/constants are missing or incomplete.
- [ ] Implement profile constants, read/write helpers, canonical validation, enabled-list derivation, and profile-aware compose resolution.
- [ ] Run `pytest -q scripts/tests/test_hatch_cli.py` and verify the new tests pass.

### Task 2: Hatch CLI Commands and Existing Command Integration

**Files:**
- Modify: `scripts/hatch_cli.py`
- Modify/Test: `scripts/tests/test_hatch_cli.py`

**Interfaces:**
- Consumes: Task 1 helpers.
- Produces: `cmd_capabilities_list(args)`, `cmd_capabilities_status(args)`, `cmd_capabilities_enable(args)`, `cmd_capabilities_disable(args)`, parser support for `hatch capabilities ...`.

- [ ] Write failing tests for `capabilities list`, `status`, `enable browser --yes --no-restart`, `enable full --yes --no-restart`, `disable --yes --no-restart`, unknown profile failure, and `--restart-all` plus `--no-restart` parser failure.
- [ ] Write failing tests that `start`, `restart`, `logs`, `uninstall`, and `update` call profile-aware compose args.
- [ ] Run the focused tests and verify they fail for missing commands or old compose behavior.
- [ ] Implement capability command handlers and parser options.
- [ ] Update `cmd_status()` output to include backend capability profile and optional capability statuses.
- [ ] Update `cmd_update()` to validate and restart with profile-aware compose files.
- [ ] Run focused tests and verify they pass.

### Task 3: Installer Profile Selection

**Files:**
- Modify: `install.sh`
- Modify: `install.ps1`
- Modify/Test: `scripts/tests/test_hatch_cli.py`

**Interfaces:**
- Consumes: backend capability schema from Task 1.
- Produces: Linux `--backend-profile` support, Windows `-BackendProfile` support, canonical persisted config, profile-aware first startup.

- [ ] Write failing static/behavior tests that Linux and Windows installers expose backend profile arguments, reject/validate known choices, write `backend_capabilities.json`, default to `core`, and use selected profile on first startup.
- [ ] Run focused tests and verify they fail against current installers.
- [ ] Implement Linux argument parsing, interactive prompt, advanced-mode copy, JSON persistence, and profile-aware Compose file construction for first startup.
- [ ] Implement Windows parameter, validation/canonicalization, interactive prompt, advanced-mode copy, JSON persistence, and profile-aware Compose file construction for first startup.
- [ ] Run focused tests and verify they pass.

### Task 4: README and Script Validation

**Files:**
- Modify: `README.md`
- Possibly Modify: `Makefile`

**Interfaces:**
- Consumes: CLI command names from Task 2 and installer flags from Task 3.
- Produces: user-facing docs for optional backend capabilities and install-time flags.

- [ ] Write or extend static tests ensuring README mentions `hatch capabilities status`, `enable browser`, `enable local-embeddings`, `enable full`, `disable`, and install flags for Linux/Windows.
- [ ] Run tests and verify they fail if docs are missing.
- [ ] Update README easy-install and Docker Services sections to present CLI as the normal path and manual Compose overrides as developer alternatives.
- [ ] Run tests and script syntax checks.

### Task 5: Final Verification and PR

**Files:**
- All changed files.

**Interfaces:**
- Consumes: completed Tasks 1-4.
- Produces: committed branch and PR.

- [ ] Run `pytest -q scripts/tests/test_hatch_cli.py`.
- [ ] Run `bash -n install.sh backend/entrypoint.sh scripts/*.sh scripts/tests/*.sh`.
- [ ] Run `python -m compileall -q scripts backend/app/skills`.
- [ ] Run Compose config validation for `easy`, each backend override, and each backend override combined with `local-ai`.
- [ ] Run `git diff --check`.
- [ ] Commit, push, and open PR for PR 1 only.
