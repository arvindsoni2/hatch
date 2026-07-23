# Coach C3 Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add privacy-safe end-to-end Coach production and benchmark observability through Hatch's existing optional OpenTelemetry facade.

**Architecture:** Enrich the existing `coach_generation` decorators rather than wrapping them, carry request correlation to background jobs with a frozen `SpanContext` link, and add exact `coach.*` orchestration stages plus bounded Coach operational metrics. The shared facade remains the sole provider/exporter/lifecycle owner and contains every telemetry failure.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy asyncio, OpenTelemetry Python 1.44.0, pytest/pytest-asyncio

## Global Constraints

- Preserve one and only one `coach_generation` root per production operation.
- Keep `hatch.ai.workflow.name="coach_generation"`; use `hatch.coach.operation` for the bounded operation.
- Never export Coach content, personal data, scores, evidence, URLs, headers, secrets, or filesystem/audio paths.
- Session, job, question, run, and scenario IDs may be trace attributes but never metric labels.
- Reuse existing shared model-call metrics exactly once; do not add a mandatory model-call span.
- Observability remains disabled by default and absent from the core dependency/profile.
- Telemetry failure must not change Coach API results, persistence, benchmark results, or async status.
- Preserve the application-owned five-second total telemetry shutdown deadline; add no shutdown path.
- Preserve existing routes, session statuses, database schema, prompts, and configured default model.

---

### Task 1: Privacy-safe facade contracts and Coach instruments

**Files:**
- Modify: `backend/app/observability/attributes.py`
- Create: `backend/app/observability/coach.py`
- Modify: `backend/app/observability/runtime.py`
- Modify: `backend/app/observability/__init__.py`
- Test: `backend/tests/test_observability/test_coach_runtime.py`
- Test: `backend/tests/test_observability/test_privacy.py`

**Interfaces:**
- Produces: `TraceContextToken`, `TelemetryRuntime.capture_trace_context()`, `TelemetryRuntime.use_background_trace_context()`, `TelemetryRuntime.coach_stage_span()`, `TelemetryRuntime.record_coach_outcome()`, `TelemetryRuntime.record_coach_question_count()`, and `trace_workflow(workflow, attributes=None)`.
- Produces: `sanitize_metric_attributes()` that always removes correlation identifiers.

- [ ] **Step 1: Write failing facade and privacy tests**

Add tests with recording tracer/meter doubles asserting:

```python
def test_coach_metric_attributes_drop_all_correlation_ids() -> None:
    safe = sanitize_metric_attributes({
        COACH_STAGE: "question_generation",
        COACH_OUTCOME: "completed",
        COACH_SESSION_ID: "session-1",
        ASYNC_JOB_ID: "job-1",
        COACH_BENCHMARK_RUN_ID: "run-1",
        COACH_SCENARIO_ID: "scenario-1",
    })
    assert safe == {
        COACH_STAGE: "question_generation",
        COACH_OUTCOME: "completed",
    }


def test_coach_stage_records_exact_span_and_bounded_metrics() -> None:
    runtime, tracer, meter = recording_runtime()
    with runtime.coach_stage_span(
        "coach.question_generation",
        {COACH_OUTCOME: "completed"},
    ):
        pass
    assert tracer.names == ["coach.question_generation"]
    assert meter.histogram("hatch.coach.stage.duration").calls[0].attributes == {
        COACH_STAGE: "question_generation",
        COACH_OUTCOME: "completed",
    }
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability/test_coach_runtime.py tests/test_observability/test_privacy.py`

Expected: collection/import failures for the new Coach contracts.

- [ ] **Step 3: Implement constants, sanitisation, stage observation, and instruments**

Use frozen tokens and bounded public methods:

```python
@dataclass(frozen=True)
class TraceContextToken:
    span_context: Any = None


@contextmanager
def use_background_trace_context(
    self,
    token: TraceContextToken,
    attributes: Mapping[str, Any] | None = None,
):
    state = BackgroundTraceState(
        token=token,
        attributes=tuple(sanitize_attributes(attributes).items()),
    )
    context_token = _background_trace_state.set(state)
    try:
        yield
    finally:
        _background_trace_state.reset(context_token)
```

When a valid token is consumed by `workflow_span`, call `start_as_current_span` with `context=Context()` and `links=(Link(span_context),)`. `coach_stage_span` must create the exact supplied span name and record stage duration/outcome through metric-only sanitisation. `record_coach_outcome` accepts only the five outcome metric families; question and async-job metrics have dedicated bounded methods.

