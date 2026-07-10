---
title: Hatch Easy Install And Hardware-Based Model Selection Spec
document_type: implementation-spec
status: implemented
implementation_status: complete
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

# Hatch Easy Install & Hardware-Based Model Selection Spec

**Repo:** https://github.com/arvindsoni2/hatch
**Feature theme:** Easy install for non-developer users while preserving Hatch as a self-hosted, privacy-first product.
**Recommended branch:** `feature/easy-install-model-selection`
**Primary audience for this spec:** Codex implementation agent

**v8 clarification update:** Resolves remaining implementation-contract gaps: `hatch update`, `hatch uninstall`, and cloud secret handling are now explicitly defined. Backend/UI may write only non-secret setup intent; host CLI is the only component that writes `${HATCH_HOME}/config/secrets.env`. Uninstall is non-destructive by default and requires explicit purge flags plus confirmation for data deletion.

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

### 2.1 Canonical local state directory

Use `${HATCH_HOME}` as the canonical per-user state directory for easy install.

Defaults:

- Linux/macOS: `${HATCH_HOME:-~/.hatch}`
- Windows: `%HATCH_HOME%` if set, otherwise `%USERPROFILE%\.hatch`

`HATCH_HOME` stores host-side state such as probe results, selected AI intent, CLI config, logs, and imported/downloaded model files. Keep `HATCH_DIR` or the existing install directory concept for the cloned application source/repo location. Do not mix source checkout location and user state location.

Required subdirectories:

```text
${HATCH_HOME}/config
${HATCH_HOME}/models
${HATCH_HOME}/probe
${HATCH_HOME}/logs
${HATCH_HOME}/bin
```

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
4. If the choice is made in the host installer/CLI, prompt for the API key securely in the terminal and write it through `hatch secrets set <provider>`.
5. If the choice is made in the UI, collect only non-secret provider metadata and show the next CLI command for secret entry. The UI/backend must not collect or write API keys in v1.
6. Save selected provider/model as non-secret setup intent; `hatch apply-ai-config` writes effective runtime config to `${HATCH_HOME}/config/ai_runtime.json`.
7. Start Hatch.
8. Show a clear privacy note before applying cloud mode:

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
10. Save selected models as non-secret setup intent; `hatch apply-ai-config` writes effective runtime config to `${HATCH_HOME}/config/ai_runtime.json`.

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

Custom GGUF import rule for v1:

- Custom GGUF files must be copied into `${HATCH_HOME}/models`.
- Do not rely on symlinks outside `${HATCH_HOME}/models`; they may break inside Docker and create support/security problems.
- The container mount is always `${HATCH_HOME}/models:/models:ro`.
- Config should store both the original imported path for user diagnostics and the managed container path used at runtime.

---

## 7. Hardware-based local model selection

### 7.1 Hardware probe

Add a safe hardware probe that runs on the host installer/CLI, not inside containers. Container-based probing must not be treated as authoritative because containers may not reliably see host RAM, GPU, disk, OS-level details, or model storage.

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
- Store the full timestamped probe result locally for diagnostics under `${HATCH_HOME}/probe/hardware_probe.json`.
- Do **not** mount `${HATCH_HOME}/probe` into the backend container.
- After `hatch probe` completes, copy a latest/sanitised probe snapshot into `${HATCH_HOME}/config/hardware_probe_latest.json`.
- The first-run UI reads the latest host-generated probe result from the mounted config directory through the backend.
- The backend may display probe data but must not become the source of truth for host hardware probing.
- If no latest probe result exists in config, the UI must show “Hardware not detected yet” and provide the CLI command `hatch probe` or `hatch doctor`.

#### 7.1.1 Sanitised hardware probe snapshot contract

The full probe result under `${HATCH_HOME}/probe/hardware_probe.json` may contain diagnostic detail for local support. The backend/UI must not read that file.

