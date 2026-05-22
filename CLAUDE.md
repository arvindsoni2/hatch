# JobPilot — Claude Code Project Configuration

## Project Context
JobPilot is an AI-powered job application automation platform for outside-IR35 UK contract roles.
This is a personal tool built for a single user (Solutions Architect with 20+ years experience).
The platform has 4 modules being built incrementally: Scout → Tracker → Tailor → Coach.

**Current Phase: v2 Enhancements — Broader Search + Auto-Apply + Smart Features**

All 4 phases are complete (130 tests passing, Docker running). v2 adds:
- Broader scraper search (all IT roles, 90-day lookback)
- AI batch classifier with 0-100 match scoring
- Auto-apply engine (Playwright, Prepare→Review→Submit)
- Daily digest email
- Recruiter contact finder
- A/B testing analytics

## Tech Stack
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic
- **Scraping:** Playwright (JS-rendered sites), BeautifulSoup4 (static sites), httpx (API calls)
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui
- **Database:** SQLite (single file, portable, zero-config)
- **AI:** Claude API (claude-sonnet-4-20250514) via anthropic Python SDK
- **Scheduling:** APScheduler (in-process) with cron-like triggers
- **Containerisation:** Docker Compose (local deployment only)

## Architecture Principles
- **Async everywhere** — all scraper and API code uses async/await
- **Repository pattern** — database access through repository classes, never raw SQL in routes
- **Service layer** — business logic in services/, routes are thin wrappers
- **Factory pattern for scrapers** — each job board = 1 scraper class inheriting BaseScraper
- **Pydantic v2** — all request/response models, strict validation
- **Fail gracefully** — scrapers log errors and continue, never crash the scheduler

## File Conventions
- Python: snake_case, type hints on all functions, Google-style docstrings on public methods
- TypeScript: camelCase, strict mode enabled, no `any` type
- Tests: pytest (backend), vitest (frontend), minimum 80% coverage on services/
- Git: conventional commits — feat:, fix:, docs:, refactor:, test:, chore:

## Project Structure
```
jobpilot/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app with lifespan events
│   │   ├── config.py                  # Pydantic Settings from .env
│   │   ├── database.py                # SQLAlchemy async engine + sessionmaker
│   │   ├── models/                    # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── job.py                 # JobPosting model
│   │   │   ├── application.py         # Application model (Phase 2)
│   │   │   └── interview.py           # InterviewRound model (Phase 4)
│   │   ├── schemas/                   # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   └── job.py
│   │   ├── scrapers/                  # One file per job board
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Abstract BaseScraper class
│   │   │   ├── contractoruk.py
│   │   │   ├── jobserve.py
│   │   │   ├── reed.py
│   │   │   ├── cwjobs.py
│   │   │   ├── itjobswatch.py
│   │   │   ├── linkedin.py
│   │   │   ├── adzuna.py
│   │   │   └── scheduler.py           # APScheduler configuration
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── job_service.py         # Job CRUD + search logic
│   │   │   └── dedup.py               # Fuzzy deduplication engine
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   └── job_repository.py      # Database access layer
│   │   └── routers/
│   │       ├── __init__.py
│   │       └── jobs.py                # /api/jobs endpoints
│   ├── alembic/                       # Database migrations
│   ├── tests/
│   │   ├── test_scrapers/
│   │   ├── test_services/
│   │   └── conftest.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx               # Dashboard home
│   │   │   └── jobs/
│   │   │       └── page.tsx           # Job listings with filters
│   │   ├── components/
│   │   │   ├── JobCard.tsx
│   │   │   ├── JobTable.tsx
│   │   │   ├── FilterPanel.tsx
│   │   │   └── StatsBar.tsx
│   │   └── lib/
│   │       └── api.ts                 # API client
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
├── CLAUDE.md                          # This file
└── README.md
```

## Key Commands
```bash
make dev          # Start full stack (backend + frontend + hot reload)
make scrape       # Run all scrapers manually once
make scrape-one   # Run a single scraper: make scrape-one BOARD=contractoruk
make test         # Run all tests
make test-back    # Backend tests only
make test-front   # Frontend tests only
make migrate      # Run Alembic migrations
make migrate-new  # Create new migration: make migrate-new MSG="add_skills_column"
make docker-up    # Build and start Docker containers
make docker-down  # Stop containers
make lint         # Run ruff (Python) + eslint (TypeScript)
make seed         # Seed database with sample data for development
```

