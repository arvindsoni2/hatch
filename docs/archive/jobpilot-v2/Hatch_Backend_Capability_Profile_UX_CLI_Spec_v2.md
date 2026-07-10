---
title: Hatch Backend Capability Profile UX and CLI Spec v2
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

# Hatch Backend Capability Profile UX and CLI Spec v2

**Project:** Hatch  
**Repository:** https://github.com/arvindsoni2/hatch  
**Spec type:** Follow-up PR after backend container-size optimisation  
**Primary audience:** Codex implementation agent  
**Status:** Ready for implementation after scope split decision  
**Date:** 2026-07-08  
**Supersedes:** `Hatch_Backend_Capability_Profile_UX_CLI_Spec.md`

---

## 0. Locked implementation decisions

Use these decisions as authoritative for implementation.

1. **Split into two PRs.**
   - **PR 1:** Host-side capability profile management: installer, CLI, persisted config, profile-aware Compose resolution, docs, and tests.
   - **PR 2:** Backend capability API and frontend/read-only UX in Settings.

2. **Keep Linux and Windows installer parity.**
   - Add `--backend-profile` to `install.sh`.
   - Add `-BackendProfile` to `install.ps1`.

3. **Default backend profile remains `core`.**
   - Hatch must stay lightweight unless the user explicitly opts into heavier packages.

4. **Advanced install mode recommends optional/full capabilities but does not force them.**
   - Interactive advanced mode should explain the trade-off and let the user choose.
   - Non-interactive advanced mode remains `core` unless `--backend-profile full` / `-BackendProfile full` is passed.

5. **`hatch capabilities enable <profile>` restarts/rebuilds the backend service only by default.**
   - Use profile-aware `docker compose ... up -d --build backend`.
   - Do not restart frontend or local LLM containers by default.
   - Add optional `--restart-all` for users who explicitly want a full stack recreate.

6. **PR 2 frontend panel should start in Settings → System.**
   - Keep it read-only.
   - Show current profile, feature availability, and exact CLI commands to enable missing capabilities.
   - Do not let the browser UI trigger Docker rebuilds.

7. **Backend capabilities API should use env/profile as product truth.**
   - Use `importlib.util.find_spec()` only as a defensive consistency check.
   - Do not import heavy optional packages just to check status.

---

## 1. Problem statement

The backend container-size optimisation correctly moved heavy optional dependencies out of the default backend image. However, that optimisation creates a product journey risk:

- Fresh install currently asks for AI mode, but not optional backend capability packages.
- The easy install path starts the lightweight core backend.
- Optional backend images/profiles exist, but a normal user has no simple guided way to enable them.
- Users may not know whether browser automation, local embeddings, perception, or advanced coach-related capabilities are installed.
- `hatch start`, `hatch restart`, `hatch update`, `hatch logs`, and `hatch status` must preserve and display the selected backend capability profile.
- Manual Docker Compose override commands are too technical for the normal easy-install journey.

The desired product outcome is:

```text
Hatch remains small and simple by default.
Users who need heavier capabilities can explicitly enable them from the host CLI.
The selected capability profile persists across start, restart, update, status, and logs.
The app can clearly explain missing capabilities instead of failing silently.
```

---

## 2. PR split

### PR 1: Backend Capability Profiles for Easy Install and Hatch CLI

Scope:

```text
- Add persisted backend capability profile config.
- Add --backend-profile to install.sh.
- Add -BackendProfile to install.ps1.
- Add hatch capabilities list/status/enable/disable.
- Make compose file resolution profile-aware.
- Make start/restart/update/status/logs/uninstall use the same profile-aware Compose resolver.
- Preserve selected profile across restart/update.
- Update README/easy-install docs with host-side commands.
- Add host-side CLI/install tests.
```

PR 1 fixes the broken install and operational journey.

### PR 2: Backend Capability Status API and Settings UX

Scope:

```text
- Add GET /api/system/capabilities.
- Report backend profile and feature availability.
- Add read-only Settings → System capability panel.
- Add lightweight onboarding/help copy.
- Show exact host CLI commands for missing capabilities.
- Add backend API tests and frontend UI tests.
```

PR 2 improves browser-side visibility, but must not trigger Docker rebuilds from the web UI.

---

## 3. Non-goals

Do not merge optional packages back into the default backend image.

Do not make `full` the default profile.

Do not allow the browser UI to run Docker commands, rebuild containers, or mutate host config.

Do not remove the manual Compose override files. This PR should make them first-class through the CLI while keeping direct Compose usage possible for developers.

Do not combine AI runtime mode and backend package profile into one setting. They are related but separate concepts.

Do not import heavy packages such as `torch`, `transformers`, `sentence_transformers`, `playwright`, or `faster_whisper` merely to check whether they are available.

---

## 4. Core product distinction

Hatch needs two separate concepts.

| Concept | Meaning | Examples |
|---|---|---|
| AI mode/runtime | How intelligence is provided | `ai-later`, `cloud`, `local`, `advanced` |
| Backend capability profile | Which optional backend Python/package capabilities are installed | `core`, `browser`, `local-embeddings`, `full` |

AI mode controls LLM routing, model setup, cloud/local mode, and local llama.cpp services.

Backend capability profile controls optional backend dependencies such as Playwright/browser automation, local embedding packages, perception packages, and advanced coach extras.

Example status output after PR 1:

```text
Hatch status
Services: available
AI mode: local
Backend capability profile: local-embeddings
Local models: 2 ready
Capabilities:
  Core backend: installed
  Browser automation: not installed
  Local embeddings: installed
  Perception/advanced coach extras: not installed

To enable browser automation:
  hatch capabilities enable browser

To enable all optional backend capabilities:
  hatch capabilities enable full
```

---

## 5. Current repo state to account for

Codex must verify current filenames before editing. The expected post-container-optimisation repo shape is:

- `install.sh` supports AI mode selection and starts the easy Compose stack.
- `install.ps1` mirrors the easy-install behaviour for Windows.
- `scripts/hatch_cli.py` owns host-side commands such as `start`, `restart`, `update`, `status`, and `logs`.
- `scripts/hatch_cli.py` currently resolves `docker-compose.easy.yml` and conditionally local LLM Compose files.
- Optional backend Compose override files exist or should exist after the container-size optimisation:
  - `docker-compose.browser.yml`
  - `docker-compose.local-embeddings.yml`
  - `docker-compose.full.yml`
  - `docker-compose.local-ai.yml` for local LLM runtime

Backwards compatibility requirement:

```text
Existing installs with no backend_capabilities.json must behave exactly like core profile installs.
```

---

## 6. Capability profiles

Implement one active backend capability profile at a time.

| Profile | Purpose | Expected Compose file set |
|---|---|---|
| `core` | Default lightweight backend | `docker-compose.easy.yml` |
| `browser` | Enables Playwright/browser-backed automation/import | `docker-compose.easy.yml` + `docker-compose.browser.yml` |
| `local-embeddings` | Enables local semantic scoring/embedding packages | `docker-compose.easy.yml` + `docker-compose.local-embeddings.yml` |
| `full` | Enables browser + local embeddings + perception/advanced coach extras | `docker-compose.easy.yml` + `docker-compose.full.yml` |

Local LLM runtime remains independent.

When AI mode/runtime requires local LLM services, also include:

```text
docker-compose.local-ai.yml
```

Example mapping:

| AI runtime | Backend profile | Compose result |
|---|---|---|
| `cloud` | `core` | easy |
| `cloud` | `browser` | easy + browser |
| `local` | `core` | easy + local-ai |
| `local` | `local-embeddings` | easy + local-embeddings + local-ai |
| `advanced` | `core` | easy + local-ai when local models are selected/configured |
| `advanced` | `full` | easy + full + local-ai when local models are selected/configured |