- [ ] **Step 4: Run facade and existing observability tests**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability`

Expected: all tests pass; disabled runtime creates no spans or metric calls.

- [ ] **Step 5: Commit the facade checkpoint**

```bash
git add backend/app/observability backend/tests/test_observability
git commit -m "feat(observability): add privacy-safe Coach facade"
```

### Task 2: Async request-to-job span links

**Files:**
- Modify: `backend/app/services/async_job_service.py`
- Modify: `backend/app/services/coach_session_queue.py`
- Modify: `backend/app/routers/coach.py`
- Test: `backend/tests/test_observability/test_coach_async_links.py`
- Test: `backend/tests/test_routers/test_coach_async.py`

**Interfaces:**
- Consumes: `TraceContextToken` and `TelemetryRuntime.use_background_trace_context()` from Task 1.
- Produces: `AsyncJobService.run(job_id, coro, *, trace_context=None, trace_attributes=None, telemetry_operation=None)`.

- [ ] **Step 1: Write failing async-link and fail-open tests**

Test a valid request span followed by a completed request context:

```python
token = runtime.capture_trace_context()
with runtime.use_background_trace_context(
    token,
    {COACH_SESSION_ID: "session-1", ASYNC_JOB_ID: "job-1"},
):
    with runtime.workflow_span(
        "coach_generation",
        {COACH_OPERATION: "answer_submit"},
    ):
        pass

root = exporter.finished_spans[-1]
assert root.parent is None
assert len(root.links) == 1
assert root.links[0].context == request_span.get_span_context()
```

Also assert disabled/degraded runtimes and a tracer that raises do not prevent the coroutine or terminal database update.

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability/test_coach_async_links.py tests/test_routers/test_coach_async.py`

Expected: failures because async trace metadata is not accepted or activated.

- [ ] **Step 3: Thread immutable context through every Coach async launch**

Extend the run signature without changing existing callers:

```python
@staticmethod
def run(
    job_id: str,
    coro: Coroutine[Any, Any, None],
    *,
    trace_context: TraceContextToken | None = None,
    trace_attributes: Mapping[str, Any] | None = None,
    telemetry_operation: str | None = None,
) -> None:
    async def _run_and_track() -> None:
        telemetry = get_telemetry()
        with telemetry.use_background_trace_context(
            trace_context or TraceContextToken(),
            trace_attributes,
        ):
            try:
                from ..database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(AsyncJob)
                        .where(
                            AsyncJob.id == job_id,
                            AsyncJob.status == "pending",
                        )
                        .values(status="running", updated_at=datetime.utcnow())
                    )
                    await db.commit()
                await coro
            except BaseException as exc:
                logger.exception(
                    "Unhandled error in async job %s: %s",
                    job_id,
                    exc,
                )
                await AsyncJobService._finish(
                    job_id,
                    None,
                    _error_message(exc),
                )
                if not isinstance(exc, Exception):
                    raise
```

Capture once in each Coach request before `AsyncJobService.run`, pass only `hatch.coach.session_id` and `hatch.async_job_id`, and record the bounded async outcome after the existing status update. Never put either ID in metric attributes.

- [ ] **Step 4: Run async and observability regressions**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability tests/test_routers/test_coach_async.py tests/test_services/test_async_job_service.py`

Expected: all tests pass and each valid background root has one link and no parent.

- [ ] **Step 5: Commit the async checkpoint**

```bash
git add backend/app/services/async_job_service.py backend/app/services/coach_session_queue.py backend/app/routers/coach.py backend/tests
git commit -m "feat(coach): link async workflows to request traces"
```

### Task 3: Production Coach root operations and stage hierarchy

**Files:**
- Modify: `backend/app/services/coach_service.py`
- Modify: `backend/app/services/question_generator.py`
- Test: `backend/tests/test_observability/test_coach_workflows.py`
- Test: `backend/tests/test_services/test_coach_contracts.py`

**Interfaces:**
- Consumes: Task 1 facade methods and constants from `app.observability.coach`.
- Produces: the exact v5 production hierarchy and Coach diagnostic outcome metrics.

- [ ] **Step 1: Write failing hierarchy/outcome/privacy tests**

Use service doubles and a recording runtime to assert one root and ordered stage descendants for session creation, answer submission, session completion, company research, and follow-up planning. Include cases for question repair, withheld model answer, unavailable evaluation, deterministic rubric fallback, and report fallback. Assert serialized span data excludes unique sentinel content and scores.

```python
assert root_names.count("hatch.ai.workflow.coach_generation") == 1
assert required_stages <= set(span_names)
assert "PRIVATE_TRANSCRIPT_SENTINEL" not in serialized_spans
assert model_call_counter.delta == expected_provider_calls
```

- [ ] **Step 2: Run hierarchy tests and verify failure**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability/test_coach_workflows.py`

