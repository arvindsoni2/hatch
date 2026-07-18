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

Stop and remove only the observability stack containers:

```bash
docker compose -f docker-compose.yml \
  -f docker-compose.observability.yml \
  --profile observability down
```

This command does not delete Hatch business data because it does not use
`--volumes`. To return to the default profile, start Hatch with the normal
Compose command and without the observability overlay.

## Shutdown behaviour

Normal export uses batched spans and periodic metrics. During backend shutdown,
Hatch gives the complete telemetry flush-and-close sequence one five-second
wall-clock deadline. A blocked exporter runs on a daemon thread and is
abandoned after that deadline, so telemetry cannot prevent application
shutdown. Hatch emits at most one redacted warning for a failed or timed-out
telemetry shutdown.
