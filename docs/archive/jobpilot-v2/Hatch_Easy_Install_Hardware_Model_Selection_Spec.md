---
title: Hatch Easy Install & Hardware-Based Model Selection Spec
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

# Hatch Easy Install & Hardware-Based Model Selection Spec

**Repo:** https://github.com/arvindsoni2/hatch  
**Feature theme:** Easy install for non-developer users while preserving Hatch as a self-hosted, privacy-first product.  
**Recommended branch:** `feature/easy-install-model-selection`  
**Primary audience for this spec:** Codex implementation agent

---

## 1. Background

Hatch is already a self-hosted job search and application assistant with a responsive/PWA-style interface. The next useful experiment is not a native app, hosted SaaS, or more mobile work. The main product friction is installation and first-run setup.

Today, the install path is still developer-oriented. It requires Docker Compose and Git, clones or updates the repo, creates config files, downloads bundled Qwen GGUF models, and starts a Docker Compose stack. This is powerful but intimidating for nontechnical users.

The previous idea of a single “private local AI” option should be revised. Hatch should not choose one local model for everyone. Hardware varies too much. Instead, Hatch should let the user choose a model setup based on their own machine, with clear guidance and safe defaults.

---

## 2. Product decision

Build **Experiment 3 only**:

> Make Hatch easy to install and first-run, without investing in native app, hosted SaaS, or additional PWA work.

Replace the old binary choice:

- Fast cloud AI
- Private local AI

with a more flexible setup:

- Configure AI later
- Use cloud provider
- Use local models selected for this machine
- Advanced custom model/provider

The key principle:

> Hatch may recommend suitable models, but the user chooses. No large model download should happen by default without explicit confirmation.

---

## 3. Goals

### 3.1 User goals

A nontechnical user should be able to:

1. Install Hatch without understanding Git, Docker Compose, `.env`, or model file paths.
2. Start Hatch even if AI is not configured yet.
3. Choose between cloud AI and local AI in plain language.
4. For local AI, see model options compatible with their hardware.
5. Understand trade-offs: speed, quality, privacy, disk usage, RAM usage, and expected latency.
6. Diagnose setup problems without reading Docker logs.
7. Start, stop, update, and repair Hatch through app-like commands.

### 3.2 Product goals

1. Preserve Hatch’s self-hosted identity.
2. Preserve existing developer workflow.
3. Avoid forcing a 6GB+ model download on first install.
4. Reduce failed installs caused by missing Docker, ports, disk space, or LLM setup.
5. Make “AI not configured yet” a valid application state.
6. Keep privacy messaging explicit and honest.

---

## 4. Non-goals

Do not implement the following in this PR:

1. Native iOS app.
2. Native Android app.
3. Hosted SaaS/multi-tenant Hatch.
4. New PWA/mobile redesign.
5. Public cloud deployment templates.
6. Paid billing/subscription flows.
7. Automatic job application submission.
8. Automatic choice of a single default local model.
9. Silent download of large model files.
10. GPU-specific optimisation beyond safe detection and recommendations.

---

## 5. Current repo context to preserve

Preserve existing architecture:

```text
Next.js frontend
       |
FastAPI API and async agent workers
       |
SQLite data + profile.yaml + generated documents
       |
llama.cpp local models or optional cloud LLM provider
```

Preserve existing product boundaries:

1. Hatch never submits applications automatically.
2. User reviews generated documents and applies externally.
3. Cloud providers receive prompts only when explicitly configured.
4. Local AI keeps prompts on the machine.
5. Existing app-lock behaviour remains unchanged.
6. Existing manual Docker install and developer commands remain valid.

---

## 6. Proposed user-facing install modes

### 6.1 Mode A — Guided install, AI later

**Label:** “Install Hatch now, configure AI later”

**Recommended default for beginner install.**

Behaviour:

1. Install Hatch.
2. Create `.env` and `data/profile.yaml` when missing.
3. Do not download local models.
4. Do not require a cloud API key.
5. Start backend/frontend/database.
6. Open Hatch in browser.
7. Show onboarding with AI status: “Not configured yet.”
8. Allow profile setup, tracker, manual application entry, settings, and basic UI usage.
9. Disable or gate AI-dependent actions with clear explanation.

