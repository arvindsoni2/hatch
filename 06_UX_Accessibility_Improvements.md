# JobPilot v2 — UX & Accessibility Improvement Spec

**Author:** Arvind Soni
**Date:** 26 May 2026
**Repo:** https://github.com/arvindsoni2/jobpilot-v2
**Status:** Ready for Claude Code implementation

---

## Context

Four issues identified from hands-on testing and the Gemini API usage screenshot showing 429 rate limit errors on the Scout agent:

1. Settings is fragmented — users edit `.env`, `profile.yaml`, and UI settings in three different places
2. Scrapers are UK-centric — new users in other regions see irrelevant board options
3. Scoring hits API rate limits on free tier — the Gemini 429 errors confirm this
4. Non-technical users can't deploy — Docker Compose + API keys + YAML editing is too much friction

---

## Issue 1: Unified Settings Experience

### Problem

Today, a user configures JobPilot in three disconnected places: `.env` (API keys), `profile.yaml` (everything else), and the Settings UI (which reads/writes profile.yaml but can't touch `.env`). Resume upload is a separate page at `/settings/resume` with raw file upload instead of a structured form.

### Solution: Single settings hub with sections

Redesign `/settings` as a tabbed single-page experience where every configuration — including API keys and resume fields — is managed from one place.

#### Tab 1: Profile
Structured form with all fields from profile.yaml, grouped logically:

```
┌─ About you ─────────────────────────────────────────────────┐
│  Name           [Arvind Soni_________________________]      │
│  Title          [Delivery Lead________________________]      │
│  Years exp.     [20___]                                     │
│  Summary        [Senior Product & Delivery...________]      │
└─────────────────────────────────────────────────────────────┘

┌─ Job search ────────────────────────────────────────────────┐
│  Target roles   [Delivery Manager] [×] [Product Owner] [×]  │
│                 [+ Add role]                                │
│  Locations      [Newcastle] [×] [Remote UK] [×]             │
│                 [+ Add location]                            │
│  Contract type  (●) Contract  ( ) Permanent  ( ) Any       │
│  Min rate       [£550____]  Max rate  [£700____]  /day ▼    │
└─────────────────────────────────────────────────────────────┘
```

#### Tab 2: Resume (structured form, not raw upload)
Instead of "upload a .docx", present a form that mirrors CV sections:

```
┌─ Professional summary ──────────────────────────────────────┐
│  [Textarea — auto-populated from parsed CV or manual entry] │
└─────────────────────────────────────────────────────────────┘

┌─ Work experience ───────────────────────────────────────────┐
│  Role 1:                                                    │
│    Title    [Senior Delivery Lead_____________________]     │
│    Company  [Northern Powergrid________________________]     │
│    Period   [2019___] to [2023___]                          │
│    Key achievement  [£500K annual savings via mobile...]    │
│    Tags     [agile] [stakeholder-mgmt] [mobile] [+]        │
│                                                             │
│  [+ Add another role]                                       │
└─────────────────────────────────────────────────────────────┘

┌─ Proof points ──────────────────────────────────────────────┐
│  Proof point 1:                                             │
│    Summary  [£500K annual savings via mobile platform_]     │
│    Context  [Northern Powergrid_______________________]     │
│    Metrics  [£500K/year, 3000+ field engineers________]     │
│    Tags     [cost-savings] [mobile] [delivery] [+]         │
│                                                             │
│  [+ Add proof point]                                        │
└─────────────────────────────────────────────────────────────┘

┌─ Skills & certifications ───────────────────────────────────┐
│  Primary     [Agile delivery] [×] [Product ownership] [×]   │
│  Certs       [PMP] [×] [PSM-1] [×] [AWS AIF-C01] [×]      │
│                                                             │
│  [Or upload existing CV: .docx / .pdf → auto-parse ↑]      │
└─────────────────────────────────────────────────────────────┘
```

The key insight: the form IS the master CV. When the user fills in work experience and proof points, the system generates `master_cv.json` from the form data. Upload is an option for initial population, not the primary interface.

#### Tab 3: AI Provider (includes API key management)
Merge `.env` management into the settings UI:

```
┌─ AI provider ───────────────────────────────────────────────┐
│                                                              │
│  Provider  (●) Gemini (free tier)                           │
│            ( ) Anthropic (Claude)                            │
│            ( ) OpenAI                                        │
│            ( ) Ollama (local — free, no API key needed)      │
│            ( ) Azure OpenAI                                  │
│                                                              │
│  API key   [AIza...•••••••••••____] [Test connection]       │
│            ✓ Connected · Gemini 2.5 Flash free tier          │
│                                                              │
│  Triage model    [gemini-2.5-flash-lite ▼] (fast, cheap)    │
│  Primary model   [gemini-2.5-flash ▼]      (detailed work)  │
│                                                              │
│  Monthly budget  [£15___]  Track costs  [✓]                 │
│                                                              │
│  ⚡ Free tier detected: rate limiting enabled automatically  │
│     (5-15 RPM depending on model, 100-1000 RPD)            │
│     JobPilot will pace LLM calls to stay within limits.     │
└─────────────────────────────────────────────────────────────┘
```

The API key save flow: user enters key → frontend sends to `PUT /api/v2/settings/env` → backend validates the key by making a test API call → on success, writes to `.env` file AND updates profile.yaml provider section → returns success with model information.

#### Tab 4: Job Boards
Shows boards available for the user's locale with toggle switches.

#### Tab 5: System
Agent status, event log, health — existing content from `/settings/system`.

### Backend changes

Add a new endpoint:

```
PUT /api/v2/settings/env
Body: { "key_name": "GOOGLE_API_KEY", "key_value": "AIza..." }
Response: { "valid": true, "provider": "google", "models_available": [...] }
```

This endpoint:
1. Validates the key by making a test LLM call
2. Writes to `.env` file (append or replace)
3. Reloads the LLM factory with the new key
4. Returns available models for the provider

Security: this endpoint should only be accessible from localhost (same-origin). The `.env` file is never served to the frontend — only the key validation result.

---

## Issue 2: Locale-Aware Scrapers

### Problem

The scraper registry shows all boards regardless of locale. A user in India sees Reed and CWJobs (UK-only boards). The locale packs exist (`locales/in.yaml`, `locales/uk.yaml`) but the frontend doesn't filter boards by locale.

### Solution

#### 2.1 Onboarding locale selection drives everything

When the user selects their country/region in onboarding (or settings), the system:
1. Loads the matching locale pack
2. Filters the scraper registry to show only locale-appropriate boards
3. Pre-fills compensation fields (CTC vs daily rate, INR vs GBP)
4. Adjusts legal fields (IR35 vs notice period)
5. Sets default scoring weights for the market

#### 2.2 Scraper registry updates

The existing `backend/app/scrapers/registry.py` already tags scrapers by locale. Ensure the frontend `Settings > Job Boards` tab filters by the user's locale from profile.yaml:

```typescript
// Frontend: filter boards by user locale
const availableBoards = allBoards.filter(
  board => board.locales.includes(userProfile.locale)
);
```

#### 2.3 Multi-locale support

Some users search across geographies (e.g., India-based looking at UK remote roles). Allow multiple locales in profile.yaml:

```yaml
locale: ["in", "uk"]  # Primary: India, also searching UK remote roles
```

This shows boards from both locales and merges compensation schemas.

#### 2.4 "Add custom board" option

For boards not in the registry, allow users to add a custom scraper URL. This creates a generic HTTP scraper that the user configures:

```
┌─ Add custom job board ──────────────────────────────────────┐
│  Board name    [_______________________________]            │
│  Search URL    [https://example.com/jobs?q={query}__]       │
│  RSS feed URL  [_______________________________] (optional) │
│                                                              │
│  This creates a basic scraper. For full scraping support,    │
│  contribute a scraper to the open-source project.           │
└─────────────────────────────────────────────────────────────┘
```

---

## Issue 3: Rate Limit Handling for Free API Tiers

### Problem

The Gemini API usage screenshot shows 429 errors (TooManyRequests). The Scout agent ran 112 times this week with a 24.1% success rate — meaning 75% of API calls failed due to rate limiting. This wastes time and creates a terrible experience.

### Solution: Smart rate-aware scoring pipeline

#### 3.1 Rate limiter middleware

Add a token-bucket rate limiter between agents and the LLM factory that respects the provider's limits:

```python
# backend/app/agents/tools/rate_limiter.py

import asyncio
from datetime import datetime, timedelta
from collections import deque

class RateLimiter:
    """Token-bucket rate limiter that respects provider free tier limits."""
    
    # Known free tier limits (RPM, RPD)
    PROVIDER_LIMITS = {
        "google": {
            "gemini-2.5-flash-lite": {"rpm": 15, "rpd": 1000},
            "gemini-2.5-flash": {"rpm": 10, "rpd": 250},
            "gemini-2.5-pro": {"rpm": 5, "rpd": 100},
        },
        "anthropic": {
            # Anthropic free tier is very limited, practically requires paid
            "default": {"rpm": 5, "rpd": 100},
        },
        "openai": {
            "default": {"rpm": 3, "rpd": 200},
        },
        "ollama": {
            # Local — no rate limits
            "default": {"rpm": 999, "rpd": 99999},
        },
    }
    
    def __init__(self, provider: str, model: str):
        limits = self.PROVIDER_LIMITS.get(provider, {}).get(
            model, self.PROVIDER_LIMITS.get(provider, {}).get("default", {"rpm": 5, "rpd": 100})
        )
        self.rpm_limit = limits["rpm"]
        self.rpd_limit = limits["rpd"]
        self.minute_window: deque = deque()
        self.day_window: deque = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> float:
        """Wait until a request slot is available. Returns wait time in seconds."""
        async with self._lock:
            now = datetime.utcnow()
            
            # Clean expired entries
            cutoff_minute = now - timedelta(minutes=1)
            cutoff_day = now - timedelta(days=1)
            while self.minute_window and self.minute_window[0] < cutoff_minute:
                self.minute_window.popleft()
            while self.day_window and self.day_window[0] < cutoff_day:
                self.day_window.popleft()
            
            # Check daily limit
            if len(self.day_window) >= self.rpd_limit:
                return -1  # Daily limit exceeded, can't proceed today
            
            # Check per-minute limit — wait if needed
            if len(self.minute_window) >= self.rpm_limit:
                wait_until = self.minute_window[0] + timedelta(minutes=1)
                wait_seconds = (wait_until - now).total_seconds()
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
            
            self.minute_window.append(now)
            self.day_window.append(now)
            return 0
```

#### 3.2 Batch scoring with pacing

Instead of scoring jobs one-at-a-time and hitting rate limits, batch and pace them:

```python
# In scorer_agent.py
async def score_batch(self, jobs: list[dict]) -> list[dict]:
    """Score a batch of jobs with rate-limit-aware pacing."""
    rate_limiter = RateLimiter(
        provider=self.profile["llm"]["provider"],
        model=self.profile["llm"]["triage_model"],
    )
    
    results = []
    for job in jobs:
        wait = await rate_limiter.acquire()
        if wait == -1:
            # Daily limit hit — park remaining jobs for next run
            logger.warning(f"Daily API limit reached. {len(jobs) - len(results)} jobs deferred to next run.")
            for remaining_job in jobs[len(results):]:
                await self.emit_event("job_deferred", {"job_id": remaining_job["id"], "reason": "daily_rate_limit"})
            break
        
        result = await self.score_single(job)
        results.append(result)
    
    return results
```

#### 3.3 Local scoring fallback

For users on free tiers or with no API key, offer a non-LLM scoring option that uses keyword matching:

```python
# backend/app/agents/tools/local_scorer.py

class LocalScorer:
    """Keyword-based scoring — no LLM needed. Less accurate but free."""
    
    def score(self, job: dict, profile: dict) -> dict:
        jd_text = job.get("description", "").lower()
        
        # Skill match: count profile skills found in JD
        skills = profile.get("skills", {}).get("primary", []) + profile.get("skills", {}).get("secondary", [])
        matched = [s for s in skills if s.lower() in jd_text]
        skill_score = len(matched) / max(len(skills), 1)
        
        # Location match: check if any target location mentioned
        locations = [loc["city"].lower() for loc in profile.get("search", {}).get("locations", [])]
        location_score = 1.0 if any(loc in jd_text for loc in locations) or "remote" in jd_text else 0.0
        
        # Rate match: parse rate from job, compare to profile range
        rate_score = self._match_rate(job, profile)
        
        # Experience match: check seniority keywords
        exp_score = self._match_experience(jd_text, profile.get("candidate", {}).get("years_experience", 0))
        
        weights = profile.get("scoring", {}).get("weights", {})
        overall = (
            skill_score * weights.get("skill_match", 0.35) +
            exp_score * weights.get("experience_match", 0.30) +
            rate_score * weights.get("compensation_match", 0.20) +
            location_score * weights.get("location_match", 0.15)
        )
        
        return {
            "overall_score": round(overall, 2),
            "skill_match": round(skill_score, 2),
            "experience_match": round(exp_score, 2),
            "rate_match": round(rate_score, 2),
            "location_match": round(location_score, 2),
            "reasoning": f"Local keyword scoring: {len(matched)}/{len(skills)} skills matched",
            "scoring_method": "local_keyword",  # vs "llm_two_tier"
        }
```

#### 3.4 Scoring strategy selector in profile.yaml

```yaml
scoring:
  method: "auto"   # "auto" | "llm" | "local" | "hybrid"
  # auto: use LLM if available and within limits, fall back to local
  # llm: LLM only (will fail if rate limited)
  # local: keyword matching only (free, fast, less accurate)
  # hybrid: local scoring first, LLM for top 20% only (cost-efficient)
```

**"hybrid" is the recommended default for free tier users.** It scores ALL jobs locally (free, instant), then sends only the top 20% to the LLM for detailed scoring. This reduces LLM calls by 80% while maintaining quality on the jobs that matter.

#### 3.5 Dashboard communication

When rate limits are hit, show it clearly on the Home page:

```
⚠ Gemini free tier: 87/100 daily API calls used.
  13 jobs deferred to tomorrow's scoring run.
  Consider: [Switch to hybrid scoring] or [Use Ollama (free, local)]
```

---

## Issue 4: Non-Technical User Deployment

### Problem

The current deployment requires: Git, Docker, Docker Compose, terminal comfort, API key acquisition, .env file editing, and profile.yaml editing. This is 7 barriers that block any non-developer.

### Solution: Three deployment tiers

#### Tier 1: One-line installer script (easiest)

A shell script that handles everything:

```bash
curl -sSL https://get.jobpilot.dev | bash
```

This script:
1. Checks for Docker (installs if missing, with user confirmation)
2. Downloads the latest release
3. Runs `docker compose up -d`
4. Opens the browser to `http://localhost:3000/onboarding`
5. The onboarding wizard handles everything else (API key, profile, boards)

For Windows: provide a `.bat` file or PowerShell script that does the same.

Create `/install.sh` at the repo root:

```bash
#!/bin/bash
set -e

echo "🚀 Installing JobPilot v2..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    echo "Docker installed. You may need to log out and back in."
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "Docker Compose not found. Please install Docker Desktop."
    exit 1
fi

# Clone or download
if [ -d "jobpilot-v2" ]; then
    echo "JobPilot directory exists. Updating..."
    cd jobpilot-v2 && git pull
else
    git clone --depth 1 https://github.com/arvindsoni2/jobpilot-v2.git
    cd jobpilot-v2
fi

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env — you'll configure API keys in the browser."
fi

# Start
docker compose up -d --build

echo ""
echo "✅ JobPilot is running!"
echo "   Open http://localhost:3000 in your browser."
echo "   The setup wizard will guide you through configuration."
echo ""
```

#### Tier 2: Desktop app via Electron/Tauri (future — medium effort)

Package JobPilot as a downloadable desktop app:
- **Tauri** (lightweight, ~5MB) wraps the Next.js frontend
- Bundled SQLite — no external database needed
- Backend runs as a sidecar process
- One-click install on Windows/macOS/Linux
- API key entered in the app settings, not a file
- Job boards, profile, everything configured via the GUI

This is a v3 feature but worth planning the architecture for now. The current settings UI redesign (Issue 1) is the groundwork — if everything is configurable via the UI, wrapping in Tauri becomes straightforward.

#### Tier 3: Cloud-hosted option (future — community contribution)

A "Deploy to Railway/Render" button in the README:

```markdown
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/jobpilot-v2)
```

This would require:
- A `railway.toml` or `render.yaml` config file
- Environment variables set via the platform's UI
- Persistent volume for SQLite data
- The app guides API key setup via onboarding wizard

### Immediate actions for v2

For the current release, the most impactful change is combining the installer script with the onboarding wizard improvements from Issue 1. If a user can run one command and then configure everything in the browser, the Docker/terminal barrier is reduced to a single copy-paste step.

---

## Claude Code Implementation Prompts

### Prompt 1: Unified settings backend — API key management

```
Add a new endpoint for managing API keys from the settings UI.

Create PUT /api/v2/settings/env in backend/app/routers/profile.py:
- Accepts: {"key_name": "GOOGLE_API_KEY", "key_value": "AIza..."}
- Validates the key by making a test LLM call using the appropriate 
  provider (detect from key_name pattern)
- On success: appends/replaces in .env file, updates profile.yaml 
  llm.provider field, reloads the LLM factory
- Returns: {"valid": true, "provider": "google", 
  "models_available": ["gemini-2.5-flash", ...], "tier": "free"}
- On failure: returns {"valid": false, "error": "Invalid API key"}

Security: only accept from localhost origins. Never return the key 
value in any response. Log key changes without the key value.

Also add GET /api/v2/settings/env/status that returns:
- Which providers have valid keys configured (without the key values)
- Current provider from profile.yaml
- Free tier vs paid tier detection
```

### Prompt 2: Unified settings frontend — tabbed settings page

```
Redesign frontend/src/app/settings/page.tsx as a tabbed interface 
with 5 tabs: Profile, Resume, AI Provider, Job Boards, System.

Tab 1 (Profile): Merge existing profile settings. Structured form 
with sections: About you, Job search (roles + locations + contract 
type + compensation), Skills & certifications, Domains. All fields 
write to profile.yaml via PUT /api/v2/profile.

Tab 2 (Resume): Structured form with sections: Professional summary 
(textarea), Work experience (repeatable group: title, company, period, 
key achievement, tags), Proof points (repeatable group: summary, 
context, metrics, tags), Skills (tag input), Certifications (tag input).
Include "Or upload CV to auto-fill" button that parses .docx/.pdf 
and populates the form fields. Form data writes to both profile.yaml 
(proof_points, skills, certifications) AND generates master_cv.json.

Tab 3 (AI Provider): Provider radio cards (Gemini, Anthropic, OpenAI, 
Ollama, Azure). API key input with mask + test button (calls 
PUT /api/v2/settings/env). Model selectors for triage and primary 
(filtered by provider). Scoring method selector (auto/llm/local/hybrid). 
Monthly budget input. Show free tier rate limit info when detected.

Tab 4 (Job Boards): Filter by user's locale. Toggle switches per board. 
Search terms input per board. "Test scraper" button. 
"Add custom board" option.

Tab 5 (System): Existing system page content (agent status, event log).

Use the existing shadcn/ui components. Save all changes to profile.yaml 
via the existing PUT /api/v2/profile endpoint except API keys which 
use the new PUT /api/v2/settings/env endpoint.
```

### Prompt 3: Rate limiter and scoring strategy

```
Create backend/app/agents/tools/rate_limiter.py with a token-bucket 
rate limiter that respects known free tier limits for Gemini, Anthropic, 
OpenAI, and Ollama (unlimited).

The rate limiter should:
1. Track requests per minute and per day using deques
2. Await a slot before allowing a request (async-safe)
3. Return -1 if daily limit is exhausted (caller should defer)
4. Auto-detect limits based on provider + model from profile.yaml

Create backend/app/agents/tools/local_scorer.py with keyword-based 
scoring that requires no LLM:
1. Match profile skills against JD text (case-insensitive)
2. Match locations (including "remote")
3. Parse and compare compensation ranges
4. Check seniority keywords against years of experience
5. Return the same score schema as the LLM scorer 
   (overall_score, skill_match, experience_match, rate_match, 
   location_match, reasoning) but with scoring_method: "local_keyword"

Update backend/app/agents/scorer_agent.py:
1. Read scoring.method from profile.yaml ("auto"|"llm"|"local"|"hybrid")
2. "auto": try LLM, fall back to local on rate limit error
3. "local": use LocalScorer only
4. "hybrid": score ALL jobs with LocalScorer first, then send 
   only the top 20% to LLM for detailed scoring
5. "llm": existing behaviour (LLM only)
6. Integrate the rate limiter — call rate_limiter.acquire() before 
   every LLM call. If daily limit hit, defer remaining jobs.
7. Emit "job_deferred" events for rate-limited jobs so the dashboard 
   can show them.

Add scoring.method to the profile.yaml Pydantic schema with 
default "auto". Update the onboarding wizard to recommend "hybrid" 
for free tier users and "auto" for paid users.
```

### Prompt 4: Locale-aware board filtering

```
Update the Job Boards settings tab and the onboarding wizard to 
filter available scrapers by the user's locale.

1. In frontend, when rendering the job boards list, call 
   GET /api/locales/{locale_id} to get the locale pack, then only 
   show boards that match the user's locale. Multi-locale support: 
   if profile.yaml has locale: ["in", "uk"], show boards from both.

2. In the onboarding wizard step 2 (location selection), when the 
   user selects their country:
   - Auto-set the locale in profile.yaml
   - Update compensation fields (CTC vs daily rate, INR vs GBP)
   - Update the board list to show locale-appropriate options
   - Update legal field labels

3. In backend/app/scrapers/registry.py, ensure every scraper has 
   a locale tag. Update the GET /api/scrapers/available endpoint 
   to accept ?locale=in and filter results.

4. Add a visual indicator on the settings page showing which locale 
   is active and how to change it: 
   "🌍 Region: India · Showing boards for India and UK"
```

### Prompt 5: One-line installer script

```
Create install.sh at the repo root — a bash script for one-command 
installation.

The script should:
1. Print a welcome banner
2. Check for Docker and Docker Compose (prompt to install if missing)
3. Clone the repo (or git pull if exists)
4. Create .env from .env.example if not exists
5. Run docker compose up -d --build
6. Wait for health check (poll GET /api/health every 2s, timeout 60s)
7. Print success message with URL: http://localhost:3000
8. Attempt to open the browser (xdg-open / open / start)

Also create install.ps1 for Windows PowerShell users.

Update README.md to show the one-line install as the primary 
quick start method, with Docker Compose as the "manual" option.

Add a Makefile target: make install that runs the script.
```

### Prompt 6: Rate limit dashboard feedback

```
Update the Home dashboard page (frontend/src/app/page.tsx) to show 
rate limit status when relevant.

1. Add a new API endpoint GET /api/v2/agents/rate-limit-status that 
   returns:
   {
     "provider": "google",
     "tier": "free",
     "daily_used": 87,
     "daily_limit": 100,
     "deferred_jobs": 13,
     "scoring_method": "hybrid",
     "recommendation": null  // or "Consider switching to hybrid scoring"
   }

2. On the Home page, if deferred_jobs > 0, show:
   "⚠ Gemini free tier: 87/100 daily API calls used. 
    13 jobs deferred to tomorrow's scoring run.
    [Switch to hybrid scoring] [Use Ollama (free)]"

3. On the Analytics page, add a "Rate limit health" section showing:
   - Daily API call usage bar (87/100)
   - Weekly trend of rate limit hits
   - Recommendation based on usage pattern

4. In the agent status strip on Home, if the Scorer's last_error 
   contains "429" or "quota" or "rate limit", show an amber dot 
   with tooltip: "Scorer hit rate limits — some jobs deferred"
```