The UI-readable snapshot at `${HATCH_HOME}/config/hardware_probe_latest.json` must contain only the following allowlisted fields:

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-04T10:00:00Z",
  "source": "hatch_host_probe",
  "sanitised": true,
  "platform": {
    "os_family": "linux|macos|windows|unknown",
    "os_name": "string|null",
    "os_version_major": "string|null",
    "arch": "x86_64|arm64|unknown"
  },
  "cpu": {
    "logical_cores": 0,
    "physical_cores": 0,
    "model_summary": "string|null"
  },
  "memory": {
    "total_gb": 0,
    "available_gb": 0
  },
  "storage": {
    "hatch_home_free_gb": 0,
    "models_dir_free_gb": 0
  },
  "gpu": {
    "detected": false,
    "vendor": "nvidia|amd|apple|intel|unknown|null",
    "model_summary": "string|null",
    "vram_gb": 0,
    "detection_confidence": "high|medium|low|unknown"
  },
  "docker": {
    "docker_available": false,
    "docker_running": false,
    "compose_available": false
  },
  "ports": {
    "3000": {"status": "available|used_by_hatch|occupied|unknown", "purpose": "frontend"},
    "8000": {"status": "available|used_by_hatch|occupied|unknown", "purpose": "backend"},
    "8080": {"status": "available|used_by_hatch|occupied|unknown", "purpose": "llm_primary"},
    "8081": {"status": "available|used_by_hatch|occupied|unknown", "purpose": "llm_triage"}
  },
  "model_support": {
    "recommended_model_ids": [],
    "compatible_model_ids": [],
    "not_recommended_model_ids": []
  },
  "warnings": [
    {"code": "string", "message": "string"}
  ]
}
```

Do not include these fields in the sanitised snapshot:

- hostnames
- usernames
- home directory paths or arbitrary absolute paths
- environment variables
- API keys, tokens, or secrets
- IP addresses, MAC addresses, network interface details
- serial numbers, machine IDs, Docker context names, or volume names
- process lists, installed package lists, shell history, or raw command output
- full filesystem mount tables

If an implementation needs extra fields, add them to this allowlist explicitly before exposing them through the backend/UI.

Port status rules:

- `available`: the port is free for Hatch to use.
- `used_by_hatch`: the port is already used by a Hatch-managed service/container from this installation.
- `occupied`: the port is used by something else and Hatch should not assume it can bind the port.
- `unknown`: the probe could not determine the state safely.

Do not expose process IDs, process names, command lines, usernames, hostnames, Docker context names, or arbitrary container names in the sanitised port snapshot. If the probe can confidently identify Hatch-owned services, expose only `used_by_hatch`.

GPU detection is display-only in v1. Model recommendations must be based on OS/architecture support, total physical RAM, and model storage capacity only. Do not promote or demote catalogue entries because a GPU is detected unless a later PR explicitly implements GPU-aware inference and tests it across supported platforms. The UI may show a note such as “GPU detected, but v1 recommendations are RAM/disk based.”

### 7.2 Model catalogue

Create the model catalogue at:

```text
backend/app/config/model_catalog.json
```

Do not place the catalogue under `data/`; `data/` is mutable user/runtime storage. The catalogue is versioned application configuration and should live with backend config/code.

The catalogue describes supported local model choices without hardcoding one default into installer logic. The canonical approved downloadable entries are defined in section 23.7. Do not duplicate placeholder catalogue entries in this section.

Required fields for each catalogue entry:

| Field | Purpose | Required |
|---|---|---|
| `id` | Stable config key | Yes |
| `display_name` | User-facing name | Yes |
| `role` | `triage` or `combined_capable_primary` for the initial catalogue | Yes |
| `format` | Model file format. Initial catalogue value must be `gguf` | Yes |
| `supported_os` | Supported host operating systems for the easy-install local AI path, for example `["linux", "macos", "windows"]` | Yes |
| `supported_arch` | Supported host CPU architectures for the easy-install local AI path, for example `["x86_64", "arm64", "aarch64"]` | Yes |
| `repo_id` | Hugging Face repository ID for approved downloads | Yes for approved downloads |
| `filename` | GGUF filename | Yes |
| `download_url_template` | Source URL template using immutable `source_revision` | Yes for approved downloads |
| `source_revision` | Full immutable Hugging Face commit SHA, never `main`, `latest`, blank, or placeholder | Yes for approved downloads |
| `sha256` | Required SHA-256 checksum | Yes for approved downloads |
| `download_size_gb` | User-facing download estimate | Yes |
| `disk_required_gb` | Required free disk space before download/extract/use | Yes |
| `min_ram_gb` | Hard minimum for beginner recommendation | Yes |
| `recommended_ram_gb` | Recommended RAM for stable use | Yes |
| `license` | Licence identifier | Yes |
| `source_trust` | Source category, for example `official_qwen_huggingface` | Yes |

Rules:

- Section 23.7 is the single source of truth for the initial approved downloadable model entries.
- Use `combined_capable_primary` for models that can serve primary tasks and may also serve triage when a separate triage model is unavailable. In the initial catalogue, Qwen3 4B and Qwen3 8B use this role.
- Use `triage` for models that must not serve quality-sensitive primary tasks. In the initial catalogue, Qwen3 0.6B uses this role.
- Catalogue examples in documentation must not include blank hashes, floating revisions, or unresolved placeholders unless clearly marked as non-executable pseudocode.
- The committed `model_catalog.json` must not contain placeholders.
- Add validation that fails the build/test suite if `source_revision` is `main`, `latest`, empty, shorter than a full commit SHA, or contains placeholder text.
- Add validation that fails if an initial approved catalogue entry omits `format`, `supported_os`, or `supported_arch`.

### 7.3 Model recommendation logic

Implement deterministic filtering and ranking.

Inputs:

- Total physical RAM in GB. Use this as the deterministic RAM input for recommendation buckets.
- Available/free RAM in GB may be collected for display and warnings only; it must not change the recommendation bucket.
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

1. A model is **recommended** if `supported_os` and `supported_arch` include the detected host OS/architecture, disk is sufficient, total physical RAM is at or above `recommended_ram_gb`, and no blocking warnings apply.
2. A model is **compatible** if `supported_os` and `supported_arch` include the detected host OS/architecture, disk is sufficient, total physical RAM is at or above `min_ram_gb`, and total physical RAM is below `recommended_ram_gb`.
3. A model is **not recommended** if total physical RAM is below `min_ram_gb`, disk is insufficient, `supported_os` does not include the detected host OS, or `supported_arch` does not include the detected host architecture.
4. Buckets are mutually exclusive. A model appears in only one primary bucket, with optional warning metadata.
5. User can still override non-recommended choices only in advanced mode.
6. Existing downloaded models should appear first with label “Already downloaded.”
7. Do not auto-download anything until the user selects and confirms.
8. If the 8B primary model is not compatible but the 4B primary model is compatible, offer a compact local setup that assigns Qwen3 4B to primary tasks. Use Qwen3 0.6B for triage when available; if 0.6B is not available, route triage tasks to Qwen3 4B as a combined-role fallback with a performance warning.
9. If the 4B primary model is also not compatible but the 0.6B triage model is compatible, do not pretend full local AI is available. Offer a triage-only local mode with mandatory feature disables for tailoring, cover-letter generation, and coach/interview prep, or suggest cloud AI/configure-later for those features.
10. If the 0.6B model is also below minimum requirements, local AI is unavailable for beginner mode; offer “configure AI later” or cloud provider setup instead.

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

Compact local setup example:

```text
Compact local setup
Primary: Qwen3 4B Q4
Triage: Qwen3 0.6B Q8, if available
Download: about 3.1 GB total if both models are selected
RAM: 8 GB+ minimum, 12 GB+ recommended
Speed: better than 8B on lower-end machines
Quality: useful for basic CV tailoring, cover-letter drafting, and coach flows, but weaker than 8B
Privacy: local
```

Triage-only card example:

```text
Triage-only local setup
Triage: Qwen3 0.6B Q8
Download: about 0.6 GB
RAM: 4 GB+ minimum, 8 GB+ recommended
Speed: fast
Quality: suitable for quick filtering and simple summaries only. Not recommended for CV tailoring, cover-letter quality, or coach/interview prep.
Privacy: local
```

Warning example:

```text
This model may be slow or unstable on your machine because it needs more memory than detected. Choose it only if you understand the trade-off.
```

Fallback copy when 8B is unavailable but 4B is compatible:

```text
Your machine does not meet the minimum requirement for the 8B primary model. Hatch can still run a compact local setup using Qwen3 4B for primary tasks.