Use when:

- User wants the fastest, lowest-risk install.
- User is unsure which AI provider/model they want.
- User has limited bandwidth/disk.

### 6.2 Mode B — Cloud AI quick setup

**Label:** “Use a cloud AI provider”

Behaviour:

1. Install Hatch.
2. Do not download local models.
3. Ask user to choose a supported provider or skip.
4. Ask for API key only if provider is selected.
5. Save secret in `.env` or existing supported secret path.
6. Save selected provider/model in profile/config.
7. Start Hatch.
8. Show a clear privacy note before saving:

```text
Cloud AI is faster to set up, but prompts needed for scoring, tailoring, and interview prep may be sent to the selected provider. Do not use this mode if you want all AI processing to remain local.
```

### 6.3 Mode C — Local model selection for this machine

**Label:** “Use local AI models on this computer”

Behaviour:

1. Install Hatch.
2. Run hardware preflight.
3. Show compatible local model options.
4. Let user choose model(s).
5. Show estimated download size, RAM need, disk need, and expected speed tier.
6. Require explicit confirmation before download.
7. Download selected models only.
8. Validate files/checksums where possible.
9. Start only required llama.cpp services based on selected configuration.
10. Save selected models in config/profile.

Important:

- Hatch should recommend but not force.
- If hardware is weak, Hatch should still allow “AI later” or “cloud provider.”
- If user chooses a model below recommended RAM, show a warning but allow advanced override.

### 6.4 Mode D — Advanced custom setup

**Label:** “Advanced/custom AI setup”

Behaviour:

Allow advanced users to provide:

1. Custom GGUF model path.
2. Custom llama.cpp server URL.
3. Custom cloud provider base URL.
4. Custom OpenAI-compatible endpoint.
5. Separate primary and triage model configuration.
6. Existing `.env`-based setup.

No existing advanced workflow should be broken.

---

## 7. Hardware-based local model selection

### 7.1 Hardware probe

Add a safe hardware probe used by installer and/or first-run UI.

Collect only local machine capability data. Do not send it anywhere.

Minimum fields:

```json
{
  "os": "linux|macos|windows|unknown",
  "arch": "x86_64|arm64|unknown",
  "cpu_model": "string|null",
  "cpu_cores": 0,
  "ram_total_gb": 0,
  "disk_free_gb": 0,
  "gpu_detected": true,
  "gpu_summary": "string|null",
  "docker_available": true,
  "docker_running": true,
  "compose_available": true,
  "ports_available": {
    "3000": true,
    "8000": true,
    "8080": true,
    "8081": true
  }
}
```

Implementation notes:

- Keep the probe conservative and cross-platform.
- Do not require admin rights.
- If GPU detection is unreliable, return `unknown` and proceed.
- Do not fail installation only because GPU detection fails.
- Store a timestamped probe result locally for diagnostics.

### 7.2 Model catalogue

Create a model catalogue file, for example:

```text
data/model_catalog.json
```

or:

```text
models/catalog.json
```

The catalogue should describe supported local model choices without hardcoding one default into installer logic.

Suggested schema:

```json
{
  "version": 1,
  "models": [
    {
      "id": "qwen3-0.6b-q8-triage",
      "display_name": "Qwen3 0.6B Q8 - fast triage",
      "role": "triage",
      "format": "gguf",
      "filename": "Qwen3-0.6B-Q8_0.gguf",
      "download_url": "",
      "sha256": "",
      "download_size_gb": 0.6,
      "disk_required_gb": 1.0,
      "min_ram_gb": 4,
      "recommended_ram_gb": 8,
      "speed_tier": "fast",
      "quality_tier": "basic",
      "privacy": "local",
      "notes": "Good for quick filtering and low-resource machines."
    }
  ]
}
```

Recommended fields:

| Field | Purpose |
|---|---|
| `id` | Stable config key |
| `display_name` | User-facing name |
| `role` | `primary`, `triage`, or `combined` |
| `format` | Usually `gguf` |
| `filename` | Expected local file name |
| `download_url` | Source URL if installer downloads it |
| `sha256` | Integrity check when available |
| `download_size_gb` | User-facing download cost |
| `disk_required_gb` | Preflight disk check |
| `min_ram_gb` | Hard warning threshold |
| `recommended_ram_gb` | Recommended threshold |
| `speed_tier` | `fast`, `balanced`, `slow` |
| `quality_tier` | `basic`, `balanced`, `higher` |
| `context_hint` | Optional context length guidance |
| `hardware_tags` | e.g. `cpu-friendly`, `gpu-helpful`, `low-ram` |
| `notes` | Plain-language trade-off |

