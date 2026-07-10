---
title: Hatch Data And Storage
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

# Data And Storage

Hatch uses local files plus SQLite databases. The exact location differs slightly between developer/manual installs and easy installs.

## Storage Summary

| Data category | Storage location | Sensitive | Back up | Removed by reset | Removed by uninstall |
|---|---|---:|---:|---:|---:|
| Application database | `data/jobpilot.db` | Yes | Yes | Yes | Only with `--purge-data` |
| LangGraph checkpoints | `data/langgraph_checkpoints.db*` | Yes | Optional | Yes | Only with `--purge-data` |
| Profile and preferences | `data/profile.yaml` | Yes | Yes | Reset unless `--keep-profile` | Only with `--purge-data` |
| App-lock state | SQLite tables in `data/jobpilot.db` | Yes | Yes | Preserved by app-lock reset | Only with `--purge-data` |
| Master CV JSON and metadata | `data/master_cv.json`, `data/master_cv.meta.json` | Yes | Yes | Yes unless `--keep-profile` | Only with `--purge-data` |
| Imported resume files | `data/master_resume.*` | Yes | Yes | Yes unless `--keep-profile` | Only with `--purge-data` |
| Generated documents | `data/generated/` | Yes | Optional | Yes | Only with `--purge-data` |
| Coach recordings | `data/recordings/` | Yes | Optional | Yes | Only with `--purge-data` |
| Upload temp files | `data/uploads/` | Maybe | No | Yes | Only with `--purge-data` |
| Host setup intent | `${HATCH_HOME}/config/ai_setup_intent.json` | No secret | Optional | Not removed by `reset-user-data.sh` | Preserved unless config is purged |
| Host runtime config | `${HATCH_HOME}/config/ai_runtime.json` | No secret | Optional | Not removed by `reset-user-data.sh` | Preserved unless config is purged |
| Host secrets | `${HATCH_HOME}/config/secrets.env` | Yes | Yes | Preserved by default | Removed only with `--purge-secrets` |
| Backend capabilities | `${HATCH_HOME}/config/backend_capabilities.json` | No | Optional | Preserved | Preserved unless config is purged |
| Probe results | `${HATCH_HOME}/probe/` and `${HATCH_HOME}/config/hardware_probe_latest.json` | Low | Optional | Preserved | Preserved unless config is purged |
| Local model files | `${HATCH_HOME}/models/` or `data/models/` | No | Optional | Preserved | Removed only with `--purge-models` |
| Host logs | `${HATCH_HOME}/logs/` | Maybe | Optional | Preserved | Preserved unless config/home is purged |
| Installer backups | `${HATCH_HOME}/backups/` | Maybe | Optional | Preserved | Preserved unless home is purged |

## Backup-Relevant Paths

Back up these first:

- `data/`
- `${HATCH_HOME}/config/`
- `${HATCH_HOME}/models/` if local model downloads are expensive to replace

## Reset And Uninstall Rules

- `scripts/reset-user-data.sh` removes workflow data and can preserve profile and secrets.
- `scripts/reset-app-lock.sh` clears only app-lock configuration and sessions.
- `hatch uninstall` preserves user data unless purge flags are supplied.
