# Local Models

Local AI in Hatch uses two optional `llama.cpp` services and a host-side model catalogue.

> Last verified against `main`: 2026-07-10

## Hardware Probe

Run:

```bash
hatch probe
```

The probe records host RAM, free disk, port availability, OS/arch, and supported model buckets.

## Model Roles

- Primary model: heavier scoring, tailoring, and coach work
- Triage model: lighter and faster relevance filtering

## Install Flow

```bash
hatch models list
hatch models install
hatch apply-ai-config
```

Downloads require explicit confirmation and checksum verification.

## Storage

Easy installs store models in `${HATCH_HOME}/models`. The developer stack mounts `./data/models`.

## Reachability

Local services bind to:

- `127.0.0.1:8080`
- `127.0.0.1:8081`

## Expectations

Model suitability depends on the host machine. Hatch recommends compatible models, but the user chooses the download set.

## Switching And Failure Handling

- Re-run `hatch models install` to add supported models
- Re-run `hatch apply-ai-config` after changing selected models
- If local runtime is unavailable, Hatch falls back to a guided setup or failure state rather than pretending the operation succeeded
