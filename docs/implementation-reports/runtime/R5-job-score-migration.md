# R5 Job Scoring migration evidence — repair round 1

## Status and superseded evidence

The implementation and measurements in rejected commit `8267ae3` are superseded.
Its fabricated fixture timings/costs and mock-only agent tests are not evidence.
This repair does not complete Gate R2 or authorize promotion.
`HATCH_RUNTIME_JOB_SCORE_MODE` remains `legacy`.

## Implemented boundary

`ScorerAgent.run()` binds mode once, before polling or scoring. NEW branches
before legacy model construction/computation. SHADOW computes legacy visibly
and independently runs the reference-resolved runtime path for comparison.

The runtime binding loads the referenced job/profile/resume into an in-memory
snapshot, persists only declared context metadata/hashes, applies the Control
Plane and Model Router to primary and triage selection, invokes the Execution
Gateway, validates the actual output, and records real execution lineage.
Existing prompt construction and normalization are shared pure code, not a
call into the legacy agent. Hybrid top-fraction/borderline selection and
optional-resume fallback are preserved independently.

The generic kernel now supports an exact-run claim. Runtime finalization and
the product score/event/cost projection commit in the same fenced transaction.
Concurrent unrelated work is not claimed; an expired/stale owner cannot invoke
the projection or escape through legacy fallback. Restart reads recorded
input references/mode/context; changed context fails closed. SQLite upsert
preserves one durable JobScore per job even under colliding runs.

Primary, fallback, context-failure and policy-refusal observations retain real
run/attempt/execution linkage, model/version/provider, measured elapsed time,
stable reasons and per-model-call metadata. Token counts are estimates derived
from the actual prompts/structured responses, explicitly marked `estimated`;
costs are corresponding estimates, not claimed provider billing. Local
computation records zero model tokens/cost. OTel spans carry actual durable IDs.
No raw prompt, resume, job description, model response or artifact is persisted
in runtime/shadow records. Sensitive scoring exception/reason/title logging
has been removed.

SHADOW comparisons link to the actual execution (including retained failure
observations). The shared store caps expiry at 30 days. Application lifespan
performs an observable best-effort purge and registers a daily retry on the
existing scheduler; purge failure cannot fail product startup/scoring.

## Red/green evidence

Tests use real SQLite, EventBus, ScorerAgent, dispatcher, context, policy,
gateway, evaluation and projection code. Only profile/resume source boundaries
and remote model transport are replaced with explicit synthetic inputs.

| Behavior | Observed RED before repair | Completed GREEN |
| --- | --- | --- |
| Real agent routing | 3 failures: missing injected runtime factory; then invalid typed runtime result exposed | LEGACY/SHADOW/NEW DB assertions, independent provider divergence |
| Exact claim and atomic projection | Wrong queued run claimed; missing projection callback | Targeted/concurrent starts, transactional rollback, single durable score |
| Lost-owner fallback | Stale NEW worker wrote a legacy score | No visible score and replacement claim preserved |
| Failure/OTel lineage | Missing safe context observation; missing actual execution span | Real context/fallback lineage and durable trace IDs |
| Policy | Missing pre-invocation refusal lineage; excluded triage was invoked | Both refused transports never invoked; local fallback linked |
| Retention | 2 failures: retention integration module absent | 4 retention tests including actual application lifespan/scheduler |
| Real benchmark | 2 failures: observed-measurement helpers absent | 50 real input pairs and nearest-rank percentile assertions |
| Public compatibility | Triage used primary endpoint | Correct endpoint, native model name and durable cost rows |
| Privacy | Response/title canaries appeared in legacy logs | Response canary checks passed; final title-log removal rerun blocked in fixture setup |

Completed commands during this repair:

```text
python -m pytest -q --no-cov tests/runtime tests/test_agents/test_scorer_agent.py \
  tests/test_tools/test_local_scorer.py tests/test_tools/test_semantic_scorer.py --tb=short
418 passed, 1 skipped in 71.46s

python -m pytest -q --no-cov tests/runtime/test_job_score_agent_integration.py --tb=short
13 passed in 4.37s

python -m pytest -q --no-cov tests/runtime/test_shadow_retention.py --tb=short
4 passed in 0.60s

ruff check [scoped application/runtime/test paths]
All checks passed

ruff format --check [22 scoped Python files]
22 files already formatted

python scripts/check_docs.py
Documentation validation passed

git diff --check
Passed

alembic heads
z3a4b5c6d7e8 (head)
```