This keeps data local and should be more useful than the 0.6B triage model for CV tailoring, cover-letter drafting, and coach flows, but quality will still be lower than the 8B setup. For best results, use 8B on stronger hardware or configure a cloud provider.
```

Fallback copy when only 0.6B is compatible:

```text
Your machine does not meet the minimum requirement for the 8B or 4B primary models. Hatch can still run a triage-only local setup using Qwen3 0.6B.

This is suitable for quick filtering and simple summaries. CV tailoring, cover-letter generation, and interview/coach features are disabled in triage-only local mode. For those features, choose a larger local model on stronger hardware or configure a cloud provider.
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
hatch apply-ai-config
hatch models
hatch models list
hatch models install
hatch models remove
hatch secrets
hatch secrets status
hatch secrets set
hatch secrets unset
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

### 8.2 `hatch update`

`hatch update` updates only the managed easy-install Hatch application code. It must preserve user data and must avoid surprising changes to developer checkouts.

Managed install contract:

- The easy installer should record its managed source location in `${HATCH_HOME}/config/install.json`.
- If the source is a managed clean checkout or managed release directory, `hatch update` may update it.
- If the source is a developer checkout, missing, not managed, or has uncommitted changes, `hatch update` must refuse by default and print the safe manual update command instead.
- `--allow-dirty` is not required for v1. If implemented, it must first create a backup and clearly warn that local source edits may be overwritten.

Configuration and data preservation:

- Must preserve `${HATCH_HOME}/config`, `${HATCH_HOME}/models`, `${HATCH_HOME}/probe`, `${HATCH_HOME}/logs`, databases, generated documents, app-lock state, and secrets.
- Must not overwrite `.env`, `profile.yaml`, `ai_runtime.json`, `ai_setup_intent.json`, or `secrets.env` without creating a backup and asking for confirmation.
- Must not delete legacy `data/models` or `${HATCH_HOME}/models`.

Safe update sequence:

1. Run preflight checks: Docker availability, compose config validity, disk space, managed-source status, and write permissions.
2. Create a timestamped update backup under `${HATCH_HOME}/backups/update-<timestamp>/` containing at least config files, database files if they are under Hatch-managed storage, app-lock state, and a manifest of current versions/paths. Large model files may be referenced in the manifest rather than copied.
3. Fetch the target Hatch version. Prefer a tagged release or pinned commit when the installer knows one; otherwise use the configured branch.
4. Validate `docker-compose.easy.yml` and the legacy developer compose file before replacing/running anything.
5. Stop affected easy-install services only after the new compose/config validation passes.
6. Apply code update.
7. Run migrations only after the backup exists.
8. Restart affected services only after migrations succeed, unless `--no-restart` is passed.
9. Run a post-update health check.

Failure handling:

- If fetch or compose validation fails, do not stop the running app.
- If migration fails, stop and report the failure, preserve the backup, and do not delete the previous source. Automatic database rollback is not required in v1 because it can risk data loss; instead print the backup path and manual recovery steps.
- If restart fails after a code update, keep the backup and print `hatch doctor` guidance. Restore previous source automatically only if the implementation can do so without touching user data.
- `hatch update --dry-run` should report what would change without applying changes.

### 8.3 `hatch uninstall`

`hatch uninstall` is non-destructive by default. Data deletion requires explicit purge flags and confirmation because this is a data-loss boundary.

Default uninstall behaviour:

- Stop and remove Hatch easy-install containers created by the easy-install compose files.
- Remove the user-level `hatch` command shim only if it was installed by the easy installer.
- Optionally remove the managed application source directory if it is recorded in `${HATCH_HOME}/config/install.json` and is not a developer checkout.
- Preserve `${HATCH_HOME}` by default, including config, databases, generated documents, models, probe results, logs, backups, app-lock state, and secrets.
- Preserve legacy repo `data/` directories and developer checkouts.

Purge behaviour:

- `hatch uninstall --purge-config` may remove non-secret easy-install config after confirmation.
- `hatch uninstall --purge-models` may remove `${HATCH_HOME}/models` after confirmation.
- `hatch uninstall --purge-secrets` may remove `${HATCH_HOME}/config/secrets.env` after confirmation.
- `hatch uninstall --purge-data` may remove databases, generated documents, app-lock state, and runtime data after confirmation.
- `hatch uninstall --purge-all` may remove all Hatch-managed `${HATCH_HOME}` content after confirmation.

Confirmation rules:

- Interactive purge must show the exact categories that will be removed and the base directory.
- Destructive purge requires typing a confirmation phrase such as `DELETE HATCH DATA`.
- Non-interactive purge requires both `--yes` and the explicit purge flag. `--yes` alone must not delete data.
- Never remove files outside `${HATCH_HOME}` or the recorded managed install source in v1.

### 8.4 `hatch secrets`

Secrets are managed by the host CLI only. Backend/UI must not write secret files.

Required subcommands:

```bash
hatch secrets status
hatch secrets set <provider>
hatch secrets unset <provider>
```

