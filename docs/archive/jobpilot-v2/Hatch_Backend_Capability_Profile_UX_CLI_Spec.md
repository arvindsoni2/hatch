---
title: Hatch Backend Capability Profile UX and CLI Spec
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

# Hatch Backend Capability Profile UX and CLI Spec

**Project:** Hatch  
**Repository:** <https://github.com/arvindsoni2/hatch>  
**Spec type:** Follow-up PR after backend container-size optimisation  
**Primary audience:** Codex implementation agent  
**Status:** Ready for Codex review and implementation  
**Date:** 2026-07-08

---

## 1. Problem statement

The previous backend container optimisation correctly reduced the default backend by moving heavy optional packages out of the core image. However, this introduced a user-journey risk:

- A fresh `install.sh` install still only asks the user for AI mode: `ai-later`, `cloud`, `local`, or `advanced`.
- The easy install path still starts the lightweight backend path by default.
- Optional backend capability images now exist, but normal users do not have a clear install-time or post-install path to enable them.
- Users may not know whether browser automation, local embeddings, perception, or coach-related advanced capabilities are available.
- `hatch start`, `hatch restart`, `hatch update`, and `hatch status` must preserve and display the selected capability profile.

This creates a mismatch between the product experience and the optimised container architecture. The user sees Hatch features, but may not know whether the required backend packages are installed or how to enable them.

---

## 2. Goal

Add a **Backend Capability Profile Management** layer that keeps Hatch lightweight by default while making optional backend packages discoverable, installable, persistent, and visible.

The desired result:

```text
Fresh install remains simple and lightweight.
Users can explicitly enable heavier backend capabilities when needed.
Hatch CLI preserves the selected backend capability profile across start/restart/update.
Frontend/settings/onboarding can show capability availability and exact enable commands.
Backend never fails silently when an optional capability is missing.
```

---

## 3. Non-goals

Do **not** implement browser-triggered Docker rebuilds from the web UI in this PR.

Do **not** merge all optional packages back into the default backend image.

Do **not** change the existing AI runtime decision model except where needed to display compatibility and status.

Do **not** force full capability mode for all users who choose local AI. Local AI runtime and backend Python package profile must remain separate concepts.

Do **not** remove the existing manual Docker Compose override files. This PR should make them first-class through the host CLI.

---

## 4. Core product distinction

Hatch now needs to treat these as separate concepts:

| Concept | Meaning | Examples |
|---|---|---|
| AI mode | How intelligence is provided | `ai-later`, `cloud`, `local`, `advanced` |
| Backend capability profile | Which optional Python/backend packages are installed | `core`, `browser`, `local-embeddings`, `full` |

AI mode controls LLM routing and model/runtime setup.

Backend capability profile controls optional backend dependencies such as Playwright/browser automation, local embedding packages, perception packages, and advanced coach support.

The CLI and UI should display both.

Example status output:

```text
Hatch status
Services: available
AI mode: local
Backend capability profile: local-embeddings
Local models: 2 ready
Capabilities:
  Coach interview prep: available
  Browser automation: not installed
  Local embeddings: available
  Perception/advanced coach: not installed
```

---

## 5. Current repo state to account for

Codex should verify exact current filenames before editing. At the time of this spec:

- `install.sh` parses `--mode` and persists AI mode under `$HATCH_HOME/config/install.json`.
- `install.sh` currently asks only for AI setup in interactive mode.
- `scripts/hatch_cli.py` has a `compose_files()` function that includes `docker-compose.easy.yml` and conditionally `docker-compose.local-ai.yml` for local LLM runtime.
- `scripts/hatch_cli.py` has no `capabilities` command group.
- `hatch status` currently shows services, AI mode, and local model count only.
- `hatch update` validates `docker-compose.easy.yml` directly instead of validating the profile-aware compose file set.
- Optional backend Compose override files exist after the container-size optimisation, including browser/local-embeddings/full variants.

Codex must preserve backwards compatibility for users who already have only `install.json` and `ai_runtime.json`.

---

## 6. Capability profiles

Implement the following profiles.