### 7.3 Model recommendation logic

Implement deterministic filtering and ranking.

Inputs:

- RAM total.
- Free disk.
- CPU core count.
- OS/architecture.
- GPU detected/unknown.
- Existing downloaded models.

Outputs:

```json
{
  "recommended": ["model-id-1", "model-id-2"],
  "compatible": ["model-id-1", "model-id-2", "model-id-3"],
  "not_recommended": [
    {
      "model_id": "model-id-4",
      "reason": "Requires more RAM than detected."
    }
  ],
  "warnings": ["GPU detection is unknown, so CPU guidance is shown."]
}
```

Rules:

1. A model is **compatible** if disk is sufficient and architecture is supported.
2. A model is **recommended** if RAM is at or above `recommended_ram_gb` and disk is sufficient.
3. A model is **not recommended** if RAM is below `min_ram_gb` or disk is insufficient.
4. User can still override non-recommended choices only in advanced mode.
5. Existing downloaded models should appear first with label “Already downloaded.”
6. Do not auto-download anything until the user selects and confirms.

### 7.4 Suggested user copy

For local AI setup:

```text
Hatch can run AI locally on your computer. This keeps prompts on your machine, but speed depends on your hardware.

We checked your machine and found:
- RAM: 32 GB
- Free disk: 180 GB
- CPU cores: 8
- GPU: not detected or not used

Choose the local model setup you want. Hatch recommends options that should work on this machine, but you stay in control.
```

Model card example:

```text
Balanced local setup
Primary: Qwen3 8B Q5
Triage: Qwen3 0.6B Q8
Download: about 6.5 GB
RAM: 16 GB+ recommended
Speed: slower on CPU, better quality for CV and interview prep
Privacy: local
```

Low-resource card example:

```text
Low-resource setup
Model: smaller local model
Download: smaller
RAM: lower requirement
Speed: faster
Quality: suitable for triage and simple drafting, weaker for detailed tailoring
Privacy: local
```

Warning example:

```text
This model may be slow or unstable on your machine because it needs more memory than detected. Choose it only if you understand the trade-off.
```

---

## 8. Beginner CLI wrapper

Add a user-facing `hatch` command wrapper where feasible.

Required commands:

```bash
hatch start
hatch stop
hatch restart
hatch status
hatch logs
hatch update
hatch doctor
hatch models
hatch models list
hatch models install
hatch models remove
hatch uninstall
```

Implementation can be:

- shell script on Linux/macOS;
- PowerShell script on Windows;
- thin wrapper around existing Docker Compose and Make commands.

The wrapper should not remove existing Make targets or Docker workflows.

### 8.1 `hatch status`

Should show:

```text
Hatch status
Frontend: running at http://localhost:3000
Backend: running at http://localhost:8000
Database: available
AI provider: not configured
Local models: none downloaded
Next step: Open Hatch and complete AI setup in Settings.
```

### 8.2 `hatch doctor`

Should run diagnostics and return plain-language fixes.

Checks:

1. Docker installed.
2. Docker running.
3. Docker Compose available.
4. Git available.
5. Install directory exists.
6. `.env` exists.
7. `data/profile.yaml` exists.
8. Ports available or already owned by Hatch.
9. Frontend container health.
10. Backend container health.
11. API health endpoint.
12. DB reachable.
13. AI provider configured.
14. Local model files selected/downloaded.
15. llama.cpp services healthy if local AI mode is active.

Example output:

```text
Hatch Install Doctor

Docker: OK
Docker Compose: OK
Git: OK
Install directory: OK
Frontend: OK
Backend: OK
Database: OK
AI setup: needs attention

Problem:
No AI provider or local model is configured.

Fix:
Open Hatch → Settings → AI Setup, then choose Cloud Provider, Local Models, or Configure Later.
```

---

## 9. First-run UI changes