Rules:

- `hatch secrets set <provider>` prompts for the provider API key without echoing it.
- It writes or updates only the relevant provider key in `${HATCH_HOME}/config/secrets.env`.
- It creates `${HATCH_HOME}/config` with user-only permissions where the platform supports it.
- It must not print, log, or return secret values or secret-length hints.
- `hatch secrets status` may show only whether each configured provider secret is present and when it was last validated if that metadata exists.
- `hatch secrets unset <provider>` removes only the selected provider secret and must ask for confirmation interactively.
- Non-interactive unset requires `--yes --provider <provider>` or equivalent explicit provider selection.


### 8.5 `hatch doctor`

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

Current local model services should not be required for basic app startup when AI mode is not configured or cloud mode is selected. At the same time, existing developer/default Docker Compose behaviour must not be broken.

Canonical strategy:

1. Keep the existing `docker-compose.yml` behaviour working as-is for developers, tests, and existing users.
2. Add a separate easy-install compose file, for example `docker-compose.easy.yml`.
3. `docker-compose.easy.yml` starts only the services needed for a beginner-safe app launch: frontend, backend, and required data mounts. It must not require local GGUF files.
4. Add a generated or static local-AI override, for example `docker-compose.local-ai.yml`, used only when the user chooses local models.
5. The Hatch CLI controls which compose files are used. The backend and UI must not call Docker directly and must not mount `/var/run/docker.sock`.

Example commands used by the CLI:

```bash
# Beginner-safe app launch
docker compose -f docker-compose.easy.yml up -d --build

# Local AI launch after explicit model selection/download
docker compose -f docker-compose.easy.yml -f docker-compose.local-ai.yml up -d --build
```

Acceptance requirements:

- Existing `docker compose up -d --build` remains backward compatible.
- Easy install must succeed without downloaded local models when local AI is not active.
- Local model services are started only when the user has explicitly selected local AI and required model files exist.

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
[2] Compact local setup - Qwen3 4B primary + Qwen3 0.6B triage
    Download: about 3.1 GB
    RAM: 12 GB+ recommended, 8 GB minimum
    Status: not downloaded

Limited:
[3] Triage-only setup - Qwen3 0.6B triage
    Download: about 0.6 GB
    RAM: 8 GB+ recommended, 4 GB minimum
    Status: not downloaded

Already downloaded:
[4] Qwen3 0.6B Q8 triage
    Status: ready
```

### 13.2 `hatch models install`

Interactive install:

1. Run hardware probe.
2. Show recommended/compatible/not-recommended models.
3. Ask user to choose.
4. Show download size and target path under `${HATCH_HOME}/models`.
5. Ask confirmation.
6. Download selected files.
7. Verify SHA-256 checksums before marking models ready.
8. Save selected model paths to non-secret setup intent; after apply, write effective paths to `${HATCH_HOME}/config/ai_runtime.json`.
9. Ask before restarting affected services, unless `--yes --restart` is passed.

### 13.3 `hatch models remove`

Allow user to remove downloaded local model files safely.

Must not remove:

- profile;
- database;
- generated documents;
- app lock;
- API keys.

Active model removal contract:

- Default behaviour: refuse to remove a model that is referenced by `${HATCH_HOME}/config/ai_runtime.json` or by pending `${HATCH_HOME}/config/ai_setup_intent.json`. Show which role uses it and the safe next actions.
- Interactive behaviour: ask the user to choose one of these actions before deleting an active model:
  1. `replace`: select another already-ready compatible model for the affected role;
  2. `degrade`: move to the best valid fallback mode from section 23.8;
  3. `clear-ai`: set `ai_mode=not_configured` and disable AI-dependent features until setup is run again;
  4. `cancel`: keep the model.
- Non-interactive behaviour: require an explicit flag, for example `--replace-with <model_id>`, `--degrade`, or `--clear-ai`. `--force` alone is not enough.
- If an active triage model is removed and the active primary model has role `combined_capable_primary`, `--degrade` may route triage to the primary model and set the matching combined quality mode.
- If an active primary model is removed and only Qwen3 0.6B remains, `--degrade` must switch to `triage_only` and set `feature_gates.cv_tailoring=false`, `feature_gates.cover_letter_generation=false`, and `feature_gates.coach_interview_prep=false`.
- Model file deletion must happen after the replacement/degrade/clear runtime config is successfully written.
- Never remove files outside `${HATCH_HOME}/models` in v1.

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
POST /api/setup/cloud-provider   # non-secret metadata only
POST /api/setup/skip-ai
GET  /api/system/doctor
```

Security:

1. All endpoints remain behind app lock after app lock is created.
2. First-run endpoints must follow existing unauthenticated onboarding rules.
3. Secrets must never be accepted by setup endpoints or returned in API responses.
4. Doctor endpoint must redact environment variables and API keys.
5. Cloud setup endpoints may store provider metadata only; they must never write `${HATCH_HOME}/config/secrets.env`.

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
8. `hatch update --dry-run` does not modify source, config, data, models, or secrets.
9. `hatch update` refuses by default on unmanaged or dirty developer checkouts.
10. `hatch uninstall` preserves `${HATCH_HOME}` by default.
11. `hatch uninstall --purge-all` requires explicit confirmation and never deletes outside `${HATCH_HOME}`.
12. `hatch secrets set/status/unset` updates only `${HATCH_HOME}/config/secrets.env` and never prints secret values.

### 17.4 Docker tests

Add tests for:

1. Default `docker compose config --quiet` for the existing developer compose path.
2. Existing default stack behaviour remains backward compatible.
3. `docker compose -f docker-compose.easy.yml config --quiet` succeeds without model files.
4. `docker compose -f docker-compose.easy.yml -f docker-compose.local-ai.yml config --quiet` includes local LLM services only after explicit local AI selection.
5. Cloud mode using `docker-compose.easy.yml` does not start local LLM containers.

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
9. Easy-install startup using `docker-compose.easy.yml` does not require local model files. Legacy/developer startup using the existing `docker-compose.yml` remains backward compatible and may retain its current local-model assumptions.
10. `hatch doctor` gives plain-language diagnostics and redacts secrets.
11. `hatch status` gives useful status without exposing implementation details.
12. Windows and Linux/macOS installers both support beginner-safe mode.
13. README clearly separates beginner install, local model setup, cloud provider setup, and developer install.
14. Tests cover not-configured, cloud, local, and advanced/custom AI states.
15. `hatch update` has safe dry-run, dirty-checkout refusal, backup, migration, and failure handling.
16. `hatch uninstall` is non-destructive by default and destructive purge requires explicit flags and confirmation.
17. Cloud secrets are written only by the host CLI, not by backend/UI endpoints.

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
3. Add the separate easy-install Compose path and local-AI Compose overlay without changing existing default Compose behaviour.
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
8. Use `${HATCH_HOME}` for easy-install state: config, probe results, logs, and models.
9. Keep backend/UI away from Docker control and `/var/run/docker.sock`; host CLI applies Docker/compose changes.
10. Preserve app-lock, privacy boundaries, application safety boundaries, manual Docker install, and existing local/cloud LLM functionality.
11. Backend/UI may write only non-secret setup intent; host CLI writes secrets and performs destructive/update operations.

Implementation priorities:
- First update backend/config/Docker so AI-not-configured mode is valid.
- Then update installers and model management.
- Then update onboarding/settings UI.
- Then update docs and tests.

Acceptance criteria are in the spec. Run existing tests and add targeted tests for installer modes, AI-not-configured mode, model recommendation logic, doctor output, and Docker Compose easy/local-AI file combinations.
```

---

## 22. Implementation discovery boundary

This spec has no remaining product questions for Codex. Implementation discovery is still allowed, but it must be limited to repo inspection and lowest-risk wiring decisions.

Codex may inspect the repo to find:

- the existing config model for LLM mode and selected model IDs;
- backend routes that need `ai_mode=not_configured` handling;
- UI components that need feature gating;
- the smallest command-wrapper location for `hatch`;
- whether to adapt `scripts/fetch_models.sh` or add a catalogue-driven downloader;
- tests that need compatibility coverage for the existing developer Docker path and the new easy-install path.

Codex should not ask new product questions unless implementation reveals a true data-loss, security, or backward-compatibility risk not covered by this spec. For ordinary ambiguity, choose the smallest change that preserves current user data and current developer workflows.

---

## 23. Resolved implementation decisions from Codex questions

These decisions override earlier sections if any conflict remains.

### 23.1 HATCH_HOME

`${HATCH_HOME}` is the canonical easy-install state root for probe results, downloaded/imported models, host CLI configuration, logs, and UI configuration intent.

Defaults:

- Linux/macOS: `${HATCH_HOME:-~/.hatch}`
- Windows: `%HATCH_HOME%` if set, otherwise `%USERPROFILE%\.hatch`

Keep the repo/source checkout location separate. Existing installer variables such as `HATCH_DIR` may continue to mean “where the Hatch repo/source is installed.”

Required directories:

```text
${HATCH_HOME}/config
${HATCH_HOME}/models
${HATCH_HOME}/probe
${HATCH_HOME}/logs
${HATCH_HOME}/bin
```

### 23.2 Custom GGUF import

Custom GGUF import must copy the selected `.gguf` file into `${HATCH_HOME}/models`.

Do not support arbitrary external symlink-based model paths in v1. Symlinks outside the managed directory can break inside Docker and are difficult to support across Linux, macOS, and Windows.

Runtime mount rule:

```text
${HATCH_HOME}/models:/models:ro
```

Config should store:

```yaml
original_import_path: /path/user/selected/model.gguf
managed_host_path: ${HATCH_HOME}/models/model.gguf
container_path: /models/model.gguf
sha256: <verified sha256>
```

### 23.3 Existing `data/models` migration

Existing model files under `data/models` must remain usable in place for the legacy/developer Docker workflow. Do not move, rename, or delete existing files automatically.

For easy install, `${HATCH_HOME}/models` is the canonical managed model directory. If the host CLI detects approved GGUF files under `data/models`, it should offer to import them into `${HATCH_HOME}/models`.

Rules:

1. Import means copy into `${HATCH_HOME}/models` and verify SHA-256 before marking the model `ready`.
2. Do not use symlinks to files outside `${HATCH_HOME}/models` in v1.
3. Do not delete or mutate the original `data/models` files.
4. If the source and destination are on the same filesystem and the implementation can safely hardlink without crossing Docker/OS compatibility boundaries, a hardlink may be used only as an internal optimisation; the user-facing contract remains “managed import into `${HATCH_HOME}/models`.”
5. If there is not enough disk space to copy/import, show a clear message and keep the existing legacy files untouched.

### 23.4 Easy-install Compose strategy

The canonical easy-install strategy is a separate compose file, not a breaking rewrite of the existing compose file.

Use:

```text
docker-compose.easy.yml
docker-compose.local-ai.yml
```

Rules:

1. Keep existing `docker-compose.yml` behaviour working for developers, tests, and current users.
2. `docker-compose.easy.yml` starts Hatch without local LLM services and without requiring GGUF model files.
3. `docker-compose.local-ai.yml` is layered only after explicit local model selection/download.
4. The host CLI decides which compose files to run.
5. Backend/UI must not control Docker and must not access `/var/run/docker.sock`.

### 23.5 UI configuration intent and runtime config storage

Store non-secret UI setup intent in:

```text
${HATCH_HOME}/config/ai_setup_intent.json
```

Mount the config directory into the backend container so the backend can safely read/write non-secret setup intent on behalf of the UI:

```text
${HATCH_HOME}/config:/hatch-home/config
```

The host CLI reads the same intent file and applies it.

Probe result strategy:

- Do not mount `${HATCH_HOME}/probe` into the backend.
- `hatch probe` writes the full diagnostic result to `${HATCH_HOME}/probe/hardware_probe.json`.
- `hatch probe` also writes/copies the latest UI-readable snapshot to `${HATCH_HOME}/config/hardware_probe_latest.json`.
- The UI/backend reads only `/hatch-home/config/hardware_probe_latest.json`.
- If the UI needs a fresh probe, it should instruct the user to run `hatch probe`; the backend must not probe host hardware itself.

Intent file responsibilities:

- selected AI mode: `not_configured | cloud | local | custom`
- selected catalogue model IDs
- local model download/import intent
- cloud provider name and non-secret provider metadata
- whether a restart is required
- last hardware probe ID/path
- latest UI-readable hardware probe snapshot path: `${HATCH_HOME}/config/hardware_probe_latest.json`

Do not store API keys or secrets in `ai_setup_intent.json`. Secrets must also not be stored in `ai_runtime.json`.

Cloud setup secret workflow for v1:

1. UI collects provider choice and non-secret metadata only, for example provider name, base URL label, and selected model label.
2. UI/backend writes provider metadata only to `${HATCH_HOME}/config/ai_setup_intent.json`.
3. UI/backend must not collect, accept, write, log, or proxy API keys in v1. This keeps the security boundary simple and avoids backend writes to secret files.
4. After provider metadata is saved, UI shows the next host command, for example `hatch secrets set openai`, `hatch secrets set groq`, or `hatch secrets set gemini`.
5. If cloud setup is run from the host installer/CLI instead of the UI, the CLI may prompt for the API key securely and write it through the same `hatch secrets set <provider>` logic.
6. `hatch secrets set <provider>` writes secrets only to `${HATCH_HOME}/config/secrets.env`.
7. `secrets.env` must use provider-specific environment variable names already supported by the app where possible, for example `OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, or equivalent existing repo names.
8. Installer/CLI must create `${HATCH_HOME}/config` with user-only permissions where the platform allows it and warn if permissions are too broad.
9. API responses and doctor/status output may report only `configured: true|false`, provider name, and last validation status. They must never return secret values or secret-length hints.
10. `hatch apply-ai-config` validates that required secret names are present before writing cloud `ai_runtime.json`. It must not print secret values.
11. Services receive secrets through the easy-install compose env-file or existing environment mechanism. Do not copy secrets into Docker labels, command lines, logs, `ai_setup_intent.json`, or `ai_runtime.json`.
12. Secret removal must be explicit through `hatch secrets unset <provider>`. A UI action may only display the required CLI command; it must not remove secrets itself in v1.