| Profile | Purpose | Expected backend target/image | Compose files |
|---|---|---|---|
| `core` | Default lightweight backend | core backend | `docker-compose.easy.yml` |
| `browser` | Enables browser automation / Playwright-backed import | browser backend | `docker-compose.easy.yml` + `docker-compose.browser.yml` |
| `local-embeddings` | Enables heavier local semantic scoring / embedding packages | local embeddings backend | `docker-compose.easy.yml` + `docker-compose.local-embeddings.yml` |
| `full` | Enables browser + local embeddings + perception/advanced coach packages | full backend | `docker-compose.easy.yml` + `docker-compose.full.yml` |

Important: local LLM runtime remains independent and should still add `docker-compose.local-ai.yml` when AI runtime is local.

Example:

| AI mode | Backend profile | Compose result |
|---|---|---|
| `cloud` | `core` | easy only |
| `local` | `core` | easy + local-ai |
| `local` | `local-embeddings` | easy + local-embeddings + local-ai |
| `advanced` | `full` | easy + full + local-ai when local models are selected |

---

## 7. Host-side persisted config

Add a new persisted config file:

```text
$HATCH_HOME/config/backend_capabilities.json
```

Recommended schema:

```json
{
  "schema_version": 1,
  "profile": "core",
  "enabled": [],
  "updated_at": "2026-07-08T00:00:00Z",
  "updated_by": "hatch_cli"
}
```

Profile-specific examples:

```json
{
  "schema_version": 1,
  "profile": "browser",
  "enabled": ["browser"],
  "updated_at": "2026-07-08T00:00:00Z",
  "updated_by": "hatch_cli"
}
```

```json
{
  "schema_version": 1,
  "profile": "full",
  "enabled": ["browser", "local-embeddings", "perception", "advanced-coach"],
  "updated_at": "2026-07-08T00:00:00Z",
  "updated_by": "hatch_cli"
}
```

Rules:

- Missing file means `core`.
- Invalid JSON should warn and fall back to `core`, not crash normal status/start commands.
- Persist with existing atomic JSON writer if available.
- File permissions should match other config files: parent directory `0700`, file `0600`.
- The file must contain no secrets.

---

## 8. CLI changes

Add a new command group:

```bash
hatch capabilities list
hatch capabilities status
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
hatch capabilities disable
```

### 8.1 `hatch capabilities list`

Shows available backend profiles and what each enables.

Example:

```text
Backend capability profiles:
  core              Smallest backend image. Recommended for most users.
  browser           Adds Playwright/browser automation for supported imports.
  local-embeddings  Adds local semantic embedding packages.
  full              Adds browser, local embeddings, perception, and advanced coach packages.
```

### 8.2 `hatch capabilities status`

Shows selected profile, enabled capabilities, missing capabilities, and whether restart is recommended.

Example:

```text
Backend capability profile: core
Enabled backend packages: none
Available features:
  Coach interview prep: available when AI mode is cloud/local with a capable model
  Browser automation: not installed
  Local embeddings: not installed
  Perception/advanced coach: not installed
Enable browser automation: hatch capabilities enable browser
Enable all optional packages: hatch capabilities enable full
```

### 8.3 `hatch capabilities enable <profile>`

Supported values:

```text
browser
local-embeddings
full
```

Behaviour:

1. Validate profile.
2. Explain that this may rebuild/pull a larger backend image.
3. Prompt for confirmation unless `--yes` is provided.
4. Persist `backend_capabilities.json`.
5. Run `docker compose config --quiet` using the selected profile-aware compose files.
6. Restart backend stack by default, or print restart instruction if `--no-restart` is provided.

Suggested options:

```bash
hatch capabilities enable browser --yes
hatch capabilities enable local-embeddings --yes --no-restart
hatch capabilities enable full --yes
```

Example output:

```text
Backend capability profile set to: browser
This enables: browser automation
Rebuilding backend with selected capability profile...
Done. Run hatch status to confirm.
```

### 8.4 `hatch capabilities disable`

Returns profile to `core`.

Behaviour:

1. Prompt unless `--yes` is provided.
2. Persist core profile.
3. Restart by default, or print restart instruction if `--no-restart` is provided.
4. Preserve AI runtime config and downloaded local models.

Example:

```bash
hatch capabilities disable --yes
```

### 8.5 Parser integration

Update `scripts/hatch_cli.py` parser to add:

```text
capabilities
  list
  status
  enable <profile> [--yes] [--no-restart]
  disable [--yes] [--no-restart]
```

Use the same command style as existing `models`, `secrets`, and `update` commands.

---

## 9. Compose resolution changes

