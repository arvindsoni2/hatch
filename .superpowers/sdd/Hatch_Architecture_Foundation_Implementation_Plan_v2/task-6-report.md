# Task 6 implementation report

## Scope

Replaced the incomplete Task 6 attempt with durable waiting, approval, and generic
`OUTCOME_UNKNOWN` reconciliation behavior. The implementation baseline is `f614e20`;
the overall implementation range is `f614e20..4834991`. Fix Round 2 is
`eb9c4bb..68a6570`; Fix Round 3 is based on `68a6570` and implemented by `4834991`.
Code/specification re-review remains pending.

## TDD evidence

Initial RED command:

```text
cd backend
python -m pytest -q --no-cov tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py
```

Observed: collection failed because the new `approvals` and `reconciliation` modules did
not exist (and the first draft’s test-relative import was corrected before implementation).
The replacement contract suite was then implemented against real isolated SQLite storage.

GREEN evidence:

```text
local Python 3.12.13 image
python -m pytest -q --no-cov tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py
23 passed in 110.30s

python -m pytest -q --no-cov tests/runtime/test_approvals.py::test_invalid_decision_metadata_leaves_approval_pending
1 passed in 5.57s

python -m ruff check app/runtime/workflow/approvals.py app/runtime/workflow/reconciliation.py app/runtime/workflow/kernel.py app/runtime/workflow/repository.py app/runtime/storage/sqlite.py tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py tests/runtime/workflow_test_support.py
All checks passed

python -m pytest -q --no-cov tests/runtime/test_claims.py tests/runtime/test_fencing.py tests/runtime/test_retries.py tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py tests/runtime/test_runtime_restart_recovery.py tests/runtime/test_sqlite_contention.py tests/runtime/test_event_atomicity.py
49 passed in 187.89s
```

## Behavior delivered

- `wait_for` requires the active claim and fencing token, validates `WaitingReason`,
  clears `current_claim_id`, and releases the claim in the same transaction.
- `resume_waiting` permits only approval/user-input waits and returns a claimable context;
  retry-time remains scheduler-owned.
- Approvals bind workflow/run/attempt scope, capability, exact canonical JSON SHA-256
  digest and algorithm identity. Decisions are bounded, expiry-aware, one-shot CAS
  transitions. Payload mutation invalidates both pending and approved records.
- Reconciliation registry handlers are process-local dispatch only; durable authority is
  repository state. An unknown outcome receives one fenced reconciler. Confirmation
  finalizes; not-found only retries under supplied policy; non-retryable effects finish
  terminally; handler failure restores durable unknown state for restart.

## Pending verification / concern

### Controller verification appended

This historical controller verification predates the current fix round.

```text
Current-tree Python 3.12 R2-focused gate: 50 passed in 5.74s.
Only 3 container pytest-cache permission warnings were emitted.

Full Python 3.12 backend suite with whole-repository mount:
3384 passed, 2 failed, 9 warnings in 417.76s.
```

Both full-suite failures were environment-only, not Task 6 product failures: the benchmark
manifest could not determine a clean Git worktree from the container bind mount and recorded
`working_tree_clean_before='not_recorded'`; the database setup test could not invoke absent
`make`. The two exact failed tests reran on the host without database access: 2 passed in
0.52s. Ruff on current Task 6/runtime paths, `git diff --check`, and documentation checks
passed.

`alembic heads` reports the sole head `s6t7u8v9w0x`. A raw fresh-database `alembic upgrade
head` failed at legacy revision `c30577e861e2` with `NoSuchTableError(applications)`. This is
pre-existing and not Task 6: the repository's canonical fresh-database bootstrap,
`python -m app.database_setup`, succeeded on isolated SQLite, stamped `s6t7u8v9w0x`, and
then `alembic current --check-heads` succeeded.

Do not claim review clean yet. Code/specification review remains pending.

## Fix round 1 resumed — contract audit and verification