Add or revise first-run setup so AI setup is not a hidden developer configuration.

### 9.1 First-run steps

Suggested flow:

1. App lock password.
2. Profile basics.
3. AI setup choice:
   - Configure later.
   - Cloud provider.
   - Local model selection.
   - Advanced/custom.
4. Confirmation screen.
5. Dashboard.

### 9.2 AI-not-configured state

The app must remain usable when AI is not configured.

Allowed:

- Dashboard shell.
- Settings.
- Profile editing.
- Applications tracker.
- Manual application creation.
- Manual job import/save where no AI is needed.
- AI setup page.

Disabled/gated:

- scoring;
- tailoring;
- cover letter generation;
- interview prep generation;
- Coach output;
- any agent step requiring LLM.

Show plain-language gating:

```text
AI is not configured yet. This feature needs either a cloud provider or local model. Set it up now or continue using Hatch as a tracker.
```

---

## 10. Configuration changes

Add a clear AI setup status model.

Suggested config shape:

```yaml
llm:
  mode: not_configured | cloud | local | custom
  provider: null
  primary_model: null
  triage_model: null
  local_models:
    primary_model_id: null
    triage_model_id: null
    custom_primary_path: null
    custom_triage_path: null
  setup:
    completed: false
    completed_at: null
    skipped_at: null
    hardware_probe_id: null
```

Requirements:

1. Existing configs must migrate safely.
2. If old default Qwen files exist, detect them and mark them as available.
3. Do not break existing `.env` cloud provider setup.
4. Do not expose secrets in UI, logs, or doctor output.
5. Do not require `llm.mode != not_configured` for app startup.

---

## 11. Installer changes

### 11.1 Linux/macOS `install.sh`

Update installer to support modes:

```bash
./install.sh --mode ai-later
./install.sh --mode cloud
./install.sh --mode local
./install.sh --mode advanced
```

If mode is not passed and script is interactive, ask.

If mode is not passed and script is non-interactive, default to `ai-later`.

Do not download models in `ai-later` or `cloud` mode.

### 11.2 Windows `install.ps1`

Add equivalent parameters:

```powershell
.\install.ps1 -Mode AiLater
.\install.ps1 -Mode Cloud
.\install.ps1 -Mode Local
.\install.ps1 -Mode Advanced
```

If mode is not passed and interactive, ask.

If mode is not passed and non-interactive, default to `AiLater`.

### 11.3 Backward compatibility

Existing command should still work:

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
```

But behaviour should change to beginner-safe default:

1. Install Hatch.
2. Do not download models automatically.
3. Start app.
4. Let first-run setup handle AI choice.

If maintainers want to preserve the old “download bundled models” behaviour, add:

```bash
HATCH_INSTALL_LEGACY_LOCAL_MODELS=true
```

or:

```bash
./install.sh --mode legacy-local
```

Only include legacy mode if needed for existing users/tests.

---

## 12. Docker Compose changes

Current local model services should not be required for basic app startup when AI mode is not configured or cloud mode is selected.

Recommended approach:

1. Make `llm-primary` and `llm-triage` optional via Docker Compose profiles.
2. Default compose startup should run frontend/backend/database only.
3. Local AI mode should enable LLM services.
4. Cloud AI mode should not start local LLM services.
5. Advanced custom endpoint mode should not require bundled llama.cpp services.

Possible implementation:

```yaml
services:
  llm-primary:
    profiles: ["local-ai"]

  llm-triage:
    profiles: ["local-ai"]
```

Then wrapper can run:

```bash
docker compose --profile local-ai up -d --build
```

for local AI mode.

Acceptance requirement:

- `docker compose up -d --build` must succeed without downloaded local models when local AI is not active.

---

## 13. Model management commands

Add model management commands/scripts.

### 13.1 `hatch models list`

Shows:

```text
Available local models for this machine

Recommended:
[1] Balanced local setup - Qwen3 8B primary + Qwen3 0.6B triage
    Download: about 6.5 GB
    RAM: 16 GB+ recommended
    Status: not downloaded

Compatible:
[2] Low-resource setup
    Download: smaller
    RAM: lower requirement
    Status: not downloaded

Already downloaded:
[3] Qwen3 0.6B Q8 triage
    Status: ready
