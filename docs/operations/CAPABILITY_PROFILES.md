# Capability Profiles

Capability profiles control optional backend dependencies. They are separate from the chosen AI runtime.

> Last verified against `main`: 2026-07-10

## Current Profiles

| Capability | core | browser | local-embeddings | full |
|---|---:|---:|---:|---:|
| Base backend APIs | Yes | Yes | Yes | Yes |
| Browser automation dependencies | No | Yes | No | Yes |
| Local embeddings dependencies | No | No | Yes | Yes |
| Perception and advanced coach dependencies | No | No | No | Yes |

## Install-Time Selection

The easy install defaults to `core`. Advanced installs can choose a larger backend profile when they explicitly need it.

## Enabling Later

```bash
hatch capabilities status
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
```

## Disabling

```bash
hatch capabilities disable
```

That returns the backend profile to `core`.

## Persistence

The active profile is stored in `${HATCH_HOME}/config/backend_capabilities.json`.

## Compose Resolution

- `core`: `docker-compose.easy.yml`
- `browser`: add `docker-compose.browser.yml`
- `local-embeddings`: add `docker-compose.local-embeddings.yml`
- `full`: add `docker-compose.full.yml`

## Hardware Impact

- `core`: lightest backend
- `browser`: adds browser/runtime dependencies
- `local-embeddings`: adds local embedding dependencies
- `full`: largest backend footprint
