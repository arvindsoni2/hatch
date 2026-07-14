# Local Models

Local AI in Hatch uses two optional `llama.cpp` services and a host-side curated model catalogue. Local services are never selected for Cloud mode.

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
hatch models install --primary <catalog-id> --triage <catalog-id>
hatch apply-ai-config --restart
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

Model suitability depends on the host machine. After `hatch probe`, Hatch performs curated live Hugging Face discovery, validates immutable revision and LFS checksum metadata, and ranks models against RAM and model-storage space. If live discovery is unavailable or rate-limited, a recent validated cache or pinned fallback catalogue is shown. The user always chooses both routes; discovery never starts a download.

## Switching And Failure Handling

- Re-run `hatch models install --primary <catalog-id> --triage <catalog-id>` to install a selected pair
- Re-run `hatch apply-ai-config` after changing selected models

Downloads are written to `.part`, verified with SHA-256 and exact size when available, atomically renamed, and recorded in `${HATCH_HOME}/config/model_verification.json`. A failed download leaves any existing verified file in place. `scripts/fetch_models.sh` is only a compatibility wrapper and refuses to choose defaults.

`docker-compose.local-ai.yml` requires explicit filenames supplied by the host CLI. The root `docker-compose.yml` retains a fixed model pair only for developer-stack reproducibility.
- If local runtime is unavailable, Hatch falls back to a guided setup or failure state rather than pretending the operation succeeded
