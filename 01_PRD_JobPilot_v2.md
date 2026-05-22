# JobPilot v2 — Product Requirements Document

**Author:** Arvind Soni  
**Date:** 21 May 2026  
**Status:** Draft v1.0 — for review  
**Supersedes:** JobPilot v1 (manual 4-module pipeline) — to be archived as `jobpilot-v1-archived`, not extended.  
**Companion document:** `02_Design_JobPilot_v2.md`  
**Build instructions:** `CLAUDE.md` (project root)

---

## 1. Problem statement

> *"Today I waste a significant amount of time manually researching jobs across multiple boards, sorting them by relevance, tailoring my CV for each application, tracking application states across spreadsheets and browser tabs, and preparing for interviews without a structured coaching system. The entire pipeline — from discovery to interview readiness — is manual, repetitive, and time-consuming. I want to automate this end-to-end, keeping myself in the loop only for the decisions that genuinely need human judgment."*

### 1.1 The daily reality

A typical job search week currently looks like this:

| Activity | Time/week | Pain level |
|----------|-----------|------------|
| Browsing 4-5 job boards manually | 4-5 hours | High — repetitive, easy to miss listings |
| Reading JDs, mentally scoring relevance | 2-3 hours | High — no consistent framework, gut-feel decisions |
| Tailoring CV + cover letter per role | 3-4 hours per application | Very high — most time-intensive step |
| Tracking applications (spreadsheet/notes) | 1-2 hours | Medium — state gets stale, follow-ups missed |
| Interview preparation (ad hoc research) | 3-5 hours per interview | High — no structure, no feedback, no coaching |
| **Total** | **15-20+ hours/week** | — |

This is on top of a full-time role at Natoora. The cognitive load of context-switching between "day job" and "job search" is the hidden cost that doesn't appear in the hours.

### 1.2 What's broken specifically

1. **Discovery is pull-based, not push-based.** I go to job boards; job boards don't come to me. This means I either check obsessively (wasting time) or check infrequently (missing opportunities). There's no middle ground without automation.

2. **Relevance scoring is inconsistent.** When I scan 30 listings, my scoring framework shifts depending on fatigue, time of day, and which listing I saw first. A strong match buried at listing #25 gets less attention than a mediocre one at listing #3. No consistent rubric is applied.

3. **CV tailoring is the bottleneck.** Each application requires 45-90 minutes of CV restructuring and cover letter drafting. This limits me to 3-4 quality applications per week. An AI-assisted approach could reduce this to a review-and-approve workflow, increasing throughput 3-5x.

4. **Application tracking has no intelligence.** A spreadsheet tracks status but doesn't remind me when follow-ups are due, doesn't surface which applications are going cold, and doesn't correlate outcomes with application quality.

5. **Interview prep is uncoached.** I prepare alone, with no feedback on answer quality, no structured STAR practice, and no company-specific intelligence beyond what I manually research. This is the highest-stakes phase with the least support.

---

## 2. Product vision

**JobPilot v2** is an open-source, self-hosted, autonomous multi-agent system that manages the complete job search lifecycle — from discovery through interview readiness — for any professional in any domain. It scores opportunities against a user-defined profile, auto-generates tailored application materials, and prepares structured interview coaching, with human-in-the-loop checkpoints at the two highest-stakes decision points: approving applications and reviewing interview preparation.

The system operates as a background agent on any machine capable of running Docker, continuously discovering opportunities matched to the user's configured role, location, and preferences — surfacing only what needs human judgment, when it needs it.

### 2.1 One-sentence pitch

> An open-source agentic AI system that finds, scores, tailors, tracks, and coaches — so any job seeker spends time on decisions, not drudgery.

---

## 3. Users

### 3.1 Target user

Any professional actively searching for jobs — whether contract, permanent, or freelance — who wants to automate the repetitive parts of the search pipeline while retaining control over high-stakes decisions (applications and interview preparation).

**Typical user profile:**
- Mid-career to senior professional in any domain
- Comfortable self-hosting Docker (or following a setup guide)
- Searching across multiple job boards simultaneously
- Spending 10-20+ hours/week on manual job search activities
- Wants structured interview preparation, not ad-hoc Googling

