<!-- markdownlint-disable MD033 MD041 -->

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
       → 12 new jobs discovered across 4 boards
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

**Reducing 15-20 hours/week of manual job search to < 1 hour of review.**

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Profile-driven** | All user config in `profile.yaml` — roles, location, skills, weights, LLM provider. No code changes per user. |
| **Pluggable AI** | Anthropic, OpenAI, Google, Ollama (free/local), Azure, AWS Bedrock — switch via `profile.yaml` |
| **Two-tier scoring** | Cheap triage model pre-filters; strong primary model scores on 4 dimensions with configurable weights |
| **Human-in-the-loop** | Mandatory approval checkpoint before any application leaves the system — never auto-submits |
| **Autonomous pipeline** | APScheduler cron → event bus → LangGraph StateGraph routes events to correct agents |
| **Interview coaching** | Company research, 12 categorised questions, STAR model answers mapped to your proof points |
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
│  │  Profile Loader (profile.yaml → Pydantic)       │ │
│  └─────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────┐ │
│  │       Next.js 14 Frontend (TypeScript)          │ │
│  │  Dashboard · Approvals · Kanban · Interview Prep │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

**v2 adds on top of v1:**

| Component | Status | Description |
|-----------|--------|-------------|
| `schemas/profile.py` | **New** | Pydantic schema for `profile.yaml` validation |
| `services/profile_service.py` | **New** | Read / write / validate profile.yaml |
| `agents/tools/profile_loader.py` | **New** | Runtime profile loader with mtime-based caching |
| `agents/tools/llm_factory.py` | **New** | LangChain `init_chat_model()` factory — provider-agnostic |
| `agents/scorer_agent.py` | **Updated** | Two-tier scoring; weights from profile.yaml; no Anthropic SDK import |
| `agents/tailor_agent.py` | **Updated** | Score threshold from profile.yaml |
| `agents/supervisor.py` | **Updated** | Shortlist threshold from profile.yaml |
| `routers/profile.py` | **New** | Profile CRUD + validation API |
| `app/onboarding/page.tsx` | **New** | 6-step first-run setup wizard |
| `app/settings/profile/page.tsx` | **New** | Profile settings UI |
| `examples/` | **New** | 3 example profiles (UK contractor, US SWE, EU PM) |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- An API key for your chosen LLM provider (or Ollama for local/free)

### 1. Clone

```bash
git clone https://github.com/arvindsoni2/jobpilot-v2.git
cd jobpilot-v2
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set at least one LLM provider key:
# ANTHROPIC_API_KEY=sk-ant-...   (default)
# OPENAI_API_KEY=sk-...
# GOOGLE_API_KEY=...
```

### 3. Start

```bash
make dev
```

On first launch, if `data/profile.yaml` is absent, the dashboard redirects to the **onboarding wizard** at `http://localhost:3000/onboarding`.

The wizard walks you through:
1. Identity (name, title, years experience)
2. Target roles + location
3. Compensation range
4. Skills + domains
5. LLM provider selection
6. Review + launch

### 4. Or configure manually

```bash
cp data/profile.yaml.example data/profile.yaml
# Edit data/profile.yaml with your details
```

See `examples/` for complete worked examples:
- `examples/profile_uk_contractor.yaml` — UK outside-IR35 Delivery Lead
- `examples/profile_us_swe.yaml` — US Senior Software Engineer (OpenAI)
- `examples/profile_eu_pm.yaml` — EU Freelance Product Manager (Google AI)

---

## Configuration

All user-specific configuration lives in `data/profile.yaml`. The system reads this at runtime — changing it takes effect on the next agent run without restart.

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

---

## Agents

### Scout
- **Trigger:** APScheduler cron (interval from `profile.yaml → preferences.scrape_interval_hours`)
- **Does:** Scrapes configured job boards, deduplicates, emits `job_discovered` events
- **LLM:** None — fully deterministic

### Scorer
- **Trigger:** `job_discovered` events
- **Does:** Two-tier scoring — triage model pre-filters, primary model scores on 4 dimensions
- **Weights:** Read from `profile.yaml → scoring.weights` at runtime
- **LLM:** Triage model + primary model (both from `profile.yaml`)

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
- Enforces human-in-the-loop approval checkpoint (`interrupt()`)
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
GET    /api/v2/profile              # Current profile (raw)
GET    /api/v2/profile/validated    # Profile validated against schema
PUT    /api/v2/profile              # Update profile (validates before writing)
POST   /api/v2/profile/validate     # Dry-run validation
GET    /api/v2/profile/status       # Profile completeness check

GET    /api/agents/status           # All agent statuses
POST   /api/agents/{name}/trigger   # Manual trigger

GET    /api/v2/approvals/pending    # Pending approval queue
POST   /api/v2/approvals/{id}/approve
POST   /api/v2/approvals/{id}/reject
```

---

## Development

```bash
make dev          # Start full stack
make test         # Run all tests
make test-agents  # Agent tests only
make migrate      # Run Alembic migrations
make scrape       # Manually trigger Scout
make score        # Manually trigger Scorer on pending jobs
make status       # Show all agent statuses
```

---

## Cost Estimate (Anthropic default)

| Activity | Volume/month | Cost |
|----------|-------------|------|
| Triage pre-filter | 3,600 jobs | £0.36 |
| Primary scoring | 540 jobs | £1.62 |
| CV + CL generation | 50 applications | £1.15 |
| Coach (research + Q&A) | 2 interviews | £0.09 |
| **Total** | | **~£3.22** |

Well within the default £15/month budget. Use Ollama for £0.

---

## FAQ

**Why LangGraph instead of CrewAI?**
LangGraph's explicit state machine maps cleanly to the application lifecycle; `interrupt()` gives clean human-in-the-loop; `SqliteSaver` matches the existing SQLite stack. CrewAI is great for fast prototyping but lacks built-in checkpointing.

**Can I use a local model?**
Yes — set `provider: ollama` in `profile.yaml` and point `base_url` at your Ollama instance. Quality varies; `qwen3:14b` or `llama3.1:8b` are reasonable choices for primary_model.

**Is my data safe?**
All data stays local. The only external calls are to your configured LLM provider's API (with your key). profile.yaml and master_cv.json are gitignored — never committed.

**Can I add a new job board?**
Yes — create a new scraper in `backend/app/scrapers/` following the `BaseScraper` pattern, register it in `SCRAPER_REGISTRY`, then add it to `job_boards` in your `profile.yaml`. No agent code changes needed.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