```

### 13.2 `hatch models install`

Interactive install:

1. Run hardware probe.
2. Show recommended/compatible/not-recommended models.
3. Ask user to choose.
4. Show download size and target path.
5. Ask confirmation.
6. Download selected files.
7. Verify.
8. Save config.

### 13.3 `hatch models remove`

Allow user to remove downloaded local model files safely.

Must not remove:

- profile;
- database;
- generated documents;
- app lock;
- API keys.

---

## 14. API requirements

Add backend endpoints if needed for first-run UI and settings.

Suggested endpoints:

```text
GET  /api/setup/status
GET  /api/setup/hardware
GET  /api/setup/models/catalog
GET  /api/setup/models/recommendations
POST /api/setup/ai-mode
POST /api/setup/local-model-selection
POST /api/setup/cloud-provider
POST /api/setup/skip-ai
GET  /api/system/doctor
```

Security:

1. All endpoints remain behind app lock after app lock is created.
2. First-run endpoints must follow existing unauthenticated onboarding rules.
3. Secrets must never be returned in API responses.
4. Doctor endpoint must redact environment variables and API keys.

---

## 15. Frontend requirements

Add or update screens/components:

1. AI setup step in onboarding.
2. AI setup page in Settings.
3. Local hardware summary card.
4. Model recommendation cards.
5. Download confirmation modal.
6. AI-not-configured banner.
7. Feature-gating message component.
8. Doctor/status view if practical in UI.

### 15.1 AI setup card states

States:

- Not configured.
- Cloud provider configured.
- Local model selected, download pending.
- Local model downloaded, service not running.
- Local model healthy.
- Local model unhealthy.
- Custom endpoint configured.

### 15.2 Plain-language labels

Avoid developer-heavy labels as primary copy.

Use:

- “Use Hatch now, set up AI later”
- “Use a cloud AI provider”
- “Run AI locally on this computer”
- “Advanced custom setup”

Developer details can appear in expandable sections.

---

## 16. Privacy and safety copy

Add explicit copy wherever the user chooses AI mode.

### 16.1 Cloud mode copy

```text
Cloud AI is convenient and usually faster to set up. Hatch may send the text needed for scoring, CV tailoring, cover letters, or interview prep to the provider you choose. Your application is still self-hosted, but AI processing is not fully local in this mode.
```

### 16.2 Local mode copy

```text
Local AI keeps prompts on this computer. It may be slower, especially on CPU-only machines. You choose which model files to download based on your hardware.
```

### 16.3 AI later copy

```text
You can use Hatch as a profile and application tracker now. AI features such as scoring, tailoring, and interview prep will be available after you choose a cloud provider or local model.
```

---

## 17. Testing requirements

### 17.1 Unit tests

Add tests for:

1. Hardware probe parser.
2. Model catalogue validation.
3. Model recommendation logic.
4. Config migration from existing LLM settings.
5. AI-not-configured mode.
6. Cloud provider mode without local model files.
7. Local mode with selected model files.
8. Doctor result generation.
9. Secret redaction.

### 17.2 Integration tests

Add tests for:

1. Fresh install without model download.
2. Backend starts with `llm.mode=not_configured`.
3. Frontend can load dashboard/settings when AI is not configured.
4. AI-dependent endpoint returns actionable setup-required error.
5. Local model selected but missing file returns model-not-downloaded status.
6. Cloud provider selected but missing key returns provider-needs-key status.
7. Existing downloaded Qwen model files are detected.

### 17.3 Script tests

Add tests for:

1. `install.sh --mode ai-later` does not call model download.
2. `install.sh --mode local` asks for/uses model selection.
3. `install.ps1 -Mode AiLater` does not call model download.
4. `hatch doctor` exits nonzero only for true fatal issues.
5. `hatch status` works when containers are stopped.
6. `hatch models list` works without network.
7. `hatch models install` requires confirmation before download.

### 17.4 Docker tests

Add tests for:

1. Default `docker compose config --quiet`.
2. Default stack can start without `data/models` files.
3. `local-ai` profile includes LLM services.
4. Cloud mode does not start local LLM containers.

---

## 18. Acceptance criteria

Implementation is complete when:

1. Beginner install no longer downloads local models by default.
2. Hatch can start and show UI without AI configured.
3. AI-dependent features are clearly gated when AI is not configured.
4. User can choose cloud AI, local model selection, configure later, or advanced setup.
5. Local model setup shows recommendations based on detected hardware.
6. Local model setup requires explicit user confirmation before downloading.
7. Existing local Qwen setup still works for current users.
8. Existing manual Docker/developer workflow still works.
9. Docker Compose default startup does not require local model files.
10. `hatch doctor` gives plain-language diagnostics and redacts secrets.
11. `hatch status` gives useful status without exposing implementation details.
12. Windows and Linux/macOS installers both support beginner-safe mode.
13. README clearly separates beginner install, local model setup, cloud provider setup, and developer install.
14. Tests cover not-configured, cloud, local, and advanced/custom AI states.

---

## 19. Documentation updates

Update README sections:

1. Quick Start.
2. AI setup choices.
3. Local model selection.
4. Cloud provider setup.
5. Hardware guidance.
6. Troubleshooting.
7. Useful commands.
8. Privacy and safety.

Suggested README structure:

```text
Quick Start
  Beginner install
  What works before AI setup
  Choose AI mode

