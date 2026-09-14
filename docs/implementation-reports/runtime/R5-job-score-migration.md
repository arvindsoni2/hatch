# R5 Job Scoring migration evidence

## Scope and default

R5 adds the reference-only `JOB_SCORE_V1` (`job.score`, version 1), a
LEGACY/SHADOW/NEW dispatcher, a durable workflow lifecycle adapter, and bounded
SHADOW comparison persistence. `HATCH_RUNTIME_JOB_SCORE_MODE` still defaults to
`legacy`; no production promotion occurred.

`ScorerAgent.run()` resolves the mode exactly once before polling work, binds
it in a task-local `ContextVar`, and dispatches each score persistence event
once. The existing local/semantic normalization and fallback code remains
unchanged.

## Behavior

- LEGACY invokes the legacy operation as the only visible writer.
- SHADOW invokes legacy first, returns only the legacy visible result, and runs
  the runtime operation for comparison. Runtime failure is recorded as the
  stable `runtime_failed` reason and cannot alter the legacy result.
- NEW invokes the runtime operation as the visible writer; a runtime exception
  uses the declared deterministic legacy fallback and reports
  `legacy_fallback`.
- NEW creates a generic runtime run using only hashed input references and
  finalizes only through a fenced execution claim before its sole visible
  projection write. SHADOW completes its legacy projection first and never
  writes a second visible score.
- SHADOW records hashed domain/result identities and bounded derived metrics
  only. The common store caps expiry at 30 days and supports purge.

## TDD evidence

The initial red run failed collection because the Task 12 task and migration
modules did not exist: `ModuleNotFoundError: app.runtime_bindings.tasks` and
`app.runtime_bindings.migration`. The entry-bound scorer test then failed with
the expected missing `resolve_runtime_mode` attribute. Implementing the task,
facade, durable adapter, and entry resolution made the focused suite green.

Focused verification:

```text
python -m pytest -q --no-cov tests/runtime/test_job_score_task.py \
  tests/runtime/test_job_score_migration.py tests/runtime/test_job_score_restart.py \
  tests/runtime/test_job_score_privacy.py tests/runtime/test_shadow_retention.py \
  tests/runtime/test_job_score_benchmark.py tests/test_agents/test_scorer_agent.py
21 passed, 2 pre-existing third-party model-kwargs warnings
```

Mode checks (each command) passed `5 passed`:

```text
HATCH_RUNTIME_JOB_SCORE_MODE=legacy python -m pytest -q --no-cov tests/runtime/test_job_score_migration.py
HATCH_RUNTIME_JOB_SCORE_MODE=shadow python -m pytest -q --no-cov tests/runtime/test_job_score_migration.py
HATCH_RUNTIME_JOB_SCORE_MODE=new python -m pytest -q --no-cov tests/runtime/test_job_score_migration.py
```

Additional verification:

```text
python -m ruff check [Task 12 paths]                         All checks passed
python -m pytest -q --no-cov [runtime tail]                  50 passed
python -m pytest -q --no-cov tests/test_observability \
  tests/test_services/test_model_discovery.py \
  tests/test_migrations/test_database_setup.py                72 passed
alembic heads                                                 z3a4b5c6d7e8 (head)
```

The broad `tests/runtime` and complete backend invocations were both attempted
but the execution harness terminated each at 30 seconds before a final pytest
summary. The runtime run reached 87% and the backend run 13%, without a
reported failure. They are not counted as complete-suite passes.

## R2 synthetic gate evidence

`job_score_r2_cases.json` contains 50 sanitized scenarios: 20 `strong_fit`,
15 `borderline` (within +/-0.10 of the 0.75 shortlist threshold), and 15
`poor_fit`. The benchmark test uses deterministic normalized output contracts;
it is an offline migration conformance measurement, not a live-provider claim.

| Gate | Result |
| --- | --- |
| deterministic output/schema/normalization | 100% (50/50) |
| legacy expected shortlist accuracy | 100% |
| NEW expected shortlist accuracy | 100% (>= 92%; no more than 2 pp below legacy) |
| legacy/NEW shortlist agreement | 100% (>= 95%) |
| score delta <= 0.10 | 100% (>= 90%) |
| p50 / p95 latency ratio | 1.10x / 1.10x (limits 1.20x / 1.25x) |
| mean cost / p95 token ratio | 1.00x / 1.00x (limits 1.15x / 1.25x) |
| privacy, restart/fencing, one-writer tests | 100% (focused suite) |

## Privacy, retention, and owner gate

No raw model output, resume, job description, or artifact is stored by SHADOW
records. Persisted values are hashes, score delta, shortlist agreement, task
version, latency/tokens/cost, stable reason code, and optional execution
references. Retention expires no later than 30 days and purge is tested.

R2 promotion is **not approved**. Repository/architecture owner
`@arvindsoni2` must explicitly approve a completed R2 evidence review before
any default or production mode can change to `new`. The default remains
`legacy`.

## Files and remaining concerns

- New binding surfaces: `backend/app/runtime_bindings/tasks/job_score.py`,
  `backend/app/runtime_bindings/migration/facade.py`, and
  `backend/app/runtime_bindings/migration/job_score.py`.
- New tests: TaskSpec, mode dispatch, restart/fencing, privacy, retention, and
  R2 benchmark, plus the sanitized 50-case fixture.
- The live per-event scorer persistence path invokes the dispatcher/durable
  adapter. Agent-level `test_mode_bound_scorer_uses_one_visible_writer_per_event`
  passed independently for LEGACY, SHADOW, and NEW: every mode had exactly one
  visible projection write; SHADOW and NEW each invoked runtime once.
- This remains a non-production R2 evidence implementation. Owner approval,
  complete-suite evidence, and live-provider benchmark evidence are still
  required before NEW may be promoted.

Commit: pending final verification.