The inherited partial diff was audited rather than assumed correct. The first isolated
Python 3.12 focused run exposed concrete failures: persisted attempt status is a string
(so reconciliation used an invalid `.value` lookup), direct approval-store decisions
accepted an unsafe actor identifier, the decision-reason boundary accepted arbitrary
slug-like content, and several tests did not reflect the now-required exact scope.

RED evidence:

```text
docker run ... python -m pytest -q --no-cov \
  tests/runtime/test_approvals.py::test_store_rejects_unsafe_actor_and_unregistered_reason_code \
  tests/runtime/test_reconciliation.py::test_stale_not_found_reconciliation_reports_ownership_loss

# approval-store boundary test failed before the actor/reason validation fix;
# reconciliation could not start its handler because persisted status was a string.

docker run ... python -m pytest -q --no-cov \
  tests/runtime/test_storage_contract.py::test_sqlite_repository_conforms_to_backend_neutral_workflow_store

# collection failed: the semantic WorkflowStore protocol did not yet exist.
```

GREEN evidence, all in an isolated disposable copy using the repository's local
`localhost/job_pilot_v2_backend:latest` Python 3.12.13 image:

```text
tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py
# 37 passed in 6.52s

tests/runtime/test_storage_contract.py tests/runtime/test_schema_migration.py
# 13 passed in 10.55s

R2 focused gate (claims, fencing, retries, waiting, approvals, reconciliation,
restart recovery, SQLite contention, event atomicity, storage and schema)
# 78 passed in 22.37s

ruff check --no-cache [changed Task 6 paths]
# All checks passed

python scripts/check_docs.py && git diff --check
# Documentation validation passed; diff check passed

alembic heads && python -m app.database_setup && alembic current --check-heads
# sole head t7u8v9w0x1y2; canonical isolated bootstrap and current-head check passed
```

The resumed work adds a linear additive migration `t7u8v9w0x1y2` from
`s6t7u8v9w0x` for durable reconciliation binding and claim purpose. Its upgrade,
downgrade, and re-upgrade are covered. Approval scope is deliberately exact at the
attempt level: request derives and persists its owning step/run, validation requires
all three IDs plus capability and canonical payload hash, and invalidation applies to
all active records for that attempt. ARCH-08 approval transitions append metadata-only
events in the same UoW; Task 6 deliberately enqueues no outbox entry because it
defines no delivery destination.

A broader Python 3.12 suite was also run from a disposable full-repository copy.
The runtime portion passed; the broad run exposed the known benchmark-manifest
environment limitation. Its exact single-test rerun failed because the copied worktree's
`.git` pointer is not mounted in the container, so it records
`working_tree_clean_before="not_recorded"` rather than a boolean. This is outside the
Task 6 runtime diff; the Task 6 focused gate is the authoritative result above.

## Fix round 2 — reconstructed restart and repository contract

Verified overall implementation range: `f614e20..4834991`. Fix Round 2 range:
`eb9c4bb..68a6570`; Fix Round 3 range: `68a6570..4834991`.
This round corrects the reviewer’s remaining evidence and seam findings without changing
workflow behavior:

- `WorkflowStore` is now the exact kernel-facing semantic repository protocol. Its explicit
  signatures match `SQLiteWorkflowRepository`, including keyword-only `create_run`, attempt
  reads, fencing, retry, waiting, and reconciliation transitions. The transaction-bound CRUD
  protocol is explicitly named `WorkflowRecordStore`.
- `WorkflowKernel.get_attempt` delegates to its injected `WorkflowStore`; a protocol-compatible
  in-memory repository proves a non-SQLite implementation is not bypassed.
- Restart tests persist synthetic work to file-backed SQLite, dispose the first engine, and
  reconstruct a new session factory, `SQLiteWorkflowRepository`, `WorkflowKernel`, registry,
  and reconciler. They prove a durable `artifact.publish` binding dispatches handler A rather
  than a registered handler B, and a reconciliation claim abandoned by the first process is
  recovered by the reconstructed kernel while remaining `OUTCOME_UNKNOWN`.

