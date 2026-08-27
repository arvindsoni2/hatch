# R2 workflow-kernel evidence

## Scope and immutable provenance

- R1 baseline: `fb4d6d2`.
- Overall R2 implementation range: `fb4d6d2..8c53fcc`.
- Latest release-fix implementation head: `8c53fcc`
  (`fix(workflow): fence deferred recovery reclaims`).
- Task 5 implementation and fixes: `f637490`, `c3d5f3e`, `f7e678f`.
- Task 6 implementation and fixes: `f614e20`, `eb9c4bb`, `68a6570`, `4834991`.
- Prior release hardening: `394bbfb`; release recovery hardening: `e9ae56c`; final
  deferred-reclaim CAS hardening: `8c53fcc`.
- Prior evidence-only commits: `bb59fe6`, `eeeb184`. This evidence is a docs-only
  follow-up and does not self-reference its own commit ID.
- Architecture SHA-256: `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36`.
- Foundation spec SHA-256: `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`.
- Coach V6 SHA-256: `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`.

All runtime tests use disposable SQLite databases and synthetic identifiers,
metadata references, and result references only. R2 changes generic workflow
records; it does not change Coach routes, commands, media, transcripts, deletion,
exports, UI sinks, telemetry, or domain finalizers.

## Release-fix controls

- Reconciliation reads a fresh injected clock after every external handler outcome.
  Confirmed, retry, terminal not-found, and handler-error paths refuse to mutate at
  exact lease expiry and just after it.
- Claim, attempt, step, and run lifecycles are synchronized in the same UoW for
  claim, wait/resume, retry, terminal failure, success, expiry recovery, and
  `OUTCOME_UNKNOWN` recovery. An injected aggregate-sync failure rolls all of those
  records back together.
- Terminal failure reasons and recovery errors are bounded stable codes. Unsafe
  prompt, transcript/CV, path, model-output, whitespace, boolean, and oversized
  values reject without changing durable ownership.
- Expired-claim recovery validates batch sizes (1--100), pages deterministically,
  commits per record, and continues after a poisoned record. A failed recovery stores
  only `recovery_not_before`, incremented `recovery_failure_count`, and
  `recovery_failed`; it does not extend the execution lease or store exception text.
  Deferred work becomes eligible again after the bounded delay, so it cannot starve
  later records.
- Both the ordinary reclaim and per-record reconciliation compare-and-swap operations
  recheck `recovery_not_before` after selection. Thus a recovery deferral committed
  between selection and mutation cannot authorize a stale worker. Reconciliation
  claims cannot bypass that disposition: the active claim remains the attempt's
  current fenced owner until a due recovery releases it.
- Additive migration `u8v9w0x1y2z3` extends `runtime_execution_claims` with the
  recovery disposition fields. It follows `t7u8v9w0x1y2` and leaves one Alembic head.

## TDD and verification

The release-contract suite was written RED first (20 intended failures for missing
lease, aggregate, stable-code, and recovery controls), then turned GREEN. The final
release-fix audit added deterministic post-handler clock and poisoned-recovery cases
to the inherited partial change. Fix Round 3 added a deterministic stale-reclaim RED
case: after selection, a committed `recovery_not_before` still allowed reclaim to
create a new claim. The final CAS guard turns that case GREEN; it is not a timing test.
The authoritative Python 3.12 gates are below.

```text
# Isolated Python 3.12.13 backend image; synthetic disposable SQLite only
python -m pytest -q --no-cov \
  tests/runtime/test_claims.py tests/runtime/test_fencing.py \
  tests/runtime/test_retries.py tests/runtime/test_waiting.py \
  tests/runtime/test_approvals.py tests/runtime/test_runtime_restart_recovery.py \
  tests/runtime/test_sqlite_contention.py tests/runtime/test_event_atomicity.py \
  tests/runtime/test_storage_contract.py
# 66 passed in 10.54s

python -m pytest -q --no-cov tests/runtime/test_release_contract.py
# 42 passed in 7.27s

python -m pytest -q --no-cov tests/runtime
# 168 passed; includes reconciliation, storage, schema, event-atomicity,
# SQLite contention, restart, approvals, and release-contract coverage.

python -m pytest -q --no-cov tests/runtime/test_schema_migration.py
# 4 passed in 14.14s

# The focused release/reconciliation pair collects 59 cases; the complete runtime
# suite collects 168 cases.

python -m ruff check --no-cache [all changed runtime, migration, and test paths]
# All checks passed.

python scripts/check_docs.py
git diff --check
# Documentation validation passed; diff check passed.

python -m app.database_setup
alembic heads
alembic current --check-heads
# Canonical isolated SQLite setup succeeded; sole/current head is u8v9w0x1y2z3.
```

The full Python 3.12 backend suite was also run in the same isolated container:
`3448 passed, 2 failed, 6 warnings in 441.65s`. The two failures are verification
container limitations outside this diff: the benchmark manifest cannot read the
worktree's Git metadata through the disposable mount and records
`working_tree_clean_before="not_recorded"`; the canonical setup server test cannot
find `make` in the image. Both exact tests reran on the host where Git metadata and
`/usr/bin/make` are available: `2 passed in 0.51s` (host Python 3.14.7; one existing
requests/urllib3 compatibility warning). This is not a claim that the container full
suite passed; the focused Python 3.12 release gate above is the authoritative R2
product result.

## Security disposition, rollback, and review

Applicable generic controls are covered by isolated synthetic fixtures, negative
state/claim/approval input validation, replay/race and stale-worker fencing,
exact-expiry fencing, contention/restart coverage, bounded recovery fairness, and
atomic rollback. No candidate, transcript, evidence, CV, raw media, secret, or
untrusted exception text is captured in this evidence. Coach-specific V6 boundary
classes are not applicable because no Coach boundary changed.

Rollback is code-first. Revert `8c53fcc` together with the R2 implementation range
only after checking for active workflow claims that need recovery. Migration
`u8v9w0x1y2z3` has an additive downgrade that removes only its three recovery
disposition columns; use it only after confirming those durable fields are no longer
needed. Review disposition: final whole-branch review pending.
