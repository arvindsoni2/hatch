# CLI Reference

The host `hatch` command manages easy-install lifecycle, AI setup, optional capabilities, and local maintenance.

> Last verified against `main`: 2026-07-10

## Core Commands

### `hatch start`

- Purpose: start the easy-install Compose stack
- Files changed: none directly
- Containers restarted: starts missing services
- Destructive: no

### `hatch stop`

- Purpose: stop the easy-install Compose stack
- Files changed: none
- Containers restarted: stops services
- Destructive: no

### `hatch restart`

- Purpose: restart the easy-install Compose stack
- Files changed: none
- Containers restarted: yes
- Destructive: no

### `hatch logs`

- Purpose: stream Compose logs for the current stack
- Files changed: none
- Containers restarted: no
- Destructive: no

### `hatch status`

- Purpose: print current runtime and capability summary
- Files changed: none
- Containers restarted: no
- Destructive: no

### `hatch doctor`

- Purpose: run local runtime checks
- Files changed: none
- Containers restarted: no
- Destructive: no

### `hatch probe`

- Purpose: collect a host-side hardware snapshot
- Files changed: `${HATCH_HOME}/probe/hardware_probe.json`, `${HATCH_HOME}/config/hardware_probe_latest.json`
- Containers restarted: no
- Destructive: no

### `hatch models list`

- Purpose: show supported models and current readiness
- Files changed: none
- Containers restarted: no
- Destructive: no

### `hatch models install [model_ids...] [--yes]`

- Purpose: download and verify supported GGUF models
- Files changed: `${HATCH_HOME}/models/*`, `${HATCH_HOME}/config/ai_setup_intent.json`
- Containers restarted: no
- Destructive: no

### `hatch models remove <model_id>`

- Purpose: remove a downloaded model with explicit runtime handling flags
- Files changed: model files and optional runtime intent
- Containers restarted: no
- Destructive: yes

### `hatch apply-ai-config [--yes] [--restart|--no-restart]`

- Purpose: convert setup intent plus secrets into effective runtime config
- Files changed: `${HATCH_HOME}/config/ai_runtime.json`
- Containers restarted: optional
- Destructive: no

## Capability Commands

### `hatch capabilities list`

- Purpose: list supported backend capability profiles

### `hatch capabilities status`

- Purpose: show the active backend profile and enabled optional capabilities

### `hatch capabilities enable <core|browser|local-embeddings|full>`

- Purpose: switch the backend profile
- Files changed: `${HATCH_HOME}/config/backend_capabilities.json`
- Containers restarted: no automatic restart by itself
- Destructive: no

### `hatch capabilities disable`

- Purpose: return to the `core` profile
- Files changed: `${HATCH_HOME}/config/backend_capabilities.json`

## Secret Commands

### `hatch secrets status`

- Purpose: show which supported provider secrets are present

### `hatch secrets set <provider>`

- Purpose: securely prompt for and store a provider secret
- Files changed: `${HATCH_HOME}/config/secrets.env`
- Destructive: no

### `hatch secrets unset <provider> [--yes]`

- Purpose: remove a stored provider secret
- Files changed: `${HATCH_HOME}/config/secrets.env`
- Destructive: yes

## Lifecycle Commands

### `hatch update [--dry-run] [--no-restart]`

- Purpose: update a managed easy-install checkout
- Files changed: `${HATCH_HOME}/backups/*`, managed checkout
- Containers restarted: yes unless `--no-restart`
- Destructive: no, but refused on dirty managed checkouts

### `hatch uninstall [--yes] [--purge-config] [--purge-models] [--purge-secrets] [--purge-data] [--purge-all]`

- Purpose: stop the stack and optionally remove selected local data
- Files changed: local user data depending on flags
- Containers restarted: stops services
- Destructive: yes when purge flags are used

## Windows Notes

- The PowerShell installer and wrappers support the same concepts as the shell script flow.
- Windows users should prefer `install-hatch.cmd` for first install and preflight.

## Example Flow

```bash
hatch status
hatch probe
hatch models list
hatch models install qwen3-small qwen3-medium --yes
hatch apply-ai-config
hatch capabilities enable full
```