## Environment Variables (.env)
```
# Required
DATABASE_URL=sqlite+aiosqlite:///./jobpilot.db
ANTHROPIC_API_KEY=sk-ant-...

# Scraper Config
SCRAPE_INTERVAL_HOURS=4
SCRAPE_DELAY_MIN_SECONDS=2
SCRAPE_DELAY_MAX_SECONDS=8
PLAYWRIGHT_HEADLESS=true

# Optional API Keys (for boards with APIs)
REED_API_KEY=                    # Free at reed.co.uk/developers
ADZUNA_APP_ID=                   # Free at developer.adzuna.com
ADZUNA_APP_KEY=

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000

# Notifications
NOTIFICATION_EMAIL=              # For email alerts (Phase 2)
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASS=
```

## Scraper Guidelines
- ALWAYS add random delays between requests (2-8 seconds)
- ALWAYS rotate User-Agent strings from the UA pool in config.py
- ALWAYS respect robots.txt — check before scraping a new domain
- NEVER scrape more than 1 request per 3 seconds per domain
- Use Playwright stealth plugin for JS-heavy sites (ContractorUK, JobServe, CWJobs)
- Use httpx for REST APIs (Reed, Adzuna)
- Use BeautifulSoup4 for static HTML (ITJobsWatch)
- Log all scrape runs with timestamp, count, errors to scrape_log table
- Each scraper MUST implement the BaseScraper abstract class

## Database Rules
- All timestamps stored as UTC
- Use Alembic for ALL schema changes, never modify SQLite directly
- Repository methods return Pydantic schemas, not ORM objects outside the repo layer
- Soft-delete pattern: `is_active` flag, never hard delete job postings

## Testing Rules
- Mock all external HTTP calls in tests (use pytest-httpx or responses)
- Mock Playwright browser in scraper tests
- Use factory_boy for test data generation
- Integration tests use a separate SQLite in-memory database
- Every new scraper MUST have tests with sample HTML fixtures

## Common Patterns

### Adding a New Scraper
1. Create `backend/app/scrapers/{board_name}.py`
2. Inherit from `BaseScraper`
3. Implement `scrape()` → returns `List[JobPostingCreate]`
4. Register in `scheduler.py`
5. Add HTML fixture in `tests/fixtures/{board_name}/`
6. Write tests in `tests/test_scrapers/test_{board_name}.py`

### API Endpoint Pattern
```python
@router.get("/jobs", response_model=PaginatedResponse[JobPostingRead])
async def list_jobs(
    skip: int = 0,
    limit: int = 50,
    ir35_status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    repo = JobRepository(db)
    return await repo.list_with_filters(skip, limit, ir35_status, source, search)
```

## Error Handling
- Scrapers: catch all exceptions per-listing, log and continue to next
- API: return proper HTTP status codes with detail messages
- Database: use SQLAlchemy's built-in retry for connection issues
- Never expose stack traces to frontend in production

## Current TODO (Scout Module)
- [ ] Project scaffold with Docker Compose
- [ ] SQLAlchemy models + Alembic initial migration
- [ ] BaseScraper abstract class
- [ ] ContractorUK scraper (Playwright)
- [ ] JobServe scraper (Playwright)
- [ ] Reed scraper (REST API)
- [ ] CWJobs scraper (Playwright)
- [ ] ITJobsWatch scraper (BeautifulSoup)
- [ ] LinkedIn scraper (RSS/API)
- [ ] Adzuna scraper (REST API)
- [ ] Fuzzy dedup engine
- [ ] APScheduler integration
- [ ] FastAPI endpoints for job listing/search
- [ ] Next.js job listing dashboard
- [ ] Desktop notification on new matches
- [ ] Docker production build

---

## v2 Architecture Changes

### Scraper Evolution
- Scrapers now fetch ALL IT jobs (not just outside IR35 / contract)
- 90-day lookback window; quick (3h, Reed+Adzuna only) and full (8h, all boards) triggers
- New fields extracted: employment_type, working_pattern, rate_type
- AI batch classifier enriches jobs with: seniority, match_score, red_flags

### Auto-Apply Engine
- Playwright-based form automation for Reed + CWJobs ONLY
- 3-stage flow: Prepare → Review → Submit (individual review mandatory)
- Rate limit: 10 applications per hour, 30s cooldown
- CAPTCHA → falls back to manual with browser handoff
- Safety rules: never submit without approval; always screenshot; always log

### Match Scoring
- Batch classifier: 30 jobs per Claude API call
- Score 0-100: skill overlap, seniority, sector, rate, location
- Scores cached in job_postings.match_score

### Daily Digest
- APScheduler CronTrigger at configured time (default 07:00 Europe/London)
- HTML email: new high-match jobs, action items, interviews, pipeline stats
- Sent via aiosmtplib; skips if nothing to report

## v2 Key Commands
```bash
make classify             # Run AI classifier on pending jobs
make digest-preview       # Preview digest email in browser
make digest-send          # Send digest now
```