The 418-test run preceded the final endpoint/cost/lifespan/privacy refinements;
the separate 13-agent and 4-retention runs verified those refinements except
the final removal of title text from an existing log statement.

Full backend attempts are **incomplete**, not passes:

- `python -m pytest -q --no-cov tests --tb=short`: stopped, exit 130,
  stalled at Coach benchmark
  `test_e2e_01_persists_report_rubric_counts_and_followup_focus` (~1%).
- `python -m pytest -q --no-cov tests --ignore=tests/benchmarks --tb=short`:
  stopped, exit 130, stalled during setup of the first runtime approval test.
- A fresh 120-second bounded focused rerun exited 124 before the first LEGACY test body.
  Its 20-second faulthandler dump shows pytest-asyncio fixture setup waiting,
  with the aiosqlite connection worker at its queue wait. This is not reported
  as a product assertion failure or as proof that the final full suite passes.
- A final 90-second benchmark rerun also exited 124 during database fixture
  setup. The previously completed real measurements below remain explicitly
  identified as measurements from the repair iteration.
- An independent probe importing only Python `asyncio` and `aiosqlite`,
  connecting to `:memory:` under `asyncio.wait_for(..., 5)`, failed with
  `TimeoutError` in `aiosqlite._connect` (exit 1). It imports no repository code.
  This independently reproduces the database verification blocker.
- Final non-database dispatcher/immutable-contract selection:
  `7 passed, 3 deselected in 0.07s`.

## Real 50-case offline measurement

`backend/tests/runtime/fixtures/job_score_r2_cases.json` now contains inputs,
not canned scores or timings: 20 strong-fit, 15 borderline, and 15 poor-fit
synthetic scenarios, 50 distinct job descriptions, profile/resume/job snapshots,
expected shortlist classifications and stable scenario labels. Borderline
outputs are checked within ±0.10 of the configured threshold in both modes.

Every case is executed through the actual LEGACY and NEW agent paths, against
the same isolated database, machine and local-keyword scorer; concurrency is
one and there is no explicit warm-up. End-to-end elapsed times are measured
with `perf_counter`. Percentiles use sorted nearest rank `ceil(p*n)-1`,
independently tested on a 20-sample sequence.

Completed command:
`python -m pytest -q --no-cov -s tests/runtime/test_job_score_benchmark.py --tb=short`
— `2 passed in 9.01s`.

| Observed offline metric | Result |
| --- | --- |
| Validated schema cases | 50/50 |
| Expected shortlist accuracy, LEGACY / NEW | 100% / 100% |
| Shortlist agreement | 100% |
| Absolute score delta ≤ 0.10 | 100%; no exceptions |
| LEGACY p50 / p95 | 34.503 / 45.966 ms |
| NEW p50 / p95 | 109.062 / 128.408 ms |
| NEW/LEGACY p50 / p95 | 3.161× / 2.794× |

These are completed measurements from this repair iteration, not fabricated
values or evidence from `8267ae3`. They are offline deterministic conformance,
not the required 20-case live same-provider/model performance gate.
The observed offline latency ratios exceed the 1.20×/1.25× limits.

## Gate R2 remains incomplete

Quality thresholds are 100% schema/normalization, ≥92% expected shortlist
accuracy, NEW no more than 2 percentage points below LEGACY, ≥95% decision
agreement, ≥90% score deltas within 0.10, and no high/critical privacy or
correctness regression. Offline deterministic comparisons meet their measured
quality checks; this does not establish model quality.

The same 20-case live subset must measure p50 ≤1.20×, p95 ≤1.25×, mean estimated
cost ≤1.15× and p95 total tokens ≤1.25× against the same provider/model,
machine, warm-up and concurrency. No provider credentials were available and
both configured local model endpoints were unreachable in the environment.
Live latency, token and cost thresholds therefore remain **unmeasured**.
Zero-token local scoring is not a substitute for those measurements.

Complete-backend no-new-failure evidence remains outstanding. Only repository
owner `@arvindsoni2` can approve promotion after the actual R2 thresholds pass.
No approval, default-mode change, push or PR is part of this repair.
