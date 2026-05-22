# JobPilot v2 — Design Document (System Architecture + UX)

**Author:** Arvind Soni  
**Date:** 21 May 2026  
**Status:** Draft v1.0 — for review  
**Companion to:** `01_PRD_JobPilot_v2.md`  
**Build instructions:** `CLAUDE.md` (project root)

This document covers (1) the user experience, (2) the system architecture, (3) the resolution of open technology decisions from the PRD, (4) the data model, (5) the agent specification, and (6) the test and rollout strategy.

---

## Part 1 — User Experience

### 1.1 The four touchpoints

The user interacts with JobPilot v2 at exactly four surfaces. Every other moving part is invisible.

| Surface | What happens here | Frequency |
|---------|-------------------|-----------|
| **Approval queue** | Review tailored CV + cover letter + score breakdown. Approve, reject, or edit. | 1-3x per day |
| **Prep review** | Review interview questions, model answers, STAR notes. Approve or request regeneration. | Per interview scheduled |
| **Dashboard** | Monitor pipeline health: agent statuses, event timeline, funnel metrics, score distribution. | Glance 1-2x per day |
| **Kanban board** | Existing tracker — drag applications between states, mark interviews, add notes. | As needed |

Everything else — scraping, scoring, tailoring, company research, question generation — is autonomous. The user never triggers these manually in normal operation (though manual trigger is available for debugging).

### 1.2 UX flow: the autonomous day

```
06:00  Scout agent runs (cron)
       → 12 new jobs discovered across 4 boards
       → Scorer agent processes batch
       → 3 score ≥ 0.75 → auto-shortlisted
       → Tailor agent generates CV + CL for each
       → 3 items land in approval queue

08:30  User opens dashboard over morning coffee
       → Sees "3 pending approvals" badge
       → Reviews each: score breakdown, tailored CV preview, cover letter preview
       → Approves 2, rejects 1 (wrong IR35 status)
       → Approved applications move to "Ready to Apply"

10:00  Scout agent runs again
       → 5 new jobs, 1 scores ≥ 0.75
       → Desktop notification: "1 new approval pending"
       → User approves during lunch break

14:00  User marks "Interview scheduled" on Kanban for Accenture role
       → Coach agent auto-triggers:
         - Researches Accenture (cached from 2 weeks ago → refreshes)
         - Generates 12 questions (4 behavioural, 3 technical, 2 situational, 3 company)
         - Creates model answers mapped to user's proof points
         - Builds STAR prep sheet
       → "Prep ready" notification

18:00  User reviews prep materials
       → Approves 10 questions, edits 2 model answers
       → Optionally runs voice practice session with 3 questions
       → Receives feedback: "Filler words: 4, Answer length: good, STAR structure: 3/5"

22:00  Scout runs again (unmanned)
       → Results queue for tomorrow morning
```

### 1.3 Page layouts

#### 1.3.1 Dashboard (`/dashboard`)

```
┌──────────────────────────────────────────────────────────────┐
│  JobPilot v2                                    [Agent Status]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Scout   │ │ Scorer  │ │ Tailor  │ │ Coach   │          │
│  │ ● Idle  │ │ ● Idle  │ │ ● Idle  │ │ ● Idle  │          │
│  │ Last:   │ │ Last:   │ │ Last:   │ │ Last:   │          │
│  │ 2h ago  │ │ 2h ago  │ │ 1h ago  │ │ 3d ago  │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│                                                              │
│  ┌─ Pipeline Funnel ──────────────────────────────────────┐  │
│  │  Discovered (142) → Scored (142) → Shortlisted (23)   │  │
│  │  → Tailored (18) → Approved (12) → Applied (10)       │  │
│  │  → Interview (3) → Offered (0)                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ Approval Queue (3 pending) ───────────────────────────┐  │
│  │  [card] Senior Delivery Lead — Accenture — 0.87 — £650 │  │
│  │  [card] Product Owner — DWP Digital — 0.82 — £600      │  │
│  │  [card] Solutions Architect — NTT DATA — 0.79 — £700   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ Event Timeline ──────────────────────────────────────┐  │
│  │  10:02 Scout: 5 jobs discovered from Reed             │  │
│  │  10:03 Scorer: batch scored 5 jobs (2 shortlisted)    │  │
│  │  10:05 Tailor: CV generated for "Senior DL — Accent." │  │
│  │  10:06 Tailor: CV generated for "PO — DWP Digital"    │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

#### 1.3.2 Approval detail (`/approvals/[id]`)

```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to Queue                                             │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Senior Delivery Lead — Accenture ATC Newcastle              │
│  £650/day · Outside IR35 · Hybrid (Newcastle)                │
│  Source: ContractorUK · Discovered: 2h ago                   │
│                                                              │
│  ┌─ Score Breakdown ────┐  ┌─ Agent Reasoning ────────────┐ │
│  │ Skill:      0.92 ███ │  │ Strong match on Agile        │ │
│  │ Experience: 0.88 ██▓ │  │ delivery and stakeholder     │ │
│  │ Rate:       0.85 ██▓ │  │ management. Public sector    │ │
│  │ Location:   1.00 ███ │  │ SC eligibility is a plus.    │ │
│  │ ─────────────────── │  │ Rate within target range.    │ │
│  │ Overall:    0.91 ███ │  │ Newcastle location: perfect. │ │
│  └──────────────────────┘  └──────────────────────────────┘ │
│                                                              │
│  ┌─ Tailored CV Preview ──────────────────────────────────┐  │
│  │  [Rendered .docx preview — scrollable]                 │  │
│  │  ATS Score: 87%                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ Cover Letter Preview ─────────────────────────────────┐  │
│  │  [Rendered cover letter — scrollable]                  │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ Original JD ──────────────────────────────────────────┐  │
│  │  [Collapsible — full job description text]             │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  [✓ Approve]  [✗ Reject]  [✎ Edit & Approve]               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### 1.3.3 Interview prep review (`/prep/[session_id]`)

