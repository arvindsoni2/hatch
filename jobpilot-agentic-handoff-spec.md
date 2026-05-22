# JobPilot v2 — Agentic Architecture Handoff Spec

## Purpose

This document is a Claude Code handoff spec for converting JobPilot from a manually-triggered 4-module pipeline into a multi-agent system with a supervisor. Each existing module (Scout, Tracker, Tailor, Coach) becomes an autonomous agent. A Supervisor agent orchestrates handoffs, enforces human-in-the-loop checkpoints, and manages the shared state.

**Target framework:** LangGraph (Python)
**Existing stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite, Next.js 14, Claude API (Sonnet)
**Deployment:** Docker Compose, single-user, self-hosted

---

## 1. Architecture Overview

```
                    ┌─────────────────────────┐
                    │    Supervisor Agent      │
                    │  (LangGraph StateGraph)  │
                    │                          │
                    │  • Routes events         │
                    │  • Enforces checkpoints  │
                    │  • Manages agent state   │
                    └────┬──────┬──────┬───────┘
                         │      │      │
              ┌──────────┘      │      └──────────┐
              ▼                 ▼                  ▼
     ┌────────────────┐ ┌──────────────┐ ┌────────────────┐
     │  Scout Agent   │ │ Tailor Agent │ │  Coach Agent   │
     │                │ │              │ │                │
     │ • Scrape jobs  │ │ • Score fit  │ │ • Research co. │
     │ • Dedup        │ │ • Tailor CV  │ │ • Generate Qs  │
     │ • Emit events  │ │ • Cover ltr  │ │ • STAR prep    │
     └───────┬────────┘ └──────┬───────┘ └───────┬────────┘
             │                 │                  │
             └────────┬────────┴────────┬─────────┘
                      ▼                 ▼
             ┌────────────────┐  ┌──────────────┐
             │  Shared State  │  │  Event Bus   │
             │   (SQLite +    │  │  (in-process │
             │  vector store) │  │   pub/sub)   │
             └────────────────┘  └──────────────┘
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestration | LangGraph StateGraph | Explicit state machine maps to Kanban states; conditional edges; built-in checkpoints |
| Agent framework | LangGraph agents (not CrewAI) | Finer control over state, better single-user perf, no YAML configs |
| LLM | Claude Sonnet via anthropic SDK | Already integrated; consistent with existing Tailor/Coach prompts |
| Event bus | In-process Python (asyncio queues) | Single-user, no need for Redis/Kafka overhead |
| Vector store | ChromaDB (local, file-backed) | Lightweight, Python-native, no server process |
| State persistence | Existing SQLite via SQLAlchemy | Already has job/application/session models |
| Human-in-the-loop | LangGraph interrupt_before | Native checkpoint support, resumes on approval |

---

## 2. Shared State Schema

### 2.1 New Table: agent_events

```sql
CREATE TABLE agent_events (
    id TEXT PRIMARY KEY,               -- UUID
    event_type TEXT NOT NULL,           -- e.g. 'job_discovered', 'job_scored', 'cv_tailored'
    source_agent TEXT NOT NULL,         -- 'scout', 'tailor', 'coach', 'supervisor'
    payload TEXT NOT NULL,              -- JSON blob
    status TEXT DEFAULT 'pending',      -- 'pending', 'processing', 'completed', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    error_message TEXT
);
CREATE INDEX idx_events_status ON agent_events(status, event_type);
CREATE INDEX idx_events_created ON agent_events(created_at);
```

### 2.2 New Table: agent_state

```sql
CREATE TABLE agent_state (
    agent_name TEXT PRIMARY KEY,        -- 'scout', 'tailor', 'coach', 'supervisor'
    last_run_at TIMESTAMP,
    status TEXT DEFAULT 'idle',         -- 'idle', 'running', 'waiting_approval', 'error'
    current_task TEXT,                  -- JSON: what the agent is currently doing
    config TEXT,                        -- JSON: agent-specific configuration
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.3 New Table: job_scores

```sql
CREATE TABLE job_scores (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job_postings(id),
    overall_score REAL NOT NULL,        -- 0.0 to 1.0
    skill_match REAL,
    experience_match REAL,
    rate_match REAL,
    location_match REAL,
    reasoning TEXT,                      -- LLM explanation of scoring
    scored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);
CREATE INDEX idx_scores_overall ON job_scores(overall_score DESC);
```

### 2.4 Additions to Existing Tables

```sql
-- Add to job_postings
ALTER TABLE job_postings ADD COLUMN embedding BLOB;          -- ChromaDB reference
ALTER TABLE job_postings ADD COLUMN auto_scored BOOLEAN DEFAULT FALSE;
ALTER TABLE job_postings ADD COLUMN auto_tailored BOOLEAN DEFAULT FALSE;

-- Add to applications
ALTER TABLE applications ADD COLUMN agent_created BOOLEAN DEFAULT FALSE;
ALTER TABLE applications ADD COLUMN approval_status TEXT DEFAULT 'pending';
    -- 'pending', 'approved', 'rejected'
```

---

## 3. Event Types & Flow

### 3.1 Event Catalogue

| Event | Source | Consumed By | Payload |
|-------|--------|-------------|---------|
| `job_discovered` | Scout | Supervisor → Scorer | `{job_id, title, company, rate, source}` |
| `job_scored` | Scorer (sub-agent) | Supervisor | `{job_id, score, reasoning}` |
| `job_shortlisted` | Supervisor | Tailor | `{job_id, score}` (score >= threshold) |
| `cv_tailored` | Tailor | Supervisor | `{job_id, application_id, cv_path, cl_path, ats_score}` |
| `application_ready` | Supervisor | Dashboard (human) | `{application_id, job_id, cv_path, cl_path}` |
| `application_approved` | Human (via API) | Supervisor | `{application_id}` |
| `interview_scheduled` | Human (via Tracker) | Coach | `{application_id, interview_date, round_type}` |
| `prep_ready` | Coach | Dashboard (human) | `{application_id, session_id, questions_count}` |
| `scout_error` | Scout | Supervisor | `{source, error, retry_count}` |
| `agent_heartbeat` | All agents | Supervisor | `{agent_name, status, timestamp}` |

### 3.2 The Autonomous Loop

```
  ┌──── CRON (every 4 hours) ────┐
  │                               │
  ▼                               │
Scout Agent                       │
  │ scrape all boards             │
  │ dedup against existing        │
  ▼                               │
emit job_discovered (×N)          │
  │                               │
  ▼                               │
Supervisor receives events        │
  │ batch scoring                 │
  ▼                               │
Scorer sub-agent                  │
  │ score each job against        │
  │ master profile + preferences  │
  ▼                               │
emit job_scored (×N)              │
  │                               │
  ▼                               │
Supervisor checks threshold       │
  │ score >= 0.75 → shortlist     │
  │ score < 0.75 → park          │
  ▼                               │
Tailor Agent (for shortlisted)    │
  │ generate CV + cover letter    │
  │ run ATS scoring               │
  ▼                               │
emit cv_tailored                  │
  │                               │
  ▼                               │
Supervisor creates application    │
  status = 'ready_to_apply'       │
  approval_status = 'pending'     │
  │                               │
  ▼                               │
  ╔═══════════════════════════╗   │
  ║  HUMAN CHECKPOINT #1     ║   │
  ║  Review CV + cover letter ║   │
  ║  Approve / Reject / Edit  ║   │
  ╚═══════════════════════════╝   │
  │                               │
  ▼  (on approve)                 │
Application status → 'applied'    │
  │                               │
  ... (human marks interview)     │
  │                               │
  ▼                               │
  ╔═══════════════════════════╗   │
  ║  TRIGGER: interview       ║   │
  ║  scheduled in Tracker     ║   │
  ╚═══════════════════════════╝   │
  │                               │
  ▼                               │
Coach Agent                       │
  │ research company              │
  │ generate questions            │
  │ create STAR model answers     │
  ▼                               │
emit prep_ready                   │
  │                               │
  ▼                               │
  ╔═══════════════════════════╗   │
  ║  HUMAN CHECKPOINT #2     ║   │
  ║  Review prep materials    ║   │
  ║  Start mock interview     ║   │
  ╚═══════════════════════════╝   │
  │                               │
  └───────────────────────────────┘
```

---

## 4. Agent Specifications

### 4.1 Scout Agent

**File:** `backend/app/agents/scout_agent.py`

**Responsibilities:**
- Run all scrapers on schedule (existing Playwright/BS4 scrapers)
- Deduplicate against existing jobs in DB
- Emit `job_discovered` events for genuinely new jobs
- Handle scraper errors gracefully, emit `scout_error` on failure

**Tools available:**
- `scrape_contractoruk()` — existing scraper
- `scrape_jobserve()` — existing scraper
- `scrape_reed()` — existing scraper
- `scrape_cwjobs()` — existing scraper
- `check_duplicate(title, company, location)` — existing dedup via rapidfuzz
- `emit_event(event_type, payload)` — new, writes to agent_events table

**State:**
- `last_scrape_at` per source
- `jobs_found_this_run` counter
- `errors_this_run` list

**LLM usage:** None (Scout is deterministic). LLM only used if adding natural language job description parsing later.

**Trigger:** APScheduler cron (every 4h, configurable via SCRAPE_INTERVAL_HOURS)

```python
# Pseudocode for Scout Agent node in LangGraph
class ScoutState(TypedDict):
    sources_to_scrape: list[str]
    jobs_found: list[dict]
    errors: list[dict]
    current_source: str | None

def scout_node(state: ScoutState) -> ScoutState:
    """Scrape next source, dedup, emit events."""
    source = state["sources_to_scrape"][0]
    scraper = ScraperFactory.get(source)
    raw_jobs = await scraper.scrape()
    new_jobs = [j for j in raw_jobs if not check_duplicate(j)]
    for job in new_jobs:
        save_to_db(job)
        emit_event("job_discovered", job.to_event_payload())
    return {
        "sources_to_scrape": state["sources_to_scrape"][1:],
        "jobs_found": state["jobs_found"] + new_jobs,
        "current_source": source,
    }
```

### 4.2 Scorer Sub-Agent

**File:** `backend/app/agents/scorer_agent.py`

**Responsibilities:**
- Receive batch of `job_discovered` events
- Score each job against the master profile (skills, experience, rate, location)
- Use Claude to reason about fit quality
- Emit `job_scored` events

**Tools available:**
- `get_master_profile()` — reads master CV JSON + preferences
- `score_job(job, profile)` — Claude API call with structured output
- `emit_event(event_type, payload)`

**LLM prompt structure:**
```
You are a job fit scorer. Given a candidate profile and a job description,
score the match on four dimensions (0.0-1.0 each):

1. skill_match: How well do the candidate's skills match the requirements?
2. experience_match: Does the seniority and domain experience align?
3. rate_match: Is the offered rate within the candidate's range?
4. location_match: Does the location/remote policy work?

Overall score = weighted average:
  skill_match * 0.35 + experience_match * 0.30 +
  rate_match * 0.20 + location_match * 0.15

Respond with JSON only:
{
  "skill_match": 0.85,
  "experience_match": 0.90,
  "rate_match": 0.70,
  "location_match": 1.0,
  "overall_score": 0.84,
  "reasoning": "Strong match on delivery and architecture skills..."
}
```

**Master profile anchors (hardcoded for now):**
- Skills: Agile delivery, product ownership, GenAI/ML, cloud architecture, stakeholder management
- Seniority: Senior / Lead (20+ years)
- Rate range: £550-£700/day (outside IR35)
- Location: Newcastle upon Tyne, open to remote/hybrid UK-wide
- Domain preference: Energy, Financial Services, Aviation, Public Sector, Tech

### 4.3 Tailor Agent

**File:** `backend/app/agents/tailor_agent.py`

**Responsibilities:**
- Receive `job_shortlisted` events
- Generate tailored CV from master CV JSON
- Generate tailored cover letter
- Run ATS compatibility scoring
- Emit `cv_tailored` event

**Tools available:**
- `get_master_cv()` — reads master CV JSON
- `analyse_jd(job_description)` — existing Claude API service
- `generate_cv(jd_analysis, master_cv)` — existing Tailor service
- `generate_cover_letter(jd_analysis, master_cv)` — existing Tailor service
- `score_ats(cv_text, jd_text)` — existing ATS scorer
- `save_documents(cv, cl, application_id)` — saves .docx files
- `emit_event(event_type, payload)`

**Proof points to anchor (always include in tailored output):**
1. £500K annual savings — Northern Powergrid mobile platform
2. 90% reduction in manual processing — Natoora GenAI initiative
3. 40% time-to-market improvement — Natoora Agile transformation
4. £400K legacy rationalisation savings — Northern Powergrid ADM

**Threshold:** Only tailor if `job_score.overall_score >= 0.75`

### 4.4 Coach Agent

**File:** `backend/app/agents/coach_agent.py`

**Responsibilities:**
- Triggered when an interview is scheduled (via Tracker status change)
- Research the company (using existing CompanyResearch service)
- Generate role-specific interview questions with model answers
- Create STAR-structured preparation notes
- Emit `prep_ready` event

**Tools available:**
- `research_company(company_name)` — existing CompanyResearch service
- `generate_questions(jd, company_research, interview_type)` — existing question generator
- `generate_model_answers(questions, master_cv, jd)` — existing model answer generator
- `create_star_prep(questions, cv_achievements)` — maps STAR stories to likely questions
- `emit_event(event_type, payload)`

**LLM usage:** Heavy — company research, question generation, model answer generation, STAR mapping.

### 4.5 Supervisor Agent

**File:** `backend/app/agents/supervisor.py`

**Responsibilities:**
- Central orchestrator implemented as a LangGraph StateGraph
- Polls event bus for new events
- Routes events to appropriate agents
- Enforces human-in-the-loop checkpoints
- Handles errors and retries
- Maintains agent health via heartbeats

**Supervisor StateGraph definition:**

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver

class SupervisorState(TypedDict):
    pending_events: list[dict]
    current_event: dict | None
    agent_results: dict
    human_approval_needed: bool
    approved_applications: list[str]
    errors: list[dict]

def route_event(state: SupervisorState) -> str:
    """Conditional edge: route based on event type."""
    event = state["current_event"]
    if event is None:
        return "poll_events"
    match event["event_type"]:
        case "job_discovered":
            return "score_job"
        case "job_scored":
            score = event["payload"]["score"]
            if score >= 0.75:
                return "tailor_job"
            return "park_job"
        case "cv_tailored":
            return "request_approval"
        case "application_approved":
            return "mark_applied"
        case "interview_scheduled":
            return "prepare_interview"
        case _:
            return "log_unknown"

# Build the graph
graph = StateGraph(SupervisorState)

# Add nodes
graph.add_node("poll_events", poll_events_node)
graph.add_node("score_job", scorer_agent_node)
graph.add_node("tailor_job", tailor_agent_node)
graph.add_node("park_job", park_job_node)
graph.add_node("request_approval", request_approval_node)  # interrupt_before
graph.add_node("mark_applied", mark_applied_node)
graph.add_node("prepare_interview", coach_agent_node)
graph.add_node("log_unknown", log_unknown_node)

# Add edges
graph.add_conditional_edges("poll_events", route_event)
graph.add_edge("score_job", "poll_events")
graph.add_edge("tailor_job", "poll_events")
graph.add_edge("park_job", "poll_events")
graph.add_edge("request_approval", "poll_events")
graph.add_edge("mark_applied", "poll_events")
graph.add_edge("prepare_interview", "poll_events")

# Human checkpoint
graph.add_node("request_approval", request_approval_node)
# LangGraph interrupt_before pauses execution here until human resumes

# Compile with SQLite checkpointing
memory = SqliteSaver.from_conn_string("sqlite:///jobpilot.db")
app = graph.compile(checkpointer=memory, interrupt_before=["request_approval"])
```

---

## 5. Project Structure (New Files)

```
backend/app/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py              # BaseAgent ABC with emit_event, log, health check
│   ├── scout_agent.py             # Scout: wraps existing scrapers
│   ├── scorer_agent.py            # Scorer: LLM-based job fit scoring
│   ├── tailor_agent.py            # Tailor: wraps existing CV/CL generation
│   ├── coach_agent.py             # Coach: wraps existing interview prep
│   ├── supervisor.py              # Supervisor: LangGraph StateGraph
│   └── tools/
│       ├── __init__.py
│       ├── event_bus.py           # In-process async event pub/sub
│       ├── job_scorer_tool.py     # Claude API tool for scoring
│       ├── profile_loader.py      # Load master profile for scoring
│       └── approval_manager.py    # Human-in-the-loop approval logic
├── models/
│   ├── agent_event.py             # SQLAlchemy model for agent_events
│   ├── agent_state.py             # SQLAlchemy model for agent_state
│   └── job_score.py               # SQLAlchemy model for job_scores
├── schemas/
│   ├── agent_events.py            # Pydantic schemas for events
│   └── agent_state.py             # Pydantic schemas for agent state
├── routes/
│   ├── agents.py                  # API: agent status, trigger, approve
│   └── events.py                  # API: list events, retry failed
└── services/
    └── agent_orchestrator.py      # Startup, scheduling, lifecycle management
```

---

## 6. API Endpoints (New)

### 6.1 Agent Management

```
GET    /api/agents/status                    # All agent statuses
GET    /api/agents/{name}/status             # Single agent status
POST   /api/agents/{name}/trigger            # Manually trigger an agent run
POST   /api/agents/{name}/pause              # Pause an agent
POST   /api/agents/{name}/resume             # Resume a paused agent
```

### 6.2 Event Management

```
GET    /api/events                           # List events (filterable by type, status)
GET    /api/events/{id}                      # Single event detail
POST   /api/events/{id}/retry                # Retry a failed event
```

### 6.3 Approval Flow

```
GET    /api/approvals/pending                # List applications awaiting approval
GET    /api/approvals/{application_id}       # Get approval detail (CV, CL, score)
POST   /api/approvals/{application_id}/approve   # Approve an application
POST   /api/approvals/{application_id}/reject    # Reject with reason
POST   /api/approvals/{application_id}/edit      # Edit CV/CL before approving
```

### 6.4 Dashboard Additions

```
GET    /api/dashboard/pipeline               # Pipeline stats (discovered → scored → tailored → applied)
GET    /api/dashboard/agent-activity         # Recent agent activity timeline
GET    /api/dashboard/score-distribution     # Histogram of job scores
```

---

## 7. Frontend Additions

### 7.1 Agent Dashboard Page

**Route:** `/dashboard/agents`

**Components:**
- `AgentStatusCards` — one card per agent showing status, last run, jobs processed
- `EventTimeline` — chronological feed of agent events
- `PipelineFunnel` — visual funnel: discovered → scored → shortlisted → tailored → approved
- `ApprovalQueue` — list of applications pending human review

### 7.2 Approval Review Page

**Route:** `/approvals/[application_id]`

**Components:**
- `JobSummaryCard` — job title, company, rate, score breakdown
- `CVPreview` — rendered preview of tailored CV
- `CoverLetterPreview` — rendered preview of cover letter
- `ScoreBreakdown` — radar chart of skill/experience/rate/location match
- `ApprovalActions` — Approve / Reject / Edit buttons
- `EditModal` — inline editing of CV/CL before approval

### 7.3 Updates to Existing Pages

- **Kanban board:** Add colour-coded score badges on job cards
- **Job detail page:** Show agent activity timeline for that job
- **Interview prep page:** Auto-populated when Coach agent completes prep

---

## 8. Configuration

### 8.1 Environment Variables (additions to .env)

```bash
# Agent configuration
SCORE_THRESHOLD=0.75                 # Minimum score for auto-shortlisting
SCRAPE_INTERVAL_HOURS=4              # Scout agent schedule
MAX_TAILOR_BATCH=5                   # Max jobs to tailor per run
AUTO_APPROVE=false                   # If true, skip human checkpoint (dev only)
AGENT_LOG_LEVEL=INFO                 # DEBUG for development

# Vector store
CHROMA_PERSIST_DIR=./data/chroma     # ChromaDB storage path

# LangGraph
LANGGRAPH_CHECKPOINT_DB=sqlite:///data/langgraph_checkpoints.db
```

### 8.2 Master Profile Config

**File:** `backend/app/config/master_profile.yaml`

```yaml
candidate:
  name: "Arvind Soni"
  title: "Senior Product & Delivery Professional"
  years_experience: 20
  location: "Newcastle upon Tyne, UK"
  remote_preference: "hybrid_or_remote"

rate:
  min_daily: 550
  max_daily: 700
  currency: "GBP"
  ir35_status: "outside"

skills:
  primary:
    - "Agile delivery management"
    - "Product ownership"
    - "Stakeholder management"
    - "Digital transformation"
    - "Cloud architecture (AWS)"
  secondary:
    - "GenAI / Agentic AI"
    - "Python / FastAPI"
    - "Data platform design"
    - "DevOps practices"

domains:
  preferred:
    - "Energy & Utilities"
    - "Financial Services"
    - "Aviation"
    - "Public Sector"
    - "Technology"

proof_points:
  - id: "npg_mobile"
    summary: "£500K annual savings via mobile workforce platform"
    context: "Northern Powergrid"
    metrics: "£500K/year savings, 2000+ field engineers"
  - id: "natoora_genai"
    summary: "90% reduction in manual processing via GenAI"
    context: "Natoora Ltd"
    metrics: "90% reduction, automated order processing"
  - id: "natoora_agile"
    summary: "40% time-to-market improvement via Agile transformation"
    context: "Natoora Ltd"
    metrics: "40% faster delivery cycles"
  - id: "npg_adm"
    summary: "£400K savings via legacy system rationalisation"
    context: "Northern Powergrid"
    metrics: "£400K savings, 12 legacy apps decommissioned"

certifications:
  - "PMP"
  - "PMI-ACP"
  - "PSM-1"
  - "PSPO-1"
  - "AWS SAA-C03 (in progress)"
  - "AWS AIF-C01 (in progress)"
```

---

## 9. Implementation Order (Claude Code Prompts)

Execute these in order. Each prompt is self-contained and builds on the previous.

### Phase A — Foundation (Day 1-2)

**Prompt A1: Dependencies & Models**
```
Install langgraph, chromadb, and pyyaml. Add SQLAlchemy models for
agent_events, agent_state, and job_scores as specified in the handoff
spec (Section 2). Create Alembic migration. Add Pydantic schemas for
all event types. Follow existing patterns in backend/app/models/ and
backend/app/schemas/.
```

**Prompt A2: Event Bus**
```
Create backend/app/agents/tools/event_bus.py — an in-process async
event bus using asyncio.Queue. Methods: emit(event_type, source,
payload), subscribe(event_type, handler), poll(event_type=None,
status='pending'). Events are persisted to agent_events table on
emit and status-updated on processing. Include batch polling for
the supervisor.
```

**Prompt A3: Base Agent**
```
Create backend/app/agents/base_agent.py — an abstract base class
for all agents. Include: emit_event(), update_state(), health_check(),
structured logging with agent name prefix. Each agent has a name,
tools list, and state dict. Use the event bus from A2.
```

### Phase B — Scout & Scorer (Day 3-4)

**Prompt B1: Scout Agent**
```
Create backend/app/agents/scout_agent.py wrapping the existing
scrapers. It should iterate through configured sources, run each
scraper, dedup results using the existing dedup engine, save new
jobs to DB, and emit job_discovered events for each new job.
Handle scraper errors gracefully — log and continue to next source.
Inherit from BaseAgent.
```

**Prompt B2: Scorer Agent**
```
Create backend/app/agents/scorer_agent.py. Load master profile from
config/master_profile.yaml. For each job_discovered event, call
Claude API with the scoring prompt from Section 4.2. Parse structured
JSON response. Save scores to job_scores table. Emit job_scored event.
Batch up to 10 jobs per scoring run to manage API costs.
```

### Phase C — Tailor & Coach Agents (Day 5-6)

**Prompt C1: Tailor Agent**
```
Create backend/app/agents/tailor_agent.py wrapping the existing
Tailor services (JD analysis, CV generation, cover letter generation,
ATS scoring). Triggered by job_shortlisted events. Use existing
services in backend/app/services/. Save generated documents. Emit
cv_tailored event with file paths and ATS score.
```

**Prompt C2: Coach Agent**
```
Create backend/app/agents/coach_agent.py wrapping the existing Coach
services (company research, question generation, model answer
generation). Triggered by interview_scheduled events. Use existing
services. Create InterviewSession record. Emit prep_ready event.
```

### Phase D — Supervisor & Orchestration (Day 7-8)

**Prompt D1: Supervisor StateGraph**
```
Create backend/app/agents/supervisor.py implementing the LangGraph
StateGraph from Section 4.5. Define SupervisorState TypedDict. Add
nodes for: poll_events, score_job, tailor_job, park_job,
request_approval, mark_applied, prepare_interview. Add conditional
edges via route_event function. Compile with SqliteSaver checkpointer.
Set interrupt_before on request_approval node for human-in-the-loop.
```

**Prompt D2: Orchestrator Service**
```
Create backend/app/services/agent_orchestrator.py. This is the
lifecycle manager. On FastAPI startup (lifespan event): initialise
all agents, start APScheduler for Scout cron, start supervisor
event polling loop. On shutdown: graceful stop of all agents.
Expose methods for manual trigger, pause, resume of individual agents.
```

**Prompt D3: API Routes**
```
Create backend/app/routes/agents.py and backend/app/routes/events.py
with the endpoints from Section 6. Include the approval flow endpoints.
The approve endpoint should resume the LangGraph checkpoint for that
application. Use existing auth patterns (or none — single user).
```

### Phase E — Frontend (Day 9-10)

**Prompt E1: Agent Dashboard**
```
Create a new Next.js page at app/dashboard/agents/page.tsx. Include:
AgentStatusCards (one per agent with status indicator, last run time,
jobs processed count), EventTimeline (chronological feed with event
type badges), PipelineFunnel (discovered → scored → shortlisted →
tailored → approved counts). Use shadcn/ui Card, Badge, and
ScrollArea components. Poll /api/agents/status every 30 seconds.
```

**Prompt E2: Approval Queue**
```
Create app/approvals/page.tsx showing pending approvals as cards.
Each card shows: job title, company, rate, overall score (colour-coded),
tailored CV preview (iframe or rendered markdown), cover letter preview.
Actions: Approve (green), Reject (red), Edit (yellow). On approve,
POST to /api/approvals/{id}/approve and show success toast.
Create app/approvals/[id]/page.tsx for detailed single-approval view.
```

**Prompt E3: Kanban Updates**
```
Update the existing Kanban board to show score badges on job cards
(green >= 0.85, amber >= 0.75, red < 0.75). Add an "Agent Activity"
tab to the job detail page showing the event timeline for that
specific job. Auto-populate the interview prep section when
prep_ready event exists for the application.
```

---

## 10. Testing Strategy

### Unit Tests
- Each agent: test with mocked dependencies (DB, Claude API, scrapers)
- Event bus: test emit/subscribe/poll cycle
- Scorer: test with known job/profile pairs, assert score ranges
- Supervisor: test routing logic with mock events

### Integration Tests
- Full pipeline: seed a job → score → tailor → approval flow
- LangGraph checkpoint: verify pause/resume at approval node
- Error handling: simulate scraper failure, verify retry

### E2E Tests (Playwright)
- Agent dashboard loads and shows agent statuses
- Approval queue shows pending items
- Approve/reject flow updates application status

---

## 11. Observability

### Logging
- Structured JSON logs per agent with correlation IDs
- Event lifecycle logged: emitted → processing → completed/failed
- Claude API calls logged with token counts and latency

### Metrics (future: Prometheus)
- `agent_runs_total` counter per agent
- `jobs_discovered_total` counter per source
- `job_score_histogram` for score distribution
- `tailor_duration_seconds` histogram
- `approval_wait_seconds` histogram (time from ready to human decision)
- `event_processing_duration_seconds` per event type

### Health Check
```
GET /api/health
{
  "status": "healthy",
  "agents": {
    "scout": {"status": "idle", "last_run": "2026-04-09T10:00:00Z"},
    "scorer": {"status": "idle", "last_run": "2026-04-09T10:01:30Z"},
    "tailor": {"status": "idle", "last_run": "2026-04-09T10:02:15Z"},
    "coach": {"status": "idle", "last_run": "2026-04-09T08:30:00Z"},
    "supervisor": {"status": "running", "events_pending": 3}
  },
  "database": "connected",
  "uptime_seconds": 86400
}
```

---

## 12. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Claude API costs from scoring every job | Batch scoring (10/run), cache profile embedding, pre-filter by keyword before LLM |
| Rate limiting on job boards | Existing respectful scraping with delays; rotate user agents |
| LangGraph checkpoint corruption | SQLite WAL mode, periodic backup, manual retry endpoint |
| Tailor generates poor CV | ATS score gate (reject if < 70%), human checkpoint before send |
| Coach generates irrelevant questions | Company research cache with 30-day TTL, cross-reference with JD |
| Single point of failure (supervisor) | Supervisor is stateless (state in DB), restart-safe via checkpoints |
| Scope creep into auto-apply | AUTO_APPROVE=false by default, require explicit human approval |

---

## 13. Future Extensions (v3)

- **MCP integration:** Expose agents as MCP tools for cross-platform orchestration
- **A2A protocol:** Agent-to-agent communication for multi-user scenarios
- **RAG over past interviews:** ChromaDB-indexed interview feedback for coaching improvement
- **LinkedIn agent:** Monitor and respond to recruiter messages (with approval)
- **Salary benchmarking agent:** ITJobsWatch scraping for rate validation
- **Email agent:** Auto-send follow-ups on a schedule (with approval)
