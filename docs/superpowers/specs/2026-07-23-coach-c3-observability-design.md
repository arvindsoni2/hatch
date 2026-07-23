# Coach C3 Observability Design

**Status:** Approved by the v5 specification and the owner's prior architecture approval

**Scope:** PR C3 only. Extend the merged OpenTelemetry facade and instrument production Coach and the Coach benchmark without changing Coach APIs, persistence contracts, configured models, or the default/core runtime profile.

## Context and constraints

PR C1 and C2 are merged. The shared observability facade on `main` already owns provider setup, exporters, HTTP instrumentation, structured-log correlation, shared AI metrics, and the application-wide five-second shutdown deadline. It also owns the three existing `coach_generation` workflow roots through decorators on session creation, answer submission, and session completion.

C3 must preserve those roots and shared model-call counters. It may add only privacy-safe Coach attributes, Coach operational metrics, stage helpers, and immutable request-context linking. Telemetry must remain optional, disabled by default, and unable to affect a Coach result or database transition.

## Approaches considered

### 1. Extend the shared facade and enrich the existing roots (selected)

Add immutable trace-context capture and a background-context handoff to the existing facade. Extend `trace_workflow` with static, allowlisted root attributes, and add one Coach stage helper that records the exact span names and Coach stage metrics. The three current decorators remain the sole roots; follow-up planning receives the missing decorator, while company research uses a decorated public entry point and an undecorated internal implementation so session creation cannot create a nested second root.

This is the smallest change consistent with v5. It centralises privacy filtering, preserves fail-open behaviour, and makes duplicate instrumentation structurally difficult.

### 2. Create roots in routers or `AsyncJobService`

This could make request/background boundaries obvious, but it would wrap already-decorated service methods and create duplicate `coach_generation` roots. It is rejected by v5.

### 3. Instrument each provider client directly

This could yield detailed timings but would compete with shared model-call metrics, spread Coach attribute policy across many services, and fail to describe persistence and deterministic stages. It is rejected in favour of orchestration-level stages around the existing provider instrumentation.

## Architecture

### Shared facade extensions

`app.observability.attributes` remains the only telemetry attribute allowlist. It gains the v5 `hatch.coach.*` constants, typed value classes, and separate trace-versus-metric sanitisation. Trace sanitisation permits the two correlation IDs; metric sanitisation always removes them.

`TelemetryRuntime` gains:

- `capture_trace_context()`, returning a frozen token containing only a valid OpenTelemetry `SpanContext`, or an empty token when disabled/unavailable;
- `use_background_trace_context(token)`, a fail-open context manager that carries the token to the existing workflow decorator without retaining the request span object;
- workflow-span link creation using an empty OpenTelemetry parent context and exactly one `Link`, so the completed HTTP request is correlated but is not the background parent;
- static attributes on `trace_workflow`, allowing an operation to be attached to the existing root;
- `coach_stage_span()`, which creates an exact `coach.*` stage span, applies only allowlisted attributes, and records duration/outcome;
- bounded Coach metric recording methods for the seven v5 operational outcome/count families.

All imports of OpenTelemetry context/link types stay inside the facade. Disabled or degraded runtimes return no-op tokens/spans and do not create instruments.

### Async correlation

The request-side Coach queue captures a token after the async job is persisted and before scheduling. `AsyncJobService.run` accepts that immutable token and a frozen set of allowlisted trace-correlation attributes as optional metadata. Its task wrapper activates them only while awaiting the supplied coroutine. The existing service decorator consumes them when opening the single workflow root.

Task creation may copy the request's ambient context, but the facade explicitly passes an empty parent context when a valid background token exists. The resulting root therefore has no parent and has one link to the request `SpanContext`. The root carries session/job IDs as trace attributes only.

### Production trace hierarchy

The existing `coach_generation` root gains one bounded operation value:

- `session_create`
- `answer_submit`
- `session_end`
- `followup_plan`
- `company_research`

Each operation opens its named orchestration stage (`coach.session.create`, `coach.answer.submit`, `coach.session.end`, or `coach.followup.plan`) and then the applicable child stages listed in v5 sections 18.4–18.7. Existing provider-level `hatch.ai.stage.*` spans and shared model-call metrics remain below those orchestration stages and are not recreated.

Stage attributes come from persisted diagnostics and bounded request metadata: counts, category, recording mode, outcome, fallback state, and gate-code events. Content, scores, role/company names, URLs, prompts, responses, transcripts, paths, and evidence are never attached.

### Benchmark hierarchy

Each scheduled Coach scenario receives one `coach_benchmark` root with operation `benchmark_scenario`. It contains `coach.benchmark.scenario`, prepare, the production stage call, validate, score, and persist spans. Correlation attributes are limited to run ID, suite version, scenario ID, configured model ID, seed, repetition, profile, status/outcome, and bounded gate-code events.

The benchmark's existing artifacts remain authoritative. A telemetry failure is swallowed and cannot alter validation, scoring, classification, persistence, or resume state.

### Metrics

The facade creates these instruments only for an active meter:

- `hatch.coach.stage.duration`
- `hatch.coach.stage.outcomes`
- `hatch.coach.question_generation.count`
- `hatch.coach.model_answer.outcomes`
- `hatch.coach.evaluation.outcomes`
- `hatch.coach.rubric.outcomes`
- `hatch.coach.report.outcomes`
- `hatch.coach.async_job.outcomes`

Dimensions are drawn from a metric-specific allowlist and bounded value sets. Session, job, question, run, and scenario IDs are excluded from metric dimensions. Shared `hatch.ai.model.*` instruments continue to be recorded only by their existing call sites.

## Failure handling

Every new facade operation is fail-open. Span/link/instrument creation and exporter failures are contained in the facade. Coach persistence and async terminal status run outside telemetry error paths. No new provider lifecycle, exporter, collector, database migration, or shutdown call is introduced.

## Testing strategy

Tests use in-memory/fake tracers and meters at the facade boundary and service doubles at orchestration boundaries. They prove disabled no-op behaviour, exact root/stage structure, one-link/no-parent async correlation, trace/metric allowlist separation, privacy exclusions, diagnostic outcomes and fallbacks, no shared model metric double-counting, benchmark correlation, exporter failure isolation, unchanged five-second shutdown, and unchanged core Compose behaviour.

Production tests assert behaviour and database state before inspecting telemetry so telemetry cannot become a hidden correctness dependency. Existing Coach, benchmark, and observability suites remain regression gates.

## Documentation and completion

Update the existing `docs/operations/OBSERVABILITY.md` rather than adding an operator guide. On completion, update the v5 implementation status to record C1–C3 delivery and archive the completed specification following the repository's existing convention.
