# Task 11 implementation report

Status: `DONE_WITH_CONCERNS` pending the controller-authorized whole-repository Python 3.12 gate.

## Scope

Implemented the generic, product-independent Task 11 contracts: finite deterministic-first
evaluation, declared evaluator provenance/lineage, shared-facade OTel correlation, fail-open
telemetry, normal deployment capture policy validation, and normal-mode LLM preview suppression.
No product slice was migrated; no Coach product code or the unrelated PDF was touched.

## RED / GREEN

- RED: initial focused collection failed with three expected imports missing:
  `app.runtime.evaluation.service` and `app.runtime.observability`.
- GREEN: authoritative Python 3.12 focused Task 11 suite: `23 passed in 42.82s`, two cache-write warnings.
- RED: opaque evaluation `{ "answer": "MODEL-OUTPUT-CANARY" }` was accepted.
- GREEN: store now rejects non-null opaque `result_json`; focused canary test passes.
- RED: initial migration downgrade failed because SQLite could not reflect/drop named FKs.
- GREEN: `batch_alter_table(recreate="always", naming_convention=...)` produces stable named
  lineage FKs; local migration contract suite: `7 passed`.

## Verification

- Python 3.12 complete `tests/runtime`: `340 passed, 3 PytestCacheWarning warnings in 89.86s`.
- Python 3.12 observability + model-discovery subset: `55 passed, 2 PytestCacheWarning warnings in 1.87s`.
- `alembic heads`: one head, `z3a4b5c6d7e8`.
- Local `tests/runtime/test_schema_migration.py`: `7 passed in 23.19s`.
- Python 3.12 observability/model-discovery/database-setup set: `71 passed, 1 failed` only
  because the image lacks `make`; a narrow read-only Makefile mount also fails because GNU make
  tries to remake it. The documented whole-repo read-only mount requires explicit approval and
  has not been run. Full backend was not run for the same authorization reason.

## Required follow-up

Run the documented whole-repository host `make`/`git` mount gate with explicit authorization,
then the complete backend suite. Record those outcomes in `R4-evidence.md` before integration.