RED evidence (before this round’s production change):

```text
python -m pytest -q tests/runtime/test_storage_contract.py tests/runtime/test_reconciliation.py
# expected failures: WorkflowStore exposed lower-level **values CRUD rather than the
# repository signatures; WorkflowKernel.get_attempt bypassed the injected repository.
```

GREEN evidence:

```text
# Isolated local Python 3.12.13 backend image; synthetic file-backed SQLite only
python -m pytest -q --no-cov tests/runtime/test_storage_contract.py tests/runtime/test_reconciliation.py
# 20 passed in 3.24s

python -m pytest -q --no-cov \
  tests/runtime/test_claims.py tests/runtime/test_fencing.py \
  tests/runtime/test_retries.py tests/runtime/test_waiting.py \
  tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py \
  tests/runtime/test_runtime_restart_recovery.py tests/runtime/test_sqlite_contention.py \
  tests/runtime/test_event_atomicity.py tests/runtime/test_storage_contract.py \
  tests/runtime/test_schema_migration.py
# 79 passed in 20.18s

python -m ruff check [scoped runtime files] && python scripts/check_docs.py && git diff --check
# all passed

alembic heads && DATABASE_URL=sqlite+aiosqlite:////tmp/runtime-r2/runtime-r2.db \
  python -m app.database_setup && DATABASE_URL=sqlite+aiosqlite:////tmp/runtime-r2/runtime-r2.db \
  alembic current --check-heads
# sole head t7u8v9w0x1y2; canonical bootstrap/current-head passed
```

## Fix round 3 — return annotation and provenance

Fix Round 3 is based on `68a6570` and implemented by `4834991`. The repository
`create_run` method now explicitly returns `WorkflowRunRecord`, and the storage
contract test resolves and compares normalized return annotations in addition to
parameter names, kinds, and defaults.

RED evidence:

```text
python -m pytest -q --no-cov tests/runtime/test_storage_contract.py::test_sqlite_repository_matches_the_kernel_workflow_store_contract
# failed: concrete create_run return annotation was None while WorkflowStore required WorkflowRunRecord
```

GREEN evidence:

```text
python -m pytest -q --no-cov tests/runtime/test_storage_contract.py tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py
# 49 passed in 6.62s
```

Commit `4834991` is implementation-only. The subsequent evidence commit is
documentation-only and records this immutable implementation head without
self-referencing its own hash.

## Release fix round 1 — ownership deadline and lifecycle closure

Implementation commit `394bbfb`; evidence-only follow-up `eeeb184`; baseline
`fb4d6d2`. Strict RED was captured with 20 intended failures in the new synthetic
release-contract test before implementation. GREEN evidence: the final runtime gate
passed 148 tests in 31.33s, storage/schema/event/contention regression passed 22 tests
in 11.94s, and the full backend gate passed 3420 tests with 2 skipped in 440.22s.
Ruff, docs validation, and diff check passed. `alembic heads` reports sole head
`t7u8v9w0x1y2`; isolated `current --check-heads` blocked without output and was
interrupted, so no unsupported current-head success is claimed. Host Python is 3.14.7;
`python3.12` is unavailable. Fixtures are isolated synthetic SQLite only.

## Release fix round 2 — reconciliation completion and bounded poison recovery

Implementation commit `e9ae56c`, based on release evidence `eeeb184`. The inherited
partial diff was audited before use. It provides a fresh injected reconciler clock after
every handler path, aggregate lifecycle synchronization and rollback, durable bounded
per-record recovery disposition, and additive migration `u8v9w0x1y2z3` from
`t7u8v9w0x1y2`.

TDD evidence: the inherited implementer recorded RED for the post-handler clock cases;
the audited exact/after-expiry confirmed/retry/terminal/error cases and poisoned recovery
fairness cases are green below. All fixtures are isolated synthetic SQLite.

