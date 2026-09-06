# Task 11 implementation report

Status: `REPAIR_VERIFIED` pending ordered re-reviews.

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
- REVIEW RED: the first ordered spec review found six Important gaps: missing production
  telemetry wiring; incomplete evaluation bounds; disconnected durable lineage; scalar-field
  privacy gaps; incomplete OTel provider/exception/non-blocking evidence; and incomplete or
  mislabeled gate evidence.
- REPAIR GREEN: evaluation limits now tighten against immutable effective constraints and
  shared usage; real workflow and evaluation paths are fail-open under exporter failure;
  PRIMARY → REPAIR → FALLBACK → EVALUATOR lineage commits and reloads; scalar/JSON canaries
  are rejected from evaluation, validation, and observation persistence.

## Verification

- Python 3.12 focused repaired Task 11 set: `47 passed, 3 PytestCacheWarning warnings in 30.57s`.
- Python 3.12 complete `tests/runtime`: `364 passed, 3 PytestCacheWarning warnings in 57.11s`.
- Python 3.12 observability + model-discovery + database-setup subset:
  `72 passed, 2 PytestCacheWarning warnings in 31.52s`.
- `alembic heads`: one head, `z3a4b5c6d7e8`.
- Python 3.12 lineage + schema migration set: `10 passed, 2 PytestCacheWarning warnings in 28.19s`.
- The first complete backend run reached `3649 passed`, coverage `76.58%`, and one environment-only
  benchmark failure because the parent Git metadata was not mounted. The isolated failure passes
  when the parent `.git` is mounted read-only.
- Corrected-mount complete backend suite: `3650 passed, 24 warnings in 574.26s`; total coverage
  `76.58%` against the required `58%`.

## Required follow-up

Run exact Ruff/docs/diff checks, then obtain the two ordered Task 11 re-reviews before integration.