Notes:

- Do not infer backend profile from AI mode automatically after install.
- Do not force `full` for `advanced`.
- It is acceptable for `advanced + core` to exist. The user has advanced AI runtime options but lightweight backend packages.

---

## 7. Persisted host config

Add a new non-secret config file:

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
  "updated_by": "install"
}
```

Examples:

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
  "profile": "local-embeddings",
  "enabled": ["local-embeddings"],
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
- Invalid JSON should warn and fall back to `core` for read-only commands such as `status`.
- Invalid JSON should require confirmation before overwrite in mutating commands.
- Parent config directory should be `0700` where platform supports it.
- Config file should be `0600` where platform supports it.
- The file must contain no secrets.
- The `enabled` field should be derived from `profile`; do not allow contradictory state.
- For v1, support one active profile only. Keep schema extensible for future combinations.

---

## 8. PR 1 installer requirements

### 8.1 `install.sh`

Add:

```bash
--backend-profile core|browser|local-embeddings|full
```

Default:

```text
core
```

Interactive flow:

After AI setup mode selection, ask a backend capability question.

Suggested prompt:

```text
Backend capability profile:
[1] Core only - smallest image, recommended
[2] Browser automation - adds Playwright/browser-backed imports
[3] Local embeddings - adds heavier local semantic scoring packages
[4] Full - browser + local embeddings + perception/advanced coach extras
Choose backend capability profile [1]:
```

For `advanced` AI mode, show extra copy before the prompt:

```text
Advanced AI mode can use optional backend capabilities such as browser automation,
local embeddings, and perception/advanced coach extras.
Hatch stays lightweight unless you explicitly enable those packages.
```

Still default to `[1] Core only`.

Non-interactive behaviour:

```bash
./install.sh --mode advanced
```

must use:

```text
backend profile: core
```

unless explicitly provided:

```bash
./install.sh --mode advanced --backend-profile full
```

Validation:

- Reject unknown profile values with a clear message.
- Persist selected profile before first `docker compose up`.
- Use profile-aware Compose file resolution for first startup.

### 8.2 `install.ps1`

Add Windows parity:

```powershell
-BackendProfile core|browser|local-embeddings|full
```

Requirements:

- Same default: `core`.
- Same interactive choices.
- Same advanced-mode recommendation copy.
- Same validation behaviour.
- Persist the same `backend_capabilities.json` schema under the Windows Hatch home/config path used by the installer.
- Use profile-aware Compose file resolution for first startup.

PowerShell may also accept friendly aliases if simple to implement:

```text
Core
Browser
LocalEmbeddings
Local-Embeddings
Full
```

but must persist canonical lowercase profile names:

```text
core
browser
local-embeddings
full
```

---

## 9. PR 1 CLI requirements

Add a new command group:

```bash
hatch capabilities list
hatch capabilities status
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
hatch capabilities enable core
hatch capabilities disable
```

`enable core` and `disable` should both resolve to the `core` profile.

### 9.1 `hatch capabilities list`

Output:

```text
Backend capability profiles:
  core              Smallest backend image. Recommended for most users.
  browser           Adds Playwright/browser automation for supported imports.
  local-embeddings  Adds local semantic embedding packages.
  full              Adds browser, local embeddings, perception, and advanced coach packages.

Current profile: core
```

### 9.2 `hatch capabilities status`

Output should show:

- current profile
- enabled backend package groups
- missing optional package groups
- whether a backend recreate is needed if detectable
- exact enable commands

Example:

```text
Backend capability profile: core
Enabled backend packages: none

Available optional backend capabilities:
  Browser automation: not installed
  Local embeddings: not installed
  Perception/advanced coach extras: not installed

Enable commands:
  hatch capabilities enable browser
  hatch capabilities enable local-embeddings
  hatch capabilities enable full