```text
Python 3.12.13 image:
core R2 runtime/storage/event/contention: 66 passed in 10.54s
reconciliation plus release contracts: 56 passed in 12.02s
schema/migration: 4 passed in 14.14s
# 126 cases collected across the three focused gates.

ruff (all changed runtime, migration, and test paths): passed
docs validation and git diff --check: passed
canonical isolated app.database_setup, alembic heads, and current --check-heads:
# sole/current head u8v9w0x1y2z3

full Python 3.12 backend: 3448 passed, 2 failed, 6 warnings in 441.65s.
# The two failures are container-only: inaccessible mounted Git metadata in a benchmark
# provenance assertion and absent `make` in the image. Exact host rerun: 2 passed in 0.51s.
```

The tracked evidence commit following `e9ae56c` replaces stale pre-fix counts/ranges and
records the container limitation without claiming that the complete container suite passed.

## Release fix round 4 — proof closure

Implementation/test head: `07b89df48be55b63e5958b8aefeccd431f3740ac`.
The release-contract tests passed 43/43, and the combined reconciliation plus release
focused gate passed 60/60 on the available host Python 3.14.7. Python 3.12 is not
installed in this environment. Runtime collection reports 169 tests. The full runtime
execution was attempted but stalled in the existing approval test before a reliable
completion count could be produced, so no full-suite pass is claimed. Ruff and
`git diff --check` passed. Scoped re-review remains pending.

## Release fix round 5 — exhaustive lifecycle and deferred-claim proof

Implementation/test head: `95ffd30` (this evidence commit deliberately does not
self-reference). This proof-only round changes no production code. It expands
release snapshots to every persisted task-attempt, workflow-step, workflow-run,
and execution-claim field, then compares a deep-copied before image with only
the explicit transition deltas. It covers final success, delayed retry creation,
due promotion, delayed final success, budget terminal failure, explicit terminal
failure, ordinary expired recovery, `OUTCOME_UNKNOWN` expired recovery, rollback,
and the deferred reconciliation claim lifecycle. Scoped attempt and claim counts
are asserted before and after each covered transition.

The deferred `OUTCOME_UNKNOWN` proof records the full reconciliation-claim image
before poison. Deferral may change only `recovery_not_before`,
`recovery_failure_count`, and the stable recovery error code; stale alternate
claim/finalize/fail/return operations leave the full image untouched. At due
recovery the original claim becomes expired with `released_at=due`, while its
lease, fence, purpose, and durable capability binding remain exact; a replacement
reconciliation claim has a strictly higher fence and the reconciliation purpose.

TDD evidence: the initial expanded due-promotion expectation failed because it
expected `not_before` to clear. The persisted contract deliberately retains that
timestamp as retry-schedule provenance; the corrected explicit expectation now
asserts the exact retained value. No production defect was exposed.

```text
Authoritative local backend development container: Python 3.12.13
python -m pytest --no-cov -q tests/runtime/test_release_contract.py tests/runtime/test_reconciliation.py
# 61 passed in 15.86s (release-contract 44; reconciliation 17).

python -m pytest --no-cov -p no:cacheprovider --collect-only -q -o log_cli=false tests/runtime
# 170 tests collected in 0.94s.

Full Python 3.12 runtime execution was invoked repeatedly with the same isolated
synthetic SQLite suite. The execution transport returned partial/empty output
around the release-contract midpoint despite no surviving pytest/container process,
so it did not provide a reliable final execution count. It is not claimed passed.

python -m ruff check tests/runtime/test_release_contract.py
python scripts/check_docs.py
git diff --check
# all passed.
```

The focused 61-case Python 3.12 result is authoritative. All fixtures are synthetic,
file-backed SQLite databases; no Coach API, media, transcript, deletion, export, or
production data boundary is touched. Review remains pending.