```
┌──────────────────────────────────────────────────────────────┐
│  Interview Prep: Senior Delivery Lead — Accenture            │
│  Round 1: Behavioural · 45 min · 28 May 2026                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─ Company Intelligence ─────────────────────────────────┐  │
│  │  Accenture ATC Newcastle — Technology consulting       │  │
│  │  Recent: Won DWP contract, expanding Newcastle hub     │  │
│  │  Culture: Innovation-led, diverse, community-focused   │  │
│  │  Tech: Cloud-first (AWS/Azure), Agile at scale         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌─ Questions (12) ───────────────────────────────────────┐  │
│  │                                                        │  │
│  │  Q1: Tell me about a time you managed a complex        │  │
│  │      stakeholder landscape.                            │  │
│  │                                                        │  │
│  │  ┌─ Model Answer ──────────────────────────────────┐   │  │
│  │  │  S: At Northern Powergrid, the Smart Timesheet  │   │  │
│  │  │     programme involved TCS, NPg IT, field ops...│   │  │
│  │  │  T: I needed to align five stakeholder groups...│   │  │
│  │  │  A: I established a RACI matrix, set up...     │   │  │
│  │  │  R: Delivered £500K annual savings, adopted by  │   │  │
│  │  │     3,000+ field engineers.                     │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │                                                        │  │
│  │  [✎ Edit answer]  [🎤 Practice this question]         │  │
│  │                                                        │  │
│  │  Q2: How do you handle scope creep on a live...       │  │
│  │  ... (10 more questions)                               │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  [✓ Approve Prep]  [↻ Regenerate]  [🎤 Start Mock Session] │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## Part 2 — System Architecture

### 2.1 High-level architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Docker Compose                               │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    FastAPI Backend (Python 3.12)                │  │
│  │                                                                │  │
│  │  ┌────────────────────────────────────────────────────────┐    │  │
│  │  │              Supervisor Agent (LangGraph StateGraph)    │    │  │
│  │  │                                                        │    │  │
│  │  │  poll_events → route_event → [agent_node] → poll      │    │  │
│  │  │                    │                                   │    │  │
│  │  │          ┌─────────┼─────────┬───────────┐             │    │  │
│  │  │          ▼         ▼         ▼           ▼             │    │  │
│  │  │    ┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐  │    │  │
│  │  │    │  Scout   │ │ Scorer │ │  Tailor  │ │  Coach   │  │    │  │
│  │  │    │  Agent   │ │  Agent │ │  Agent   │ │  Agent   │  │    │  │
│  │  │    └────┬─────┘ └───┬────┘ └────┬─────┘ └────┬─────┘  │    │  │
│  │  │         │           │           │             │        │    │  │
│  │  │    Existing    Claude API   Existing      Existing     │    │  │
│  │  │    Scrapers    (scoring)    Tailor Svc    Coach Svc    │    │  │
│  │  └────────────────────┬───────────────────────────────────┘    │  │
│  │                       │                                        │  │
│  │  ┌────────────────────▼───────────────────────────────────┐    │  │
│  │  │              Shared State Layer                         │    │  │
│  │  │  SQLite (jobs, applications, events, scores, state)     │    │  │
│  │  │  + ChromaDB (embeddings for semantic dedup + matching)  │    │  │
│  │  │  + LangGraph Checkpointer (SqliteSaver)                 │    │  │
│  │  └────────────────────────────────────────────────────────┘    │  │
│  │                                                                │  │
│  │  ┌────────────────────────────────────────────────────────┐    │  │
│  │  │  APScheduler        Event Bus (asyncio.Queue)           │    │  │
│  │  │  Scout: */4h         emit → persist → poll → process    │    │  │
│  │  └────────────────────────────────────────────────────────┘    │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │               Next.js 14 Frontend (TypeScript)                 │  │
│  │                                                                │  │
│  │  Dashboard · Approval Queue · Kanban · Interview Prep · Voice  │  │
│  │  SSE for real-time agent status updates                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │               Nginx (reverse proxy, static files)              │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  External APIs   │
                    │  Claude Sonnet   │
                    │  Job board sites │
                    └──────────────────┘
```

### 2.2 Technology decisions (resolving PRD §9)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Orchestration framework** | **LangGraph** | Explicit state machine maps to application lifecycle states; `interrupt()` primitive provides clean human-in-the-loop; `SqliteSaver` checkpointer matches our existing SQLite stack; 30K+ GitHub stars, production use at Uber/Klarna/LinkedIn; better fit than CrewAI for single-user stateful workflows (CrewAI excels at fast prototyping but lacks built-in checkpointing and fine-grained state control). |
| **LLM provider** | **Pluggable via LangChain `init_chat_model()`** | Default: Anthropic Claude. Users can switch to OpenAI, Google, Ollama (local), Azure, or Bedrock via `profile.yaml`. Two-tier model config: fast/cheap triage model + strong primary model. LangChain's model abstraction handles provider differences transparently. |
| **Scoring LLM tier** | **Two-tier: triage model → primary model** | Triage model (e.g. Haiku, GPT-4o-mini, Gemini Flash) for keyword pre-filter. Primary model (e.g. Sonnet, GPT-4o, Gemini Pro) for detailed scoring. Estimated 80% cost reduction vs primary-only. |
| **Vector store** | **ChromaDB (local, file-backed)** | Needed for (1) semantic dedup across job sources, (2) embedding-based profile-to-JD matching as scoring signal. Lightweight, Python-native, no separate server process. FAISS is faster but ChromaDB has better metadata filtering. |
| **Event bus** | **In-process asyncio.Queue + SQLite persistence** | Single-user, single-process — no need for Redis/Kafka overhead. Events persisted to `agent_events` table on emit for durability; asyncio.Queue for in-memory dispatch speed. |
| **Frontend real-time** | **Server-Sent Events (SSE)** | Simpler than WebSocket for unidirectional updates (agent status, new approvals). FastAPI supports SSE natively via `StreamingResponse`. No connection management complexity. |
| **Document generation** | **Existing docx-js pipeline (keep)** | Already working in v1; generates .docx with proper formatting. No reason to change. |
| **Voice practice** | **Web Speech API (browser-native)** | Already designed in v1 Coach module. No external dependency. Chrome/Edge only — acceptable for single-user. |