Runtime configuration file:

```text
${HATCH_HOME}/config/ai_runtime.json
```

`ai_setup_intent.json` is pending UI intent. It is not the authoritative runtime source. `hatch apply-ai-config` validates intent and writes the effective non-secret runtime configuration to `ai_runtime.json`.

Recommended runtime fields:

```json
{
  "schema_version": 1,
  "ai_mode": "not_configured|cloud|local|custom",
  "quality_mode": "not_configured|cloud|balanced_local|compact_local|compact_local_combined|triage_only|custom",
  "primary_model_id": "string|null",
  "triage_model_id": "string|null",
  "effective_routing": {
    "primary": "string|null",
    "triage": "string|null"
  },
  "provider": "string|null",
  "custom_endpoint_name": "string|null",
  "feature_gates": {
    "cv_tailoring": true,
    "cover_letter_generation": true,
    "coach_interview_prep": true
  },
  "warnings": []
}
```

Configuration precedence:

1. Explicit runtime environment overrides, for example `HATCH_AI_MODE`, `HATCH_LLM_PROVIDER`, or explicit model/endpoint override variables, take highest precedence for operator/developer deployments.
2. `${HATCH_HOME}/config/ai_runtime.json` is the canonical easy-install runtime configuration.
3. Existing legacy configuration such as `data/profile.yaml` AI settings or existing `.env` model/provider settings is used only as a fallback when `ai_runtime.json` does not exist.
4. App defaults apply last and must resolve to `ai_mode=not_configured` rather than failing startup.

Secret precedence:

- API keys and tokens are never stored in `ai_setup_intent.json` or `ai_runtime.json`.
- For easy install, secrets come from `${HATCH_HOME}/config/secrets.env` or explicit environment variables. Legacy/developer flows may continue to use existing `.env`/environment handling.
- A provider API key being present must not force `ai_mode=cloud` by itself. Mode selection comes from explicit env override, `ai_runtime.json`, legacy AI config fallback, or default `not_configured`.

Legacy migration rule:

- On first easy-install run, if `ai_runtime.json` does not exist but legacy AI settings are found, `hatch status` or `hatch apply-ai-config` may offer to migrate them into `ai_runtime.json`.
- Migration must be non-destructive and must not remove legacy `.env`, `profile.yaml`, or model files.
- Existing developer/manual Docker behaviour must continue to read legacy configuration as before unless the easy-install runtime config is explicitly used.

### 23.6 Apply config and restart behaviour

`hatch apply-ai-config` must not silently restart services by default.

Default interactive behaviour:

1. Read `${HATCH_HOME}/config/ai_setup_intent.json`.
2. Validate selected mode, models, checksums, and required files.
3. Write effective runtime configuration.
4. Explain which services are affected.
5. Ask: “Restart Hatch now?”

Automation flags:

```bash
hatch apply-ai-config --yes --restart
hatch apply-ai-config --yes --no-restart
```

If run non-interactively without an explicit restart flag, apply config but do not restart. Print the next command: `hatch restart`.

### 23.7 Initial approved model catalogue

