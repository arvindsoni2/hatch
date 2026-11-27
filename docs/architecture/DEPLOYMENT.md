---
title: Hatch Deployment
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main
last_verified: 2026-11-27
supersedes: []
superseded_by: []
---

# Deployment

## Supported Model

Hatch is designed for local Docker Compose deployment on a single machine.

## Easy Install

Easy installs use `docker-compose.easy.yml` and add `docker-compose.local-ai.yml` when local runtime AI is selected. The easy path also mounts host-managed config and model directories from `${HATCH_HOME}`.

## Developer Deployment

The developer stack uses `docker-compose.yml`, which starts frontend, backend, and both local `llama.cpp` services by default.

## Capability Profiles

The current backend capability profiles are:

- `core`
- `browser`
- `local-embeddings`
- `full`

Those map to Compose overlays such as `docker-compose.browser.yml`, `docker-compose.local-embeddings.yml`, and `docker-compose.full.yml`, and to targets in `backend/Dockerfile` (`core`, `browser`, `local-ai` for local embeddings, `full`). An `observability` target and `docker-compose.observability.yml` add an opt-in local OpenTelemetry collector.

## Images

- Every base image is pinned by multi-architecture digest: `python:3.12-slim` for the backend, `node:24-bookworm-slim` for the backend's Node binary and DOCX template modules, `node:24-alpine` for the frontend, and the `llama.cpp` server image for local models.
- Node 24 is the supported Node.js version for images, CI and local development.
- Every backend API target includes Node and the DOCX template modules, so CV and cover-letter rendering works in each profile.
- Python packages install against `backend/constraints.txt`.

## Optional Model Tiers

- `llm-primary` (Tier S) and `llm-triage` (Tier T) are the default local model services.
- `llm-deep` (Tier L) is defined in `docker-compose.local-ai.yml` under the Compose profile `deep`. It starts only when the owner enables Tier L in Settings and a deep model has been promoted.

## Ports

- `3000` frontend
- `8000` backend
- `8080` local primary LLM
- `8081` local triage LLM
- `8082` optional deep LLM (`deep` profile)
- `8889` optional collector metrics (observability overlay)

All published ports bind to `127.0.0.1`.

## Health Checks

Current health checks are wired for:

- frontend root page
- backend `/api/health`
- local model `/health` endpoints

## Start, Stop, Restart

The host CLI wraps Compose:

- `hatch start`
- `hatch stop`
- `hatch restart`
- `hatch logs`

## Update Model

Managed easy installs support `hatch update`, which backs up config and data, validates Compose, and can restart the stack.

## Windows Differences

Windows runs through Docker Desktop with Linux containers and a PowerShell-based installer flow.

## Unsupported Assumptions

- Kubernetes is not a current deployment target.
- Multi-user hosted SaaS operation is not a current deployment target.
- Secrets management beyond the current host-config and local-env flows is not part of the current deployment contract.