Update `compose_files()` so it becomes the single source of truth for all Docker Compose operations.

Required behaviour:

```python
compose_files(local: bool | None = None, backend_profile: str | None = None) -> list[str]
```

Pseudo-logic:

```python
files = ["-f", str(ROOT / "docker-compose.easy.yml")]

profile = backend_profile or read_backend_profile()

if profile == "browser":
    files += ["-f", str(ROOT / "docker-compose.browser.yml")]
elif profile == "local-embeddings":
    files += ["-f", str(ROOT / "docker-compose.local-embeddings.yml")]
elif profile == "full":
    files += ["-f", str(ROOT / "docker-compose.full.yml")]
elif profile == "core":
    pass
else:
    warn and fall back to core

if local_ai_runtime_is_enabled:
    files += ["-f", str(ROOT / "docker-compose.local-ai.yml")]
    add local-primary/local-triage profiles as today
```

Every command must use this function:

- `hatch start`
- `hatch stop`
- `hatch restart`
- `hatch logs`
- `hatch status`
- `hatch update`
- `hatch uninstall`
- `hatch apply-ai-config --restart`
- new `hatch capabilities enable/disable`

Do not hard-code `docker-compose.easy.yml` in `cmd_update()` after this PR. `cmd_update()` should validate:

```bash
docker compose <profile-aware compose files> config --quiet
```

---

## 10. Environment variables for backend/runtime visibility

The selected backend capability profile should be visible to the backend container.

Add environment variables through Compose or CLI environment injection:

```text
HATCH_BACKEND_CAPABILITY_PROFILE=core|browser|local-embeddings|full
HATCH_BACKEND_CAPABILITIES=browser,local-embeddings,perception,advanced-coach
```

For `core`:

```text
HATCH_BACKEND_CAPABILITY_PROFILE=core
HATCH_BACKEND_CAPABILITIES=
```

For `full`:

```text
HATCH_BACKEND_CAPABILITY_PROFILE=full
HATCH_BACKEND_CAPABILITIES=browser,local-embeddings,perception,advanced-coach
```

Implementation options:

- Preferred: have `hatch_cli.py` inject the env variables when running Docker Compose.
- Acceptable: define these env vars in the corresponding Compose override files.

If both exist, CLI-injected values should match the selected persisted profile.

---

## 11. Install script UX changes

Update `install.sh` to support backend capability selection.

### 11.1 New optional argument

Add:

```bash
./install.sh --mode local --backend-profile local-embeddings
./install.sh --mode advanced --backend-profile full
```

Supported values:

```text
core
browser
local-embeddings
full
```

Default value:

```text
core
```

### 11.2 Interactive install flow

After AI setup selection, ask backend capability profile only when interactive.

Recommended prompt:

```text
Backend capabilities:
[1] core - smallest backend image, recommended
[2] browser - adds Playwright/browser automation
[3] local embeddings - adds heavier local semantic scoring packages
[4] full - browser + local embeddings + perception/advanced coach packages
Choose backend capability profile [1]:
```

Default remains `core`.

For `advanced` mode, use a stronger hint:

```text
Advanced mode works best with the full backend capability profile.
Enable full backend capabilities now? [y/N]
```

Decision:

- Do not silently force `full`.
- Recommend `full` for `advanced` mode.
- Keep default lightweight unless user opts in.

### 11.3 Persist during install

`install.sh` should write both:

```text
$HATCH_HOME/config/install.json
$HATCH_HOME/config/backend_capabilities.json
```

`install.json` may optionally include the selected backend profile for human readability, but the source of truth must be `backend_capabilities.json`.

Example `install.json` addition:

```json
{
  "mode": "local",
  "backend_capability_profile": "local-embeddings"
}
```

### 11.4 Start selected profile

After writing the selected profile, install should start Hatch using the profile-aware CLI path.

Preferred:

```bash
"$HATCH_HOME/bin/hatch" start
```

rather than manually constructing `docker compose -f ... up -d --build` inside `install.sh`.

If this is too risky for the current installer, duplicate the profile compose mapping carefully and add tests to prevent drift.

---

## 12. Backend API: system capabilities endpoint

Add an endpoint so frontend/onboarding/settings can display capability availability without guessing.

Recommended endpoint:

```text
GET /api/system/capabilities
```

If the existing API route style uses a different prefix, follow the current backend convention.

Response shape:

```json
{
  "schema_version": 1,
  "backend_profile": "core",
  "enabled_backend_capabilities": [],
  "ai_mode": "local",
  "features": {
    "coach_interview_prep": {
      "available": true,
      "status": "available",
      "reason": null,
      "requires": ["ai_runtime"],
      "enable_command": null
    },
    "browser_automation": {
      "available": false,
      "status": "not_installed",
      "reason": "Browser automation packages are not installed in the active backend profile.",
      "requires": ["browser"],
      "enable_command": "hatch capabilities enable browser"
    },
    "local_embeddings": {
      "available": false,
      "status": "not_installed",
      "reason": "Local embedding packages are not installed in the active backend profile.",
      "requires": ["local-embeddings"],
      "enable_command": "hatch capabilities enable local-embeddings"
    },
    "perception_advanced_coach": {
      "available": false,
      "status": "not_installed",
      "reason": "Perception and advanced coach packages require the full backend profile.",
      "requires": ["full"],
      "enable_command": "hatch capabilities enable full"
    }
  }
}
```

### 12.1 Capability detection rules

Do not import heavy libraries in the capability endpoint.

Use one of:

1. Environment variables from the selected profile.
2. `importlib.util.find_spec()` for optional packages if needed.
3. Existing runtime config for AI mode and feature gates.

The endpoint must be cheap, fast, and safe.

### 12.2 Coach capability nuance

Do not mark all Coach features unavailable just because the backend profile is `core`.

Separate basic and advanced coach capability:

| Feature | Required condition |
|---|---|
| Basic coach interview prep | AI runtime has a capable cloud/local/custom model and feature gate is enabled |
| Advanced coach with perception/audio/video/document analysis | `full` backend profile, plus AI runtime where relevant |
| Local semantic coach enhancements | `local-embeddings` or `full` backend profile |

This avoids confusing users who can use basic coach with cloud/local LLM even on the core backend.

---

## 13. Frontend UX changes

Add lightweight capability awareness to onboarding/settings and any affected feature screens.

### 13.1 Onboarding / first-run

Show a short capability summary after AI setup:

```text
Backend capability profile: core
This keeps Hatch small and fast to install.
Optional features such as browser automation and local embeddings can be enabled later with:
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
```

For advanced mode:

```text
You selected advanced AI setup.
Some advanced features require the full backend capability profile.
Run: hatch capabilities enable full
```

### 13.2 Settings screen

Add a read-only backend capabilities panel:

```text
Backend capabilities
Profile: core
Browser automation: not installed
Local embeddings: not installed
Advanced coach/perception: not installed

Enable from terminal:
hatch capabilities enable full
```

Do not add a browser button that directly rebuilds Docker images in this PR.

### 13.3 Feature-specific guardrails

For features that require optional packages, show actionable messages instead of generic errors.

Examples:

```text
Browser automation is not installed in your current Hatch backend profile.
Run this command in your terminal:
hatch capabilities enable browser
```

```text
Local embeddings are not installed.
Run:
hatch capabilities enable local-embeddings
```

```text
Advanced coach capabilities require the full backend profile.
Run:
hatch capabilities enable full
```

---

## 14. Documentation updates

Update README and install docs to explain:

1. Default install is intentionally lightweight.
2. AI mode and backend capability profile are different choices.
3. Optional features can be enabled through `hatch capabilities`.
4. `advanced` mode may benefit from `full` backend capabilities.
5. How to disable optional packages and return to core.

Add a compact table:

| Need | Command |
|---|---|
| Keep smallest install | `hatch capabilities disable` |
| Enable browser automation | `hatch capabilities enable browser` |
| Enable local semantic scoring | `hatch capabilities enable local-embeddings` |
| Enable all optional backend packages | `hatch capabilities enable full` |
| Check current profile | `hatch capabilities status` |

Also update any existing manual Compose instructions to say they are advanced/manual alternatives and that the normal path is now the CLI.

---

## 15. Tests

Add tests at the level already used in the repo. If there are no direct tests for installer/CLI, add focused Python tests for pure functions and a smoke script for shell-level behaviour.

### 15.1 Unit tests for profile config

Test:

- missing config returns `core`
- invalid JSON returns `core` with warning/non-fatal behaviour
- valid config returns expected profile
- writing profile creates expected schema
- unsupported profile is rejected

### 15.2 Unit tests for compose resolution

Test matrix:

| AI runtime local? | Backend profile | Expected compose files |
|---|---|---|
| false | core | easy |
| false | browser | easy + browser |
| false | local-embeddings | easy + local-embeddings |
| false | full | easy + full |
| true | core | easy + local-ai |
| true | browser | easy + browser + local-ai |
| true | local-embeddings | easy + local-embeddings + local-ai |
| true | full | easy + full + local-ai |

Also test that local model profiles `local-primary` and `local-triage` remain unchanged.

### 15.3 CLI smoke tests

Add or update a script such as:

```text
scripts/smoke-capabilities.sh
```

Suggested checks:

```bash
hatch capabilities list
hatch capabilities status
hatch capabilities enable browser --yes --no-restart
hatch capabilities status
hatch capabilities enable local-embeddings --yes --no-restart
hatch capabilities status
hatch capabilities enable full --yes --no-restart
hatch capabilities status
hatch capabilities disable --yes --no-restart
hatch capabilities status
```

The smoke test should not require pulling/building large images if it uses `--no-restart`.

### 15.4 Compose config tests

At minimum, run:

```bash
docker compose -f docker-compose.easy.yml config --quiet
docker compose -f docker-compose.easy.yml -f docker-compose.browser.yml config --quiet
docker compose -f docker-compose.easy.yml -f docker-compose.local-embeddings.yml config --quiet
docker compose -f docker-compose.easy.yml -f docker-compose.full.yml config --quiet
docker compose -f docker-compose.easy.yml -f docker-compose.local-ai.yml config --quiet
```

Also validate combined cases:

```bash
docker compose -f docker-compose.easy.yml -f docker-compose.browser.yml -f docker-compose.local-ai.yml config --quiet
docker compose -f docker-compose.easy.yml -f docker-compose.local-embeddings.yml -f docker-compose.local-ai.yml config --quiet
docker compose -f docker-compose.easy.yml -f docker-compose.full.yml -f docker-compose.local-ai.yml config --quiet
```

### 15.5 Backend API tests

Add tests for `GET /api/system/capabilities`:

- core profile returns browser/local-embeddings/full-dependent features as not installed
- browser profile enables browser automation
- local-embeddings profile enables local embeddings
- full profile enables browser, local embeddings, perception/advanced coach
- coach basic availability follows AI runtime feature gate, not only backend profile
- endpoint does not import heavy modules

### 15.6 Frontend tests

If frontend tests exist, add a small test for capability messaging. Otherwise, ensure manual QA covers:

- onboarding shows current backend profile
- settings shows current backend profile
- missing browser/local-embedding/full feature shows terminal command
- no UI button directly triggers Docker rebuild

---

## 16. Migration and backward compatibility

Existing users may not have `backend_capabilities.json`.

Required behaviour:

- Treat missing file as `core`.
- Do not modify AI runtime config when enabling/disabling backend capabilities.
- Do not delete downloaded models when disabling optional backend packages.
- Existing `hatch start`, `hatch restart`, `hatch update`, and `hatch status` should continue working.
- Existing manual Compose override usage should not break.

Optional migration:

When any `hatch capabilities` command runs, create `backend_capabilities.json` if missing.

Do not create noisy migration prompts during `hatch status`.

---

## 17. Security and safety constraints

- Browser UI must not execute host commands or Docker rebuilds.
- Backend capability config contains no secrets.
- Do not expose filesystem paths unnecessarily through API responses.
- Capability endpoint should only expose high-level status and enable commands.
- Do not import heavyweight optional packages during health/status calls.
- Do not allow arbitrary compose file names or profile names from user input.
- Validate profile values against a fixed allow-list.
- Preserve current host-side secrets handling.

---

## 18. Implementation phases

### Phase 1: CLI profile foundation

- Add constants for profiles and compose override mapping.
- Add `BACKEND_CAPABILITIES_PATH`.
- Add `read_backend_capabilities()` and `write_backend_capabilities()`.
- Update `compose_files()`.
- Update `cmd_status()` to show backend profile.
- Update `cmd_update()` to validate profile-aware Compose config.

### Phase 2: CLI commands

- Add `hatch capabilities list/status/enable/disable`.
- Add `--yes` and `--no-restart` options.
- Add status messages and warnings.
- Add smoke script/tests.

### Phase 3: install journey

