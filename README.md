<!-- markdownlint-disable MD033 MD041 MD060 -->

<div align="center">

# Hatch

**Open-source, self-hosted, autonomous AI job search with human-in-the-loop approvals.**

Discover → Score → Tailor → Track → Coach — fully automated, human-in-the-loop at the decisions that matter.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/next.js-14-black.svg)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-green.svg)](https://github.com/langchain-ai/langgraph)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docs.docker.com/compose/)

[Quick Start](#quick-start) · [Architecture](#architecture) · [Configuration](#configuration) · [Agents](#agents) · [FAQ](#faq)

</div>

---

## What is Hatch?

> **Status:** Active development — v4 + Coach Multimodal Uplift (Phases A–E) complete. Full pipeline (Scout → Score → Tailor → Coach) with two-step assisted apply, Agent Skills layer, Direction A UX, server-side ASR, delivery metrics, vocal-tone analysis, multi-dimensional session rubric, follow-up session chaining, on-device face analysis (MediaPipe), and optional Piper TTS. 598 backend + 336 frontend tests green.

Hatch is an autonomous, multi-agent job search system that handles the full pipeline from discovery to interview readiness — while keeping you in control of the two decisions that actually matter: approving applications and reviewing interview prep.

```text
06:00  Scout agent runs (scheduled every 4h)
       → 12 new jobs discovered across boards for your locale
       → Scorer agent processes batch (triage model filters, primary model scores)
       → 3 jobs score ≥ 0.75 → auto-shortlisted
       → Tailor agent generates tailored CV + cover letter for each
       → Skills layer assembles: screening answers + form paste-map
       → 3 items land in Today → "Needs your approval"

08:30  You open Today (Direction A cockpit)
       → Review overlay: score breakdown, tailored CV, cover letter preview
       → Tap "Approve & prepare" → package assembled instantly
       → Application ready card: screening answers, paste-map, "Open application"
       → You open the job site, paste, submit → tap "Mark as applied"
       → Confirmed apply moves to Tracker → Applied

11:00  Stale ready_to_apply? → Today shows "Finish applying" nudge
       → Tap "Undo" to revert back to review queue

14:00  You mark "Interview scheduled" on Tracker
       → Coach agent auto-triggers: company research, 12 questions, model answers
       → "Prep ready" notification — 45 minutes of prep, ready to review in Prep tab
```

**Reducing 15–20 hours/week of manual job search to < 1 hour of review.**

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Profile-driven** | All user config in `profile.yaml` — roles, location, skills, weights, LLM provider. No code changes per user. |
| **Locale Pack System** | YAML-driven market packs for 🇬🇧 UK, 🇮🇳 India, 🇮🇪 Ireland, 🇦🇪 UAE. Controls job boards, compensation defaults, and legal/compliance fields. |
| **Pluggable AI** | Anthropic, OpenAI, Google, Ollama (free/local), Azure, AWS Bedrock — switch via `profile.yaml` |
| **Dynamic model picker** | Settings page auto-discovers models from your running Ollama instance — no manual config needed. `gemma4:e2b` (primary) and `phi3:mini` (triage) are installed automatically on first run |
| **Two-tier scoring** | Cheap triage model pre-filters; strong primary model scores on 4 dimensions with configurable weights |
| **Locale-aware scoring** | Contract status, work authorisation, notice period, and other locale-specific signals injected into the `location_match` scoring dimension |
| **Assisted apply (two-step)** | Approve → package assembled (CV + cover letter + screening answers + paste-map) → you open the job site and submit → tap "Mark as applied". Hatch never submits autonomously — you are always in control of the final click. |
| **Direction A UX** | Today cockpit · Stream · Tracker · Prep — four focused screens with StageTrack pipeline visibility on every card. "Finish applying" nudge for stale `ready_to_apply` roles. |
| **Agent Skills layer** | 7 capability skills with `SKILL.md` metadata, deterministic `scripts/`, and YAML `resources/` — progressively loaded to keep LLM context lean. `screening-answers` + `form-mapping` generate clipboard-ready answers and paste-maps for the application-ready card. |
| **Autonomous pipeline** | APScheduler cron → event bus → LangGraph StateGraph routes events to correct agents |
| **Async notification bell** | Tailor and Coach run in the background; a persistent notification bell fires when jobs complete or fail, with error detail on failure |
| **Tailor history panel** | Per-job document history: all generated CV and cover letter variants listed with ATS score, download link, and regeneration button |
| **Manual JD tailoring** | Paste any job description from any website — Hatch auto-creates the job and application records, then generates tailored documents without requiring a scraper |
| **Multimodal interview coach** | Three capture modes — **Text**, **Voice**, and **Video** (opt-in with explicit consent). Voice uses server-side `faster-whisper` ASR for delivery metrics (WPM, fillers, pauses, STAR coverage) and dimensional vocal-tone analysis (arousal · valence · dominance via `audeering/wav2vec2`). Video adds in-browser MediaPipe Face Landmarker — blendshapes + head pose + eye-contact proxy; raw video never leaves the device. |
| **Session rubric** | Multi-dimensional scoring: content, STAR structure, technical depth, conciseness, impact metrics, delivery, vocal confidence, and presence (when face data available). Dimensions only appear when the signal exists. LLM-as-judge synthesiser adds transcript-quoted evidence and a focus-for-next-session directive. |
| **Follow-up session chaining** | After a session completes, plan a follow-up session targeting the 1–2 weakest rubric dimensions. Sessions form a chain via `parent_session_id`; a progress trend view tracks per-skill deltas across the chain. |
| **Technical drills** | For Technical/Domain questions, the coach generates worked-example walkthroughs and "say it out loud" drill prompts — "show, don't tell" practice rather than bare Q&A. |
| **Coach voice (TTS)** | Optional Piper TTS (CPU-real-time) speaks question prompts and feedback summaries. Disabled by default; enabled via `perception.tts.provider: piper` in `profile.yaml`. |
| **Perception factory** | Provider-agnostic perception layer (`perception_factory.py`) mirrors the LLM factory. Swap ASR, voice-emotion, face, or TTS providers via `profile.yaml → perception` — no code changes. Perception deps are in a separate `requirements-perception.txt` Docker layer for lean installs. |
| **JD gap analysis** | Per-job skill gap card: matched skills, missing skills, JD-only keywords, match %, actionable recommendations |
| **LLM trace panel** | Per-call latency, token counts, and response preview — visible in the debug panel for local troubleshooting |
| **Calendar export** | Download any interview round as an `.ics` file — one click to add to Google Calendar, Outlook, or Apple Calendar |
| **Job archiving** | Configurable auto-archive for stale listings; archived jobs stay in DB for history |
| **Self-hosted** | Docker Compose / Podman on any laptop. SQLite + ChromaDB — no external services required |

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

### What Hatch adds over the original

| Component | Status | Description |
|-----------|--------|-------------|
| `locales/*.yaml` | **New** | Locale packs — UK, India, Ireland, UAE, `_template` for contributors |
| `services/locale_service.py` | **New** | Loads/caches locale YAML; interpolates `legal_preferences` into scoring context |
| `scrapers/registry.py` | **New** | Maps locale board IDs → scraper classes; `get_scrapers_for_locale()` |
| `services/archive_service.py` | **New** | Auto-archives stale jobs; manual unarchive endpoint |
| `schemas/profile.py` | **New** | Pydantic schema with `locale`, `legal_preferences`, `archive_after_days` |
| `services/profile_service.py` | **New** | Read / write / validate `profile.yaml` |
| `agents/tools/profile_loader.py` | **New** | Mtime-cached loader; merges locale defaults into unset fields |
| `agents/tools/llm_factory.py` | **New** | LangChain `init_chat_model()` factory — provider-agnostic |
| `agents/scorer_agent.py` | **Updated** | Two-tier scoring; locale-aware `location_match`; weights from `profile.yaml` |
| `agents/tailor_agent.py` | **Updated** | Score threshold and proof points from `profile.yaml` |
| `agents/supervisor.py` | **Updated** | Shortlist threshold from `profile.yaml`; scorer owns `job_discovered` event lifecycle |
| `routers/profile.py` | **New** | Profile CRUD + live LLM connection test endpoint |
| `routers/locales.py` | **New** | Locale list, legal fields, board config for onboarding wizard |
| `components/Navigation.tsx` | **New** | 5-item nav with live approval badge, active-route highlight |
| `components/JobCard.tsx` | **Rewritten** | Horizontal card; score badge with per-dimension tooltip; gap analysis link |
| `components/ScoreBadge.tsx` | **New** | Colour-coded score badge with 4-dimension hover breakdown |
| `components/ErrorBanner.tsx` | **New** | API key invalid / scraper failure / no matching jobs banners |
| `components/GapAnalysisCard.tsx` | **New** | Inline JD gap analysis: match bar, matched/missing skill pills, JD-only keywords, recommendations |
| `components/InterviewTimeline.tsx` | **Updated** | "Add to calendar" button per interview round — downloads `.ics` |
| `app/page.tsx` (dashboard) | **Rewritten** | Redirects to `/today` — Direction A cockpit |
| `app/jobs/page.tsx` | **Rewritten** | Score band legend, match threshold toggle, archive view |
| `app/jobs/[id]/page.tsx` | **Updated** | Gap analysis section fetched server-side and rendered below job header |
| `app/onboarding/page.tsx` | **Rewritten** | 5-step wizard with locale picker, STAR proof points, API key tester, board toggles |
| `app/settings/profile/page.tsx` | **Updated** | Locale switcher, location editor (city/country/remote), job board enable/disable toggles |
| `routers/gap_analysis.py` | **New** | `GET /api/v2/jobs/{id}/gap-analysis` — keyword diff between profile skills and JD text |
| `routers/interviews_ical.py` | **New** | `GET /api/v2/interviews/{id}/ical` — iCalendar `.ics` download for interview rounds |
| `scrapers/naukri.py` | **New** | Naukri.com job scraper (India) via `jobapi/v3/search` API |
| `scrapers/indeed_india.py` | **New** | Indeed India scraper (`in.indeed.com`) |
| `examples/` | **New** | Example profiles for each supported locale (UK, India, Ireland, UAE) |
| `skills/` | **New (v4)** | 7 agent skills: `cv-tailoring`, `cover-letter`, `ats-optimization`, `company-research`, `interview-prep`, `screening-answers`, `form-mapping` — SKILL.md + scripts + resources |
| `agents/tools/perception_factory.py` | **New (Coach A/B)** | Provider-agnostic perception layer: `get_transcriber()`, `get_voice_emotion_analyser()`, `get_face_analyser()`, `get_tts()` — mirrors `llm_factory.py` |
| `services/transcriber.py` | **New (Coach A)** | `faster-whisper` CTranslate2 wrapper; returns `{text, language, words:[{w,start,end}]}`; `int8` quantised, CPU-default |
| `services/speech_analyser.py` | **Updated (Coach A)** | Derives WPM, filler rate, pause count, STAR section coverage from word timestamps; per-locale filler lexicons from `locales/*.yaml → coach.fillers` |
| `services/voice_emotion_analyser.py` | **New (Coach B)** | `AudeeringEmotionAnalyser` wrapping `audeering/wav2vec2-large-robust-12-ft-emotion-msp-dim`; returns arousal / valence / dominance in [0,1] |
| `services/rubric_builder.py` | **New (Coach B)** | Deterministic rubric builder; `score_to_band()`, per-dimension constructors; delivery and vocal_confidence only added when signal present; `presence` never added without face data |
| `services/rubric_synthesiser.py` | **New (Coach B)** | LLM-as-judge rubric enrichment via `get_json_model()`; lazy LLM init; silent fallback to deterministic baseline on any failure |
| `schemas/coach.py` | **Updated (Coach B)** | `VoiceToneResult`, `RubricDimension`, `SessionRubric`, `ScoreBand` added; `AnswerEvaluation` gains `rubric` field |
| `components/coach/CoachModalitySelector.tsx` | **Updated (Coach D)** | Text / Voice / Video picker; fetches `/api/coach/capabilities`; video gated on face_analysis capability + webcam; triggers ConsentGate on first video selection |
| `components/coach/AudioBlobRecorder.tsx` | **New (Coach B)** | `MediaRecorder`-based blob capture → `submit-audio` endpoint; shows recording timer, size/duration, and submit button |
| `components/coach/AnalysingBanner.tsx` | **New (Coach A)** | Processing-time UX — "Analysing your answer…" banner while async job is in flight; clears on result |
| `components/coach/ConsentGate.tsx` | **New (Coach D)** | Explicit consent screen for face analysis; explains on-device processing, data minimisation; one-time accept stored in `localStorage` |
| `components/coach/FaceCapture.tsx` | **New (Coach D)** | MediaPipe Face Landmarker via CDN at ~2fps; accumulates blendshape samples; computes `FaceSummary` (eye_contact_pct, head_stability, engagement_trend); 160×90 webcam preview; raw video never leaves the browser |
| `routers/coach.py` `submit-audio` | **New (Coach A)** | `POST /api/coach/sessions/{id}/submit-audio` — multipart audio blob + optional face_summary JSON; validates MIME + size cap; saves to `data/recordings/`; returns 202 + job_id |
| `routers/coach.py` Phase C + D + E | **New (Coach C–E)** | `POST plan-followup`, `GET progress/{id}/trend`, `GET capabilities`, `POST tts-question` |
| `services/technical_drills.py` | **New (Coach C)** | LLM-generated worked-example walkthroughs + "say it out loud" drill prompts for Technical/Domain questions; graceful degradation on LLM failure |
| `services/followup_planner.py` | **New (Coach C)** | Identifies 1–2 weakest rubric dimensions; creates child `InterviewSession` with `parent_session_id` + `focus_areas` and copied question set |
| `services/tts_service.py` | **New (Coach E)** | `PiperTTSService` wrapping `piper` CLI; raw PCM wrapped in WAV container; raises `PerceptionNotAvailableError` if binary absent |
| `services/rubric_builder.py` `presence` | **Updated (Coach D)** | `build_presence_dimension()` from `FaceSummary`; dimension only added when face data is present |
| Alembic migration `20260610_0001` | **New (Coach C)** | Adds `coach_mode`, `rubric`, `signals`, `parent_session_id`, `focus_areas` to `interview_sessions` |
| `services/assisted_apply.py` | **Updated (v4)** | `prepare_application` returns full `ApplicationPackage` (docs + prefill + screening answers + paste-map); no submit path |
| `routers/jobs.py` `/{id}/approve` | **New (v4)** | Two-step approve: tailor → assemble package → `ready_to_apply`; returns `ApplicationPackage` |
| `routers/applications.py` v4 | **New (v4)** | `/package`, `/mark-applied`, `/reject`, `/revert` endpoints for the assisted apply flow |
| `app/today/` | **New (v4)** | Today cockpit — pending approvals + "Finish applying" for stale `ready_to_apply` |
| `app/stream/` | **New (v4)** | Stream — full pipeline feed with StageTrack hand-off visibility |
| `app/tracker/` | **New (v4)** | Tracker — Kanban-style confirmed applies, interviews, offers |
| `app/prep/` | **New (v4)** | Prep — interview coaching questions and STAR model answers |
| `components/hatch/` | **New (v4)** | Direction A component set: `HatchNavShell`, `ReviewOverlay`, `ApplicationReadyCard`, `StageTrack`, `ScorePill`, `Btn`, `Card`, `Chip`, `HatchIcon` |

---

## Quick Start

### One-command install (recommended)

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr https://raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1 | iex
```

The installer checks prerequisites (Docker/Podman, git), clones the repo, pulls the default Ollama models (`gemma4:e2b` + `phi3:mini`) if none are present, creates a template `.env`, builds and starts the containers, and optionally installs a systemd user service on Linux.

---

### Manual install

#### Prerequisites

- Docker & Docker Compose (or Podman + podman-compose)
- An API key for your chosen LLM provider (or Ollama for local/free)
- git

#### 1. Clone

```bash
git clone https://github.com/arvindsoni2/hatch.git
cd hatch
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
| **Your market** | Locale (🇬🇧 UK · 🇮🇳 India · 🇮🇪 Ireland · 🇦🇪 UAE), target roles, location, remote preference |
| **Compensation & eligibility** | Rate range, rate type, currency + locale-specific fields (contract status, work authorisation, notice period, etc.) |
| **Skills & achievements** | Primary/secondary skills, domains, STAR proof points (used by Tailor for CV personalisation) |
| **AI setup & launch** | LLM provider, live API key test, job board toggles, scrape interval → **Start Hatch** |

### 5. Or configure manually

```bash
cp data/profile.yaml.example data/profile.yaml
# Edit with your details
```

See `examples/` for complete worked profiles:

- `examples/profile_uk_contractor.yaml` — UK Delivery Lead (outside contract)
- `examples/profile_in_engineer.yaml` — India Senior Software Engineer
- `examples/profile_ie_pm.yaml` — Ireland Product Manager
- `examples/profile_ae_architect.yaml` — UAE Solutions Architect

---

## Configuration

All user-specific configuration lives in `data/profile.yaml`. Agents read it at runtime — changes take effect on the next agent run without restart.

### Locale

```yaml
locale: "uk"   # uk | in | ie | ae (controls job boards + compliance fields)
```

The locale pack (`locales/<id>.yaml`) determines:

- Which job boards are available and enabled by default
- What legal/compliance fields appear in scoring (contract status for UK/IE, work authorisation for UAE, notice period for India, etc.)
- Default compensation currency and rate type (daily for UK/IE, annual CTC for India, monthly for UAE)
- Locale-specific guidance injected into the `location_match` scoring dimension

### LLM Providers

| Provider | `provider` value | Example triage model | Example primary model | API key env |
|----------|-----------------|---------------------|----------------------|-------------|
| Anthropic | `anthropic` | `claude-haiku-4-5-20251001` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| OpenAI | `openai` | `gpt-4o-mini` | `gpt-4o` | `OPENAI_API_KEY` |
| Google | `google` | `gemini-2.0-flash` | `gemini-2.5-pro` | `GOOGLE_API_KEY` |
| Ollama (free) | `ollama` | `gemma4:e2b` | `qwen3:4b` | — (set `base_url`) |
| Azure OpenAI | `azure` | deployment name | deployment name | `AZURE_OPENAI_API_KEY` |
| AWS Bedrock | `aws_bedrock` | model ID | model ID | AWS credentials |

```yaml
# profile.yaml — switch to Ollama for zero API cost
llm:
  provider: "ollama"
  triage_model: "gemma4:e2b"  # edge-optimised — fast background classification
  primary_model: "qwen3:4b"   # dense 4B Q4 — CV/CL generation and JD analysis
  base_url: "http://host.containers.internal:11434"  # use localhost if running outside Docker
  track_costs: false
```

> **Ollama model tip:** Thinking mode is automatically managed per model family — qwen3 has thinking ON by default (Hatch disables it for speed); gemma4 has it OFF by default (Hatch enables it only for deep analysis). The Settings page auto-discovers all locally-pulled models so you can swap them without editing YAML. See `examples/profile_local_free.yaml` for a complete zero-cost configuration.

### Choosing local models

Pull at least two models — one large (primary) and one small (triage):

```bash
ollama pull qwen3:4b && ollama pull gemma4:e2b
```

The onboarding wizard auto-detects what you have and pre-selects the best available option. It also reads your machine's RAM and shows which tier you can run.

| RAM | Recommended primary | Notes |
|-----|---------------------|-------|
| 32 GB+ | `qwen3:30b-a3b` | MoE 30B — ~3B active params; best quality |
| 16–32 GB | `gemma4:26b-a4b` | MoE 26B — ~4B active params; strong alternative |
| 8–16 GB | `qwen3:4b` | Dense 4B Q4 — solid default for most laptops |
| < 8 GB | `gemma4:e2b` | Edge-optimised; use as triage on all tiers |

All tiers use `gemma4:e2b` as the **triage model** (fast background classification). The primary model handles the heavier work: CV tailoring, cover letter generation, and coaching analysis. CPU-only — no GPU required.

### Scoring

```yaml
scoring:
  shortlist_threshold: 0.75          # jobs above this → auto-shortlisted
  weights:
    skill_match: 0.35
    experience_match: 0.30
    rate_match: 0.20
    location_match: 0.15             # locale-aware — includes contract status/work auth signals
```

### Compensation & compliance

```yaml
compensation:
  min_rate: 600
  max_rate: 800
  rate_type: "daily"                 # daily | hourly | annual | monthly
  currency: "GBP"                    # set by locale — GBP, INR, EUR, AED, etc.
  legal_preferences:                 # locale-specific — set by onboarding wizard
    contract_status: "outside"       # UK/IE: outside | inside | any
    work_authorisation: "citizen"    # UAE: citizen | visa | any
    notice_period_days: 30           # India: notice period in days
```

### Perception (Coach multimodal)

```yaml
perception:
  asr:
    provider: faster_whisper    # faster_whisper | qwen3_asr | web_speech | deepgram
    model: small                # small | medium | large-v3
    compute_type: int8          # int8 | int8_float16 | float32
    language: auto              # auto-detect; or BCP-47 language code
  voice_emotion:
    provider: audeering         # audeering | emotion2vec | hume | none
    model: wav2vec2-large-robust-12-ft-emotion-msp-dim
  face:
    provider: mediapipe_browser # mediapipe_browser | emotiefflib | hume | none
    enabled: false              # opt-in — Phase D; face data never leaves the browser
  tts:
    provider: none              # none | piper (real-time CPU) | kokoro | qwen3_tts | elevenlabs
    voice: en_GB-alan-medium    # piper voice name; see piper model card for options
```

Perception models are downloaded on first use (hundreds of MB) and cached in the `data/models/` volume — they survive `podman-compose build --pull` rebuilds. The perception stack lives in a separate `requirements-perception.txt` Docker layer; a slim install (scorer/tailor only) can omit it.

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
- **Locale context:** Contract status, work authorisation, notice period etc. injected into `location_match` prompt from locale pack
- **LLM:** Triage model (cheap, fast) + primary model (strong)

### Tailor

- **Trigger:** `job_shortlisted` events (score ≥ threshold), or manually via the UI for any job URL
- **Does:** Generates tailored CV + cover letter; ATS compatibility scoring. All runs are tracked in the tailor history panel per job — download any previous variant or regenerate at any time
- **Proof points:** Mapped from `profile.yaml → proof_points` to JD requirements by tag matching
- **Reliability:** Hard 20-minute timeout prevents indefinite hangs when Ollama is busy with background classification. 16 K context window (`num_ctx=16384`) ensures full CV prompts are never silently truncated
- **LLM:** Primary model (`gemma4:e2b` default for Ollama) with 16 K context

### Coach

- **Trigger:** `interview_scheduled` events (user action on Tracker)
- **Does:** Company research, 12 categorised questions, STAR model answers. Multiple coach sessions are queued and processed in order — each session is tracked as an async job with notification on completion
- **User context:** Skills and proof points injected from `profile.yaml`
- **LLM:** Primary model

#### Multimodal pipeline (Phases A–E complete)

The coach supports three capture modes selectable per session:

| Mode | Capture path | Perception layers | Rubric dimensions |
|------|-------------|-------------------|-------------------|
| **Text** | Typed answer or Web Speech → `submit-answer` | None | content, STAR structure, conciseness, impact, technical depth |
| **Voice** | `AudioBlobRecorder` → `submit-audio` → `faster-whisper` | ASR + delivery metrics + vocal tone (audeering) | All above + **delivery** (WPM/fillers/pauses) + **vocal confidence** (arousal/valence/dominance) |
| **Video** *(opt-in, explicit consent required)* | Audio + webcam; MediaPipe Face Landmarker runs in-browser | ASR + tone; only `FaceSummary` (eye_contact_pct, head_stability, engagement_trend) sent to server | All above + **presence** (eye contact/engagement) |

After transcription and metric computation, `RubricSynthesiserService` (LLM-as-judge) enriches the deterministic rubric with transcript-quoted evidence and a "focus for next session" directive. It falls back silently to the deterministic rubric if the LLM call fails.

**Follow-up session chaining (Phase C):** After a session completes, a "Plan follow-up" button creates a linked child session targeting the 1–2 weakest rubric dimensions. Sessions form a chain via `parent_session_id`; a progress trend panel shows per-skill score deltas across the chain. For Technical/Domain questions, `TechnicalDrillsService` generates worked-example walkthroughs and "say it out loud" drill prompts.

**On-device face analysis (Phase D):** When video mode is selected, a `ConsentGate` must be explicitly accepted. `FaceCapture.tsx` runs MediaPipe Face Landmarker at ~2fps in the browser; raw video frames never leave the device. Only an aggregate `FaceSummary` is posted alongside the audio, unlocking the `presence` rubric dimension.

**Coach voice (Phase E):** Optional Piper TTS speaks question prompts. Disabled by default (`perception.tts.provider: none`). Enable by setting `provider: piper` and ensuring the `piper` binary is in PATH.

**Perception is provider-agnostic.** ASR, voice-emotion, face, and TTS providers are configured in `profile.yaml → perception` and loaded via `perception_factory.py` — the same pattern as the LLM factory.

### Supervisor (LangGraph StateGraph)

- Routes events to the correct agent
- Enforces human-in-the-loop approval checkpoint (`interrupt()` from `langgraph.types`)
- Reads `shortlist_threshold` from `profile.yaml` at runtime
- Safety valve: `max_iterations` prevents infinite loops

---

## Human-in-the-Loop

Hatch **never submits applications autonomously.** Two mandatory human actions:

1. **Approve & prepare** (Today → Review overlay) — review score breakdown, tailored CV, cover letter. Tap "Approve & prepare" → Hatch assembles the package (screening answers, paste-map, docs). You open the job site and submit yourself. Tap "Mark as applied" to confirm. The Tracker only shows confirmed applies — no guessing.
2. **Interview prep review** (Prep tab) — review questions, model answers, STAR notes. Regenerate any answer.

`AUTO_APPROVE=true` exists only for automated testing. Never set it in production.

---

## API Reference

```text
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
GET    /api/v2/jobs/{id}/gap-analysis    JD skill gap: matched, missing, keywords, recommendations
POST   /api/jobs/scrape                  Trigger scraper(s) now
POST   /api/jobs/archive/run             Archive jobs older than profile threshold
POST   /api/jobs/{id}/unarchive          Restore an archived job

# Two-step assisted apply (v4)
POST   /api/jobs/{id}/approve            Approve job → assemble package → ready_to_apply
                                          Returns: ApplicationPackage (cv_path, cover_letter_path,
                                          job_url, prefill_map, screening_answers, paste_map)
GET    /api/applications/{id}/package    Re-fetch package for the application-ready card
POST   /api/applications/{id}/mark-applied  Confirm submission → applied (step 2)
POST   /api/applications/{id}/reject     Reject → rejected
POST   /api/applications/{id}/revert     Undo approve → ready_to_apply → ready

# Coach
GET    /api/coach/sessions              List sessions (filter by status)
GET    /api/coach/sessions/{id}         Session details + questions + technical drills
DELETE /api/coach/sessions/{id}         Remove session (marks abandoned)
POST   /api/coach/sessions/{id}/submit-answer   Text answer → 202 + job_id
POST   /api/coach/sessions/{id}/submit-audio    Audio blob (multipart) → ASR → 202 + job_id
POST   /api/coach/sessions/{id}/end     End session → report generation → 202 + job_id
GET    /api/coach/sessions/{id}/report  Full session feedback report
POST   /api/coach/sessions/{id}/plan-followup   Create follow-up session targeting weakest dimensions
POST   /api/coach/sessions/{id}/tts-question    WAV audio of question text (503 if TTS disabled)
GET    /api/coach/progress/{session_id}/trend   Per-skill score trend across session chain
GET    /api/coach/capabilities          Feature flags: face_analysis, tts (from profile.yaml)
GET    /api/async-jobs/{job_id}         Poll async job status (done | running | failed)

# Interviews
GET    /api/v2/interviews/{id}/ical      Download interview round as .ics calendar file

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

| Activity | Volume/month | Cost (USD) |
|----------|-------------|------|
| Triage pre-filter | 3,600 jobs | ~$0.45 |
| Primary scoring | 540 jobs | ~$2.05 |
| CV + CL generation | 50 applications | ~$1.45 |
| Coach (research + Q&A) | 2 interviews | ~$0.11 |
| **Total** | | **~$4.06** |

Well within the default monthly budget configured in `profile.yaml`. Use Ollama for $0.

---

## FAQ

**Why LangGraph instead of CrewAI?**
LangGraph's explicit state machine maps cleanly to the application lifecycle; `interrupt()` gives clean human-in-the-loop; `SqliteSaver` matches the existing SQLite stack. CrewAI is great for fast prototyping but lacks built-in checkpointing.

**Can I use a local model?**
Yes — Ollama is the default and requires no API key. The installer automatically pulls both `gemma4:e2b` (primary model, ~3 GB — used for CV/CL generation and JD analysis) and `phi3:mini` (triage model, ~2.3 GB — used for fast background job classification) when no models are present. Thinking mode is automatically disabled on both to avoid multi-minute response delays. You can swap models at any time from the Settings page without editing YAML.

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
