# R4 bounded evaluation and privacy-safe OTel evidence

## Scope and authority

- Base/head at implementation start: `541a78ac11860a06c0a246cb3d52ad471a6a40e5`.
- Scope: generic runtime evaluation, runtime telemetry correlation, capture policy,
  LLM trace preview suppression, and additive evaluation provenance only.
- Exclusions: no product slice migration, no Coach route/state/media/export/deletion
  behavior, no new provider, and no raw candidate/model content persisted.
- Inputs were synthetic, local SQLite fixtures only.

| Authority | SHA-256 |
|---|---|
| Foundation plan v2 | `bb09a80b78b0643e2eab65c2d7b8a72fb7c00fd767506bd31ca4d58ae67c40bb` |
| Foundation spec v2 | `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0` |
| Runtime architecture v8 | `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36` |
| Coach V6 Phase 1 spec | `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8` |

## Traceability and TDD

| Contract / invariant | RED evidence | Implementation | GREEN evidence |
|---|---|---|---|
| `INV-CTR-001` deterministic evaluation stops later model work | `ModuleNotFoundError: app.runtime.evaluation.service` before the evaluator module existed | `backend/app/runtime/evaluation/{validators,service,evidence}.py` | `test_deterministic_failure_stops_unneeded_model_evaluation` passes; model calls remain empty |
| `INV-CTR-001` finite evaluator ladder | Same focused RED collection | `service.py`, immutable `EvaluationPolicy.max_evaluations` | Ordered deterministic → heuristic → model result is bounded; human review is not reached after the budget is exhausted |
| `INV-OBS-001` trace correlation, never metric dimensions | `ModuleNotFoundError: app.runtime.observability` before the wrapper existed | `backend/app/runtime/observability/*`, `backend/app/observability/attributes.py` | Six required `hatch.*` IDs are present on spans and absent from sanitized metrics |
| `INV-OBS-002` exporter failure is non-fatal | Same focused RED collection | shared `TelemetryRuntime` wrapper only; no second provider | Failing span close leaves workflow result unchanged |
| `INV-PRV-001` capture defaults and no normal-mode preview | Existing trace ring retained raw previews before this task | `backend/app/config.py`, `backend/app/agents/tools/llm_factory.py` | Metadata/redacted/disabled canary never appears in traces; `debug_content` environment setting is rejected |
| `INV-PRV-001` no opaque model output in evaluation records | `test_evaluation_store_rejects_opaque_model_output`: expected `MetadataOnlyViolation`, none raised | `backend/app/runtime/storage/sqlite.py` | The test passes with `MODEL-OUTPUT-CANARY` rejected |
| `INV-LIN-001` durable evaluator provenance and primary→repair→fallback lineage | Migration test initially showed absent named lineage FKs | evaluation ORM/store and `z3a4b5c6d7e8` migration | Upgrade from prior head has named lineage FKs targeting `runtime_execution_records.id`; downgrade/re-upgrade passes |

## Verification

Authoritative isolated Python 3.12 image:

```text
python -m pytest -q -o log_cli=false --no-cov \
  tests/runtime/test_evaluation_service.py tests/runtime/test_otel_correlation.py \
  tests/runtime/test_otel_export_failure.py tests/runtime/test_runtime_privacy.py \
  tests/runtime/test_schema_migration.py
# 23 passed, 2 PytestCacheWarning warnings in 42.82s.

python -m pytest -q -o log_cli=false --no-cov tests/runtime
# 340 passed, 3 PytestCacheWarning warnings in 89.86s.

python -m pytest -q -o log_cli=false --no-cov \
  tests/test_observability tests/test_services/test_model_discovery.py
# 55 passed, 2 PytestCacheWarning warnings in 1.87s.
```

Local migration contract evidence:

```text
python -m pytest -q --no-cov tests/runtime/test_schema_migration.py
# 7 passed in 23.19s.

alembic heads
# z3a4b5c6d7e8 (head)
```

The first Python 3.12 observability/model-discovery/database-setup run obtained
`71 passed, 1 failed`; the sole failure was image-only: `make` was absent. A narrower
backend + read-only Makefile + `make` rerun also obtained `71 passed, 1 failed`, because
GNU make needs write access while attempting to remake a read-only mounted Makefile.
The documented whole-repository mount with host `make`/`git` was not run after automatic
review rejected that broader mount. This is an environment limitation, not a product-test
failure; it remains outstanding for the controller with explicit authorization.

`git diff --check` passed after the final report update. No secrets, IDs, prompts, CVs, jobs,
transcripts, evidence, model output, exception messages, or user paths were placed in the
new telemetry/evaluation records or this report.

## Security disposition

- Binding V6 privacy/observability controls applied: safe errors only, no default OTel
  exception event, span-only correlation IDs, metric identifier dropping, capture-policy
  validation, and canary coverage.
- Coach-specific command, ownership, media, retention, deletion, export, and frontend
  boundary tests are not applicable because no Coach product path changed.
- No critical/high finding. The incomplete broader Python 3.12 gate is an environment
  limitation and must be rerun before integration approval.
