# Local AI Observability

Status: current for the optional `observability` backend profile.

Hatch can emit privacy-safe OpenTelemetry traces and metrics for backend HTTP
requests, AI workflows, and representative local-model benchmark pairs. The
feature is disabled by default and is not installed in the core backend image.

## Enable the local stack

Start Hatch with the observability image and local OpenTelemetry Collector:

```bash
docker compose -f docker-compose.yml \
  -f docker-compose.observability.yml \
  --profile observability up -d --build
```

The backend sends OTLP over the private Compose network. OTLP is not published
on the host. The Collector writes basic trace diagnostics to its container log
and publishes Prometheus metrics only on `127.0.0.1:8889`.

Check the backend health response:

```bash
curl http://127.0.0.1:8000/api/health
```

The `telemetry.status` value is one of:

- `disabled`: observability was not enabled.
- `active`: providers and instrumentation initialized.
- `degraded`: setup failed, but Hatch continued without telemetry.

Exporter errors, endpoints, environment values, and credentials are never
included in the health response.

## Data boundary

Hatch exports controlled identifiers and operational measurements only:
workflow and stage names, provider type, model ID, prompt and skill versions,
attempt and repair counts, stable validation gate codes, token counts when
available, durations, benchmark run/case/seed values, and a document ID only
after successful persistence.

Hatch does not export prompt or response text, CV content, job-description
content, personal fields, authorization data, secrets, or raw filesystem
paths. Attribute values pass through a bounded Hatch-owned allowlist before
they reach OpenTelemetry. HTTP instrumentation does not capture headers or
bodies. Log correlation injects trace and span IDs but does not enable
OpenTelemetry log export.

Coach applies the same boundary to interview data. Question text, model-answer
text, transcripts, word timestamps, rubric evidence, strengths and
improvements, company-research text and URLs, face-analysis values, audio/video
URIs, filesystem paths, and user performance scores stay in local business
data or benchmark artifacts. Session, async-job, benchmark-run, and scenario
IDs are permitted only on traces for correlation and are always removed from
metric dimensions.

## Coach trace structure

Production operations keep the existing `coach_generation` root workflow and
identify the operation with `hatch.coach.operation`:

```text
hatch.ai.workflow.coach_generation
└── coach.session.create | coach.answer.submit | coach.session.end |
    coach.followup.plan | coach.company_research
    └── coach.* orchestration stages
```

The child stages cover session persistence, research, question generation and
its optional repair, one model-answer stage per question, technical drills,
text/audio answer processing, evaluation, rubric synthesis, report generation,
and follow-up planning. Audio jobs include `coach.audio.persist` and
`coach.transcription`; no audio URI or transcript is attached.

Each scheduled Coach benchmark scenario has a separate root:

```text
hatch.ai.workflow.coach_benchmark
└── coach.benchmark.scenario
    ├── coach.benchmark.prepare
    ├── <production Coach stage>
    ├── coach.benchmark.validate
    ├── coach.benchmark.score
    └── coach.benchmark.persist
```

Benchmark roots may carry the run ID, suite version, scenario ID, configured
model ID, seed, repetition, profile, status, and outcome. Each gate is a
bounded `coach_gate` event. Synthetic fixture content is not attached.

Coach HTTP handlers capture an immutable request `SpanContext` when an async
job is created. The background `coach_generation` root has one link to that
context, no request-span parent, and does not keep the completed request open.
The linked root contains the session and async-job IDs as trace attributes;
those IDs are absent from metrics.

## Coach metrics

Coach reuses the shared `hatch.ai.*` model-call metrics for provider duration,
calls, tokens, repairs, validation failures, and outcomes. It does not
increment those metrics a second time or add another mandatory model-call
span. The Coach-only operational instruments are:

- `hatch.coach.stage.duration`
- `hatch.coach.stage.outcomes`
- `hatch.coach.question_generation.count`
- `hatch.coach.model_answer.outcomes`
- `hatch.coach.evaluation.outcomes`
- `hatch.coach.rubric.outcomes`
- `hatch.coach.report.outcomes`
- `hatch.coach.async_job.outcomes`

Allowed dimensions are bounded operational values such as stage, outcome,
provider type, configured model ID, recording mode, and gate code. Company
name, role title, session/job/question/run/scenario IDs, scenario text, and
user or benchmark scores are not metric dimensions.

## Inspect and stop

Read the Collector's local trace diagnostics:

```bash
docker compose -f docker-compose.yml \
  -f docker-compose.observability.yml \
  --profile observability logs otel-collector
```

Prometheus-format metrics are available locally:

```bash
curl http://127.0.0.1:8889/metrics
```

Useful local searches include `hatch_coach_stage_duration`,
`hatch_coach_evaluation_outcomes`, and
`hatch_coach_async_job_outcomes` (Prometheus normalises dots to underscores).

Stop and remove only the observability stack containers:

```bash
docker compose -f docker-compose.yml \
  -f docker-compose.observability.yml \
  --profile observability down
```

This command does not delete Hatch business data because it does not use
`--volumes`. To return to the default profile, start Hatch with the normal
Compose command and without the observability overlay. The default/core image
does not install the optional OpenTelemetry SDK, start a Collector, or set
`HATCH_OBSERVABILITY_ENABLED`.

## Shutdown behaviour

Normal export uses batched spans and periodic metrics. During backend shutdown,
Hatch gives the complete telemetry flush-and-close sequence one five-second
wall-clock deadline. A blocked exporter runs on a daemon thread and is
abandoned after that deadline, so telemetry cannot prevent application
shutdown. Hatch emits at most one redacted warning for a failed or timed-out
telemetry shutdown.