### 2.3 LLM provider abstraction

The LLM layer uses LangChain's `init_chat_model()` factory, which provides a unified interface across all major providers. This means agent prompts are provider-agnostic — no `anthropic.Client()` or `openai.ChatCompletion()` calls anywhere in agent code.

```python
# backend/app/agents/tools/llm_factory.py

from langchain.chat_models import init_chat_model
from app.agents.tools.profile_loader import load_profile

def get_triage_model():
    """Return the user's configured triage (fast/cheap) model."""
    profile = load_profile()
    llm_config = profile["llm"]
    return init_chat_model(
        model=llm_config["triage_model"],
        model_provider=llm_config["provider"],
        temperature=llm_config.get("temperature", 0.3),
        max_retries=llm_config.get("max_retries", 3),
        base_url=llm_config.get("base_url"),       # For Ollama / Azure
    )

def get_primary_model():
    """Return the user's configured primary (strong) model."""
    profile = load_profile()
    llm_config = profile["llm"]
    return init_chat_model(
        model=llm_config["primary_model"],
        model_provider=llm_config["provider"],
        temperature=llm_config.get("temperature", 0.3),
        max_retries=llm_config.get("max_retries", 3),
        base_url=llm_config.get("base_url"),
    )
```

**How agents use it — no provider-specific code:**

```python
# In scorer_agent.py
from app.agents.tools.llm_factory import get_triage_model, get_primary_model

class ScorerAgent(BaseAgent):
    async def run(self, state):
        triage_llm = get_triage_model()     # Could be Haiku, GPT-4o-mini, Gemma, etc.
        primary_llm = get_primary_model()   # Could be Sonnet, GPT-4o, Qwen, etc.
        
        # Pre-filter with triage model
        result = await triage_llm.ainvoke(pre_filter_prompt)
        if not result.relevant:
            return state
        
        # Detailed scoring with primary model
        score = await primary_llm.ainvoke(scoring_prompt)
        ...
```

**Ollama (local/free) example** — users who want zero API cost can run everything locally:

```yaml
# profile.yaml — Ollama configuration
llm:
  provider: "ollama"
  triage_model: "gemma3:4b"          # Fast, runs on CPU
  primary_model: "qwen3:14b"         # Stronger, needs 16GB+ RAM
  base_url: "http://localhost:11434"
  temperature: 0.3
  track_costs: false                  # No cost tracking for local models
```

**Key design rules for LLM abstraction:**

1. **Never import provider SDKs directly** (`anthropic`, `openai`, `google.generativeai`). Always go through `llm_factory.py`.
2. **Prompts must be provider-agnostic.** Use plain text instructions with JSON output requests. No Anthropic-specific XML tags, no OpenAI function-calling format. LangChain's `with_structured_output()` handles the translation.
3. **Test with at least two providers.** Integration tests should run against both Anthropic and OpenAI (or a mock) to catch provider-specific assumptions.
4. **Structured output via `with_structured_output()`.** Define Pydantic models for expected responses and let LangChain handle the provider-specific structured output mechanism (tool use for Anthropic, function calling for OpenAI, etc.).

```python
# Structured output — works with any provider
from pydantic import BaseModel

class JobScore(BaseModel):
    skill_match: float
    experience_match: float
    rate_match: float
    location_match: float
    overall_score: float
    reasoning: str

primary_llm = get_primary_model()
structured_llm = primary_llm.with_structured_output(JobScore)
score = await structured_llm.ainvoke(scoring_prompt)
# score.skill_match, score.overall_score, etc. — typed, validated
```

### 2.4 What's new vs. what's wrapped

This is the critical design principle: **v2 wraps v1, it does not rewrite it.**

| Component | v1 (exists, keep as-is) | v2 (new, wraps v1) |
|-----------|------------------------|-------------------|
| Playwright/BS4 scrapers | ✅ `backend/app/scrapers/` | Scout agent calls these via `ScraperFactory` |
| Dedup engine (rapidfuzz) | ✅ `backend/app/services/dedup.py` | Scout agent calls `check_duplicate()` |
| JD analyser (Claude API) | ✅ `backend/app/services/jd_analyser.py` | Tailor agent calls this as a tool |
| CV generator (docx-js) | ✅ `backend/app/services/cv_generator.py` | Tailor agent calls this as a tool |
| Cover letter generator | ✅ `backend/app/services/cl_generator.py` | Tailor agent calls this as a tool |
| ATS scorer | ✅ `backend/app/services/ats_scorer.py` | Tailor agent uses as quality gate |
| Company researcher | ✅ `backend/app/services/company_researcher.py` | Coach agent calls this as a tool |
| Question generator | ✅ `backend/app/services/question_generator.py` | Coach agent calls this as a tool |
| Model answer generator | ✅ `backend/app/services/model_answer_gen.py` | Coach agent calls this as a tool |
| SQLAlchemy models | ✅ `backend/app/models/` | Extended with 3 new tables |
| FastAPI routes | ✅ `backend/app/routes/` | Extended with agent/event/approval routes |
| Next.js dashboard | ✅ `frontend/app/` | Extended with agent dashboard + approval pages |
| — | — | **New:** Supervisor StateGraph |
| — | — | **New:** Event bus |
| — | — | **New:** Scorer agent + prompts |
| — | — | **New:** Master profile config |
| — | — | **New:** Agent lifecycle manager |