AI Setup
  Option 1: Configure later
  Option 2: Cloud provider
  Option 3: Local models for your hardware
  Option 4: Advanced/custom endpoint

Local Models
  How Hatch recommends models
  How to list/install/remove models
  Where models are stored

Troubleshooting
  hatch status
  hatch doctor
  Common fixes

Developer Install
  Manual Docker setup
  Make targets
  Tests
```

---

## 20. Implementation order for Codex

Recommended order:

1. Add config model for AI setup status.
2. Make backend tolerate `llm.mode=not_configured`.
3. Make Docker local LLM services optional via Compose profile.
4. Update installers to skip model download by default.
5. Add hardware probe and model catalogue.
6. Add recommendation logic.
7. Add model management scripts/commands.
8. Add doctor/status commands.
9. Add onboarding/settings AI setup UI.
10. Add feature gating for AI-dependent actions.
11. Update README.
12. Add tests.

Do not start with UI until backend/config/Docker can support AI-not-configured mode.

---

## 21. Codex implementation prompt

Use this prompt with Codex:

```text
You are working in https://github.com/arvindsoni2/hatch.

Implement the Hatch Easy Install & Hardware-Based Model Selection spec.

Primary objective:
Make Hatch beginner-friendly to install while preserving self-hosted operation and existing developer workflows.

Key decisions:
1. Do not download bundled local models by default during beginner install.
2. Hatch must start and show the UI with AI not configured.
3. AI setup choices are: configure later, cloud provider, local models selected for this machine, and advanced/custom setup.
4. Local AI must be user-selected based on hardware recommendations. Do not hardcode a single mandatory local model choice.
5. Large local model downloads require explicit confirmation.
6. Local LLM Docker services should be optional and not required for basic app startup.
7. Add beginner-friendly status/doctor/model commands or scripts.
8. Preserve app-lock, privacy boundaries, application safety boundaries, manual Docker install, and existing local/cloud LLM functionality.

Implementation priorities:
- First update backend/config/Docker so AI-not-configured mode is valid.
- Then update installers and model management.
- Then update onboarding/settings UI.
- Then update docs and tests.

Acceptance criteria are in the spec. Run existing tests and add targeted tests for installer modes, AI-not-configured mode, model recommendation logic, doctor output, and Docker Compose profiles.
```

---

## 22. Open implementation questions for Codex to answer from repo inspection

Codex should inspect the current repo and answer these before coding if unclear:

1. Where is the best existing config model for `llm.mode` and selected model IDs?
2. Which backend routes currently assume an LLM is always configured?
3. Which UI components currently assume AI is always available?
4. Should the model catalogue live under `models/`, `data/`, or `backend/`?
5. Is there already a script wrapper pattern to extend for `hatch` commands?
6. Should local model download continue to use `scripts/fetch_models.sh` or be split into model-specific downloads?
7. Can Docker Compose profiles be introduced without breaking current tests?
8. How should Windows command wrappers be exposed: PowerShell function, script, or generated shortcut?

If a decision is required, prefer the smallest change that preserves current user data and current developer workflows.
