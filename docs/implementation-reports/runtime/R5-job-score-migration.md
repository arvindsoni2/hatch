# R5 Job Scoring migration evidence — repair round 3

## Latest repair: durable source acknowledgement and complete event API reads

Round 3 starts from `b60b1b3`. Source event status is now an acknowledgement of
the authoritative runtime outcome, not permission to execute another run.
NEW completes its source event inside fenced runtime finalization, including
irrelevant/skip results. Post-commit or acknowledgement exceptions reconcile
to the durable scored/skipped success rather than marking the source failed.

The public retry route matches the exact NEW task/version, source reference
and job/domain references. Already-completed work returns `status=completed`
without scoring again. Existing pending/claimed/failed runtime lifecycles
cannot escape through a product retry: HTTP 409 preserves runtime ownership.
Legacy events without a NEW runtime binding keep their existing retry behavior.

`GET /api/events` and `GET /api/events/{id}` now return canonical narrative,
fit reasoning, strengths, gaps and keywords in response-only JSON strings.
Stored events remain metadata/reference-only. Cross-job references resolve no
content and legacy inline JSON strings remain byte-for-byte unchanged.

TDD reproduced `7 failed, 10 passed in 3.35s`: five duplicate-run cases after
real public retry/reprocessing and two missing-content event API cases.
The expanded focused lifecycle/API suite passed `46 tests in 10.35s`, covering
scored/irrelevant results, three post-commit/acknowledgement failure timings,
stale source state, repeated retry of runtime-owned failures, endpoint reads,
cross-job privacy and legacy compatibility. Tests count real durable runs,
executions, costs, scores and events, rather than only mocked call counts.

Final full-backend verification, including the strengthened independent
source-acknowledgement assertion, completed with exit 0:

```text
timeout 600s python -m pytest -q --no-cov tests --tb=short
3706 passed, 2 skipped, 16 warnings in 417.85s (0:06:57)
```

All source reconciliation and event API tests, all seven prompt-catalog tests,
and migration upgrade/downgrade tests passed. This supersedes the incomplete
full-suite evidence below without rewriting the historical results. The run
used narrow approved execution outside the SQLite-blocking sandbox. Coach
fallback tests emitted connection warnings; pytest also reported 16 existing
coroutine/resource/provider-parameter warnings. No warning-free result is
claimed. Lint passes on ten changed Python files; formatting passes on eight,
with confirmed baseline whole-file failures retained in the event router and
schema. Docs/diff checks pass; migration head remains `z3a4b5c6d7e8`.

Round 2 and round 1 results below remain historical; their narrower completion
claims do not replace the round-3 evidence. Production/default mode is still
LEGACY, and live same-provider/model R2 measurements and owner approval remain
outstanding.

## Round 2: lifecycle-safe failures and reference-only events

Round 2 starts from `f8a011f` and repairs two subsequently verified P1 findings.
The descriptions below supersede round 1's claims about general exception
fallback and NEW event privacy; the older measured results remain historical.

NEW has **no legacy exception fallback**. The runtime already owns the bounded
provider-to-local fallback and its fenced finalization. Unexpected exceptions
propagate to the agent's stable failure outcome without another visible write.
An exception cannot establish whether run creation or finalization committed,
so the dispatcher must not guess. Durable state determines recovery: a pending
or expired claimed attempt can resume; an already-completed attempt cannot
project again. The same production projection callback is used by execution
and restart tests.

NEW `job_scored` events now contain an explicit `job-score:<UUID>` reference,
job identity, numeric score components and bounded model/usage/method metadata.
Reasoning, fit reasoning, strengths, gaps and keyword lists remain only in the
canonical product `JobScore`; no whole-model dump enters the event. An
adversarial test supplies oversized source-like text in every explanatory
field, verifies all required JobScore fields survive, and verifies the stored
event is under 2 KB with none of that content.

The decision trail, activity view, skill-gap view and skill-frequency view
resolve canonical score references in memory so their required output remains
available. Resolution checks both score UUID and event job identity, batches
reads, and never mutates/flushed-enriches an ORM event. Cross-job references
return no content. Existing legacy inline payloads remain readable; historical
legacy events are not rewritten as part of this scoped repair.

TDD evidence: five lifecycle RED failures demonstrated unfenced writes after
start/claim, a projection rollback, and two visible events after a committed
runtime result. These became nine passing lifecycle/fallback tests. The
oversized-output privacy regression failed on retained event content before
the allowlist/reference change. Four product-read regressions failed before
read-through resolution and then passed, alongside cross-job rejection tests.

Completed focused verification (outside the SQLite-blocking sandbox):

```text
timeout 120s python -m pytest -q --no-cov \
  tests/runtime/test_job_score_agent_integration.py \
  tests/runtime/test_job_score_migration.py tests/runtime/test_job_score_restart.py \
  tests/runtime/test_job_score_privacy.py --tb=short
32 passed in 5.74s

timeout 120s python -m pytest -q --no-cov \
  tests/runtime/test_job_score_event_readers.py tests/test_routers/test_jobs_router.py \
  tests/test_routers/test_events_router.py tests/test_routers/test_analytics_router.py --tb=short
34 passed in 3.73s
```

The subsequent full backend run completed, but was not clean:

```text
timeout 600s python -m pytest -q --no-cov tests --tb=short
1 failed, 3688 passed, 2 skipped, 18 warnings in 381.04s (0:06:21)
```

The only failure was the prompt-catalog runtime-metadata wiring check. Round 1
had moved the scoring prompts to `agents/tools/scoring_contract.py` without
updating their three catalog paths and matching audit rows. Those six source
references now name the actual owning module. After this correction:

```text
timeout 180s python -m pytest -q --no-cov tests/runtime \
  tests/test_agents/test_scorer_agent.py tests/test_tools/test_local_scorer.py \
  tests/test_tools/test_semantic_scorer.py tests/test_integration/test_scoring_calibration.py \
  tests/test_services/test_prompt_catalog.py tests/test_routers/test_jobs_router.py \
  tests/test_routers/test_events_router.py tests/test_routers/test_analytics_router.py --tb=short
482 passed, 1 skipped in 82.55s (0:01:22)
```

All seven prompt-catalog checks passed in that final run, alongside runtime,
scoring and affected product-route regressions. There was no second full
backend rerun, so this is not a claim of a clean full-backend pass. Lint passes
on all eleven changed Python files; seven repaired/new files pass formatting.
The three routers and catalog retain confirmed baseline whole-file formatting
failures without unrelated formatting changes. Docs and diff checks pass; the
migration head remains `z3a4b5c6d7e8` and no migration was added.

The round 1 database hang is now isolated to the sandbox: the same standalone
in-memory aiosqlite probe still times out there but succeeds immediately with
narrow approved execution permission. No dependency or application workaround
was added. Live inference/provider measurements were not repeated in round 2;
prior endpoint availability checks were sandbox-limited. Gate R2 remains
incomplete and the production/default mode remains LEGACY.

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

Round 3 provides complete-backend no-failure evidence, but the live-provider
measurements above remain outstanding. Only repository owner `@arvindsoni2`
can approve promotion after the actual R2 thresholds pass.
No approval, default-mode change, push or PR is part of this repair.