### 3.2 User-defined configuration

JobPilot v2 is fully configurable via a `profile.yaml` file and an onboarding wizard (first-run setup). Nothing is hardcoded to a specific user, role, or geography.

#### 3.2.1 Profile configuration (`profile.yaml`)

The user defines their entire search context in a single YAML file. The system uses this for scoring, tailoring, and coaching — every agent reads from this profile.

```yaml
# ─── Identity ───────────────────────────────────────────────
candidate:
  name: ""                          # Full name (used in CV/cover letter generation)
  title: ""                         # Current or target professional title
  years_experience: 0               # Total years of professional experience
  summary: ""                       # 2-3 sentence professional summary

# ─── Search Parameters ──────────────────────────────────────
search:
  target_roles:                     # List of role titles to search for
    - ""                            # e.g. "Delivery Lead", "Product Owner", "Software Architect"
  locations:                        # Target locations (supports multiple)
    - city: ""                      # e.g. "London", "Manchester", "Remote"
      country: ""                   # e.g. "UK", "US", "Germany"
      radius_miles: 30              # Search radius from city centre
      remote_preference: ""         # "onsite" | "hybrid" | "remote" | "any"
  contract_type: ""                 # "contract" | "permanent" | "freelance" | "any"
  
# ─── Compensation ───────────────────────────────────────────
compensation:
  min_rate: 0                       # Minimum acceptable rate/salary
  max_rate: 0                       # Maximum / target rate/salary
  rate_type: ""                     # "daily" | "hourly" | "annual"
  currency: ""                      # "GBP" | "USD" | "EUR" | etc.
  ir35_preference: ""               # "outside" | "inside" | "any" (UK-specific, ignored elsewhere)

# ─── Skills & Experience ────────────────────────────────────
skills:
  primary:                          # Core skills — weighted highest in scoring
    - ""
  secondary:                        # Supporting skills — weighted lower
    - ""
  certifications:                   # Professional certifications
    - ""

domains:
  preferred:                        # Industry domains, ordered by preference
    - ""
  excluded:                         # Domains to filter out entirely
    - ""

# ─── Proof Points (for CV/CL tailoring) ─────────────────────
# These are the user's key achievements that get mapped into tailored materials.
# Each proof point has an ID, summary, context, and quantified metrics.
proof_points:
  - id: ""                          # Short identifier (e.g. "digital_transformation")
    summary: ""                     # One-line achievement summary
    context: ""                     # Company/project where this happened
    metrics: ""                     # Quantified result (e.g. "£500K annual savings")
    tags: []                        # Skill tags for matching to JD requirements

# ─── Master CV ───────────────────────────────────────────────
# Path to master CV in JSON format (structured for reordering/tailoring)
master_cv_path: "./data/master_cv.json"

# ─── Job Board Configuration ────────────────────────────────
# Each board can be enabled/disabled and configured independently
job_boards:
  - name: ""                        # e.g. "reed", "indeed", "linkedin"
    enabled: true
    scraper: ""                     # Scraper class name (must exist in scrapers/)
    search_params: {}               # Board-specific search parameters (keywords, filters)

# ─── Scoring Weights ─────────────────────────────────────────
# Users can adjust how much each dimension matters in the overall score
scoring:
  weights:
    skill_match: 0.35
    experience_match: 0.30
    rate_match: 0.20
    location_match: 0.15
  shortlist_threshold: 0.75         # Minimum score for auto-shortlisting

# ─── LLM Provider ───────────────────────────────────────────
# Choose your preferred model provider. JobPilot uses LangChain's model
# abstraction layer, so any LangChain-supported provider works.
llm:
  provider: "anthropic"             # "anthropic" | "openai" | "google" | "ollama" | "azure" | "aws_bedrock"
  
  # Two-tier model config: a fast/cheap model for triage, a strong model for synthesis
  triage_model: "claude-haiku-4-5-20251001"    # Used for: pre-filtering, quick relevance checks
  primary_model: "claude-sonnet-4-20250514"    # Used for: scoring, CV tailoring, coaching, question gen
  
  # Provider-specific settings
  api_key_env: "ANTHROPIC_API_KEY"  # Name of the env var holding the API key (never store keys in YAML)
  base_url: null                    # Override base URL (e.g. for Ollama: "http://localhost:11434")
  temperature: 0.3                  # Default temperature for all LLM calls
  max_retries: 3                    # Retry count on API failures
  
  # Cost tracking (optional — used for dashboard cost estimates)
  track_costs: true
  monthly_budget: 15.00             # Budget cap in your currency — warns when approaching
  currency: "GBP"

# ─── Preferences ─────────────────────────────────────────────
preferences:
  scrape_interval_hours: 4          # How often Scout agent runs
  max_tailor_batch: 5               # Max jobs to auto-tailor per run
  follow_up_days: [5, 10, 15]       # Reminder schedule after application
  locale: "en-GB"                   # Language/locale for generated content
```

