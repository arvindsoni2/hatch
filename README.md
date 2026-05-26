<!-- markdownlint-disable MD033 MD041 MD060 -->

<div align="center">

# JobPilot v2

**Open-source, self-hosted, autonomous multi-agent job search automation.**

Discover → Score → Tailor → Track → Coach — fully automated, human-in-the-loop at the decisions that matter.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/next.js-14-black.svg)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-green.svg)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docs.docker.com/compose/)

[Quick Start](#quick-start) · [Architecture](#architecture) · [Configuration](#configuration) · [Agents](#agents) · [FAQ](#faq)

</div>

---

## What is JobPilot v2?

JobPilot v2 is an autonomous, multi-agent job search system that handles the full pipeline from discovery to interview readiness — while keeping you in control of the two decisions that actually matter: approving applications and reviewing interview prep.

```text
06:00  Scout agent runs (scheduled every 4h)
       → 12 new jobs discovered across boards for your locale
       → Scorer agent processes batch (triage model filters, primary model scores)
       → 3 jobs score ≥ 0.75 → auto-shortlisted
       → Tailor agent generates tailored CV + cover letter for each
       → 3 items land in your approval queue

08:30  You open the dashboard
       → Review: score breakdown, tailored CV preview, cover letter preview
       → Approve 2, reject 1 (wrong IR35 status)
       → Approved applications move to "Ready to Apply"

14:00  You mark "Interview scheduled" on Kanban
       → Coach agent auto-triggers: company research, 12 questions, model answers
       → "Prep ready" notification — 45 minutes of prep, ready to review
```

**Reducing 15–20 hours/week of manual job search to < 1 hour of review.**

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Profile-driven** | All user config in `profile.yaml` — roles, location, skills, weights, LLM provider. No code changes per user. |
| **Locale Pack System** | YAML-driven market packs for 🇬🇧 UK, 🇮🇳 India, 🇺🇸 US, 🇩🇪 Germany. Controls job boards, compensation defaults, and legal/compliance fields. |
| **Pluggable AI** | Anthropic, OpenAI, Google, Ollama (free/local), Azure, AWS Bedrock — switch via `profile.yaml` |
| **Two-tier scoring** | Cheap triage model pre-filters; strong primary model scores on 4 dimensions with configurable weights |
| **Locale-aware scoring** | IR35, work authorisation, notice period, and other locale-specific signals injected into the `location_match` scoring dimension |
| **Human-in-the-loop** | Mandatory approval checkpoint before any application leaves the system — never auto-submits |
| **Autonomous pipeline** | APScheduler cron → event bus → LangGraph StateGraph routes events to correct agents |
| **Interview coaching** | Company research, 12 categorised questions, STAR model answers mapped to your proof points |
| **Job archiving** | Configurable auto-archive for stale listings; archived jobs stay in DB for history |
| **Self-hosted** | Docker Compose on any laptop. SQLite + ChromaDB — no external services required |

---

## Architecture

```text
┌──────────────────────────────────────────────────────┐
│                   Docker Compose                     │
│  ┌─────────────────────────────────────────────────┐ │
│  │          FastAPI Backend (Python 3.12)           │ │
│  │                                                 │ │
│  │  Supervisor (LangGraph StateGraph)              │ │
│  │  poll_events → route → [scout|scorer|tailor|coach] │
│  │                                                 │ │
│  │  Event Bus (asyncio.Queue + SQLite persistence) │ │
│  │  APScheduler (Scout cron — configurable)        │ │
│  │  LLM Factory (LangChain init_chat_model())      │ │
│  │  Locale Service (YAML packs → scoring context)  │ │
│  │  Profile Loader (profile.yaml → Pydantic)       │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────┐ │
│  │       Next.js 14 Frontend (TypeScript)          │ │
│  │  Dashboard · Jobs · Approvals · Kanban · Coach  │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### What v2 adds over v1

| Component | Status | Description |
|-----------|--------|-------------|
| `locales/*.yaml` | **New** | Locale packs — UK, India, US, Germany, `_template` for contributors |
| `services/locale_service.py` | **New** | Loads/caches locale YAML; interpolates `legal_preferences` into scoring context |
| `scrapers/registry.py` | **New** | Maps locale board IDs → scraper classes; `get_scrapers_for_locale()` |
| `services/archive_service.py` | **New** | Auto-archives stale jobs; manual unarchive endpoint |
| `schemas/profile.py` | **New** | Pydantic schema with `locale`, `legal_preferences`, `archive_after_days` |
| `services/profile_service.py` | **New** | Read / write / validate `profile.yaml` |
| `agents/tools/profile_loader.py` | **New** | Mtime-cached loader; merges locale defaults into unset fields |
| `agents/tools/llm_factory.py` | **New** | LangChain `init_chat_model()` factory — provider-agnostic |
| `agents/scorer_agent.py` | **Updated** | Two-tier scoring; locale-aware `location_match`; weights from `profile.yaml` |
| `agents/tailor_agent.py` | **Updated** | Score threshold and proof points from `profile.yaml` |
| `agents/supervisor.py` | **Updated** | Shortlist threshold from `profile.yaml` |
| `routers/profile.py` | **New** | Profile CRUD + live LLM connection test endpoint |
| `routers/locales.py` | **New** | Locale list, legal fields, board config for onboarding wizard |
| `components/Navigation.tsx` | **New** | 5-item nav with live approval badge, active-route highlight |
| `components/JobCard.tsx` | **Rewritten** | Horizontal card; score badge with per-dimension tooltip |
| `components/ScoreBadge.tsx` | **New** | Colour-coded score badge with 4-dimension hover breakdown |
| `components/ErrorBanner.tsx` | **New** | API key invalid / scraper failure / no matching jobs banners |
| `app/page.tsx` (dashboard) | **Rewritten** | Agent status strip, action cards, pipeline bar, top matches |
| `app/jobs/page.tsx` | **Rewritten** | Score band legend, match threshold toggle, archive view |
| `app/onboarding/page.tsx` | **Rewritten** | 5-step wizard with locale picker, STAR proof points, API key tester, board toggles |
| `examples/` | **New** | 3 example profiles (UK contractor, US SWE, EU PM) |

---

## Quick Start

### One-command install (recommended)

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/jobpilot-v2/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr https://raw.githubusercontent.com/arvindsoni2/jobpilot-v2/main/install.ps1 | iex
```

The installer checks prerequisites (Docker/Podman, git), clones the repo, creates a template `.env`, builds and starts the containers, and optionally installs a systemd user service on Linux.

---

### Manual install

#### Prerequisites

- Docker & Docker Compose (or Podman + podman-compose)
- An API key for your chosen LLM provider (or Ollama for local/free)
- git

#### 1. Clone

```bash
git clone https://github.com/arvindsoni2/jobpilot-v2.git
cd jobpilot-v2
```

#### 2. Configure environment

```bash
# Create .env — add at least one LLM provider key:
echo "GOOGLE_API_KEY=AIza..." > .env   # Gemini (free tier available)
# or: ANTHROPIC_API_KEY / OPENAI_API_KEY / (no key for Ollama)
```

> You can also add/rotate API keys later via **Settings → AI Provider** in the dashboard — keys are validated live and saved to `data/api_keys.env` (survives container restarts).

#### 3. Start

```bash
make dev
```

Open `http://localhost:3000`. If `data/profile.yaml` is absent, the dashboard redirects automatically to the **onboarding wizard**.

### 4. Onboarding wizard (5 steps)

| Step | What you configure |
|------|--------------------|
| **Identity** | Name, title, years of experience, professional summary |
| **Your market** | Locale (🇬🇧 UK · 🇮🇳 India · 🇺🇸 US · 🇩🇪 Germany), target roles, location, remote preference |
| **Compensation & eligibility** | Rate range, rate type, currency + locale-specific fields (IR35, work authorisation, notice period, etc.) |
| **Skills & achievements** | Primary/secondary skills, domains, STAR proof points (used by Tailor for CV personalisation) |
| **AI setup & launch** | LLM provider, live API key test, job board toggles, scrape interval → **Start JobPilot** |

### 5. Or configure manually

```bash
cp data/profile.yaml.example data/profile.yaml
# Edit with your details
```

See `examples/` for complete worked profiles:
- `examples/profile_uk_contractor.yaml` — UK outside-IR35 Delivery Lead
- `examples/profile_us_swe.yaml` — US Senior Software Engineer (OpenAI)
- `examples/profile_eu_pm.yaml` — EU Freelance Product Manager (Google AI)

---

## Configuration

All user-specific configuration lives in `data/profile.yaml`. Agents read it at runtime — changes take effect on the next agent run without restart.

### Locale

```yaml
locale: "uk"   # uk | in | us | de (controls job boards + compliance fields)
```

The locale pack (`locales/<id>.yaml`) determines:
- Which job boards are available and enabled by default
- What legal/compliance fields appear in scoring (`IR35` for UK, `work_auth` for US, `notice_period` for India, etc.)
- Default compensation rate type (daily for UK, annual CTC for India, annual salary for US/DE)
- Locale-specific guidance injected into the `location_match` scoring dimension

### LLM Providers

| Provider | `provider` value | Example triage model | Example primary model | API key env |
|----------|-----------------|---------------------|----------------------|-------------|
| Anthropic | `anthropic` | `claude-haiku-4-5-20251001` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `gpt-4o-mini` | `gpt-4o` | `OPENAI_API_KEY` |
| Google | `google` | `gemini-2.0-flash` | `gemini-2.5-pro` | `GOOGLE_API_KEY` |
| Ollama (free) | `ollama` | `gemma3:4b` | `qwen3:14b` | — (set `base_url`) |
| Azure OpenAI | `azure` | deployment name | deployment name | `AZURE_OPENAI_API_KEY` |
| AWS Bedrock | `aws_bedrock` | model ID | model ID | AWS credentials |

```yaml
# profile.yaml — switch to Ollama for zero API cost
llm:
  provider: "ollama"
  triage_model: "gemma3:4b"
  primary_model: "qwen3:14b"
  base_url: "http://localhost:11434"
  track_costs: false
```

### Scoring

```yaml
scoring:
  shortlist_threshold: 0.75          # jobs above this → auto-shortlisted
  weights:
    skill_match: 0.35
    experience_match: 0.30
    rate_match: 0.20
    location_match: 0.15             # locale-aware — includes IR35/work auth signals
```

### Compensation & compliance

```yaml
compensation:
  min_rate: 600
  max_rate: 800
  rate_type: "daily"                 # daily | hourly | annual | monthly
  currency: "GBP"
  legal_preferences:                 # locale-specific — set by onboarding wizard
    ir35_preference: "outside"       # UK only
    right_to_work: "citizen"         # UK only
```

### Preferences

```yaml
preferences:
  scrape_interval_hours: 4
  max_tailor_batch: 5
  archive_after_days: 30             # auto-archive inactive jobs older than this
  follow_up_days: [5, 10, 15]
```

---

## Agents

### Scout
- **Trigger:** APScheduler cron (`preferences.scrape_interval_hours`)
- **Does:** Scrapes enabled job boards for the configured locale, deduplicates, emits `job_discovered` events
- **LLM:** None — fully deterministic

### Scorer
- **Trigger:** `job_discovered` events
- **Does:** Two-tier scoring — triage model pre-filters, primary model scores on 4 dimensions
- **Weights:** Read from `profile.yaml → scoring.weights` at runtime
- **Locale context:** IR35, work authorisation, notice period etc. injected into `location_match` prompt from locale pack
- **LLM:** Triage model (cheap, fast) + primary model (strong)

### Tailor
- **Trigger:** `job_shortlisted` events (score ≥ threshold)
- **Does:** Generates tailored CV + cover letter; ATS compatibility scoring
- **Proof points:** Mapped from `profile.yaml → proof_points` to JD requirements by tag matching
- **LLM:** Primary model (delegates to existing TailorService)

### Coach
- **Trigger:** `interview_scheduled` events (user action on Kanban)
- **Does:** Company research, 12 categorised questions, STAR model answers
- **User context:** Skills and proof points injected from `profile.yaml`
- **LLM:** Primary model (delegates to existing CoachService)

### Supervisor (LangGraph StateGraph)
- Routes events to the correct agent
- Enforces human-in-the-loop approval checkpoint (`interrupt()` from `langgraph.types`)
- Reads `shortlist_threshold` from `profile.yaml` at runtime
- Safety valve: `max_iterations` prevents infinite loops

---

## Human-in-the-Loop

JobPilot **never submits applications autonomously.** Two mandatory checkpoints:

1. **Application approval** (`/approvals`) — review tailored CV, cover letter, score breakdown. Approve / reject / edit.
2. **Interview prep review** (`/prep/[session_id]`) — review questions, model answers, STAR notes. Approve or regenerate.

`AUTO_APPROVE=true` exists only for automated testing. Never set it in production.

---

## API Reference

```
# Profile
GET    /api/v2/profile                    Raw profile dict
GET    /api/v2/profile/validated          Profile validated against Pydantic schema
PUT    /api/v2/profile                    Replace profile (validates before writing)
POST   /api/v2/profile/validate           Dry-run validation (does not save)
GET    /api/v2/profile/status             Profile completeness + onboarding_required flag
POST   /api/v2/profile/test-connection    Test LLM API key (key never persisted)

# Locales
GET    /api/v2/locales                    List installed locale packs
GET    /api/v2/locales/{id}              Full locale pack
GET    /api/v2/locales/{id}/boards       Job board configs (enabled_only=true by default)
GET    /api/v2/locales/{id}/legal-fields Compliance field definitions for onboarding

# Jobs
GET    /api/jobs/                         List jobs (filter, paginate, match score)
GET    /api/jobs/{id}                    Single job
POST   /api/jobs/scrape                  Trigger scraper(s) now
POST   /api/jobs/archive/run             Archive jobs older than profile threshold
POST   /api/jobs/{id}/unarchive          Restore an archived job

# Agents
GET    /api/agents/status                All agent statuses
POST   /api/agents/{name}/trigger        Manual trigger
GET    /api/agents/approvals/pending     Pending approval queue
POST   /api/agents/approvals/{id}/approve
POST   /api/agents/approvals/{id}/reject
GET    /api/agents/dashboard/pipeline    Pipeline funnel stats
```

Full interactive docs at `http://localhost:8000/docs` when running.

---

## Development

```bash
make dev          # Start full stack (FastAPI + Next.js)
make test         # Run all tests
make test-agents  # Agent tests only
make migrate      # Run Alembic migrations
make scrape       # Manually trigger Scout agent
make score        # Manually trigger Scorer on pending jobs
make status       # Show all agent statuses
```

### Adding a locale

1. Copy `locales/_template.yaml` to `locales/<id>.yaml` and fill in the fields
2. Add new scraper classes to `backend/app/scrapers/registry.py` if new boards are referenced
3. No backend restart needed — `locale_service.py` hot-reloads from disk

### Adding a job board

1. Create `backend/app/scrapers/<name>.py` following the `BaseScraper` pattern
2. Register it in `backend/app/scrapers/registry.py`
3. Add it to the relevant locale YAML under `job_boards`
4. Enable it in `profile.yaml → job_boards` (or via the UI Settings page)

---

## Cost Estimate (Anthropic default)

| Activity | Volume/month | Cost |
|----------|-------------|------|
| Triage pre-filter | 3,600 jobs | £0.36 |
| Primary scoring | 540 jobs | £1.62 |
| CV + CL generation | 50 applications | £1.15 |
| Coach (research + Q&A) | 2 interviews | £0.09 |
| **Total** | | **~£3.22** |

Well within the default £15/month budget configured in `profile.yaml`. Use Ollama for £0.

---

## FAQ

**Why LangGraph instead of CrewAI?**
LangGraph's explicit state machine maps cleanly to the application lifecycle; `interrupt()` gives clean human-in-the-loop; `SqliteSaver` matches the existing SQLite stack. CrewAI is great for fast prototyping but lacks built-in checkpointing.

**Can I use a local model?**
Yes — set `provider: ollama` in `profile.yaml` and point `base_url` at your Ollama instance. `qwen3:14b` or `llama3.1:8b` are reasonable choices for `primary_model`.

**Is my data safe?**
All data stays local. The only external calls are to your configured LLM provider's API. `profile.yaml` and `master_cv.json` are gitignored — never committed.

**How do I add support for a new country?**
Copy `locales/_template.yaml`, fill in the locale-specific fields (currency, rate types, legal fields, job boards), and place it in `locales/`. The system discovers it automatically on next start.

**Can I add a new job board?**
Yes — create a scraper in `backend/app/scrapers/` following the `BaseScraper` pattern, register it in `SCRAPER_REGISTRY`, then reference it in the relevant locale YAML. No agent code changes needed.

**What happens to old job listings?**
Jobs older than `preferences.archive_after_days` (default 30) are automatically set to `is_active=False` by the archive service. They remain in the database and can be viewed via the "Archived" toggle on the Jobs page or restored via `/api/jobs/{id}/unarchive`.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