---

## Part 3 — Agent Architecture (Deep Dive)

### 3.1 Supervisor StateGraph

The Supervisor is the heartbeat of the system. It is implemented as a LangGraph `StateGraph` with typed state, conditional routing, and two interrupt points.

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from typing import TypedDict, Annotated
from operator import add

class SupervisorState(TypedDict):
    # Event processing
    pending_events: list[dict]
    current_event: dict | None
    
    # Agent results (accumulated across the loop)
    agent_results: Annotated[list[dict], add]
    
    # Human-in-the-loop
    approval_request: dict | None     # Populated before interrupt
    approval_response: dict | None    # Populated after human resumes
    
    # Error tracking
    errors: Annotated[list[dict], add]
    
    # Loop control
    iteration_count: int
    max_iterations: int               # Safety: prevent infinite loops

# Graph definition
graph = StateGraph(SupervisorState)

# Nodes
graph.add_node("poll_events", poll_events_node)
graph.add_node("score_job", scorer_node)
graph.add_node("tailor_job", tailor_node)
graph.add_node("park_job", park_job_node)
graph.add_node("request_approval", approval_node)      # ← interrupt()
graph.add_node("process_approval", process_approval_node)
graph.add_node("prepare_interview", coach_node)
graph.add_node("handle_error", error_handler_node)

# Entry
graph.set_entry_point("poll_events")

# Conditional routing from poll_events
graph.add_conditional_edges("poll_events", route_event, {
    "score_job": "score_job",
    "tailor_job": "tailor_job",
    "park_job": "park_job",
    "request_approval": "request_approval",
    "prepare_interview": "prepare_interview",
    "handle_error": "handle_error",
    "done": END,
})

# Return edges — all lead back to poll_events for next event
graph.add_edge("score_job", "poll_events")
graph.add_edge("tailor_job", "poll_events")
graph.add_edge("park_job", "poll_events")
graph.add_edge("process_approval", "poll_events")
graph.add_edge("prepare_interview", "poll_events")
graph.add_edge("handle_error", "poll_events")

# Human-in-the-loop: interrupt pauses, then routes to process_approval
graph.add_edge("request_approval", "process_approval")

# Compile
checkpointer = SqliteSaver.from_conn_string("sqlite:///data/langgraph_checkpoints.db")
supervisor = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["process_approval"],  # Pause before processing approval
)
```

#### Routing logic

```python
def route_event(state: SupervisorState) -> str:
    """Decide which node to route to based on the current event."""
    if state["iteration_count"] >= state["max_iterations"]:
        return "done"  # Safety valve
    
    event = state["current_event"]
    if event is None:
        return "done"  # No more events
    
    event_type = event["event_type"]
    
    match event_type:
        case "job_discovered":
            return "score_job"
        case "job_scored":
            if event["payload"]["overall_score"] >= SCORE_THRESHOLD:
                return "tailor_job"
            return "park_job"
        case "cv_tailored":
            return "request_approval"
        case "application_approved":
            return "process_approval"
        case "interview_scheduled":
            return "prepare_interview"
        case "scout_error" | "tailor_error" | "coach_error":
            return "handle_error"
        case _:
            return "handle_error"  # Unknown events get logged
```

#### Human-in-the-loop pattern

```python
from langgraph.types import interrupt, Command

def approval_node(state: SupervisorState) -> dict:
    """Present application for human review. Pauses execution."""
    application = state["approval_request"]
    
    # This pauses the graph and returns the application data
    # to the caller (FastAPI endpoint → frontend)
    human_decision = interrupt({
        "type": "application_approval",
        "application_id": application["id"],
        "job_title": application["job_title"],
        "company": application["company"],
        "score": application["score"],
        "cv_path": application["cv_path"],
        "cl_path": application["cl_path"],
        "ats_score": application["ats_score"],
    })
    
    # Execution resumes here when human calls the resume endpoint
    return {"approval_response": human_decision}

# FastAPI endpoint to resume
@router.post("/approvals/{application_id}/approve")
async def approve_application(application_id: str):
    """Resume the paused graph with approval."""
    config = {"configurable": {"thread_id": f"approval-{application_id}"}}
    await supervisor.ainvoke(
        Command(resume={"decision": "approved", "application_id": application_id}),
        config=config,
    )
    return {"status": "approved"}