Initial catalogue is intentionally small. Approve only official Qwen GGUF models required for the three install tiers:

- Balanced local setup: Qwen3 8B primary + Qwen3 0.6B triage.
- Compact local setup: Qwen3 4B primary + Qwen3 0.6B triage.
- Triage-only local setup: Qwen3 0.6B triage.

All catalogue entries must use official Qwen Hugging Face repositories, Apache-2.0 licence, immutable source revisions, SHA-256 verification, and the role rules from section 7.2.

Catalogue entries:

```json
[
  {
    "id": "qwen3-0.6b-q8-triage",
    "display_name": "Qwen3 0.6B Q8 - fast triage",
    "role": "triage",
    "format": "gguf",
    "supported_os": ["linux", "macos", "windows"],
    "supported_arch": ["x86_64", "arm64", "aarch64"],
    "repo_id": "Qwen/Qwen3-0.6B-GGUF",
    "filename": "Qwen3-0.6B-Q8_0.gguf",
    "download_url_template": "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/{source_revision}/Qwen3-0.6B-Q8_0.gguf",
    "source_revision": "1eaf4d9657fe65ad10a51eab76a8db5b363bddaa",
    "sha256": "9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031",
    "download_size_gb": 0.639,
    "disk_required_gb": 1.0,
    "min_ram_gb": 4,
    "recommended_ram_gb": 8,
    "license": "apache-2.0",
    "source_trust": "official_qwen_huggingface"
  },
  {
    "id": "qwen3-4b-q4km-primary",
    "display_name": "Qwen3 4B Q4_K_M - compact primary",
    "role": "combined_capable_primary",
    "format": "gguf",
    "supported_os": ["linux", "macos", "windows"],
    "supported_arch": ["x86_64", "arm64", "aarch64"],
    "repo_id": "Qwen/Qwen3-4B-GGUF",
    "filename": "Qwen3-4B-Q4_K_M.gguf",
    "download_url_template": "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{source_revision}/Qwen3-4B-Q4_K_M.gguf",
    "source_revision": "a9a60d009fa7ff9606305047c2bf77ac25dbec49",
    "sha256": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
    "download_size_gb": 2.5,
    "disk_required_gb": 4.0,
    "min_ram_gb": 8,
    "recommended_ram_gb": 12,
    "license": "apache-2.0",
    "source_trust": "official_qwen_huggingface"
  },
  {
    "id": "qwen3-8b-q5km-primary",
    "display_name": "Qwen3 8B Q5_K_M - balanced primary",
    "role": "combined_capable_primary",
    "format": "gguf",
    "supported_os": ["linux", "macos", "windows"],
    "supported_arch": ["x86_64", "arm64", "aarch64"],
    "repo_id": "Qwen/Qwen3-8B-GGUF",
    "filename": "Qwen3-8B-Q5_K_M.gguf",
    "download_url_template": "https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/{source_revision}/Qwen3-8B-Q5_K_M.gguf",
    "source_revision": "6a569868d07d3bd59e8b97fb001bf8c0b254bb20",
    "sha256": "068bae163faa96ad48032daf4e071a6a28fe67d8dcc95367609c2ff165e52738",
    "download_size_gb": 5.85,
    "disk_required_gb": 7.0,
    "min_ram_gb": 12,
    "recommended_ram_gb": 16,
    "license": "apache-2.0",
    "source_trust": "official_qwen_huggingface"
  }
]
```

Implementation requirements:

- Do not add extra third-party model sources in this PR.
- Do not use `main`, `latest`, mutable tags, or other floating revisions in the implemented catalogue.
- The approved initial catalogue now includes immutable Hugging Face commit SHAs for all three entries. Keep those pinned unless implementation explicitly re-verifies a newer approved file, checksum, licence, and revision.
- Build the download URL from `download_url_template` and `source_revision`.
- SHA-256 verification is still mandatory even when an immutable revision is used; revision pinning protects reproducibility, while checksum verification protects integrity.
- Every downloaded file must be SHA-256 verified before becoming `ready`.
- Add a test or validation check that fails if any approved downloadable catalogue entry has `source_revision` equal to `main`, `latest`, empty, shorter than a full commit SHA, or any placeholder/non-commit value.
- Add a test or validation check that fails if any approved downloadable catalogue entry is missing `format`, `supported_os`, or `supported_arch`.
- Failed checksum verification must delete or quarantine the partial file and show a plain-language error.
- Additional models can be added later only with pinned source, licence, size, RAM guidance, and checksum.

### 23.8 Local AI fallback hierarchy

Governing decision: Qwen3 0.6B is a triage model only. It must never be assigned as the primary model for full Hatch features such as CV tailoring, cover-letter generation, or coach/interview prep.

A selected primary model may serve both primary and triage routing if the separate triage model is unavailable. This is an acceptable combined-role fallback for Qwen3 8B and Qwen3 4B only. It is not allowed for Qwen3 0.6B.

Decision hierarchy:

1. **Balanced local setup**
   - Use Qwen3 8B for `primary` tasks.
   - Use Qwen3 0.6B for `triage` tasks when compatible/available.
   - If Qwen3 0.6B is unavailable but Qwen3 8B is available, Qwen3 8B may serve both primary and triage routing.
   - This is the preferred local setup for CV tailoring, cover-letter generation, coach/interview prep, and higher-quality drafting.

2. **Compact local setup**
   - If 8B is not compatible but Qwen3 4B is compatible, use Qwen3 4B as the `primary` model.
   - Use Qwen3 0.6B for `triage` tasks when compatible/available.
   - If Qwen3 0.6B is unavailable but Qwen3 4B is available, Qwen3 4B must serve both primary and triage routing.
   - Label this as compact/local, not best quality.
   - This is acceptable for basic CV tailoring, cover-letter drafting, and coach flows with quality warnings.
   - If 4B serves both roles, show a performance warning because quick triage tasks may be slower than with a separate 0.6B triage model.

