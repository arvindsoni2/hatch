# R2 workflow-kernel evidence

## Scope and authority

- Current fix verification range: `f614e20..HEAD` (symbolic `HEAD` until the immutable
  fix-round commit is created).
- Architecture SHA-256: `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36`.
- Foundation spec SHA-256: `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`.
- Coach V6 SHA-256: `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`.
- Fixtures are isolated file-backed SQLite databases and contain only synthetic IDs,
  payload references, and result references.

| Contract / invariant | RED test and observed failure | Implementation files | GREEN verification | Result |
|---|---|---|---|---|
| `INV-WF-004`: waiting owns no worker claim | Initial Task 6 RED collection failed because `wait_for`, `resume_waiting`, and the new contract modules were absent. | `workflow/kernel.py`, `workflow/repository.py`, `test_waiting.py` | Python 3.12 focused suite | Waiting releases the current fenced claim atomically; only approval/user-input waits may resume and their next claim advances fencing. |
| `INV-APP-001`: approval binds exact payload | Initial Task 6 RED collection failed because `approvals.py` was absent. | `workflow/approvals.py`, `storage/sqlite.py`, `test_approvals.py` | Python 3.12 focused suite | SHA-256 canonical UTF-8 JSON, algorithm identity, capability, expiry, scope, and one-shot decisions are all checked. Payload change invalidates pending and approved records. |
| `INV-EXE-003`: ambiguous external outcome reconciles before retry | Initial Task 6 RED collection failed because `reconciliation.py` and `mark_outcome_unknown` were absent. | `workflow/reconciliation.py`, `workflow/kernel.py`, `workflow/repository.py`, `test_reconciliation.py` | Python 3.12 focused suite | An `OUTCOME_UNKNOWN` attempt has no normal claimant; one fenced reconciler invokes the durably-bound capability check. Confirmed finalizes; not-found can retry only through explicit retry policy; non-retryable effects terminalize. |
| Atomic rollback / stale ownership | Negative waiting, invalid approval-scope, expiry/race, handler-failure, and concurrent reconciler tests. | Same as above | Python 3.12 focused suite | Conditional updates preserve prior state on invalid/stale inputs; handler failures restore durable `OUTCOME_UNKNOWN`. |

### Fix round 1 audit additions

The inherited partial Task 6 diff was independently re-tested. The RED cases exposed
unsafe direct-store approval metadata, an invalid persisted-status `.value` access in
reconciliation, and a missing backend-neutral durable-store protocol. The corrective
tests prove scheduler-only retry waiting, exact run/step/attempt/capability/payload
approval scope, JSON-native canonical values and string keys, fixed digest vectors,
bounded reason-code and actor metadata at public and store boundaries, stale `NOT_FOUND`
ownership loss, reconciling crash/lease expiry, durable capability/version/idempotency/
reference binding, and direct restart recovery after a handler failure.

### Fix round 2 audit additions

The final review corrections replace the coarse runtime-only conformance check with an
explicit `WorkflowStore` semantic protocol whose method names, parameter kinds, and defaults
match `SQLiteWorkflowRepository`. `WorkflowRecordStore` is the intentionally narrower
transaction-bound CRUD interface used by `RuntimeUnitOfWork.workflows`. A protocol-compatible
in-memory workflow repository proves `WorkflowKernel.get_attempt` delegates through the injected
semantic store rather than opening a SQLite unit of work directly.

Restart evidence is now a real reconstruction rather than reuse of the same object: each test
persists synthetic data to file-backed SQLite, disposes the first engine, then creates a new
engine/session factory/repository/kernel and a new reconciliation registry/reconciler. The
durable `artifact.publish` capability/version binding dispatches handler A even when handler B
is present in the restarted registry. A reconciliation claim abandoned before process loss is
recovered only as `OUTCOME_UNKNOWN` by the reconstructed kernel, never as normal executable
work. The same tests retain atomic rollback coverage through conditional claim transitions.

ARCH-08 coverage additionally proves `approval.requested`, `approval.granted`,
`approval.denied`, `approval.expired`, and `approval.invalidated` append metadata-only
runtime events in the same UoW. The injected decision failure leaves no granted event
or approval state behind; the already-committed requested event remains. Task 6 has no
delivery destination, so these runtime events deliberately create no outbox entry.

## Commands and observed evidence

```text
# Host Python 3.14 (collection/static only; aiosqlite 0.22.1 connects indefinitely)
python -m pytest -q --collect-only --no-cov tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py
# 22 tests collected, exit 0 (before one later non-retryable case was added)

python -m ruff check app/runtime/workflow/approvals.py app/runtime/workflow/reconciliation.py app/runtime/workflow/kernel.py app/runtime/workflow/repository.py app/runtime/storage/sqlite.py tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py tests/runtime/workflow_test_support.py
# exit 0, All checks passed

# Isolated local image localhost/job_pilot_v2_backend:latest, Python 3.12.13
python -m pytest -q --no-cov tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py
# 23 passed in 110.30s

# Current follow-up metadata-negative case after the focused run
python -m pytest -q --no-cov tests/runtime/test_approvals.py::test_invalid_decision_metadata_leaves_approval_pending
# 1 passed in 5.57s
```

