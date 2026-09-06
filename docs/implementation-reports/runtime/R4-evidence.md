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
| `INV-EVL-001` deterministic-first evaluation and shared bounds | Initial collection failed before the evaluator module existed; ordered review then found repair/deadline/token/cost bounds absent | `backend/app/runtime/evaluation/{validators,service,evidence}.py`, immutable `EvaluationPolicy` and `EvaluationUsage` | Deterministic terminal failure skips later work; shared evaluation/repair/token/cost ceilings tighten policy; an async evaluator cannot cross the absolute deadline |
| `INV-OBS-001` OTel failure does not fail correct workflow | Ordered review found only a facade-level dictionary test and no production runtime call site | shared `TelemetryRuntime` wrapper composed into `WorkflowKernel` and `EvaluationService`; batch span export | Real workflow start/claim and evaluation results survive failing export; a slow exporter does not block workflow persistence; no second global provider is installed |
| `INV-OBS-002` durable execution lineage is reconstructable | Ordered review found `evaluation_execution_id` only in memory and no round-trip graph test | explicit evaluation execution FK, bounded lineage store, and `z3a4b5c6d7e8` migration | `test_primary_repair_fallback_lineage_reconstructs` commits and reloads PRIMARY → REPAIR → FALLBACK → EVALUATOR parent links; all four named FKs and downgrade/re-upgrade pass |
| `INV-PRV-001` capture defaults and no normal-mode preview | Existing trace ring retained raw previews before this task | `backend/app/config.py`, `backend/app/agents/tools/llm_factory.py` | Metadata/redacted/disabled canary never appears in traces; `debug_content` environment setting is rejected |
| `INV-PRV-001` metadata-only durable evaluation records | Ordered review found scalar and non-result JSON fields accepted raw canaries | typed bounded validation in `backend/app/runtime/storage/sqlite.py` | Parameterized evaluation, validation, and observation canaries are rejected and committed-table scans remain empty; typed metadata commits successfully |

## Verification

Authoritative isolated Python 3.12 image:

```text
python -m pytest -q --no-cov \
  tests/runtime/test_evaluation_service.py tests/runtime/test_otel_correlation.py \
  tests/runtime/test_otel_export_failure.py tests/runtime/test_runtime_privacy.py \
  tests/runtime/test_execution_lineage.py tests/runtime/test_schema_migration.py
# 47 passed, 3 PytestCacheWarning warnings in 30.57s.

python -m pytest -q --no-cov tests/runtime
# 364 passed, 3 PytestCacheWarning warnings in 57.11s.

python -m pytest -q --no-cov tests/test_observability \
  tests/test_services/test_model_discovery.py \
  tests/test_migrations/test_database_setup.py
# 72 passed, 2 PytestCacheWarning warnings in 31.52s.
```

Local migration contract evidence:

```text
python -m pytest -q --no-cov tests/runtime/test_execution_lineage.py \
  tests/runtime/test_schema_migration.py
# 10 passed, 2 PytestCacheWarning warnings in 28.19s.

alembic heads
# z3a4b5c6d7e8 (head)
```

The first complete-suite repair run reached `3649 passed` with coverage `76.58%` and one
manifest assertion failure because the container could see the worktree `.git` pointer but
not its parent repository metadata. The failing benchmark reproduced with
`working_tree_clean_before="not_recorded"`; mounting the parent `.git` read-only made the
same benchmark pass. No source change was made for this environment-only result. The final
complete-suite result with the corrected mount is recorded below.

```text
COVERAGE_FILE=/tmp/.coverage python -m pytest -q
# 3650 passed, 24 warnings in 574.26s; total coverage 76.58% (required 58%).
```

`git diff --check` passed after the final report update. No secrets, IDs, prompts, CVs, jobs,
transcripts, evidence, model output, exception messages, or user paths were placed in the
new telemetry/evaluation records or this report.

## Security disposition

- Binding V6 privacy/observability controls applied: safe errors only, no default OTel
  exception event, span-only correlation IDs, metric identifier dropping, capture-policy
  validation, and canary coverage.
- Coach-specific command, ownership, media, retention, deletion, export, and frontend
  boundary tests are not applicable because no Coach product path changed.
- No critical/high finding. The first ordered review's six Important gaps were repaired;
  the corrected complete-suite gate passed. Final ordered re-reviews remain required before
  integration approval.