```

### 9.3 `hatch capabilities enable <profile>`

Supported profiles:

```text
core
browser
local-embeddings
full
```

Behaviour:

1. Validate profile.
2. Show impact summary.
3. Ask confirmation unless `--yes` is passed.
4. Persist selected profile.
5. Run profile-aware backend recreate by default:

```bash
docker compose <profile-aware -f args> up -d --build backend
```

6. Show resulting status summary.

Example:

```bash
hatch capabilities enable browser
```

Suggested confirmation copy:

```text
This will switch the backend capability profile from core to browser.
It may download/build a larger backend image with browser automation dependencies.
The frontend and local model services will not be restarted.
Continue? [y/N]
```

Flags:

```bash
--yes          Skip confirmation.
--no-restart   Persist profile only. Do not rebuild/recreate services now.
--restart-all  Recreate the full profile-aware stack instead of backend only.
```

Flag precedence:

- `--restart-all` and `--no-restart` are mutually exclusive.
- If both are provided, fail with clear usage error.

### 9.4 `hatch capabilities disable`

Equivalent to:

```bash
hatch capabilities enable core
```

Behaviour:

- Persist `core`.
- Recreate backend only by default.
- Show message that optional backend packages are no longer active.

Example:

```text
Backend capability profile changed from full to core.
Recreating backend with lightweight core profile...
```

---

## 10. PR 1 Compose resolution requirements

Create or refactor a single source of truth in `scripts/hatch_cli.py`, for example:

```python
def compose_files(ai_runtime: str | None = None, backend_profile: str | None = None) -> list[Path]:
    ...
```

Rules:

1. Always include the base easy Compose file.
2. Add backend profile override based on `backend_capabilities.json`:
   - `core`: no backend override
   - `browser`: `docker-compose.browser.yml`
   - `local-embeddings`: `docker-compose.local-embeddings.yml`
   - `full`: `docker-compose.full.yml`
3. Add local LLM runtime Compose override independently when AI runtime requires it:
   - `docker-compose.local-ai.yml`
4. Preserve deterministic file order:

```text
docker-compose.easy.yml
backend capability override, if any
local AI runtime override, if any
```

If current repo conventions require a different order, Codex should use the order that makes Docker Compose overrides behave correctly and document it in a code comment.

All host commands must call this same resolver:

```text
hatch start
hatch restart
hatch update
hatch status
hatch logs
hatch uninstall
hatch capabilities enable/disable
```

Important update fix:

```text
hatch update must not validate or restart only docker-compose.easy.yml.
It must validate and operate on the selected profile-aware Compose file set.
```

---

## 11. PR 1 command behaviour requirements

### 11.1 `hatch start`

Use profile-aware Compose files.

Example:

```text
Starting Hatch...
AI mode: local
Backend capability profile: browser
Compose files: docker-compose.easy.yml, docker-compose.browser.yml, docker-compose.local-ai.yml
```

### 11.2 `hatch restart`

Use profile-aware Compose files.

Default restart should recreate full selected stack because this is an explicit stack command. This is separate from `hatch capabilities enable`, which should recreate only backend by default.

### 11.3 `hatch update`

Requirements:

- Preserve selected backend profile.
- Validate profile-aware Compose config.
- Restart using profile-aware Compose files.
- Do not silently fall back to `core` unless config is missing/invalid and user accepts fallback.

Suggested output:

```text
Updating Hatch...
AI mode: cloud
Backend capability profile: local-embeddings
Validating Compose configuration...
Restarting selected profile...
```

### 11.4 `hatch status`

Add backend profile visibility.

Minimum output:

```text
AI mode: local
Backend capability profile: local-embeddings
Local models: 2 ready
Optional backend capabilities:
  Browser automation: not installed
  Local embeddings: installed
  Perception/advanced coach extras: not installed