```

### 3.2 Agent specifications

#### 3.2.1 Scout Agent

| Aspect | Detail |
|--------|--------|
| **Trigger** | APScheduler cron: `*/4 hours` (configurable via `SCRAPE_INTERVAL_HOURS`) |
| **Input** | List of configured job board sources |
| **Output** | `job_discovered` events emitted to event bus |
| **LLM usage** | None — Scout is deterministic |
| **Tools** | `scrape_board(source)`, `check_duplicate(job)`, `emit_event()` |
| **Error handling** | Log per-board errors, continue to next board, emit `scout_error` after 3 consecutive failures for same board |
| **State** | `last_scrape_at` per source, `jobs_found_this_run`, `errors_this_run` |

#### 3.2.2 Scorer Agent

| Aspect | Detail |
|--------|--------|
| **Trigger** | Supervisor routes `job_discovered` events |
| **Input** | Job posting + master profile |
| **Output** | `job_scored` event with 4-dimension breakdown |
| **LLM usage** | Two-tier: triage model (pre-filter) → primary model (detailed scoring). Models configured in `profile.yaml`, loaded via `llm_factory.py`. |
| **Tools** | `load_master_profile()`, `get_triage_model()`, `get_primary_model()`, `score_job(job, profile)`, `emit_event()` |
| **Error handling** | Retry up to 3x with exponential backoff on API failure |
| **Batching** | Process up to 10 jobs per run |

**Triage model pre-filter prompt (runs on the fast/cheap model):**
```
You are a job relevance filter. Given a job title and brief description, 
determine if this is relevant for a senior delivery/product/architecture 
professional with 20+ years experience in UK.

Respond with JSON: {"relevant": true/false, "reason": "one sentence"}

Reject: junior roles, non-UK, unrelated domains, spam listings.
Pass: anything that could plausibly match the profile.
```

**Primary model scoring prompt (template — weights injected from `profile.yaml`):**
```
You are a job fit scorer. Given a candidate profile and a full job description,
score the match on four dimensions (0.0 to 1.0 each):

1. skill_match (weight: {weights.skill_match}): How well do the candidate's skills match?
2. experience_match (weight: {weights.experience_match}): Does seniority and domain align?
3. rate_match (weight: {weights.rate_match}): Is the offered rate within range?
4. location_match (weight: {weights.location_match}): Does location/remote policy work?

Overall = weighted sum of the four dimensions using the weights above.

The candidate profile, target roles, location preferences, rate range, and
domain preferences are injected at runtime from the user's profile.yaml.

Respond with JSON only:
{
  "skill_match": 0.85,
  "experience_match": 0.90,
  "rate_match": 0.70,
  "location_match": 1.0,
  "overall_score": 0.84,
  "reasoning": "Strong match because..."
}
```

#### 3.2.3 Tailor Agent

| Aspect | Detail |
|--------|--------|
| **Trigger** | Supervisor routes `job_shortlisted` (score ≥ threshold) |
| **Input** | Job posting + master CV JSON + score breakdown |
| **Output** | `cv_tailored` event with file paths and ATS score |
| **LLM usage** | Primary model (from `profile.yaml`) for JD analysis, CV structuring, cover letter generation |
| **Tools** | `analyse_jd()`, `generate_cv()`, `generate_cover_letter()`, `score_ats()`, `save_documents()`, `emit_event()` |
| **Quality gate** | If ATS score < 70%, regenerate once with adjusted emphasis |
| **Proof points** | Loaded from user's `profile.yaml` proof_points section; mapped to JD requirements by tag matching |

#### 3.2.4 Coach Agent

| Aspect | Detail |
|--------|--------|
| **Trigger** | Supervisor routes `interview_scheduled` event |
| **Input** | Application record + job posting + company name + interview type |
| **Output** | `prep_ready` event with session ID and question count |
| **LLM usage** | Primary model (from `profile.yaml`) for company research, question gen, model answers |
| **Tools** | `research_company()`, `generate_questions()`, `generate_model_answers()`, `create_star_prep()`, `emit_event()` |
| **Caching** | Company research cached 30 days; questions generated fresh per interview |

### 3.3 Event bus design

```python
import asyncio
from datetime import datetime
from uuid import uuid4

class EventBus:
    """In-process async event bus with SQLite persistence."""
    
    def __init__(self, db_session_factory):
        self._queue = asyncio.Queue()
        self._handlers: dict[str, list[callable]] = {}
        self._db = db_session_factory
    
    async def emit(self, event_type: str, source: str, payload: dict) -> str:
        """Emit an event — persists to DB and enqueues for processing."""
        event_id = str(uuid4())
        event = {
            "id": event_id,
            "event_type": event_type,
            "source": source,
            "payload": payload,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        # Persist first (durability)
        async with self._db() as session:
            session.add(AgentEvent(**event))
            await session.commit()
        # Then enqueue (dispatch speed)
        await self._queue.put(event)
        return event_id
    
    async def poll(self, event_type: str = None, batch_size: int = 10) -> list[dict]:
        """Poll for pending events, optionally filtered by type."""
        async with self._db() as session:
            query = select(AgentEvent).where(AgentEvent.status == "pending")
            if event_type:
                query = query.where(AgentEvent.event_type == event_type)
            query = query.order_by(AgentEvent.created_at).limit(batch_size)
            result = await session.execute(query)
            return [e.to_dict() for e in result.scalars()]
    
    async def mark_processed(self, event_id: str, status: str = "completed"):
        """Mark an event as processed or failed."""
        async with self._db() as session:
            event = await session.get(AgentEvent, event_id)
            event.status = status
            event.processed_at = datetime.utcnow()
            await session.commit()
```

---

## Part 4 — Data Model

### 4.1 New tables

#### agent_events
```sql
CREATE TABLE agent_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    payload TEXT NOT NULL,              -- JSON
    status TEXT DEFAULT 'pending',      -- pending | processing | completed | failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);
