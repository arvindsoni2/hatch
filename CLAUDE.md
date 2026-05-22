# JobPilot v2 — Claude Code Configuration

## Project Context

Open-source, self-hosted, autonomous multi-agent job search automation platform. Built as a LangGraph supervisor pattern on top of an existing FastAPI + Next.js 14 codebase. Four agents (Scout, Scorer, Tailor, Coach) orchestrated by a Supervisor StateGraph with human-in-the-loop checkpoints. Fully configurable via `profile.yaml` — no user data is hardcoded anywhere in the codebase.

**Companion documents (read before building):**
- `01_PRD_JobPilot_v2.md` — problem statement, goals, requirements
- `02_Design_JobPilot_v2.md` — architecture, data model, agent specs, prompts

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic
- **Agents:** LangGraph (StateGraph, SqliteSaver, interrupt)
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui
- **Database:** SQLite (single file, WAL mode)
- **Vector store:** ChromaDB (local, file-backed at `./data/chroma`)
- **AI:** LangChain model abstraction via `init_chat_model()` — supports Anthropic, OpenAI, Google, Ollama, Azure, Bedrock. Default: Anthropic Claude. Provider configured in `profile.yaml`, loaded via `llm_factory.py`.
- **Scraping:** Playwright (JS-rendered), BeautifulSoup4 (static), httpx (APIs)
- **Scheduling:** APScheduler (in-process, cron triggers)
- **Containerisation:** Docker Compose (local only)

## Key Architecture Principles

1. **Profile-driven, not hardcoded.** All user-specific data (roles, locations, skills, proof points, scoring weights, job boards) lives in `profile.yaml`. Agents read this at runtime via `profile_loader.py`. Never put user-specific values in code.
2. **Wrap, don't rewrite.** All existing v1 services (scrapers, tailor, coach) are called as tools by agents. Do not modify files in `services/` unless fixing a bug.
3. **Supervisor is the single entry point.** No agent runs independently — the Supervisor routes all events.
4. **Human-in-the-loop is non-negotiable.** The `request_approval` node uses `interrupt()`. Never bypass this in production code. `AUTO_APPROVE` env var exists for testing only.
5. **Events are persisted before dispatch.** The event bus writes to SQLite first, then enqueues. This ensures no event is lost on crash.
6. **SQLite is source of truth.** ChromaDB is an advisory layer for scoring. If ChromaDB is lost, rebuild from SQLite.
7. **Open-source friendly.** No secrets, no user data, no hardcoded paths in committed code. Example profiles ship in `examples/`. First-run onboarding wizard creates `profile.yaml`.

## File Conventions

- **Python:** snake_case, type hints on all functions, Google-style docstrings on public methods
- **TypeScript:** camelCase, strict mode, no `any` type
- **Tests:** pytest (backend), vitest (frontend)
- **Git:** conventional commits — `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- **New agent code goes in** `backend/app/agents/`
- **New models go in** `backend/app/models/`
- **New routes go in** `backend/app/routes/`
- **New frontend pages go in** `frontend/app/`

## Important Patterns

### Agent pattern
```python
# Every agent inherits BaseAgent and follows this structure:
class ScoutAgent(BaseAgent):
    name = "scout"
    
    async def run(self, state: dict) -> dict:
        """Single run. Called by supervisor node."""
        # 1. Get inputs from state
        # 2. Call existing services (DO NOT REWRITE)
        # 3. Emit events via self.emit_event()
        # 4. Return updated state
```

### Event emission
```python
await self.event_bus.emit(
    event_type="job_discovered",
    source="scout",
    payload={"job_id": job.id, "title": job.title, ...}
)
```

### LangGraph interrupt

```python
from langgraph.types import interrupt
human_decision = interrupt({"type": "approval", "data": application_data})
# Graph pauses here. Resumes when /api/v2/approvals/{id}/approve is called.
```

## Commands

```bash
make dev          # Start full stack (FastAPI + Next.js + Docker)
make test         # Run all tests
make test-agents  # Run agent tests only
make migrate      # Run Alembic migrations
make scrape       # Manually trigger Scout agent
make score        # Manually trigger Scorer on pending jobs
make status       # Show all agent statuses
```

## Environment Variables

```bash
# Existing (provider-dependent — set the one matching profile.yaml llm.provider)
ANTHROPIC_API_KEY=           # If using Anthropic
OPENAI_API_KEY=              # If using OpenAI
GOOGLE_API_KEY=              # If using Google
# Ollama needs no key — just set llm.base_url in profile.yaml
DATABASE_URL=sqlite:///data/jobpilot.db

# New for v2
SCRAPE_INTERVAL_HOURS=4      # Scout cron schedule
SCORE_THRESHOLD=0.75          # Min score for auto-shortlisting
MAX_TAILOR_BATCH=5            # Max jobs to tailor per run
AUTO_APPROVE=false            # NEVER set to true in production
AGENT_LOG_LEVEL=INFO          # DEBUG for development
CHROMA_PERSIST_DIR=./data/chroma
LANGGRAPH_CHECKPOINT_DB=sqlite:///data/langgraph_checkpoints.db
```

## Do NOT

- Hardcode any user-specific data (names, skills, locations, rates) anywhere in the codebase — it all comes from `profile.yaml`
- Import LLM provider SDKs directly (`anthropic`, `openai`, `google.generativeai`) — always use `llm_factory.py` which wraps LangChain's `init_chat_model()`
- Use provider-specific prompt features (Anthropic XML tags, OpenAI function-calling format) — prompts must be provider-agnostic; use LangChain's `with_structured_output()` for structured responses
- Modify existing services in `backend/app/services/` — agents wrap them, not replace them
- Set `AUTO_APPROVE=true` in any committed config
- Send any data to external APIs without human approval checkpoint
- Use `CrewAI` — this project uses LangGraph exclusively
- Add authentication — this is a single-user, self-hosted system
- Use `WidthType.PERCENTAGE` in any docx generation (breaks in Google Docs)
- Store secrets in any file under version control
- Use synchronous DB calls — all SQLAlchemy operations use `async_session`
- Commit `data/profile.yaml` or `data/master_cv.json` — these are user data, gitignored

## Do

- Use `llm_factory.py` for all LLM calls — `get_triage_model()` for pre-filtering, `get_primary_model()` for detailed work. Never instantiate provider clients directly.
- Use LangChain `with_structured_output(PydanticModel)` for all structured LLM responses — this handles provider differences transparently
- Read all user-specific parameters from `profile.yaml` via `profile_loader.py` — roles, locations, skills, weights, thresholds, proof points, board config, LLM provider
- Validate `profile.yaml` against the Pydantic schema (`schemas/profile.py`) on load
- Use `interrupt()` from `langgraph.types` for human-in-the-loop (not `interrupt_before` at compile time — we use the dynamic `interrupt()` function)
- Persist events to DB before enqueueing them
- Include the user's configured proof points (from `profile.yaml`) in every tailored CV
- Use Haiku for pre-filtering, Sonnet for detailed scoring
- Keep the Supervisor `max_iterations` safety valve
- Add structured JSON logging for every agent action
- Write tests for routing logic and approval flow
- Ship example profiles in `examples/` for new users to reference
- Ensure onboarding wizard creates a valid `profile.yaml` before agents can run