```

### 11.5 `hatch logs`

Use profile-aware Compose files.

If the selected profile uses override files, logs must still work without the user knowing those filenames.

### 11.6 `hatch uninstall`

Use profile-aware Compose files for stack shutdown/removal.

Do not delete `$HATCH_HOME/config/backend_capabilities.json` unless the uninstall flow already removes all Hatch config and the user explicitly confirms config deletion.

---

## 12. PR 1 README/docs requirements

Update user docs with a short section:

```markdown
## Optional backend capabilities

Hatch installs the lightweight backend by default.
Some advanced features need optional backend packages.

Check current profile:

```bash
hatch capabilities status
```

Enable browser automation:

```bash
hatch capabilities enable browser
```

Enable local embeddings:

```bash
hatch capabilities enable local-embeddings
```

Enable all optional backend capabilities:

```bash
hatch capabilities enable full
```

Return to lightweight mode:

```bash
hatch capabilities disable
```
```

Also document install-time flags:

```bash
./install.sh --mode cloud --backend-profile core
./install.sh --mode advanced --backend-profile full
```

```powershell
.\install.ps1 -Mode cloud -BackendProfile core
.\install.ps1 -Mode advanced -BackendProfile full
```

Clarify:

```text
AI mode and backend capability profile are separate.
AI mode decides cloud/local intelligence setup.
Backend capability profile decides which optional backend packages are installed.
```

---

## 13. PR 1 tests

Add or update tests according to current repo test conventions.

Minimum test coverage:

### Config tests

```text
- Missing backend_capabilities.json resolves to core.
- Valid profile config is loaded correctly.
- Invalid JSON falls back safely for read-only commands.
- Persisted profile writes canonical lowercase profile names.
- enabled list is derived from profile.
```

### Compose resolver tests

```text
- core + cloud => easy only.
- browser + cloud => easy + browser.
- local-embeddings + cloud => easy + local-embeddings.
- full + cloud => easy + full.
- core + local => easy + local-ai.
- local-embeddings + local => easy + local-embeddings + local-ai.
- full + local => easy + full + local-ai.
```

### CLI tests

```text
- hatch capabilities list exits 0.
- hatch capabilities status exits 0 with missing config.
- hatch capabilities enable browser --yes persists browser.
- hatch capabilities enable local-embeddings --yes persists local-embeddings.
- hatch capabilities enable full --yes persists full.
- hatch capabilities disable --yes persists core.
- unknown profile fails with non-zero exit and useful message.
- --restart-all and --no-restart together fail.
```

### Installer tests

```text
- install.sh default backend profile is core.
- install.sh --backend-profile full persists full.
- install.sh rejects unknown backend profile.
- install.ps1 default backend profile is core.
- install.ps1 -BackendProfile full persists full.
- install.ps1 rejects unknown backend profile.
```

Where direct PowerShell test execution is not available in CI, add a script-level/static validation test or clearly document manual Windows validation steps.

---

## 14. PR 1 acceptance criteria

PR 1 is complete when the following behaviours are true:

```bash
./install.sh --mode ai-later --backend-profile core
hatch capabilities status
hatch capabilities enable browser --yes
hatch status
hatch restart
hatch status
hatch capabilities enable local-embeddings --yes
hatch status
hatch capabilities enable full --yes
hatch status
hatch capabilities disable --yes
hatch status
```

Expected:

```text
- Default install remains lightweight.
- Browser profile persists and uses browser Compose override.
- Local embeddings profile persists and uses local-embeddings Compose override.
- Full profile persists and uses full Compose override.
- Disabling returns to core.
- start/restart/update/status/logs use the selected profile.
- update does not revert the selected profile to core.
- capability enable rebuilds/recreates backend only by default.
- --restart-all recreates the full selected stack.
- README documents the normal user path.
```

Windows parity acceptance:

```powershell
.\install.ps1 -Mode ai-later -BackendProfile core
.\install.ps1 -Mode advanced -BackendProfile full
```

Expected:

```text
- Windows installer accepts the same profile choices.
- Windows installer persists canonical profile names.
- Invalid profile values fail clearly.
```

---

# PR 2 Specification: Backend Capability Status API and Settings UX

PR 2 must start only after PR 1 lands or after Codex can rely on PR 1 config/profile behaviour.

---

## 15. PR 2 backend API requirements

Add endpoint:

```http
GET /api/system/capabilities
```

Response example:

```json
{
  "backend_profile": "core",
  "ai_mode": "local",
  "capabilities": {
    "core_backend": {
      "configured": true,
      "installed": true,
      "available": true,
      "reason": null,
      "enable_command": null
    },
    "browser_automation": {
      "configured": false,
      "installed": false,
      "available": false,
      "reason": "Browser automation profile is not enabled.",
      "enable_command": "hatch capabilities enable browser"
    },
    "local_embeddings": {
      "configured": false,
      "installed": false,
      "available": false,
      "reason": "Local embeddings profile is not enabled.",
      "enable_command": "hatch capabilities enable local-embeddings"
    },
    "perception_advanced_coach": {
      "configured": false,
      "installed": false,
      "available": false,
      "reason": "Full backend capability profile is not enabled.",
      "enable_command": "hatch capabilities enable full"
    }
  }
}
```

### Source of truth

Use env/profile signals as product truth.

Recommended env variables from Compose overrides:

```text
HATCH_BACKEND_PROFILE=core|browser|local-embeddings|full
HATCH_BROWSER_AUTOMATION_ENABLED=0|1
HATCH_LOCAL_EMBEDDINGS_ENABLED=0|1
HATCH_PERCEPTION_ENABLED=0|1
HATCH_ADVANCED_COACH_ENABLED=0|1
```

If env vars are missing, infer conservative defaults:

```text
backend_profile=core
optional capabilities disabled
```

### Defensive module checks

Use `importlib.util.find_spec()` only.

Example:

```python
from importlib.util import find_spec


