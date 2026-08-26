# R2 workflow-kernel evidence

## Scope and authority

- Baseline/head: `f7e678f`; Task 6 commit pending.
- Architecture SHA-256: `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36`.
- Foundation spec SHA-256: `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`.
- Coach V6 SHA-256: `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`.
- Fixtures are isolated file-backed SQLite databases and contain only synthetic IDs,
  payload references, and result references.

| Contract / invariant | RED test and observed failure | Implementation files | GREEN verification | Result |
|---|---|---|---|---|
| `INV-WF-004`: waiting owns no worker claim | Initial Task 6 RED collection failed because `wait_for`, `resume_waiting`, and the new contract modules were absent. | `workflow/kernel.py`, `workflow/repository.py`, `test_waiting.py` | Python 3.12 focused suite | Waiting releases the current fenced claim atomically; only approval/user-input waits may resume and their next claim advances fencing. |
| `INV-APP-001`: approval binds exact payload | Initial Task 6 RED collection failed because `approvals.py` was absent. | `workflow/approvals.py`, `storage/sqlite.py`, `test_approvals.py` | Python 3.12 focused suite | SHA-256 canonical UTF-8 JSON, algorithm identity, capability, expiry, scope, and one-shot decisions are all checked. Payload change invalidates pending and approved records. |
| `INV-EXE-003`: ambiguous external outcome reconciles before retry | Initial Task 6 RED collection failed because `reconciliation.py` and `mark_outcome_unknown` were absent. | `workflow/reconciliation.py`, `workflow/kernel.py`, `workflow/repository.py`, `test_reconciliation.py` | Python 3.12 focused suite | An `OUTCOME_UNKNOWN` attempt has no normal claimant; one fenced reconciler invokes the registered check. Confirmed finalizes; not-found can retry only through explicit retry policy; non-retryable effects terminalize. |
| Atomic rollback / stale ownership | Negative waiting, invalid approval-scope, expiry/race, handler-failure, and concurrent reconciler tests. | Same as above | Python 3.12 focused suite | Conditional updates preserve prior state on invalid/stale inputs; handler failures restore durable `OUTCOME_UNKNOWN`. |

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
# one head: s6t7u8v9w0x
```

Fresh database migration verification:

```text
alembic upgrade head
# failed at legacy revision c30577e861e2 with NoSuchTableError(applications)

python -m app.database_setup
# succeeded on fresh isolated SQLite; stamped s6t7u8v9w0x

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
- Code/specification review is still pending; this evidence does not claim review clean.
- The changes are additive Task 6 runtime code and tests. Rolling back the Task 6 commit
  removes the behavior; no Task 6 schema migration is introduced because the reviewed R1
  `runtime_approvals` table already contains the required durable fields.