Expected: missing operation attributes and `coach.*` stage names.

- [ ] **Step 3: Enrich existing roots and wrap orchestration boundaries**

Keep the existing decorators and add static attributes exactly as follows; retain the current method signature and indent its existing body inside the orchestration stage context:

```python
@trace_workflow(
    "coach_generation",
    attributes={COACH_OPERATION: "session_create"},
)
async def create_session(
    self,
    request: CreateSessionRequest,
    db: AsyncSession,
    session_id: str | None = None,
) -> SessionResponse:
    with telemetry.coach_stage_span("coach.session.create"):
        return await self._create_session_observed(
            request,
            db,
            session_id=session_id,
        )
```

Move the current body without semantic changes into `_create_session_observed()` with the same parameters. Apply the same thin decorated-wrapper pattern to answer submission and session completion so one orchestration stage encloses each existing implementation.

Add `coach.session.stub_persist`, `coach.company_research`, `coach.question_generation`, conditional `coach.question_generation.repair`, one `coach.model_answer.generate` per question, `coach.questions.persist`, `coach.technical_drills`, and `coach.session.activate`. Apply the equivalent v5 child sets to answer, end, and follow-up flows. The direct research method owns a root; session creation calls an internal undecorated research implementation to prevent a nested root.

Set stage outcomes from `CoachDiagnostic`, emit each gate code as a bounded `coach_gate` event, and record only the relevant Coach operational outcome/count metric. Do not move or duplicate existing `record_model_call` calls.