- Add `--backend-profile` to `install.sh`.
- Add interactive backend capability prompt.
- Persist `backend_capabilities.json` during install.
- Start via profile-aware `hatch start` where safe.

### Phase 4: backend API

- Add `/api/system/capabilities`.
- Read capability profile from env/config as appropriate.
- Merge with AI runtime feature gates.
- Add tests.

### Phase 5: frontend/documentation

- Show read-only capability status in onboarding/settings.
- Add feature-specific missing capability messages.
- Update README/manual install docs.

---

## 19. Acceptance criteria

This PR is complete only when all of the following are true:

```text
1. Fresh install still defaults to lightweight core backend.
2. Interactive install offers backend capability selection after AI mode selection.
3. Non-interactive install supports --backend-profile.
4. hatch capabilities list/status/enable/disable works.
5. Selected backend profile is persisted under $HATCH_HOME/config/backend_capabilities.json.
6. hatch start/restart/logs/status/update/uninstall use the selected profile consistently.
7. hatch update does not silently revert users to core/easy-only profile.
8. Local AI runtime still works independently of backend capability profile.
9. Backend exposes a capability status endpoint.
10. Frontend/onboarding/settings can display missing optional capabilities with exact CLI enable commands.
11. Browser UI cannot directly run Docker rebuilds.
12. Missing optional packages produce actionable messages rather than silent failures.
13. Existing users without backend_capabilities.json continue to work as core profile users.
14. Compose config validates for core/browser/local-embeddings/full and combinations with local-ai.
15. Tests or smoke scripts cover profile persistence and compose resolution.
```

---

## 20. Manual QA script

Codex should include this in implementation notes or a test script where practical.

```bash
# Start from clean config for QA only; do not include destructive commands in normal tests.
export HATCH_HOME="${HATCH_HOME:-$HOME/.hatch}"

hatch capabilities list
hatch capabilities status

hatch capabilities enable browser --yes --no-restart
hatch capabilities status
hatch start
hatch status
hatch restart
hatch status

hatch capabilities enable local-embeddings --yes --no-restart
hatch capabilities status
docker compose $(python - <<'PY'
# Optional helper only if Codex exposes compose file debug output; otherwise run direct docker compose commands.
PY
) config --quiet || true

hatch capabilities enable full --yes --no-restart
hatch capabilities status
hatch update --dry-run

curl -fsS http://localhost:8000/api/system/capabilities | python -m json.tool

hatch capabilities disable --yes --no-restart
hatch capabilities status
```

---

## 21. Suggested Codex prompt

Use this prompt after placing the spec under `docs/`:

```text
You are working in the Hatch repository.

Implement the follow-up PR described in docs/Hatch_Backend_Capability_Profile_UX_CLI_Spec.md.

Main objective:
Preserve the lightweight default backend introduced by the container optimisation work, while adding a first-class user journey for optional backend capability profiles.

Key requirements:
- Add persisted backend capability profile config under $HATCH_HOME/config/backend_capabilities.json.
- Add hatch capabilities list/status/enable/disable commands.
- Make compose_files() profile-aware for core/browser/local-embeddings/full and independent local AI runtime overlays.
- Make hatch start/restart/logs/status/update/uninstall preserve the selected backend profile.
- Update install.sh with --backend-profile and an interactive backend capability prompt.
- Add a backend system capabilities endpoint for frontend/onboarding/settings.
- Add clear missing-capability messages for optional features.
- Do not allow browser UI to trigger Docker rebuilds.
- Keep missing config backwards-compatible by defaulting to core.
- Add tests or smoke scripts for profile config, compose resolution, and capability status.

Before editing, audit the current files and report any conflicts or assumptions.
After editing, run the available tests plus compose config validation for all profile combinations.
```

---

## 22. Open implementation questions for Codex to resolve during audit

Codex should answer these before making broad changes:

1. What are the exact current names and build targets of the optional backend Compose override files?
2. Does the current backend already have a system/status router where `/api/system/capabilities` should live?
3. Which frontend settings/onboarding components are the correct places to show capability status?
4. Which coach features truly require full/perception packages versus only a capable AI runtime?
5. Are there existing tests for `hatch_cli.py`, or should this PR add the first focused CLI tests?
6. Should install use `hatch start` after creating the shim, or keep direct Docker Compose commands with shared profile mapping?

If any answer would change user-facing behaviour, Codex should pause and report the recommendation before continuing.