## v2 New Files
```
backend/app/services/job_classifier.py
backend/app/services/digest_service.py
backend/app/services/recruiter_finder.py
backend/app/services/auto_apply/  (engine + form_detector + form_filler + question_answerer + captcha_handler + platform_handlers/)
backend/app/routers/auto_apply.py
backend/app/routers/digest.py
backend/app/repositories/auto_apply_repository.py
backend/app/templates/candidate_profile.json  (personal data — gitignored)
backend/app/templates/emails/daily_digest.html
backend/app/prompts/job_classification.j2
frontend/src/components/AdvancedFilterPanel.tsx
frontend/src/components/AutoApplyReview.tsx
frontend/src/components/MatchScoreBadge.tsx
frontend/src/components/DigestPreview.tsx
frontend/src/app/auto-apply/page.tsx
frontend/src/app/settings/page.tsx
```


---

## Tier 1 Features — Follow-Up Email Automation + Ghost Job Detector

### Feature A: Follow-Up Email Automation

Automatically generates personalised recruiter follow-up emails triggered by Phase 2
follow-up reminders. Human review required before sending. Three email types:
- `post_application` — 5 days after applying (≤120 words)
- `post_interview_thankyou` — within 24h of interview completion (≤100 words)
- `warm_reengagement` — 14+ days stalled in applied (≤80 words)

**Key field rules:**
- `application.agency_name` (not `agency`)
- `job.skills` JSON list (not `skills_required`)
- `job.posted_at` (not `posted_date`)

**Email status lifecycle:** `draft` → `approved` → `sent` | `skipped` | `failed`

**Rate limits (EmailSender):** max 5/day total, 10 min between same domain, no repeat in 7 days

**New files:**
```
backend/app/models/follow_up_email.py       — FollowUpEmail ORM
backend/app/schemas/email.py                — GeneratedEmail, FollowUpEmailRead, EmailSendRequest
backend/app/services/email_generator.py    — EmailGenerator (uses ClaudeClient.complete_json)
backend/app/services/email_sender.py       — EmailSender (aiosmtplib + mailto)
backend/app/routers/emails.py              — /api/emails/* (9 endpoints)
backend/app/templates/emails/follow_up_email_wrapper.html
backend/app/templates/emails/follow_up_email_plain.j2
frontend/src/components/EmailPreviewModal.tsx
```

**Scheduler jobs:**
- `reminder_email_draft` — every 1h, drafts emails for overdue follow-ups
- `thank_you_email_check` — every 2h, drafts thank-you for completed interviews

**Make commands:**
```bash
make email-pending                          # List draft emails awaiting review
make email-generate APP_ID=xxx TYPE=post_application
```

---

### Feature B: Ghost Job Detector

Pure algorithmic 0-100 ghost score on every job posting. No Claude API needed. Six
weighted signals — score additive, capped at 100:

| Signal              | Weight | Trigger                                        |
|---------------------|--------|------------------------------------------------|
| repost_frequency    | +30    | times_seen >= 3                                |
| age_stale           | +25    | posted 60+ days ago (12 pts for 45-59 days)    |
| vague_description   | +20    | <200 words or <3 specificity markers           |
| agency_spam         | +15    | same company, 10+ active similar roles/30 days |
| missing_details     | +10    | no rate AND company name is 'confidential'     |
| no_response_history | +10    | applied 21+ days ago, still in 'applied' status|

**Verdicts:** `likely_real` (0-24) | `uncertain` (25-49) | `suspicious` (50-74) | `likely_ghost` (75+)

**Default behaviour:** `list_with_filters(hide_ghosts=True)` excludes `likely_ghost` from normal listings.
Pass `?hide_ghosts=false` to the jobs API to see ghost-flagged jobs.

**New files:**
```
backend/app/models/agency_reputation.py    — AgencyReputation ORM
backend/app/schemas/ghost.py               — GhostScore, GhostStats, GhostSignalDetail, GhostOverrideRequest
backend/app/services/ghost_detector.py    — GhostDetector (analyse_job, analyse_batch, update_from_outcome)
backend/app/routers/ghost.py              — /api/ghost/* (6 endpoints)
frontend/src/components/GhostBadge.tsx    — Warning badge with hover tooltip + override button
```

**DB columns added to job_postings:**
`ghost_score`, `ghost_verdict`, `ghost_signals` (JSON text), `ghost_analysed_at`,
`first_seen_at`, `times_seen` (default 1), `last_seen_at`

**Scheduler job:**
- `ghost_detector_daily` — daily at 03:00 UTC

**Make commands:**
```bash
make ghost-analyse                          # Trigger batch ghost analysis
make ghost-stats                            # Show verdict breakdown
```

**Migration:** `44b9ca7b1743_add_ghost_scoring` — adds ghost columns + agency_reputations table
