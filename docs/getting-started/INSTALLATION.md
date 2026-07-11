# Installation

Hatch is a self-hosted workspace that runs through Docker Compose. The recommended path is the guided installer, which starts the lightweight application stack and lets you configure AI later.

> Last verified against `main`: 2026-07-10

## Prerequisites

- Docker with `docker compose`
- Git
- Python for the host `hatch` wrapper
- Ports `3000` and `8000` available

Windows users should prefer the dedicated [Windows install guide](WINDOWS_INSTALL.md).

## Recommended Easy Install

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
```

Windows:

```powershell
.\install-hatch.cmd
```

The easy install:

- clones or updates the repo
- creates `${HATCH_HOME:-~/.hatch}` for host-managed state
- starts the lightweight backend profile
- does not download local models unless you explicitly choose local AI
- keeps provider secrets outside the browser

## Capability Profile Selection

The easy installer defaults to backend profile `core`. Advanced installs can select:

- `core`
- `browser`
- `local-embeddings`
- `full`

Examples:

```bash
./install.sh --mode advanced --backend-profile full
```

```powershell
.\install.ps1 -Mode advanced -BackendProfile full
```

## Manual Docker Compose Install

Use this when developing from a local checkout:

```bash
git clone https://github.com/arvindsoni2/hatch.git
cd hatch
cp .env.example .env
cp data/profile.yaml.example data/profile.yaml
docker compose up -d --build
```

## Expected Ports

- `127.0.0.1:3000` frontend
- `127.0.0.1:8000` backend
- `127.0.0.1:8080` optional primary local model
- `127.0.0.1:8081` optional triage local model

## Data Directory

Developer and manual installs keep application data in `./data`.

Easy installs also use host-managed state under `${HATCH_HOME}`:

- `${HATCH_HOME}/config`
- `${HATCH_HOME}/models`
- `${HATCH_HOME}/probe`
- `${HATCH_HOME}/logs`
- `${HATCH_HOME}/backups`

## Initial Health Verification

```bash
docker compose ps
curl -f http://127.0.0.1:8000/api/health
curl -f http://127.0.0.1:3000
```

## Update

Managed installs support:

```bash
hatch update --dry-run
hatch update
```

Updates are refused when the managed checkout is dirty.

## Uninstall

`hatch uninstall` is non-destructive by default and preserves user data under `${HATCH_HOME}`.

Purge flags require explicit confirmation:

```bash
hatch uninstall --purge-config --purge-models --purge-secrets --purge-data --yes
```

## Related Guides

- [First run](FIRST_RUN.md)
- [Windows install](WINDOWS_INSTALL.md)
- [Operations guide](../operations/OPERATIONS.md)
- [Troubleshooting](TROUBLESHOOTING.md)
