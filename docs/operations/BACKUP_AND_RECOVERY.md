# Backup And Recovery

Back up local data before risky updates, manual cleanup, or machine migration.

> Last verified against `main`: 2026-07-10

## What To Back Up

- `data/`
- `${HATCH_HOME}/config/`
- `${HATCH_HOME}/models/` when local model downloads are expensive to replace

## Suggested Backup Procedure

1. Stop Hatch.
2. Copy the local data and config directories to a safe location.
3. Preserve file permissions where possible.

## Restore Procedure

1. Stop Hatch.
2. Restore `data/` and `${HATCH_HOME}/config/`.
3. Restore `${HATCH_HOME}/models/` if using local AI.
4. Start Hatch and check `hatch status`.

## Reset Versus Uninstall

- `scripts/reset-user-data.sh` clears workflow state and can preserve profile and secrets.
- `scripts/reset-app-lock.sh` clears only app-lock config and sessions.
- `hatch uninstall` preserves user data unless purge flags are supplied.

## Failed Update Recovery

Managed updates back up config and data under `${HATCH_HOME}/backups/`. If `hatch update` fails after backup creation, restore the relevant snapshot manually and re-run verification.

## Conversational Coach release gate

This application PR does not execute a Coach-specific destructive database
restore command. The supported release process owns update backups and restore
rehearsals. When a release artifact containing Conversational Coach is promoted,
run the supported Hatch-managed backup/restore rehearsal, then verify report
reads, deletion receipts, and media cleanup in an isolated environment. Record
that rehearsal in the release evidence; do not invent or run an ad-hoc restore
against a user database.

Before enabling `HATCH_COACH_CONVERSATIONAL_ENABLED`, retain the benchmark
manifest, security-gate results, and owner acceptance. To roll back creation,
set the flag to `false`; do not undo privacy deletion jobs or restore deleted
candidate content.

## Broken Configuration Recovery

Useful recovery commands:

```bash
hatch status
hatch doctor
bash scripts/reset-app-lock.sh
bash scripts/reset-user-data.sh --keep-profile
```
