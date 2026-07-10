---
title: Hatch Deployment
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
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

Those map to Compose overlays such as `docker-compose.browser.yml`, `docker-compose.local-embeddings.yml`, and `docker-compose.full.yml`.

## Ports

- `3000` frontend
- `8000` backend
- `8080` local primary LLM
- `8081` local triage LLM

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
