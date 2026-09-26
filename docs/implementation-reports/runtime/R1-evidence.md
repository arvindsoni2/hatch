---
document_type: implementation-spec
status: active
implementation_status: complete
applies_to: runtime/r1-contracts-persistence-events
last_verified: 2026-08-25
---

# R1 Runtime Contracts, Persistence, Events, and Outbox Evidence

## Scope

R1 adds the architecture foundation only. All product slice modes still default to `LEGACY`; no Job Scoring, CV Tailoring, Cover Letter, or Coach route was migrated to the new runtime.

The implementation provides immutable task contracts, explicit migration-mode selection, 17 additive runtime tables, transaction-scoped semantic repositories, atomic state/event/outbox persistence, fenced at-least-once outbox delivery, and metadata-only privacy guards.

## Git baseline

- Merged R0 baseline: `971867de770a3e2ffec8679c6383f95aec50daaa`
- R1 branch: `runtime/r1-contracts-persistence-events`
- Task contracts commit: `f1a3937`
- Durable schema/store commit: `e7983b9`
- Isolated worktree: `.worktrees/runtime-r1-contracts-persistence-events`

The unrelated untracked Coach PDF in the original checkout remains untouched.

## Invariant evidence

| Invariant | Executed evidence |
| --- | --- |
| `INV-CTR-001` | `test_task_spec.py` proves frozen/versioned task contracts, bounded policies, typed IDs, canonical enums, and Pydantic I/O boundaries. |
| `INV-DB-001` | `test_event_atomicity.py` injects failure after state, event, and outbox writes and proves all three roll back together. |
| `INV-DB-002` | `test_storage_contract.py` proves attempt N remains terminal and retry N+1 preserves its reason, policy identity, wait state, and prior-attempt link. |
| `INV-EVT-001` | Atomicity tests prove an outbox row cannot survive a rolled-back event transaction. |
| `INV-EVT-002` | `test_outbox_store.py` proves append-only delivery attempts, stable `event_id` across retry, stale-fence rejection, single ownership under concurrent claims, and bounded SQLite lock recovery. |
| `INV-PRV-001` | `test_runtime_privacy.py` proves CV, transcript, prompt, file-path, alias, outbox diagnostic, sensitivity, and shadow-metric canaries are rejected before durable persistence. |

## Schema and transaction results

- Alembic has exactly one head: `r5s6t7u8v9w0`.
- Upgrade from `q4r5s6t7u8v9` creates all 17 runtime tables.
- Downgrade to `q4r5s6t7u8v9` removes only runtime additions and preserves a pre-existing Coach session row.
- Fresh canonical setup creates every registered table and reports no schema drift.
- SQLite integrity and foreign-key checks pass.
- Every repository within a runtime UoW shares one `AsyncSession`; repositories never commit independently.
- Supported outbox destinations are limited to `runtime.telemetry`, `runtime.evaluation`, and `runtime.notification`.

## Review record

Independent specification and quality/security reviews were requested after the first Task 4 implementation. Important findings covered incomplete semantic store operations, privacy enforcement outside events, unrestricted outbox error detail, and SQLite claim contention.

The implementation was revised to add the full Approval/Evaluation/Shadow/Outbox store seams, metadata-only enforcement across JSON-bearing store operations, strict event metadata/sensitivity validation, disabled raw outbox error details, conditional fencing, bounded claim and finalization lock retries, and regression tests for each finding. The optional `(event_id, destination)` uniqueness suggestion was not adopted because the approved schema declares no such uniqueness and the delivery contract is explicitly at-least-once with consumer deduplication by `event_id`.

## Verification results

R1 invariant gate:

```text
46 passed
```

Canonical database setup suite:

```text
17 passed
```

Backend health regression:

```text
1 passed
```

Static and documentation checks:

```text
All checks passed!
Documentation validation passed.
```

All pytest runs emitted the pre-existing environment-level `RequestsDependencyWarning` for the installed HTTP dependency combination. It did not affect outcomes.