**Supported LLM providers (via LangChain):**

| Provider | Config value | Triage model example | Primary model example | API key env var | Notes |
|----------|-------------|---------------------|----------------------|-----------------|-------|
| Anthropic | `anthropic` | `claude-haiku-4-5-20251001` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` | Default. Best structured output. |
| OpenAI | `openai` | `gpt-4o-mini` | `gpt-4o` | `OPENAI_API_KEY` | Strong alternative. |
| Google | `google` | `gemini-2.0-flash` | `gemini-2.5-pro` | `GOOGLE_API_KEY` | Free tier available. |
| Ollama (local) | `ollama` | `gemma3:4b` | `qwen3:14b` | — (no key needed) | Free, private, CPU-only viable. Set `base_url`. |
| Azure OpenAI | `azure` | deployment name | deployment name | `AZURE_OPENAI_API_KEY` | Enterprise. Requires `base_url`. |
| AWS Bedrock | `aws_bedrock` | model ID | model ID | AWS credentials | Enterprise. |

#### 3.2.2 First-run onboarding wizard

On first launch, if `profile.yaml` is absent or empty, the dashboard presents a guided setup wizard that walks the user through:

1. **Who are you?** — name, title, years of experience, summary
2. **What are you looking for?** — target roles (multi-select + free text), locations, contract type, compensation range
3. **What are your strengths?** — skills (suggested from common lists + free text), certifications, preferred domains
4. **What have you achieved?** — proof points with guided STAR prompts (situation, metric, context)
5. **Upload your master CV** — drag-and-drop PDF/DOCX → auto-parsed to structured JSON
6. **Which job boards?** — toggle boards on/off, configure search terms per board
7. **Choose your AI provider** — select LLM provider (Anthropic/OpenAI/Google/Ollama/Azure), pick triage and primary models from a filtered list, enter API key (stored in `.env`, never in YAML), test connection with a one-shot ping
8. **Scoring preferences** — adjust dimension weights with sliders, set shortlist threshold

The wizard writes `profile.yaml` to disk. All subsequent agent behaviour derives from this file. Users can edit the YAML directly or re-run the wizard at any time.

### 3.3 Example profiles

To demonstrate flexibility, the system ships with three example profiles:

| Example | Role | Location | Contract type |
|---------|------|----------|---------------|
| `examples/profile_uk_contractor.yaml` | Delivery Lead / Solutions Architect | Newcastle, UK | Outside-IR35 contract |
| `examples/profile_us_swe.yaml` | Senior Software Engineer | San Francisco / Remote US | Permanent |
| `examples/profile_eu_pm.yaml` | Product Manager | Berlin / Remote EU | Freelance |

---

## 4. Goals and success metrics

### 4.1 Primary goals

| Goal | Metric | Target |
|------|--------|--------|
| Reduce manual job search time | Hours/week spent on discovery + sorting | From 7-8h to < 1h (review only) |
| Increase application throughput | Quality applications submitted per week | From 3-4 to 8-10 |
| Improve application quality | ATS compatibility score on tailored CVs | ≥ 80% average |
| Reduce interview prep time | Hours per interview preparation | From 3-5h to < 1h (review + practice) |
| Improve interview readiness | Structured STAR responses per interview | ≥ 5 rehearsed, scored responses |
| Zero missed opportunities | Jobs matching profile that were not surfaced | < 5% miss rate |
| Zero missed follow-ups | Follow-up reminders that were not triggered | 0 missed |

### 4.2 Secondary goals

| Goal | Metric | Target |
|------|--------|--------|
| Portfolio demonstration | Showcase in portfolio as AI/agentic project | Complete case study |
| Cost efficiency | Monthly running cost (API + hosting) | ≤ £15/month |
| Learning vehicle | Hands-on LangGraph multi-agent experience | Production system built |

### 4.3 Non-goals

- **Multi-user SaaS.** This is a self-hosted, single-user tool. No auth, no RBAC, no multi-tenancy. Each user runs their own instance.
- **Auto-apply.** The system will never submit applications autonomously. Human approval is mandatory before any external action.
- **LinkedIn automation.** No automated LinkedIn messaging, connection requests, or profile activity. Read-only scraping only, if at all.
- **Mobile app.** Dashboard is web-only. Mobile is out of scope for v2.
- **Built-in job board accounts.** Users bring their own access to job boards. JobPilot scrapes public listings only.

---

## 5. Functional requirements

### 5.1 Discovery (Scout Agent)

| ID | Requirement | Priority |
|----|-------------|----------|
| F-SC-01 | Scrape user-configured job boards on a configurable schedule (default: every 4 hours). Ship with scrapers for ContractorUK, JobServe, Reed, CWJobs, Indeed, and LinkedIn (public listings). | Must |
| F-SC-02 | Deduplicate jobs across sources using fuzzy matching (title + company + location) | Must |
| F-SC-03 | Extract structured data from each listing: title, company, rate/salary, location, IR35 status, JD text | Must |
| F-SC-04 | Emit `job_discovered` event for each genuinely new job | Must |
| F-SC-05 | Respect rate limits and robots.txt on all job boards | Must |
| F-SC-06 | Handle scraper failures gracefully — log, continue, alert on consecutive failures | Must |
| F-SC-07 | Support adding new job board scrapers without modifying agent logic | Should |
| F-SC-08 | Track scraper health metrics: success rate, jobs found per source, latency | Should |

### 5.2 Scoring (Scorer Sub-Agent)

| ID | Requirement | Priority |
|----|-------------|----------|
| F-SR-01 | Score every discovered job against the user's `profile.yaml` on four configurable dimensions: skill match, experience match, rate match, location match — with user-adjustable weights | Must |
| F-SR-02 | Produce a weighted overall score (0.0-1.0) with human-readable reasoning | Must |
| F-SR-03 | Auto-shortlist jobs scoring ≥ user-configured threshold (default: 0.75, set in `profile.yaml`) | Must |
| F-SR-04 | Batch scoring (up to 10 jobs per run) to manage API costs | Must |
| F-SR-05 | Learn from accept/reject signals over time to refine scoring | Could |
| F-SR-06 | Pre-filter by keywords before LLM scoring to reduce API calls | Should |

### 5.3 Tailoring (Tailor Agent)

| ID | Requirement | Priority |
|----|-------------|----------|
| F-TA-01 | Generate a tailored CV from master CV JSON for each shortlisted job | Must |
| F-TA-02 | Generate a tailored cover letter for each shortlisted job | Must |
| F-TA-03 | Run ATS compatibility scoring on the generated CV | Must |
| F-TA-04 | Always include the user's configured proof points (from `profile.yaml`) in tailored materials, mapped to JD requirements by tag matching | Must |
| F-TA-05 | Save generated .docx files linked to the application record | Must |
| F-TA-06 | Support human editing of generated materials before approval | Must |
| F-TA-07 | Version-track all generated documents per application | Should |
| F-TA-08 | Regenerate with different emphasis if first version is rejected | Should |

### 5.4 Tracking (Shared State — Evolved from Tracker Module)

| ID | Requirement | Priority |
|----|-------------|----------|
| F-TR-01 | Maintain full application lifecycle: discovered → scored → shortlisted → tailored → ready → approved → applied → interview → offered → outcome | Must |
| F-TR-02 | Kanban dashboard showing all applications by state | Must |
| F-TR-03 | Auto-generate follow-up reminders (configurable: 5/10/15 days after application) | Must |
| F-TR-04 | Surface stale applications (no activity in N days) | Should |
| F-TR-05 | Pipeline analytics: funnel from discovered to outcome | Should |
| F-TR-06 | Agent activity timeline per job (which agent did what, when) | Must |

### 5.5 Coaching (Coach Agent)

| ID | Requirement | Priority |
|----|-------------|----------|
| F-CO-01 | Auto-trigger company research when interview is scheduled | Must |
| F-CO-02 | Generate role-specific interview questions (6 categories: behavioural, technical, situational, company, role, STAR) | Must |
| F-CO-03 | Generate model answers referencing the candidate's actual experience and proof points | Must |
| F-CO-04 | Create STAR-structured preparation notes mapped to likely questions | Must |
| F-CO-05 | Support voice practice with Web Speech API transcription | Should |
| F-CO-06 | Evaluate transcribed answers against STAR rubric (relevance, structure, depth, conciseness, impact) | Should |
| F-CO-07 | Mock interview mode with AI-generated follow-up questions | Could |
| F-CO-08 | Cache company research with 30-day TTL to avoid redundant API calls | Must |

### 5.6 Orchestration (Supervisor Agent)

| ID | Requirement | Priority |
|----|-------------|----------|
| F-SU-01 | Route events to appropriate agents based on event type | Must |
| F-SU-02 | Enforce human-in-the-loop checkpoint before any application materials leave the system | Must |
| F-SU-03 | Enforce human-in-the-loop checkpoint for interview prep review | Must |
| F-SU-04 | Handle agent errors with configurable retry (default: 3 attempts with exponential backoff) | Must |
| F-SU-05 | Maintain agent health status via heartbeat mechanism | Should |
| F-SU-06 | Support manual agent triggering via API/dashboard | Must |
| F-SU-07 | Support pausing and resuming individual agents | Should |
| F-SU-08 | Persist supervisor state across restarts via checkpointing | Must |

### 5.7 Human-in-the-Loop

| ID | Requirement | Priority |
|----|-------------|----------|
| F-HL-01 | **Checkpoint 1 — Application approval:** present tailored CV + cover letter + score breakdown. Actions: approve, reject, edit-then-approve. | Must |
| F-HL-02 | **Checkpoint 2 — Interview prep review:** present questions + model answers + STAR notes. Actions: approve, request regeneration, edit. | Must |
| F-HL-03 | Approval queue accessible from dashboard with pending count badge | Must |
| F-HL-04 | Desktop notification when new approvals are pending | Should |
| F-HL-05 | Never auto-approve in production (configurable override for testing only) | Must |

---

## 6. Non-functional requirements

| Category | Requirement |
|----------|-------------|
| **Performance** | Full pipeline (discover → score → tailor for 1 job) completes in < 5 minutes |
| **Reliability** | Supervisor state survives process restarts; no data loss on crash |
| **Cost** | Total monthly API cost ≤ £15 (Claude API for scoring + tailoring + coaching) |
| **Security** | All data local; API keys in `.env`, never committed; no personal data sent to job boards |
| **Privacy** | Claude API calls contain CV data — acceptable risk for single-user, review Anthropic retention policy |
| **Deployment** | Docker Compose on any Linux/macOS/WSL machine |
| **Maintainability** | New job board scrapers addable without agent logic changes |
| **Observability** | Structured JSON logs per agent; event lifecycle tracking; agent health dashboard |

---

## 7. Constraints

| Constraint | Impact |
|-----------|--------|
| Self-hosted, single-user per instance | No distributed systems complexity; SQLite is fine; no auth needed |
| Designed for commodity hardware (any laptop/desktop with 8GB+ RAM) | All LLM inference via API; no local model hosting for production tasks |
| Claude API as default LLM (pluggable via LangChain) | Users can switch to OpenAI, Google, Ollama, Azure, or Bedrock via `profile.yaml`. LangChain's `init_chat_model()` factory handles provider abstraction. Prompts are provider-agnostic. |
| Docker Compose only | No Kubernetes, no cloud deployment; health checks via Docker |
| Existing v1 codebase (Python 3.12, FastAPI, SQLAlchemy 2.0, Next.js 14) | Must wrap, not rewrite; existing scrapers, Tailor, Coach services preserved |
| Profile-driven, not hardcoded | All user-specific data lives in `profile.yaml`; no code changes needed per user |

---

## 8. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Claude API cost exceeds budget | Medium | Medium | Batch scoring, keyword pre-filter, Haiku for triage / Sonnet for synthesis |
| Job board structure changes break scrapers | High | Medium | Factory pattern per board; alert on consecutive failures; manual fallback |
| ATS scoring gives false confidence | Medium | High | Human review checkpoint; ATS score is advisory, not definitive |
| LangGraph complexity vs. benefit | Medium | Medium | Start with supervisor-only; add agent autonomy incrementally |
| Tailored CV misrepresents experience | Low | Very high | Human approval mandatory; proof points sourced from user's `profile.yaml`, never hallucinated |
| Over-automation reduces interview readiness | Low | High | Coach generates prep, but human still practices; system augments, doesn't replace |
| Scope creep into auto-apply | Low | Critical | `AUTO_APPROVE=false` hardcoded; no external-facing actions without human |

---

## 9. Technology decisions to resolve in design doc

| Decision | Options | Notes |
|----------|---------|-------|
| Orchestration framework | LangGraph vs CrewAI vs custom | LangGraph strong favourite; confirm in design |
| Scoring LLM tier | Claude Haiku (cheap triage) vs Sonnet (better reasoning) | Cost vs quality trade-off |
| Vector store for embeddings | ChromaDB vs FAISS vs none | Needed for semantic dedup and profile matching? |
| Event bus | In-process asyncio vs Redis vs none | Single-user, so in-process likely sufficient |
| Frontend state management | Polling vs WebSocket vs SSE for real-time updates | Agent dashboard needs near-real-time |
| Document generation | Existing docx-js pipeline vs PDF via react-pdf | Maintain existing .docx generation? |

---

## 10. Acceptance criteria for v2 release

- [ ] First-run onboarding wizard generates a valid `profile.yaml` from user input.
- [ ] System reads all scoring, tailoring, and coaching parameters from `profile.yaml` — no hardcoded user data in code.
- [ ] Changing `profile.yaml` (roles, location, skills, weights) takes effect on next agent run without restart.
- [ ] Scout agent discovers jobs from ≥ 3 user-configured boards on a 4-hour schedule without manual intervention.
- [ ] Scorer produces consistent scores; same job re-scored within 24h produces score within ±0.05.
- [ ] Tailor generates CV + cover letter that passes ATS scoring ≥ 80% for a shortlisted job, using proof points from `profile.yaml`.
- [ ] Human approval checkpoint blocks pipeline until explicit approve/reject action.
- [ ] Coach generates ≥ 10 relevant interview questions with model answers when interview is scheduled.
- [ ] Dashboard shows real-time agent status, event timeline, and approval queue.
- [ ] Full pipeline (discover → score → tailor → approval) runs end-to-end without manual intervention.
- [ ] Monthly API cost for 30 days of operation is ≤ £15 (at typical usage volumes).
- [ ] System recovers from process restart without losing state or pending approvals.
- [ ] No secret appears in any file under version control.
- [ ] Example profiles for 3 different user personas (UK contractor, US engineer, EU PM) are included and functional.

---

## 11. Out of scope for the PRD; will be answered in the design doc

- Component breakdown and agent topology (graph structure)
- Concrete data models for events, scores, agent state
- Exact scoring formula and prompt engineering
- LangGraph StateGraph definition and edge logic
- Frontend component architecture
- Cost model breakdown per agent per run
- Error handling, retry, and idempotency strategy
- Test strategy (unit, integration, end-to-end)
- Implementation order and Claude Code prompt sequence
