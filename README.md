# Hatch

Hatch is a self-hosted job search and application assistant. It finds roles, scores them against your profile, prepares tailored CV and cover-letter packages, tracks applications, and creates interview-preparation sessions.

Hatch never submits an application for you. You review the documents, submit on the employer's site, and then confirm the application in Hatch.

## Product Flow

1. **Scout** collects jobs from enabled boards.
2. **Scorer** ranks jobs against your profile and preferences.
3. **Tailor** prepares an ATS-oriented CV and cover letter without inventing experience.
4. You review the package, submit externally, and mark the application as applied.
5. **Coach** creates an interview-preparation session for applied roles.

The main screens are:

- **Today:** work requiring attention and clearly labelled all-time agent output.
- **Stream:** scored roles moving through the agent pipeline.
- **Tracker:** the application Kanban board.
- **Prep:** manual and application-linked Coach sessions.

## Application Tracker

The Tracker follows the real application journey from left to right:

`Discovered -> Preparing -> Ready to submit -> Applied -> Interview -> Offered -> Accepted`

- Drag a card only to its next valid stage.
- Use the card's **Move to...** menu as a keyboard-accessible alternative.
- Backward dragging is blocked.
- Rejected, withdrawn, and declined roles use explicit close actions.
- Preparing is system-managed while Hatch creates or reviews documents.
- Moving a role to Applied records the date, creates a follow-up, and queues Coach prep.

## Quick Start

### Linux and macOS

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
```

The default install directory is `~/.local/share/hatch`. Override it with `HATCH_DIR`.

### Windows PowerShell

```powershell
iwr https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1 | iex
```

The default install directory is `%LOCALAPPDATA%\Hatch`. Pass `-InstallDir` when running the script locally to change it.

Both installers:

- verify Docker Compose and Git;
- clone or update `arvindsoni2/hatch`;
- download the bundled Qwen3 GGUF models, about 3 GB total;
- create `data/profile.yaml` and `.env` when missing;
- build and start the Docker Compose stack.

Open:

- Dashboard: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>

### Manual Docker Install

```bash
git clone https://github.com/arvindsoni2/hatch.git
cd hatch
cp .env.example .env
cp data/profile.yaml.example data/profile.yaml
bash scripts/fetch_models.sh
docker compose up -d --build
```

Complete onboarding at <http://localhost:3000> or edit `data/profile.yaml` before running the agents.

## Local AI

The default stack runs two local llama.cpp services:

| Service | Model | Port | Purpose |
|---|---|---:|---|
| `llm-primary` | `Qwen3-4B-Q4_0.gguf` | 8080 | CV, cover letter, detailed scoring, Coach |
| `llm-triage` | `Qwen3-0.6B-Q4_0.gguf` | 8081 | Fast initial filtering |

The model ports bind to localhost only. Model files live in `data/models/` and are not committed.

Cloud providers are optional. Add the relevant key to `.env` and select the provider during onboarding or in Settings.

## Configuration

User configuration lives in `data/profile.yaml`:

- identity and master CV path;
- target roles and locations;
- compensation and legal preferences;
- skills, domains, certifications, and proof points;
- scoring weights and shortlist threshold;
- LLM provider and models;
- scrape interval, tailoring batch size, and follow-up timing.

Supported locale packs currently include the UK, India, Ireland, and UAE. Locale definitions live in `locales/`.

Secrets belong in `.env` or `data/api_keys.env`. Personal data, databases, generated documents, recordings, and models under `data/` are gitignored.

## Docker Services

| Service | Local address | Notes |
|---|---|---|
| Frontend | `127.0.0.1:3000` | Next.js UI |
| Backend | `127.0.0.1:8000` | FastAPI and agent workers |
| Primary LLM | `127.0.0.1:8080` | llama.cpp server |
| Triage LLM | `127.0.0.1:8081` | llama.cpp server |

Persistent user data is bind-mounted from `./data`. The existing database filename remains `data/jobpilot.db` for upgrade compatibility.

Useful commands:

```bash
docker compose ps
docker compose logs -f
docker compose restart backend frontend
docker compose down
docker compose up -d --build
```

On Linux, `install.sh` can optionally install `hatch.service` as a user service for startup on login.

## Development

Run the frontend and backend directly:

```bash
make dev
```

Quality checks:

```bash
make test
make lint
docker compose config --quiet
```

Common Make targets:

```bash
make models          # download local GGUF models
make docker-up       # build and start the stack
make docker-logs     # follow container logs
make migrate         # run database migrations
make scrape          # trigger Scout manually
make reset-user      # remove local user/job data after confirmation
```

## Architecture

```text
Next.js frontend
       |
FastAPI API and async agent workers
       |
SQLite data + profile.yaml + generated documents
       |
llama.cpp local models or an optional cloud LLM provider
```

The backend uses an event-driven Scout, Scorer, Tailor, and Coach pipeline. Long-running Tailor and Coach work is represented by asynchronous jobs so the UI can show completion and failure states.

## Troubleshooting

### The dashboard does not open

```bash
docker compose ps
docker compose logs backend frontend
curl -f http://localhost:8000/api/health
```

### A local model is unhealthy

Confirm both files exist:

```bash
ls -lh data/models/Qwen3-4B-Q4_0.gguf data/models/Qwen3-0.6B-Q4_0.gguf
bash scripts/fetch_models.sh
docker compose restart llm-primary llm-triage
```

### Tailoring or Coach is slow

Local CPU generation can take several minutes, particularly for full CV packages. Check the System Event Log and LLM Call Traces in Settings, then inspect:

```bash
docker compose logs -f backend llm-primary
```

### Reset local data

```bash
bash reset-user-data.sh
```

This is destructive and should only be used when intentionally starting again.

## Safety and Privacy

- Application submission always remains a human action.
- Tailoring may rephrase verified experience and align terminology, but must not fabricate claims.
- Local AI keeps prompts on the machine. Cloud providers receive prompts when explicitly configured.
- Raw webcam video used by optional interview practice is processed in the browser and is not uploaded.
- Optional Coach presence analysis sends only numeric camera-attention and head-stability summaries. It can be disabled and its saved consent revoked in Profile Settings.

## Outcome Learning

Hatch can calculate a separate **opportunity score** from your own resolved application history. The existing fit score remains unchanged. Opportunity adjustments are deterministic, capped, calculated locally without an LLM or embeddings, and exclude protected personal characteristics, company identity, recruiter details, notes, and document contents.

Learning activates after the configured minimum number of resolved applications. Applications without a response become eligible negatives only after the configured no-response window. Withdrawn and declined applications are excluded. Profile Settings can disable individual signals, recompute scores, or reset the learning window without deleting application history.