3. **Triage-only local setup**
   - If 8B and 4B are not compatible but Qwen3 0.6B is compatible, offer triage-only local mode.
   - Do not assign 0.6B as the default primary model for tailoring or coach features.
   - Quality-sensitive features must be disabled, not merely warned.
   - Mandatory disabled features in triage-only mode: `cv_tailoring`, `cover_letter_generation`, and `coach_interview_prep`.
   - Use triage-only mode for quick filtering, basic job summaries, smoke testing, and experimentation.

4. **No local AI**
   - If the machine is below the 0.6B minimum requirements as well, local AI is unavailable in beginner mode.
   - Offer cloud AI or configure-later mode.

Example effective config for compact fallback with separate triage model:

```json
{
  "ai_mode": "local",
  "quality_mode": "compact_local",
  "primary_model_id": "qwen3-4b-q4km-primary",
  "triage_model_id": "qwen3-0.6b-q8-triage",
  "effective_routing": {
    "primary": "qwen3-4b-q4km-primary",
    "triage": "qwen3-0.6b-q8-triage"
  },
  "warnings": [
    "This compact local setup uses Qwen3 4B for primary tasks. It is more useful than the 0.6B triage model for drafting and coach flows, but quality will be lower than the 8B setup."
  ]
}
```

Example effective config when 4B is available but 0.6B is not:

```json
{
  "ai_mode": "local",
  "quality_mode": "compact_local_combined",
  "primary_model_id": "qwen3-4b-q4km-primary",
  "triage_model_id": null,
  "effective_routing": {
    "primary": "qwen3-4b-q4km-primary",
    "triage": "qwen3-4b-q4km-primary"
  },
  "warnings": [
    "Qwen3 4B is serving both primary and triage tasks because the separate 0.6B triage model is unavailable. Quality-sensitive features remain available, but quick triage may be slower."
  ]
}
```

Example effective config for triage-only fallback:

```json
{
  "ai_mode": "local",
  "quality_mode": "triage_only",
  "primary_model_id": null,
  "triage_model_id": "qwen3-0.6b-q8-triage",
  "effective_routing": {
    "primary": null,
    "triage": "qwen3-0.6b-q8-triage"
  },
  "feature_gates": {
    "cv_tailoring": false,
    "cover_letter_generation": false,
    "coach_interview_prep": false
  },
  "warnings": [
    "This setup uses Qwen3 0.6B for triage only. CV tailoring, cover-letter generation, and coach/interview prep are disabled until you configure Qwen3 4B, Qwen3 8B, or a cloud provider."
  ]
}
```


### 23.9 Installing the `hatch` command without administrator access

Install the command wrapper into `${HATCH_HOME}/bin` by default. Do not require administrator/root access.

Linux/macOS:

- Create `${HATCH_HOME}/bin/hatch`.
- Make it executable.
- If `${HATCH_HOME}/bin` is not on `PATH`, print shell-specific instructions to add it.
- Do not write to `/usr/local/bin` unless the user explicitly chooses an advanced/admin install path.

Windows:

- Create `${HATCH_HOME}\bin\hatch.ps1`.
- Optionally create `${HATCH_HOME}\bin\hatch.cmd` as a convenience shim that invokes PowerShell.
- Do not require administrator access or machine-level PATH changes.
- If the user wants PATH integration, add only a user-level PATH entry after confirmation.
- Windows canonical state root is `%USERPROFILE%\.hatch` unless `%HATCH_HOME%` is set.

### 23.10 Security boundary

Backend/UI may prepare setup intent. Host CLI applies host changes.

Forbidden:

- backend Docker socket mount
- backend directly starting/stopping Docker services
- backend mounting arbitrary host GGUF paths
- UI-triggered silent service restart
- storing API keys in non-secret intent JSON
- backend writing `${HATCH_HOME}/config/secrets.env`
- UI/backend accepting API keys in v1

Allowed:

- backend reads/writes non-secret setup intent under `/hatch-home/config`
- host CLI reads intent and performs downloads, imports, secret writes, update/uninstall operations, compose selection, and restarts after confirmation
- UI displays the next CLI command when host action is required


### 23.11 Update and uninstall data-retention contract

`hatch update` and `hatch uninstall` are host-side CLI responsibilities. Backend/UI must not trigger them directly in v1.

`hatch update` must be safe by default:

- Update only managed easy-install source recorded in `${HATCH_HOME}/config/install.json`.
- Refuse by default on developer checkouts, unmanaged paths, or dirty checkouts.
- Create `${HATCH_HOME}/backups/update-<timestamp>/` before migrations or service changes.
- Preserve config, secrets, databases, generated documents, models, logs, app-lock state, and legacy developer files.
- Do not stop a running app if fetch or compose validation fails.
- Do not automatically rollback database migrations in v1; preserve backup and report recovery steps.

`hatch uninstall` must be non-destructive by default:

- Default uninstall removes easy-install containers and user-level shims only.
- `${HATCH_HOME}` is preserved by default.
- Databases, generated documents, models, secrets, config, probe results, logs, backups, and app-lock state are preserved by default.
- Destructive deletion requires explicit purge flags and confirmation.
- `--yes` alone is never enough to delete user data.
- No command may remove files outside `${HATCH_HOME}` or the recorded managed install source in v1.

### 23.12 Secret ownership contract

Secrets are owned by the host CLI.

- Backend/UI may write only non-secret setup intent.
- Backend/UI must not write `secrets.env`.
- Backend/UI must not accept API key values in v1.
- CLI command `hatch secrets set <provider>` is the only v1 path for writing provider secrets.
- CLI command `hatch secrets unset <provider>` is the only v1 path for removing provider secrets.
- Services consume secrets through env-file/environment mechanisms after `hatch apply-ai-config`.
