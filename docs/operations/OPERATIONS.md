# Hatch operations guide

This guide collects the installation, maintenance, development, and troubleshooting details that are useful after you understand what Hatch does. Use the [documentation index](../README.md) for the broader doc map and the root [README](../../README.md) for the product overview.

## Installation details

The one-command installers clone or update `arvindsoni2/hatch`, create per-user state, create missing local configuration files, and start the lightweight Docker Compose stack.

### Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
```

Easy installs use `${HATCH_HOME:-~/.hatch}` for host-managed state. The managed checkout location can be changed separately when running the installer locally.

The Linux installer can add Docker's official repository and install Docker Engine on Ubuntu 22.04/24.04, Debian 12/13, and Fedora 43/44. Fedora 42 and other Linux versions require manual Docker setup. macOS always requires Docker Desktop to be installed manually.

```bash
./install.sh --check-only --json
./install.sh --resume
```

Check-only is strictly read-only and creates neither logs nor resume state. Do not combine it with resume.

### Windows PowerShell

```powershell
iwr https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1 | iex
```

Windows also uses `%HATCH_HOME%` when set, otherwise `%USERPROFILE%\.hatch`, for host-managed state. Pass `-InstallDir` when running the script locally to change the managed checkout location.

Both installers:

- verify Docker Compose, Git, and Python
- create the per-user state directory at `${HATCH_HOME:-~/.hatch}`
- start without downloading a local model unless you choose local AI
- create `data/profile.yaml` and `.env` when missing
- build and start the beginner-safe Docker Compose stack

Interactive installation asks for the mode through `/dev/tty`; it does not silently choose one when invoked through a pipe. Non-interactive installation requires both mode and backend profile:

```bash
./install.sh --mode ai-later
./install.sh --mode cloud
./install.sh --mode local
./install.sh --mode advanced
./install.sh --mode advanced --backend-profile full
./install.sh --non-interactive --yes --install-docker --allow-docker-group --mode ai-later --backend-profile core
```

`--install-docker` permits repository and package installation. It never permits conflict-package removal. Docker-group membership requires `--allow-docker-group` because the docker group grants root-level privileges. Docker's bridge networking and port publishing create firewall rules and may interact with `ufw` or `firewalld`; Hatch does not disable or rewrite firewall controls.

PowerShell supports the same concepts:

```powershell
.\install.ps1 -Mode cloud -BackendProfile core
.\install.ps1 -Mode advanced -BackendProfile full
```

## Host CLI

The installer creates a host-side `hatch` command for common maintenance tasks:

```bash
hatch status
hatch doctor
hatch probe
hatch models list
hatch models install
hatch models remove
hatch apply-ai-config
hatch secrets status
hatch secrets set openai
hatch secrets unset openai
hatch capabilities list
hatch capabilities status
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
hatch capabilities disable
hatch update --dry-run
hatch uninstall
```

`hatch probe` writes `${HATCH_HOME}/probe/hardware_probe_latest.json`. The easy Compose stack mounts `${HATCH_HOME}/probe` read-only into the backend. A valid legacy snapshot under `${HATCH_HOME}/config` is copied forward without deleting the legacy file.

## Manual Docker installation

Use manual Docker setup when you are developing from a checkout rather than using the managed installer.

```bash
git clone https://github.com/arvindsoni2/hatch.git
cd hatch
cp .env.example .env
cp data/profile.yaml.example data/profile.yaml
docker compose up -d --build
```

Open these local endpoints:

- Hatch: <http://localhost:3000>
- Protected API documentation: <http://localhost:8000/docs>

## AI and capability profiles

AI mode and backend capability profile are separate choices. AI mode decides whether Hatch uses no AI, cloud AI, or local model services. Backend capability profile decides which optional Python packages are installed in the backend image.

Capability profiles:

```bash
hatch capabilities status
hatch capabilities enable browser
hatch capabilities enable local-embeddings
hatch capabilities enable full
hatch capabilities disable
```

Manual Compose overrides remain available for developers:

```bash
docker compose -f docker-compose.yml -f docker-compose.browser.yml up -d --build backend
docker compose -f docker-compose.yml -f docker-compose.local-embeddings.yml up -d --build backend
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d --build backend
```

`docker-compose.local-ai.yml` adds bundled `llama.cpp` model services after local model selection. It does not switch the Python backend to the local-embeddings image.

## Docker services

The default stack runs local services bound to localhost:

| Service | Local address | Notes |
|---|---|---|
| Frontend | `127.0.0.1:3000` | Next.js user interface |
| Backend | `127.0.0.1:8000` | FastAPI, agent workers, and protected APIs |
| Primary LLM | `127.0.0.1:8080` | Optional `llama.cpp` server |
| Triage LLM | `127.0.0.1:8081` | Optional fast `llama.cpp` server |

Persistent user data is bind-mounted from `./data`. The database filename remains `data/jobpilot.db` for upgrade compatibility.

Useful commands:

```bash
docker compose ps
docker compose logs -f
docker compose restart backend frontend
docker compose down
docker compose up -d --build
```

Optional Docker Compose overrides are documented in `infrastructure/docker/docker-compose.override.yml.example`. Copy that file to `docker-compose.override.yml` before customizing it so Compose discovers it automatically.

## Development checks

Run the frontend and backend directly:

```bash
make dev
```

Run broad quality checks:

```bash
make test
make lint
docker compose config --quiet
```

Common Make targets:

```bash
make models
make docker-up
make docker-logs
make migrate
make scrape
make reset-user
make test-reset-user
make reset-app-lock
make audit-scripts
```

Frontend checks:

```bash
cd frontend
npm ci
npm run type-check
npm test
npm run test:e2e
```

Backend checks:

```bash
cd backend
python -m pytest
```

## Configuration and secrets

User configuration lives in `data/profile.yaml`:

- identity and master CV path
- target roles and locations
- compensation and legal preferences
- skills, domains, certifications, and proof points
- scoring weights and shortlist threshold
- large language model (LLM) provider and models
- scrape interval, tailoring batch size, and follow-up timing

Supported locale packs currently include the United Kingdom, India, Ireland, and the United Arab Emirates. Locale definitions live in `locales/`.

Easy installs store cloud keys in `${HATCH_HOME}/config/secrets.env`, and only the host CLI changes that file. Existing developer installs may continue to use `.env` or `data/api_keys.env`.

## App lock recovery

App lock is enabled by default. With `HATCH_APP_PASSWORD` unset, first run stores a bcrypt password hash in SQLite. Setting `HATCH_APP_PASSWORD` makes the environment the authoritative password source.

To recover from a forgotten database-backed password:

```bash
bash scripts/reset-app-lock.sh
```

For automation after reviewing the action:

```bash
bash scripts/reset-app-lock.sh --yes
```

This removes only app-lock configuration and sessions. Profile, jobs, applications, generated documents, and other user data are preserved.

## Reset local data

Return Hatch to first-run state:

```bash
make reset-user
```

This is destructive. It removes the application database and checkpoints, generated documents, Coach recordings, temporary uploads, profile, and master CV artifacts. Downloaded models, `data/profile.yaml.example`, and `data/api_keys.env` are retained.

To clear jobs and workflow history while retaining the existing profile, CV, and saved API keys:

```bash
bash scripts/reset-user-data.sh --keep-profile
```

To deliberately clear `data/api_keys.env`, add `--delete-secrets` after reviewing the destructive prompt.

## Troubleshooting

Start with service health before changing configuration.

### Dashboard does not open

```bash
docker compose ps
docker compose logs backend frontend
curl -f http://localhost:8000/api/health
```

### Local model is unhealthy

Confirm the model files exist, then restart the local model services:

```bash
ls -lh data/models/Qwen_Qwen3.5-4B-Q4_K_M.gguf data/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf
bash scripts/fetch_models.sh
docker compose restart llm-primary llm-triage
```

### Tailoring or Coach is slow

Local CPU generation can take several minutes for full CV packages. Check the System Event Log and large language model call traces in Settings, then inspect backend and model logs:

```bash
docker compose logs -f backend llm-primary
```

## Architecture notes

Hatch is a Next.js frontend backed by FastAPI services, SQLite persistence, local files, and optional local or cloud AI providers.

```text
Next.js frontend
       |
FastAPI API and async agent workers
       |
SQLite data + profile.yaml + generated documents
       |
llama.cpp local models or an optional cloud LLM provider
```

The backend uses Scout, Scorer, Tailor, and Coach workers. Long-running Tailor and Coach work is represented by asynchronous jobs so the user interface can show completion and failure states.

## Outcome learning

Hatch can calculate a separate opportunity score from your own resolved application history. The existing fit score remains unchanged. Opportunity adjustments are deterministic, capped, calculated locally without an LLM or embeddings, and exclude protected personal characteristics, company identity, recruiter details, notes, and document contents.

Learning activates after the configured minimum number of resolved applications. Applications without a response become eligible negatives only after the configured no-response window. Withdrawn and declined applications are excluded. Profile Settings can disable individual signals, recompute scores, or reset the learning window without deleting application history.