```text
# Same isolated Python 3.12 image
python -m pytest -q --no-cov tests/runtime/test_claims.py tests/runtime/test_fencing.py tests/runtime/test_retries.py tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py tests/runtime/test_runtime_restart_recovery.py tests/runtime/test_sqlite_contention.py tests/runtime/test_event_atomicity.py
# 49 passed in 187.89s
```

```text
# Fix round 1 — local Python 3.12.13 image, disposable full backend copy
python -m pytest -q -o cache_dir=/tmp/pytest-cache --no-cov \
  tests/runtime/test_claims.py tests/runtime/test_fencing.py \
  tests/runtime/test_retries.py tests/runtime/test_waiting.py \
  tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py \
  tests/runtime/test_runtime_restart_recovery.py tests/runtime/test_sqlite_contention.py \
  tests/runtime/test_event_atomicity.py tests/runtime/test_storage_contract.py \
  tests/runtime/test_schema_migration.py
# 78 passed in 22.37s

python -m ruff check --no-cache [Task 6 runtime and test paths]
# All checks passed

python scripts/check_docs.py && git diff --check
# passed

alembic heads && python -m app.database_setup && alembic current --check-heads
# sole head t7u8v9w0x1y2; canonical isolated bootstrap/current-head passed
```

```text
# Fix round 2 RED, before the semantic-store implementation
python -m pytest -q tests/runtime/test_storage_contract.py tests/runtime/test_reconciliation.py
# failed because the protocol exposed lower-level **values CRUD and get_attempt bypassed
# the injected repository.

# Fix round 2 GREEN, isolated synthetic SQLite databases
python -m pytest -q --no-cov tests/runtime/test_storage_contract.py tests/runtime/test_reconciliation.py
# Python 3.12.13: 20 passed in 3.24s

# Full R2 runtime gate, same isolated Python 3.12.13 container copy
python -m pytest -q --no-cov [claims, fencing, retries, waiting, approvals,
  reconciliation, restart recovery, SQLite contention, event atomicity, storage, schema]
# 79 passed in 20.18s

# Scoped Ruff, docs, and diff checks
# all passed

alembic heads && DATABASE_URL=sqlite+aiosqlite:////tmp/runtime-r2/runtime-r2.db \
  python -m app.database_setup && DATABASE_URL=sqlite+aiosqlite:////tmp/runtime-r2/runtime-r2.db \
  alembic current --check-heads
# sole head t7u8v9w0x1y2; canonical bootstrap/current-head passed
```

## Controller verification

```text
# Current tree, isolated Python 3.12 container
R2 focused gate
# 50 passed in 5.74s; 3 pytest-cache permission warnings only

Full backend suite with whole repository mount
# 3384 passed, 2 failed, 9 warnings in 417.76s

# The two failed tests were environment-only:
# - benchmark manifest recorded working_tree_clean_before='not_recorded' because the
#   container bind mount did not provide usable Git metadata;
# - database setup test could not invoke absent `make` in the container.
# Exact failed tests rerun on the host (non-DB): 2 passed in 0.52s.

Ruff on current Task 6/runtime paths plus git diff --check
# passed

python scripts/check_docs.py
# passed

alembic heads
# one head: t7u8v9w0x1y2
```

Fresh database migration verification:

```text
alembic upgrade head
# failed at legacy revision c30577e861e2 with NoSuchTableError(applications)

python -m app.database_setup
# succeeded on fresh isolated SQLite; stamped t7u8v9w0x1y2

alembic current --check-heads
# succeeded after canonical bootstrap
```

The raw fresh-database `alembic upgrade head` limitation is pre-existing and not a Task 6
regression. The repository's supported fresh-database path is the canonical
`python -m app.database_setup` bootstrap, which completed successfully.

## Security disposition

R2 touches generic runtime workflow records only. No Coach route, command, media,
transcript, deletion, export, UI, logging/telemetry sink, or domain finalizer changed;
Coach V6 boundary controls are therefore not applicable to this diff. Binding generic
coverage includes invalid metadata, payload/algorithm/capability mismatch, stale claims,
one-shot decision replay, approval race, handler failure/restart, concurrent reconciler
ownership, and safe SQLite transaction rollback. No sensitive payload is persisted in
the approval record; only a bounded canonical digest and stable identifiers are stored.

## Limitations and rollback

- Host `/usr/bin/python` is Python 3.14.7 and installed `aiosqlite 0.22.1` hangs before
  workflow code runs. Database verification therefore uses the repository’s local
  Python 3.12 image.
- Full backend verification has no product regression: its two container-only failures
  passed as exact host reruns. The isolated canonical bootstrap reached the sole Alembic
  head and passed `alembic current --check-heads`.
- A fresh broad-suite attempt from a disposable full-repository Python 3.12 copy reached
  the runtime suite with all Task 6 tests passing but did not provide a passing broad
  verdict: `tests/benchmarks/test_runner.py::test_runner_ranks_gate_pass_rate_before_quality`
  sees `working_tree_clean_before="not_recorded"`. The copied worktree's `.git` pointer
  resolves outside the container, so this benchmark provenance assertion cannot observe
  Git state. Its exact rerun reproduces that container-only setup limitation; it is not
  a Task 6 product failure.
- Code/specification review is still pending; this evidence does not claim review clean.
- The changes include additive migration `t7u8v9w0x1y2` from `s6t7u8v9w0x`, adding the
  durable reconciliation binding and execution-claim purpose. Rollback requires the
  migration downgrade before reverting the Task 6 code.
