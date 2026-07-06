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

- **Today:** the recommended next action, ready work, and supporting agent progress.
- **Pipeline:** scored roles moving through the agent pipeline.
- **Applications:** the application Kanban board.
- **Interview Prep:** manual and application-linked Coach sessions.

## Applications

Applications follows the real application journey from left to right:

`Discovered -> Preparing -> Ready to apply -> Applied -> Interview -> Offered -> Accepted`

- Drag a card only to its next valid stage.
- Use the card's **Move to...** menu as a keyboard-accessible alternative.
- Backward dragging is blocked.
- Rejected, withdrawn, and declined roles use explicit close actions.
- Preparing is system-managed while Hatch creates or reviews documents.
- Moving a role to Applied records the date, creates a follow-up, and queues Coach prep.
- Use **Add application** to track a role submitted outside Hatch, such as a company-site application. Paste the role, company, URL, applied date, notes, and job description, then optionally queue Coach prep in the same flow.

## Interview Prep

Coach prep can be created from an applied Applications card or directly from **Interview Prep → New session** for external interviews.

- Ready sessions show likely questions, model answers, calendar export, and practice launch.
- New manual applications can queue Coach immediately after they are added to Tracker.
- Long-running generation is surfaced as needing attention instead of looking active forever.
- Failed or stale sessions can be retried from Prep, reusing the saved role, company, configuration, and job description where available.

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
- create the per-user state directory at `${HATCH_HOME:-~/.hatch}`;
- start without downloading a local model;
- create `data/profile.yaml` and `.env` when missing;
- build and start the beginner-safe Docker Compose stack.

The default mode is “configure AI later.” To choose a mode explicitly:

```bash
./install.sh --mode ai-later
./install.sh --mode cloud
./install.sh --mode local
./install.sh --mode advanced
```

After installation, use the host-side command wrapper:

```bash
hatch status
hatch doctor
hatch probe
hatch models list
hatch models install
hatch apply-ai-config
```

Open:

- Dashboard: <http://localhost:3000>
- API documentation after unlocking Hatch: <http://localhost:8000/docs>

On first run, Hatch asks you to create a local app-lock password. This protects
the workspace; it is not a SaaS account and has no email recovery.

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

Local AI is opt-in for beginner installs. Run `hatch probe`, review
`hatch models list`, and then run `hatch models install`. Every download
requires confirmation and SHA-256 verification. Managed model files live under
`${HATCH_HOME}/models`.

The existing developer stack continues to run two local llama.cpp services:

| Service | Model | Port | Purpose |
|---|---|---:|---|
| `llm-primary` | `Qwen3.5-4B Q4_K_M` | 8080 | CV, cover letter, detailed scoring, Coach |
| `llm-triage` | `Qwen3.5-0.8B Q8_0` | 8081 | Fast initial filtering |

The model ports bind to localhost only. Model files live in `data/models/` and are not committed.

Cloud providers are optional. Easy installs store keys in
`${HATCH_HOME}/config/secrets.env`, and only the host CLI may change that file:

```bash
hatch secrets set openai
hatch secrets status
hatch secrets unset openai
```

The browser never accepts or returns provider keys. Existing developer installs
may continue to use `.env` or `data/api_keys.env`.

### AI not configured

Hatch starts without an AI provider. Profile editing, the application tracker,
manual job entry, and settings remain available. Tailoring, cover-letter
generation, and Coach actions show an actionable setup message until you
configure cloud or local AI.

### Easy-install maintenance

`hatch update --dry-run` reports a managed update without changing files.
Updates refuse dirty or unmanaged checkouts and back up configuration and data
before migrations. `hatch uninstall` removes easy-install services and the
command shim but preserves `${HATCH_HOME}`. Data removal requires an explicit
`--purge-*` flag and confirmation.

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

### Safety and privacy

App lock is enabled by default. With `HATCH_APP_PASSWORD` unset, the first-run
screen stores a bcrypt password hash in SQLite. Setting `HATCH_APP_PASSWORD`
makes the environment the authoritative password source. Administrators may set
`HATCH_APP_LOCK_ENABLED=false` for an explicit test/demo installation; there is
no in-app disable switch.

Sessions use an HttpOnly browser-session cookie and expire server-side after 12
hours by default. API docs and product APIs are protected. To recover from a
forgotten database-backed password:

```bash
bash scripts/reset-app-lock.sh
# For automation after you have reviewed the action:
bash scripts/reset-app-lock.sh --yes
```

This removes only app-lock configuration and sessions. Profile, jobs,
applications, generated documents, and other user data are preserved.

### Resume templates and tailoring review

Resume Studio supports 10 ATS-safe DOCX templates with page-target, density,
section-order, accent-colour, and safe-font controls. Hatch recommends
templates using deterministic role and profile signals. Set global defaults in
Profile Settings and override them for an individual generation.

The HTML preview is approximate. DOCX remains the source of truth, and PDF
export remains intentionally unavailable. CV and cover-letter documents share
the selected design treatment.

Each generated CV/cover-letter pack now stores a review containing match
summary, ATS coverage, grounded evidence, unsupported requirements, and
warnings. The CV Quality Gate also parses generated DOCX output to check
readability, core sections, keyword coverage, and unsupported claims.
High-risk first-party UI exports require acknowledgement. Regeneration creates
new document versions and keeps earlier files in history.

### Smart Job Import

Open **Applications → Import from URL** to extract a public job page, review
the normalized fields, and save it as a bookmark, application, or Tailor input.
Direct JSON-LD and conservative HTML extraction run first. Firecrawl is an
optional fallback, is disabled by default, and receives only the public job URL
or page content. Hatch never sends profile, master CV, or proof-point data to
Firecrawl.

### Profile summary

Settings and Tailor show a read-only summary of the evidence Hatch will use.
Identity and contact details prefer explicit `profile.yaml` values; education
and certifications prefer the master CV. Differences are warnings rather than
generation blockers.

### Release 3 upgrade

Existing data is preserved. This release adds app-lock and tailoring-review
tables plus the `tailoring.default_template_id` setting. It does not introduce
multi-user accounts. The container entrypoint applies the database migrations
automatically on restart.

### Release 4 interface

Release 4 gives Hatch one consistent responsive shell and plain-language
navigation: Today, Pipeline, Applications, and Interview Prep. Desktop uses the
sidebar; mobile uses the bottom navigation. Settings share the same colour,
spacing, focus, touch-target, and responsive form principles.

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

On Linux, `install.sh` can optionally install
`infrastructure/systemd/hatch.service` as a user service for startup on login.

Optional Docker Compose overrides are documented in
`infrastructure/docker/docker-compose.override.yml.example`. Copy that file to
`docker-compose.override.yml` before customising it so Compose discovers it
automatically.

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
make reset-user      # return Hatch to first-run state after confirmation
make test-reset-user # verify reset behavior in a temporary directory
make reset-app-lock   # clear only the app-lock password and sessions
make audit-scripts    # safely validate operational scripts and reset tests
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
ls -lh data/models/Qwen_Qwen3.5-4B-Q4_K_M.gguf data/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf
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
make reset-user
```

This is destructive and returns Hatch to first-run state. It removes the
application database and checkpoints, generated documents, Coach recordings,
temporary uploads, profile, master CV/resume artifacts, and saved API keys.
Downloaded models and `data/profile.yaml.example` are retained; a blank
`profile.yaml` is recreated from that template. Open
<http://localhost:3000/onboarding> afterwards and clear localhost site data if
the browser offers to resume an old onboarding session.

To clear jobs and workflow history while deliberately retaining the existing
profile, CV, and saved API keys:

```bash
bash scripts/reset-user-data.sh --keep-profile
```

## Safety and Privacy

- Application submission always remains a human action.
- Tailoring may rephrase verified experience and align terminology, but must not fabricate claims.
- Local AI keeps prompts on the machine. Cloud providers receive prompts when explicitly configured.
- Raw webcam video used by optional interview practice is processed in the browser and is not uploaded.
- Optional Coach presence analysis sends only numeric camera-attention and head-stability summaries. It can be disabled and its saved consent revoked in Profile Settings.

## Outcome Learning

Hatch can calculate a separate **opportunity score** from your own resolved application history. The existing fit score remains unchanged. Opportunity adjustments are deterministic, capped, calculated locally without an LLM or embeddings, and exclude protected personal characteristics, company identity, recruiter details, notes, and document contents.

Learning activates after the configured minimum number of resolved applications. Applications without a response become eligible negatives only after the configured no-response window. Withdrawn and declined applications are excluded. Profile Settings can disable individual signals, recompute scores, or reset the learning window without deleting application history.