CREATE INDEX idx_events_status_type ON agent_events(status, event_type);
CREATE INDEX idx_events_created ON agent_events(created_at);
```

#### agent_state
```sql
CREATE TABLE agent_state (
    agent_name TEXT PRIMARY KEY,
    status TEXT DEFAULT 'idle',         -- idle | running | waiting_approval | error
    last_run_at TIMESTAMP,
    current_task TEXT,                  -- JSON
    config TEXT,                        -- JSON
    metrics TEXT,                       -- JSON: cumulative counters
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### job_scores
```sql
CREATE TABLE job_scores (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job_postings(id),
    overall_score REAL NOT NULL,
    skill_match REAL NOT NULL,
    experience_match REAL NOT NULL,
    rate_match REAL NOT NULL,
    location_match REAL NOT NULL,
    reasoning TEXT,
    haiku_passed BOOLEAN DEFAULT TRUE,
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);
CREATE INDEX idx_scores_overall ON job_scores(overall_score DESC);
```

### 4.2 Modifications to existing tables

```sql
-- job_postings: add agent tracking columns
ALTER TABLE job_postings ADD COLUMN embedding_id TEXT;       -- ChromaDB reference
ALTER TABLE job_postings ADD COLUMN auto_scored BOOLEAN DEFAULT FALSE;
ALTER TABLE job_postings ADD COLUMN auto_tailored BOOLEAN DEFAULT FALSE;
ALTER TABLE job_postings ADD COLUMN raw_jd_text TEXT;        -- Full JD for scoring

-- applications: add approval workflow columns
ALTER TABLE applications ADD COLUMN agent_created BOOLEAN DEFAULT FALSE;
ALTER TABLE applications ADD COLUMN approval_status TEXT DEFAULT 'pending';
    -- pending | approved | rejected
ALTER TABLE applications ADD COLUMN approval_decided_at TIMESTAMP;
ALTER TABLE applications ADD COLUMN rejection_reason TEXT;
```

### 4.3 Event type catalogue

| Event | Source | Consumed by | Payload schema |
|-------|--------|-------------|----------------|
| `job_discovered` | Scout | Supervisor → Scorer | `{job_id, title, company, rate, location, source, ir35_status}` |
| `job_scored` | Scorer | Supervisor | `{job_id, overall_score, skill_match, experience_match, rate_match, location_match, reasoning}` |
| `job_shortlisted` | Supervisor | Tailor | `{job_id, score}` |
| `job_parked` | Supervisor | — (logged) | `{job_id, score, reason}` |
| `cv_tailored` | Tailor | Supervisor | `{job_id, application_id, cv_path, cl_path, ats_score}` |
| `application_ready` | Supervisor | Dashboard | `{application_id}` |
| `application_approved` | Human | Supervisor | `{application_id}` |
| `application_rejected` | Human | Supervisor | `{application_id, reason}` |
| `interview_scheduled` | Human (Kanban) | Coach | `{application_id, interview_date, round_type, duration_minutes}` |
| `prep_ready` | Coach | Dashboard | `{application_id, session_id, questions_count}` |
| `agent_error` | Any agent | Supervisor | `{agent_name, error_type, message, retry_count}` |
| `agent_heartbeat` | All agents | Supervisor | `{agent_name, status, timestamp, memory_usage}` |

---

## Part 5 — Cost Model

### 5.1 Per-run cost estimates (Anthropic default — varies by provider)

| Operation | Model tier | Input tokens | Output tokens | Anthropic cost | OpenAI cost | Ollama cost |
|-----------|-----------|-------------|---------------|---------------|-------------|-------------|
| Pre-filter (1 job) | Triage | ~200 | ~50 | £0.0001 | £0.0001 | Free |
| Scoring (1 job) | Primary | ~2,000 | ~200 | £0.003 | £0.004 | Free |
| JD analysis | Primary | ~2,000 | ~500 | £0.004 | £0.005 | Free |
| CV generation | Primary | ~4,000 | ~2,000 | £0.012 | £0.015 | Free |
| Cover letter gen | Primary | ~3,000 | ~1,000 | £0.007 | £0.008 | Free |
| Company research | Primary | ~3,000 | ~1,500 | £0.009 | £0.011 | Free |
| Question gen (12 Qs) | Primary | ~4,000 | ~3,000 | £0.015 | £0.018 | Free |
| Model answer gen | Primary | ~5,000 | ~4,000 | £0.020 | £0.024 | Free |

### 5.2 Monthly cost projection (Anthropic default)

Assuming: 6 scout runs/day × 30 days, 20 jobs/run discovered, 15% pass triage, 30% of those shortlisted, 2 interviews/month.

| Activity | Volume/month | Anthropic | OpenAI | Ollama |
|----------|-------------|-----------|--------|--------|
| Triage pre-filter | 3,600 jobs | £0.36 | £0.36 | £0 |
| Primary scoring | 540 jobs | £1.62 | £2.16 | £0 |
| CV + CL generation | 50 applications | £1.15 | £1.40 | £0 |
| Coach (research + Qs + answers) | 2 interviews | £0.09 | £0.11 | £0 |
| **Total** | | **£3.22** | **£4.03** | **£0** |

All projections well within the £15/month budget. Ollama users pay £0 but trade quality and speed — local models are slower and may produce less consistent structured output. The dashboard tracks actual costs per run when `track_costs: true` is set in `profile.yaml`.

---

## Part 6 — API Endpoints

### 6.1 Agent management

```
GET    /api/v2/agents/status                      # All agent statuses
GET    /api/v2/agents/{name}/status               # Single agent
POST   /api/v2/agents/{name}/trigger              # Manual trigger
POST   /api/v2/agents/{name}/pause                # Pause
POST   /api/v2/agents/{name}/resume               # Resume
```

### 6.2 Events

```
GET    /api/v2/events                             # List (filter: type, status, date range)
GET    /api/v2/events/{id}                        # Detail
POST   /api/v2/events/{id}/retry                  # Retry failed
GET    /api/v2/events/stream                      # SSE stream for real-time updates
```

### 6.3 Approvals

```
GET    /api/v2/approvals/pending                  # Pending queue
GET    /api/v2/approvals/{application_id}         # Detail with CV/CL previews
POST   /api/v2/approvals/{application_id}/approve # Approve → resumes LangGraph
POST   /api/v2/approvals/{application_id}/reject  # Reject with reason
POST   /api/v2/approvals/{application_id}/edit    # Edit CV/CL → then approve
```

### 6.4 Dashboard

```
GET    /api/v2/dashboard/pipeline                 # Funnel stats
GET    /api/v2/dashboard/agent-activity           # Recent event timeline
GET    /api/v2/dashboard/score-distribution        # Histogram of scores
GET    /api/v2/dashboard/health                   # System health check
```

---

## Part 7 — Project Structure (New Files)

```
backend/app/
├── agents/                              # NEW — all agent code
│   ├── __init__.py
│   ├── base_agent.py                    # Abstract base: emit, log, health
│   ├── scout_agent.py                   # Wraps existing scrapers
│   ├── scorer_agent.py                  # Two-tier triage/primary scoring
│   ├── tailor_agent.py                  # Wraps existing Tailor services
│   ├── coach_agent.py                   # Wraps existing Coach services
│   ├── supervisor.py                    # LangGraph StateGraph
│   └── tools/
│       ├── __init__.py
│       ├── event_bus.py                 # Async event pub/sub + persistence
│       ├── llm_factory.py              # NEW — LangChain model factory (provider-agnostic)
│       ├── profile_loader.py            # Load + validate profile.yaml at runtime
│       └── approval_manager.py          # Human-in-the-loop logic
├── models/
│   ├── agent_event.py                   # NEW
│   ├── agent_state.py                   # NEW
│   └── job_score.py                     # NEW
├── schemas/
│   ├── agent_events.py                  # NEW — Pydantic schemas
│   ├── agent_state.py                   # NEW
│   └── profile.py                       # NEW — Pydantic model for profile.yaml validation
├── routes/
│   ├── agents.py                        # NEW — agent management API
│   ├── events.py                        # NEW — event API + SSE
│   ├── approvals.py                     # NEW — approval flow API
│   └── profile.py                       # NEW — profile CRUD + validation API
└── services/
    ├── agent_orchestrator.py            # NEW — lifecycle manager
    └── profile_service.py              # NEW — profile read/write/validate

data/
├── profile.yaml                         # User's profile (created by onboarding wizard)
├── master_cv.json                       # User's structured master CV
├── jobpilot.db                          # SQLite database
├── chroma/                              # ChromaDB embeddings
└── langgraph_checkpoints.db             # LangGraph state persistence

examples/
├── profile_uk_contractor.yaml           # Example: UK outside-IR35 contractor
├── profile_us_swe.yaml                  # Example: US senior software engineer
└── profile_eu_pm.yaml                   # Example: EU freelance product manager

frontend/app/
├── onboarding/
│   └── page.tsx                         # NEW — first-run setup wizard
├── settings/
│   └── profile/
│       └── page.tsx                     # NEW — edit profile.yaml via UI
├── dashboard/
│   └── agents/
│       └── page.tsx                     # NEW — agent status + pipeline
├── approvals/
│   ├── page.tsx                         # NEW — approval queue
│   └── [id]/
│       └── page.tsx                     # NEW — approval detail
└── prep/
    └── [session_id]/
        └── page.tsx                     # NEW — interview prep review
```

---

## Part 8 — Observability

### 8.1 Structured logging

Every agent log entry follows this format:

```json
{
  "timestamp": "2026-05-21T10:02:15Z",
  "agent": "scout",
  "event": "scrape_complete",
  "source": "contractoruk",
  "jobs_found": 8,
  "new_jobs": 3,
  "duplicates_filtered": 5,
  "duration_ms": 4200,
  "correlation_id": "run-abc123"
}
```

### 8.2 Health endpoint

```
GET /api/v2/dashboard/health
{
  "status": "healthy",
  "uptime_seconds": 86400,
  "agents": {
    "scout":  {"status": "idle", "last_run": "2026-05-21T10:00:00Z", "runs_today": 5},
    "scorer": {"status": "idle", "last_run": "2026-05-21T10:01:30Z", "scored_today": 42},
    "tailor": {"status": "idle", "last_run": "2026-05-21T10:02:15Z", "tailored_today": 3},
    "coach":  {"status": "idle", "last_run": "2026-05-18T08:30:00Z", "preps_this_week": 1},
    "supervisor": {"status": "running", "events_pending": 0, "checkpoint_count": 147}
  },
  "database": {"status": "connected", "size_mb": 12.4},
  "chromadb": {"status": "connected", "embeddings_count": 342},
  "api_usage_this_month": {"haiku_calls": 2800, "sonnet_calls": 340, "estimated_cost_gbp": 2.80}
}
```

---

## Part 9 — Test Strategy

### 9.1 Unit tests (pytest)

| Component | What to test | Mocking |
|-----------|-------------|---------|
| Each agent | Input/output contract, error handling, event emission | DB, Claude API, scrapers |
| Event bus | emit → poll → process cycle, persistence, status transitions | DB (use in-memory SQLite) |
| Scorer | Known job+profile pairs → expected score ranges | Claude API (fixture responses) |
| Routing logic | All event types route to correct nodes | Full supervisor state |
| Approval flow | Interrupt → resume → state update | LangGraph (in-memory checkpointer) |

### 9.2 Integration tests

| Test | What it validates |
|------|------------------|
| Full pipeline | Seed job → score → tailor → approval queue populated |
| Checkpoint persistence | Pause at approval → restart process → resume from same state |
| Error recovery | Inject scraper failure → verify retry → verify error event |
| SSE stream | Connect to event stream → emit event → verify SSE message received |

### 9.3 E2E tests (Playwright)

| Test | User flow |
|------|-----------|
| Dashboard loads | Visit `/dashboard` → verify agent cards render, pipeline funnel shows |
| Approval flow | Visit `/approvals` → click pending item → verify CV preview → click approve → verify status change |
| Kanban integration | Drag application to "Interview" → verify Coach agent triggers → verify prep appears |

---

## Part 10 — Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM API costs from scoring every job | Two-tier triage/primary; keyword pre-filter; batch scoring; cost tracking in health endpoint; Ollama option for zero cost |
| Job board structure changes | Factory pattern per board; alert on 3 consecutive failures; manual scrape fallback |
| LangGraph checkpoint corruption | SQLite WAL mode; periodic backup; manual retry endpoint; checkpointer tested on restart |
| Tailored CV misrepresents experience | ATS quality gate (≥ 70%); proof points hardcoded; human approval mandatory |
| Infinite agent loops | `max_iterations` safety valve in supervisor state; timeout per agent run |
| Scope creep into auto-apply | `AUTO_APPROVE=false` hardcoded in production; no external API calls without human action |
| State inconsistency between SQLite and ChromaDB | ChromaDB is advisory (scoring signal); SQLite is source of truth; rebuild ChromaDB from DB if needed |

---

## Part 11 — Implementation Plan

### Claude Code build: single phase

All implementation prompts are designed to be executed sequentially in Claude Code within a single session or a small number of sessions. The CLAUDE.md file (companion document) provides all conventions, file structure, and constraints.

**Prompt sequence:**

| # | Prompt | Depends on |
|---|--------|-----------|
| 1 | Create Pydantic schema for `profile.yaml` validation (`schemas/profile.py`). Create `profile_service.py` for read/write/validate. Create `profile_loader.py` tool that agents use to read profile at runtime. Ship 3 example profiles in `examples/`. Create API route `routes/profile.py` for profile CRUD. | Existing models |
| 2 | Create onboarding wizard frontend page (`frontend/app/onboarding/page.tsx`) — 7-step guided setup that generates `profile.yaml`. Create profile settings page (`frontend/app/settings/profile/page.tsx`) for editing. | Prompt 1 |
| 3 | Install dependencies (langgraph, chromadb, pyyaml). Create new SQLAlchemy models (agent_event, agent_state, job_score). Run Alembic migration. Create Pydantic schemas for all event types. | Prompt 1 |
| 4 | Create `event_bus.py` — async event bus with SQLite persistence and asyncio.Queue dispatch. | Prompt 3 |
| 5 | Create `base_agent.py` — abstract base class with `emit_event()`, `update_state()`, `health_check()`, structured logging. All agents read from `profile_loader` — never hardcode user data. | Prompt 4 |
| 6 | Create `llm_factory.py` with `get_triage_model()` and `get_primary_model()` using LangChain `init_chat_model()`. Create `scorer_agent.py` with two-tier scoring. All model config read from `profile.yaml`. | Prompt 5 |
| 7 | Create `scout_agent.py` wrapping existing scrapers. Board configuration read from `profile.yaml`. Emit `job_discovered` events. | Prompt 5 |
| 8 | Create `tailor_agent.py` wrapping existing Tailor services. Proof points and master CV path read from `profile.yaml`. Quality gate on ATS score. | Prompt 5 |
| 9 | Create `coach_agent.py` wrapping existing Coach services. User's skills and proof points from `profile.yaml` used for model answer generation. | Prompt 5 |
| 10 | Create `supervisor.py` — LangGraph StateGraph with all nodes, conditional edges, interrupt for approval. Shortlist threshold from `profile.yaml`. | Prompts 6-9 |
| 11 | Create `agent_orchestrator.py` — lifecycle manager. FastAPI lifespan integration. APScheduler for Scout (interval from profile). SSE endpoint. | Prompt 10 |
| 12 | Create API routes: `agents.py`, `events.py`, `approvals.py`. | Prompt 11 |
| 13 | Create frontend: Agent dashboard page with status cards, pipeline funnel, event timeline. | Prompt 12 |
| 14 | Create frontend: Approval queue page + approval detail page with CV/CL previews. | Prompt 12 |
| 15 | Create frontend: Interview prep review page. Update Kanban with score badges. | Prompt 12 |
| 16 | Write tests: unit tests for agents + event bus + routing + profile validation, integration test for full pipeline using example profile. | All above |

---

## Part 12 — Future Extensions (v3+)

| Extension | Description | Complexity |
|-----------|-------------|-----------|
| **MCP server** | Expose JobPilot as an MCP server — query pipeline from Claude Desktop or Claude Code | Medium |
| **Learning loop** | Scorer learns from accept/reject signals to refine weights over time | Medium |
| **LinkedIn agent** | Read-only monitoring of recruiter messages; alert on matches | Medium |
| **Email agent** | Auto-draft follow-up emails on schedule (with approval checkpoint) | Low |
| **Salary benchmarking** | ITJobsWatch scraping for rate validation | Low |
| **RAG over past interviews** | ChromaDB-indexed interview feedback for continuous coaching improvement | Medium |
| **Browser extension** | "Save to JobPilot" button on any job board page | Low |
| **LangSmith observability** | Production tracing and time-travel debugging via LangSmith | Low |
| **Agent-to-Agent (A2A)** | Cross-system agent communication for multi-tool orchestration | High |