def module_available(module_name: str) -> bool:
    return find_spec(module_name) is not None
```

Do not do this:

```python
import torch
import transformers
import sentence_transformers
import playwright
```

Potential checks:

```text
playwright             -> browser installed check
sentence_transformers  -> local embeddings installed check if that is still the chosen package
transformers           -> local/perception consistency check only
faster_whisper         -> perception consistency check if used
```

The API should distinguish:

| Field | Meaning |
|---|---|
| `configured` | Product profile/env says this capability is enabled. |
| `installed` | Defensive module check says expected dependency appears present. |
| `available` | Capability can be used now. Usually configured AND installed. |
| `reason` | Human-readable reason if unavailable. |
| `enable_command` | Host CLI command to enable missing capability. |

---

## 16. PR 2 frontend UX requirements

Add first panel under:

```text
Settings → System
```

Panel name:

```text
Backend capabilities
```

Show:

```text
Backend profile: core
AI mode: local

Core backend: Installed
Browser automation: Not installed
Local embeddings: Not installed
Perception/advanced coach extras: Not installed
```

For missing optional capabilities, show exact commands:

```text
Enable browser automation from your terminal:
hatch capabilities enable browser
```

```text
Enable local embeddings from your terminal:
hatch capabilities enable local-embeddings
```

```text
Enable all optional backend capabilities from your terminal:
hatch capabilities enable full
```

Important UX rules:

- Read-only panel only.
- No Docker rebuild button.
- No API endpoint that mutates host profile from browser.
- Do not block normal Hatch usage if the endpoint fails; show a soft warning.
- Keep onboarding copy lightweight.

Suggested onboarding/help copy:

```text
Hatch installs the lightweight backend by default.
Some advanced features need optional backend capabilities.
You can enable them from your terminal with hatch capabilities commands.
```

---

## 17. PR 2 feature-specific messaging

If a user reaches a feature that requires a missing capability, show a clear message instead of a broken flow.

Examples:

### Browser import missing

```text
Browser automation is not installed.
To enable it, run this from your terminal:

hatch capabilities enable browser
```

### Local embeddings missing

```text
Local embeddings are not installed.
Hatch can still use lightweight matching or cloud AI, depending on your AI setup.
To enable local embeddings, run:

hatch capabilities enable local-embeddings
```

### Advanced coach/perception missing

```text
Advanced coach extras are not installed in the current backend profile.
To enable all optional backend capabilities, run:

hatch capabilities enable full
```

Coach baseline rule:

```text
Do not label the entire coach module as unavailable unless it truly requires full/perception packages.
Show granular availability for basic coach features versus advanced extras.
```

---

## 18. PR 2 tests

Backend tests:

```text
- GET /api/system/capabilities returns core defaults when env vars are missing.
- browser env enabled reports configured=true for browser_automation.
- local embeddings env enabled reports configured=true for local_embeddings.
- full env enabled reports all optional groups configured=true.
- find_spec missing dependency reports installed=false and available=false.
- API does not import heavy optional packages.
```

Frontend tests:

```text
- Settings → System renders backend capability panel.
- Missing browser capability shows hatch capabilities enable browser.
- Missing local embeddings capability shows hatch capabilities enable local-embeddings.
- Missing full/perception capability shows hatch capabilities enable full.
- API failure shows a soft warning and does not break settings page.
```

---

## 19. PR 2 acceptance criteria

PR 2 is complete when:

```text
- GET /api/system/capabilities exists and is covered by tests.
- API uses env/profile truth first and find_spec only defensively.
- API does not import heavy packages for status checks.
- Settings → System shows current backend capability profile.
- Missing capabilities show exact hatch capabilities commands.
- Browser UI cannot trigger Docker rebuilds or mutate host profile.
- Feature-specific missing capability states are clear and non-broken.
```

---

## 20. Safety and reliability notes

- Host CLI owns Docker Compose mutation.
- Browser UI is read-only for capability management.
- Config file contains no secrets.
- Missing/invalid config falls back safely to `core`.
- Heavy optional dependencies stay out of the default image.
- `hatch update` must preserve user-selected capability profile.
- `hatch capabilities enable` must tell the user when it may build/download a larger image.
- Do not silently change backend profile based on AI mode.

---

## 21. Suggested Codex prompt for PR 1

```text
Implement PR 1 from docs/Hatch_Backend_Capability_Profile_UX_CLI_Spec_v2.md.

Scope only:
- installer + CLI + persisted backend capability profile config
- profile-aware Docker Compose resolution
- start/restart/update/status/logs/uninstall profile awareness
- README/docs updates
- tests for config, compose resolver, CLI, and installer behaviour

Do not implement backend API or frontend UX in this PR.

Locked decisions:
- Default backend profile is core.
- Advanced install mode recommends optional/full capabilities but does not force them.
- install.sh gets --backend-profile.
- install.ps1 gets -BackendProfile.
- hatch capabilities enable <profile> recreates backend only by default with profile-aware compose up -d --build backend.
- Add --restart-all and --no-restart flags.
- start/restart/update/status/logs/uninstall must all use the same profile-aware compose_files() resolver.
- Missing backend_capabilities.json means core.
- Existing users must not break.

After implementation, run relevant unit/smoke tests and report any commands that could not be run.
```

---

## 22. Suggested Codex prompt for PR 2

```text
Implement PR 2 from docs/Hatch_Backend_Capability_Profile_UX_CLI_Spec_v2.md after PR 1 is complete.

Scope only:
- GET /api/system/capabilities
- Settings → System read-only backend capability panel
- missing capability messages with exact hatch capabilities commands
- backend and frontend tests

Do not add browser-triggered Docker rebuilds.
Do not mutate host backend profile from frontend.
Use env/profile state as product truth.
Use importlib.util.find_spec only for defensive installed checks.
Do not import heavy optional packages just to check status.
```