- [ ] **Step 4: Run production Coach and observability regressions**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability tests/test_services/test_coach_contracts.py tests/test_services/test_question_generator.py tests/test_routers/test_coach_async.py tests/test_routers/test_coach_router.py`

Expected: all tests pass; root count and shared model-call counts are unchanged.

- [ ] **Step 5: Commit the production hierarchy checkpoint**

```bash
git add backend/app/services/coach_service.py backend/app/services/question_generator.py backend/tests
git commit -m "feat(coach): trace production workflow stages"
```

### Task 4: Coach benchmark trace hierarchy and correlation

**Files:**
- Modify: `backend/benchmarks/coach/runner.py`
- Test: `backend/tests/benchmarks/coach/test_observability.py`

**Interfaces:**
- Consumes: Task 1 workflow/stage facade.
- Produces: one `coach_benchmark` root per scheduled scenario with v5 correlation and stage outcome/gate events.

- [ ] **Step 1: Write failing benchmark hierarchy tests**

Run one deterministic scenario and assert:

```python
assert root.attributes[WORKFLOW_NAME] == "coach_benchmark"
assert root.attributes[COACH_OPERATION] == "benchmark_scenario"
assert root.attributes[COACH_BENCHMARK_RUN_ID] == "run-1"
assert root.attributes[COACH_SCENARIO_ID] == scenario.id
assert [span.name for span in children] == [
    "coach.benchmark.scenario",
    "coach.benchmark.prepare",
    expected_production_stage,
    "coach.benchmark.validate",
    "coach.benchmark.score",
    "coach.benchmark.persist",
]
```

Assert IDs are absent from all metric calls, one bounded event is emitted per gate code, synthetic input is absent, and a raising telemetry double does not change the result artifact.

- [ ] **Step 2: Run benchmark observability tests and verify failure**

Run: `cd backend && python -m pytest -q --no-cov tests/benchmarks/coach/test_observability.py`

Expected: missing Coach benchmark root and stages.

- [ ] **Step 3: Instrument the scenario attempt without changing result control flow**

Wrap the existing scheduled-attempt body with one facade root and stages. Set result-derived attributes/events only after each existing operation completes; persist artifacts through the existing atomic writer. Keep all exception/status mapping outside telemetry failure paths.

- [ ] **Step 4: Run all Coach benchmark tests**

Run: `cd backend && python -m pytest -q --no-cov tests/benchmarks/coach`

Expected: all Coach benchmark tests pass and deterministic artifacts remain stable.

- [ ] **Step 5: Commit the benchmark checkpoint**

```bash
git add backend/benchmarks/coach/runner.py backend/tests/benchmarks/coach/test_observability.py
git commit -m "feat(coach-benchmark): trace scenario execution"
```

### Task 5: Failure isolation, privacy, and deployment invariants

**Files:**
- Modify: `backend/tests/test_observability/test_coach_runtime.py`
- Modify: `backend/tests/test_observability/test_coach_workflows.py`
- Modify: `backend/tests/test_observability/test_coach_async_links.py`
- Modify: `backend/tests/benchmarks/coach/test_observability.py`
- Modify: `backend/tests/test_tools/test_observability_compose_contract.py`
- Verify: `backend/tests/test_observability/test_shutdown.py`

**Interfaces:**
- Validates all 17 v5 section 19 requirements as executable regressions.

- [ ] **Step 1: Add the remaining explicit v5 invariant tests**

Add a parameterized prohibited-sentinel test for CV, JD, question, answer, transcript, path, and score values across spans/events/metrics. Add exporter/span/instrument failure doubles and assert unchanged API/database/artifact outcomes. Assert Compose core does not select the collector or set `HATCH_OBSERVABILITY_ENABLED`, optional requirements remain outside core, and `main.py` still calls `shutdown_telemetry(deadline_seconds=5.0)` once.

- [ ] **Step 2: Run the C3 acceptance test slice**

Run: `cd backend && python -m pytest -q --no-cov tests/test_observability tests/benchmarks/coach/test_observability.py tests/test_tools/test_observability_compose_contract.py tests/test_routers/test_coach_async.py`

Expected: all tests pass.

- [ ] **Step 3: Audit names and duplicate call sites**

Run:

```bash
rg -n 'hatch\.ai\.(workflow|provider|model_id)([^.]|$)' backend/app backend/benchmarks
rg -n 'record_model_call' backend/app/services backend/benchmarks/coach
rg -n 'TracerProvider|MeterProvider|shutdown_telemetry' backend/app
```

Expected: no conflicting aliases, no C3-added model-call recorder, and provider/shutdown ownership remains only in the shared runtime/application lifecycle.

- [ ] **Step 4: Commit the acceptance-test checkpoint**

```bash
git add backend/tests
git commit -m "test(coach): prove C3 observability invariants"
```

### Task 6: Operator documentation and specification status

**Files:**
- Modify: `docs/operations/OBSERVABILITY.md`
- Modify then move: `docs/implementation-specs/active/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md`
- Modify: `docs/README.md`
- Test: documentation/Compose command checks from Task 5

**Interfaces:**
- Documents the delivered trace hierarchy, safe data flow, metrics, privacy boundary, async links, and disable/cleanup procedure.

- [ ] **Step 1: Update the existing observability guide**

Add production and benchmark hierarchy examples, all eight Coach metrics, allowed dimensions, explicit content/score exclusions, the root-link semantics for async jobs, local inspection, and the fact that the default/core profile installs no collector or observability SDK.

- [ ] **Step 2: Complete and archive v5**

Set the frontmatter/status text to completed with C1/C2/C3 PR/checkpoint evidence, remove stale branch-state wording, move v5 from `active/` to `completed/`, and update `docs/README.md` to point to the completed location. Do not rewrite locked requirements.

- [ ] **Step 3: Run docs/config checks and commit**

Run: `git diff --check && cd backend && python -m pytest -q --no-cov tests/test_tools/test_observability_compose_contract.py tests/test_observability/test_shutdown.py`

Expected: all checks pass.

```bash
git add docs
git commit -m "docs(observability): document Coach telemetry"
```

### Task 7: Full verification and cohesive PR

**Files:**
- Verify all changed files; do not add unrelated changes.

**Interfaces:**
- Produces: a review-ready `feat/coach-c3-observability` branch containing only C3.

- [ ] **Step 1: Run formatting and lint checks**

Run: `cd backend && ruff check app tests benchmarks && ruff format --check app tests benchmarks`

Expected: zero errors.

- [ ] **Step 2: Run the complete backend and benchmark suites**

Run: `cd backend && python -m pytest -q`

Expected: all tests pass and the configured coverage floor passes.

- [ ] **Step 3: Run frontend type-check and Compose validation**

Run: `cd frontend && npm run type-check`

Run: `docker compose -f docker-compose.yml config --quiet && docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile observability config --quiet`

Expected: all commands exit zero.

- [ ] **Step 4: Confirm branch scope and checkpoint final state**

Run:

```bash
git status --short
git diff --check origin/main...HEAD
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
```

Expected: clean worktree, C3-only commits, no unrelated main-workspace `.gitignore` change.

- [ ] **Step 5: Push and create the cohesive C3 PR**

```bash
git push -u origin feat/coach-c3-observability
gh pr create --base main --head feat/coach-c3-observability --title "feat(coach): add privacy-safe observability" --body-file /tmp/coach-c3-pr.md
```

Expected: one PR containing the complete C3 scope and verification evidence.
