# JobPilot v2 — UX Redesign Spec (Claude Code Instructions)

**Author:** Arvind Soni
**Date:** 22 May 2026
**Status:** Ready for implementation
**Companion to:** `01_PRD_JobPilot_v2.md`, `02_Design_JobPilot_v2.md`

This document is a Claude Code instruction set for fixing the current JobPilot v2 UX. It addresses 12 specific issues identified in a UX audit of the live implementation (localhost:3001). Execute these changes in the order listed.

---

## Design Principles (apply to all changes)

1. **Task-first, not data-first.** The dashboard answers: "what needs my attention?" — not "here's everything in the database."
2. **Onboarding gates everything.** No data is shown until a valid profile exists. Period.
3. **Hide complexity.** Agent names (Scout, Scorer, Tailor, Coach) are implementation details. Users think in tasks: review, approve, prepare.
4. **Only show actionable data.** Jobs below threshold are parked automatically, not shown. Empty columns are hidden, not displayed with "—" or "Unknown".
5. **Three-band colour system.** Green = above threshold (auto-shortlisted). Amber = between 50% and threshold (parked). Gray = below 50% (hidden). Bands align to the user's configured threshold.

---

## 1. Onboarding Gate (CRITICAL — implement first)

### Problem
New users land on a dashboard showing 159 stale jobs with match scores against no profile. The system shows "Outside-IR35 UK contract roles" — hardcoded from a previous user.

### Fix

**File:** `frontend/app/page.tsx` (or the root layout that renders the dashboard)

Add a profile status check on mount. If no valid `profile.yaml` exists (check via `GET /api/v2/profile/status`), redirect to `/onboarding` instead of rendering the dashboard.

```typescript
// In the dashboard page component (page.tsx)
useEffect(() => {
  async function checkProfile() {
    const res = await fetch('/api/v2/profile/status');
    const data = await res.json();
    if (!data.profileExists || !data.isComplete) {
      router.push('/onboarding');
    }
  }
  checkProfile();
}, []);
```

**Backend:** Ensure `GET /api/v2/profile/status` returns:
```json
{
  "profileExists": false,
  "isComplete": false,
  "missingFields": ["candidate.name", "search.target_roles", "llm.provider"],
  "completionPercent": 0
}
```

**Empty state:** If profile exists but no jobs have been scraped yet (fresh setup), show an encouraging empty state — not a table of zeros:

```
┌────────────────────────────────────────────┐
│  🔍 Your agents are warming up             │
│                                            │
│  First scrape scheduled in 12 minutes.     │
│  We'll notify you when jobs are ready.     │
│                                            │
│  [Trigger scrape now]  [Edit profile]      │
└────────────────────────────────────────────┘
```

---

## 2. Navigation Simplification

### Problem
11 nav items including contradictory ones (Auto Apply) and implementation-detail labels (Scout, Tailor, Coach, Agents, API Docs).

### Fix

**File:** `frontend/components/Navigation.tsx` (or equivalent nav component)

Replace the entire nav with 5 task-oriented items plus a settings gear:

```
[Logo] JobPilot    Home    Jobs    Approvals (3)    Pipeline    Interview prep    [⚙ settings icon]
```

| Current item | What happens |
|-------------|-------------|
| Dashboard → | **Home** (renamed) |
| All Jobs → | **Jobs** (renamed, simplified) |
| Applications → | Merged into **Pipeline** (Kanban view) |
| Auto Apply → | **REMOVED** entirely (contradicts PRD non-goal) |
| Calendar → | Moved to **Settings** |
| Coach → | Merged into **Interview prep** |
| Tailor → | Removed from nav — tailoring is automatic, results appear in Approvals |
| Agents → | Moved to **Settings > System** |
| Approvals → | **Approvals** (kept, with pending count badge) |
| API Docs → | Moved to **Settings > Developer** |
| Analytics → | Removed — key metrics are on Home dashboard |

**The "Scout · Tracker · Tailor · Coach · Agents" subtitle** under the logo — remove entirely. It's implementation jargon.

**Approvals badge:** Show a red count badge when pending approvals > 0. Use SSE or polling to keep it current.

**Settings page** (`/settings`): Consolidate moved items here with tabs:
- Profile (edit profile.yaml via UI)
- Job boards (configure sources)
- AI provider (LLM settings)
- System (agent status, logs, health — moved from "Agents" page)
- Developer (API docs, event log)

---

## 3. Dashboard Redesign — Action Cards

### Problem
Dashboard leads with vanity metrics (Total Jobs: 159, New Today: 0) and a dense table of irrelevant listings.

### Fix

**File:** `frontend/app/page.tsx` (dashboard page)

Restructure the dashboard into three vertical sections:

### Section A: Agent status strip (top, minimal)
A single-line strip showing system health. Not a hero section — just reassurance.

```
● All agents running    Last scrape: 23 min ago    Next: in 3h 37m
```

- Green dot = all agents healthy
- Amber dot = one agent has warnings
- Red dot = an agent has failed (with "View details" link to settings)

If agents haven't run in > 8 hours (2x the scrape interval), show a yellow warning banner instead:
```
⚠ No scrapes in the last 8 hours. [Check agent status] [Trigger scrape now]
```

### Section B: Action cards (the main focus — 3 cards max)
These tell the user what needs their attention RIGHT NOW. Only show cards that have non-zero counts.

```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ ☑ Review needed │ │ 🎓 Prep ready   │ │ ✨ New matches  │
│                 │ │                 │ │                 │
│       3         │ │       1         │ │      17         │
│                 │ │                 │ │                 │
│ tailored apps   │ │ NTT DATA — 3d   │ │ 5 above 75%    │
│ ready           │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

- **"Review needed"** card: 2px info-coloured border (featured). Count of pending approvals. Clicking navigates to `/approvals`. Only shows if count > 0.
- **"Prep ready"** card: Count of interview prep sessions awaiting review. Shows nearest interview company + days until. Only shows if count > 0.
- **"New matches"** card: Jobs discovered today. Subtitle shows how many scored above threshold. Links to `/jobs?filter=today&min_score=75`.

If ALL three counts are zero:
```
✓ You're all caught up. Next scrape in 3h 37m.
```

### Section C: Top matches (below the fold)
Show only jobs scoring ABOVE the user's configured threshold. Sorted by score descending. Max 5 shown.

Each job card is a single row:
```
[91%]  Senior Delivery Lead — Accenture — Newcastle — £650/day    [CV ready]
[86%]  Product Owner — DWP Digital — Remote UK — £600/day         [Tailoring...]
[79%]  Solutions Architect — NTT DATA — London — £700/day         [Scored]
```

- Score badge colour: Green (≥75%), Amber (50-74%), Gray (<50%)
- Status pill: "CV ready" (green), "Tailoring" (blue), "Scored" (gray)
- No columns for missing data (no "Unknown" IR35, no "—" rate, no "unknown" type)
- Clicking a job row opens the job detail page
- "View all jobs →" link at the bottom

### Section D: Pipeline bar (minimal, at bottom)
A proportional horizontal bar showing the funnel:
```
[====== 142 discovered ====][=== 23 shortlisted ===][= 12 applied =][3]
                                                                    ↑ interview
```
This replaces the "Jobs by Source" section which is moved to Settings > System.

---

## 4. Job Listing Improvements

### Problem
The Recent Listings table shows 8 columns, most with missing data. "Unknown" appears everywhere. Irrelevant jobs (0% match) are shown prominently.

### Fix

**File:** `frontend/app/jobs/page.tsx` (or the jobs listing page)

### 4.1 Filter by default
Only show jobs scoring ≥ the user's threshold (from profile.yaml). Below-threshold jobs are accessible via a "Show all" toggle or filter, but not the default view.

### 4.2 Simplify columns
Remove columns that frequently show missing data. New column set:

| Column | Content |
|--------|---------|
| Match | Score badge (coloured) |
| Job | Title + company (two lines in one cell) |
| Location | City or "Remote" |
| Rate | Only show if available; hide column entirely if >80% empty |
| Status | Pipeline state: Scored → Tailoring → Ready → Applied → Interview |
| Actions | Quick actions: View, Track, Approve (if ready) |

### 4.3 Hide empty data
If a field is genuinely unknown, omit it — don't show "Unknown" or "—". A missing rate is better communicated by absence than by showing a dash.

### 4.4 Score colour bands
Align to threshold from profile.yaml:
- Green (≥ threshold): auto-shortlisted, prominently displayed
- Amber (≥50% but < threshold): shown in "parked" section with muted styling
- Gray (<50%): hidden by default, accessible via "Show low-match jobs" toggle
- Never show 0% match jobs in the default view

---

## 5. Remove "Auto Apply"

### Problem
"Auto Apply" nav item contradicts the PRD non-goal that the system never auto-submits.

### Fix
Remove the "Auto Apply" nav link entirely. Remove the page if it exists. If there's backend functionality for auto-apply, remove or disable it. The human approval checkpoint is the core trust mechanism — any UI suggesting otherwise undermines it.

---

## 6. Dynamic Dashboard Subtitle

### Problem
Dashboard shows "Outside-IR35 UK contract roles" — hardcoded, not from profile.

### Fix
Read from profile.yaml and display dynamically:

```typescript
// Generate subtitle from profile
const roles = profile.search.target_roles.join(', ');
const locations = profile.search.locations.map(l => l.city).join(', ');
const subtitle = `${roles} — ${locations}`;
// e.g. "Delivery Lead, Product Owner — Newcastle, Remote UK"
```

If no profile, show nothing (the onboarding gate handles this).

---

## 7. Stale Data Handling

### Problem
All jobs show "about 1 month ago" with "New Today: 0". System appears dead.

### Fix

### 7.1 Add "last scraped" timestamp
Show per-source last scrape time in the agent status strip. If the most recent scrape is > 2x the configured interval, show a warning.

### 7.2 Archive stale jobs
Jobs older than 30 days should be auto-archived (moved to a separate "Archive" view, not shown on the main listing). Configurable via `profile.yaml`:
```yaml
preferences:
  archive_after_days: 30
```

### 7.3 Show relative time accurately
"about 1 month ago" for everything suggests the timestamp is broken or all jobs were loaded in a single batch. Ensure the `posted` field is parsed correctly from each job board. If the board doesn't provide a date, use the `discovered_at` timestamp instead and label it "Discovered: 23 May" rather than "Posted: 1 month ago".

---

## 8. Onboarding Wizard Redesign

### Problem
The onboarding wizard exists at `/onboarding` but either isn't enforced or isn't creating a valid profile.

### Fix

5-step wizard (reduced from 8 — combine related steps):

**Step 1: About you**
- Name, professional title, years of experience
- Short summary (optional — auto-generated from other fields if left blank)

**Step 2: What you're looking for**
- Target roles (tag input, with common suggestions)
- Locations (searchable, with "Remote" toggle)
- Contract type: permanent / contract / freelance / any
- Compensation range + currency + rate type (daily/hourly/annual)

**Step 3: Your strengths**
- Primary skills (tag input with autocomplete from common skills database)
- Certifications (tag input)
- Preferred domains (multi-select from common list + free text)
- Key achievements / proof points (guided STAR input: what happened + metric + where)

**Step 4: AI and job boards**
- LLM provider selection (radio cards: Anthropic, OpenAI, Google, Ollama, Azure)
- Model selection (filtered list based on provider, with sensible defaults)
- API key input (masked, stored in .env, never in YAML)
- Connection test button ("Test connection" → shows success/failure)
- Job board toggles (on/off per board, with keyword overrides)

**Step 5: Review and launch**
- Summary of all settings in a clean card layout
- "Edit" links next to each section to go back
- "Start JobPilot" button — writes profile.yaml, triggers first scrape, redirects to dashboard

Each step has:
- Progress dots (● ○ ○ ○ ○)
- Back / Next navigation
- Validation before proceeding (name, at least one role, at least one location, valid API key)
- "Skip for now" option on optional fields (achievements, certifications)

---

## 9. Match Score Display Rules

### Problem
Scores are shown without a profile to match against. Colour coding is inconsistent.

### Fix

### 9.1 No scores without a profile
If profile completeness < 80%, do not display match scores. Show "Set up profile to see match scores" in place of the score badge.

### 9.2 Three-band colour system
Define three CSS utility classes:

```css
/* Score bands — threshold comes from profile (default 75%) */
.score-high {
  background: var(--color-background-success);
  color: var(--color-text-success);
}
.score-mid {
  background: var(--color-background-warning);
  color: var(--color-text-warning);
}
.score-low {
  background: var(--color-background-tertiary);
  color: var(--color-text-tertiary);
}
```

Apply based on the user's threshold:
```typescript
function getScoreBand(score: number, threshold: number): string {
  if (score >= threshold) return 'score-high';
  if (score >= 50) return 'score-mid';
  return 'score-low';
}
```

### 9.3 Score tooltip
On hover/click of the score badge, show the 4-dimension breakdown:
```
Skill match:      92%  ████████████░░
Experience match: 88%  ███████████░░░
Rate match:       85%  ██████████░░░░
Location match:   100% ██████████████
───────────────────────────────────
Overall:          91%
```

---

## 10. Job Card Redesign

### Problem
Current table rows show too many columns with missing data. Type shows "unknown/unknown" badges.

### Fix

Replace the table with a card-based list. Each job is a horizontal card:

```
┌──────────────────────────────────────────────────────────────┐
│ [91%]  Senior Delivery Lead                                  │
│        Accenture · Newcastle · £650/day · Outside IR35       │
│        Discovered 2h ago from Reed                   [Track] │
└──────────────────────────────────────────────────────────────┘
```

Rules:
- Score badge on the left (colour-coded)
- Title as main text (14px, weight 500)
- Metadata on a second line (13px, secondary colour)
- Only show fields that have data — no "Unknown", no "—"
- Source shown in metadata (not as a separate column)
- "Track" button to add to pipeline
- If already in pipeline, show status pill instead of Track button

---

## 11. Error States

Add explicit error handling for common failure modes:

### 11.1 API key invalid
After onboarding or on first agent run:
```
⚠ Your Anthropic API key returned an authentication error.
  [Update API key in settings]  [View error details]
```

### 11.2 Scraper failure
If a job board scraper fails 3 times:
```
⚠ Reed scraper has failed 3 times. Last error: "Rate limited (429)".
  The next retry is in 4 hours. Other boards are working normally.
```

### 11.3 No matching jobs
If scored jobs are all below threshold:
```
No high-match jobs discovered today. This could mean:
• Your target roles are very specific (that's fine — quality over quantity)
• Try broadening your search terms in Settings > Job boards
• 142 jobs were discovered but none scored above your 75% threshold
```

---

## 12. Locale Pack System (Geography Abstraction)

### Problem
The current codebase has UK-specific assumptions hardcoded across multiple layers: job board names (Reed, ContractorUK), compensation format (daily rate in GBP), legal fields (IR35 status), and scraper implementations. This makes the system unusable outside the UK without code changes.

### Solution: locale packs

A locale pack is a YAML file in `locales/` that defines everything that varies by geography. The user selects their locale during onboarding, and the pack pre-fills all geography-specific defaults. The user can override anything — the pack is just the starting point.

**Each locale pack defines:**
1. **Job boards** — which scrapers are available, which are enabled by default, board-specific search parameters
2. **Compensation schema** — rate types (daily/annual/CTC/LPA), currency, display format
3. **Legal/regulatory fields** — IR35 (UK), H-1B/visa (US), notice period (India), Brutto/Netto (Germany)
4. **Scoring defaults** — weight adjustments for the local market
5. **Onboarding defaults** — contract type, remote preference, scrape interval

**File locations:**
```
locales/
├── uk.yaml              # United Kingdom
├── in.yaml              # India
├── us.yaml              # United States
├── de.yaml              # Germany
├── _template.yaml       # Template for community contributors
└── README.md            # How to create a new locale pack
```

### 12.1 Profile.yaml changes

Add `locale` field at the top of profile.yaml:

```yaml
# ─── Locale ──────────────────────────────────────────────────
locale: "uk"                        # Loaded from locales/uk.yaml
                                    # Sets defaults for boards, compensation, legal fields
                                    # User can override any value below
```

The `locale` field is selected in onboarding step 2. When set, the profile loader merges the locale pack defaults with any user overrides.

### 12.2 Compensation schema changes

Replace the current hardcoded compensation section with a locale-aware structure:

```yaml
# Current (UK-centric):
compensation:
  min_rate: 550
  max_rate: 700
  rate_type: "daily"
  currency: "GBP"
  ir35_preference: "outside"

# New (locale-aware):
compensation:
  min_rate: 550                     # Interpreted based on rate_type from locale
  max_rate: 700
  rate_type: "daily"                # Default from locale pack (daily for UK, annual_ctc for India)
  currency: "GBP"                   # Default from locale pack
  legal_preferences:                # Dynamic — fields come from locale pack
    ir35_status: "outside"          # Only present if locale defines ir35_status
```

For India, the same section would be:
```yaml
compensation:
  min_rate: 2000000                 # ₹20 LPA
  max_rate: 3500000                 # ₹35 LPA
  rate_type: "annual_ctc"
  currency: "INR"
  legal_preferences:
    notice_period: "60 days"
```

### 12.3 Onboarding wizard changes

**Step 2 ("What are you looking for?")** — add locale selection as the first sub-step:

1. User selects country/region from a dropdown or map
2. System loads the locale pack
3. Compensation fields auto-adapt (daily rate → CTC, GBP → INR)
4. Job board list updates to show locale-appropriate boards
5. Legal fields update (IR35 disappears, notice period appears)

**Visual:** Show a locale card during selection:
```
┌──────────────────────────────────┐
│  🇮🇳 India                       │
│                                  │
│  Boards: Naukri, LinkedIn,       │
│          foundit, Indeed India    │
│  Compensation: CTC (₹ LPA)      │
│  Key fields: Notice period,      │
│              Employment type     │
│                                  │
│  [Select]                        │
└──────────────────────────────────┘
```

### 12.4 Scraper registry changes

Current: scrapers are registered as a hardcoded list.
New: scrapers register themselves with a `locale_id` tag, and the ScraperFactory filters by the user's locale.

```python
# backend/app/scrapers/registry.py
SCRAPER_REGISTRY = {
    # UK scrapers
    "reed": {"class": ReedScraper, "locales": ["uk"]},
    "contractoruk": {"class": ContractorUKScraper, "locales": ["uk"]},
    "cwjobs": {"class": CWJobsScraper, "locales": ["uk"]},
    
    # India scrapers
    "naukri": {"class": NaukriScraper, "locales": ["in"]},
    "foundit": {"class": FounditScraper, "locales": ["in"]},
    
    # Multi-locale scrapers
    "linkedin": {"class": LinkedInScraper, "locales": ["uk", "us", "in", "de"]},
    "indeed": {"class": IndeedScraper, "locales": ["uk", "us", "in", "de"]},
}

def get_scrapers_for_locale(locale_id: str) -> list:
    return [s for s in SCRAPER_REGISTRY.values() if locale_id in s["locales"]]
```

### 12.5 Scoring prompt changes

The scoring prompt must be locale-aware. Legal fields from the locale pack are injected into the prompt dynamically:

```python
# UK scoring prompt includes:
# "4. ir35_match: Does the IR35 status match the candidate's preference?"

# India scoring prompt includes:
# "4. notice_period_match: Is the notice period compatible with the candidate's availability?"

# The dimension name and description come from the locale pack, not hardcoded.
```

### 12.6 Dashboard and UI changes

- **Compensation display:** Format based on locale — `£650/day` (UK), `₹25 LPA` (India), `$180K/yr` (US)
- **Legal field columns:** Only show fields defined in the active locale pack. No more "IR35: Unknown" when the user is in India.
- **Job card metadata:** Dynamically composed from locale pack `display_in_job_card: true` fields
- **Score tooltip:** Fourth dimension label adapts — "IR35 match" (UK) vs "Notice period match" (India)

---

## 13. Implementation Order for Claude Code

Execute these prompts in sequence:

| # | Prompt summary | Files affected |
|---|---------------|----------------|
| 1 | Create locale pack YAML structure. Create 4 starter packs (UK, India, US, Germany) + template. Create locale loader service that merges pack defaults with profile overrides. | `locales/*.yaml`, `backend/app/services/locale_service.py` |
| 2 | Update profile.yaml Pydantic schema to include `locale` field. Update profile_loader to merge locale pack defaults. Update compensation schema to be locale-aware (dynamic rate_types, legal_preferences). | `backend/app/schemas/profile.py`, `backend/app/agents/tools/profile_loader.py` |
| 3 | Update scraper registry to tag scrapers by locale. Update ScraperFactory to filter by user's locale. | `backend/app/scrapers/registry.py`, `backend/app/scrapers/factory.py` |
| 4 | Add profile status API endpoint that returns `profileExists`, `isComplete`, `completionPercent`, `missingFields`. | `backend/app/routers/profile.py` |
| 5 | Add onboarding gate to dashboard — redirect to `/onboarding` if profile is missing/incomplete. Add empty-state component for fresh profiles with no jobs yet. | `frontend/app/page.tsx`, `frontend/components/EmptyState.tsx` |
| 6 | Redesign navigation: replace 11-item nav with 5-item task-oriented nav. Add pending approvals count badge (polling). Move removed items to `/settings` page. Remove "Auto Apply" entirely. | `frontend/components/Navigation.tsx`, `frontend/app/settings/page.tsx` |
| 7 | Redesign dashboard page: agent status strip, action cards (review/prep/new matches), top matches list (above-threshold only), pipeline bar. Dynamic subtitle from profile. Locale-aware compensation display. | `frontend/app/page.tsx`, `frontend/components/dashboard/*` |
| 8 | Redesign job listing: card-based layout, hide columns with missing data, default filter to above-threshold, three-band score colours, score tooltip with 4-dimension breakdown. Dynamic legal field columns from locale pack. | `frontend/app/jobs/page.tsx`, `frontend/components/JobCard.tsx`, `frontend/components/ScoreBadge.tsx` |
| 9 | Redesign onboarding wizard: 5 steps with locale selection in step 2 that dynamically adapts compensation fields, job boards, and legal fields. API key test. Progress dots. "Start JobPilot" flow. | `frontend/app/onboarding/page.tsx`, `frontend/components/onboarding/*` |
| 10 | Update scorer agent to inject locale-aware legal field dimension into scoring prompt. | `backend/app/agents/scorer_agent.py` |
| 11 | Add error states: API key errors, scraper failures, no matching jobs empty state, stale data warnings. | `frontend/components/ErrorBanner.tsx`, `frontend/components/EmptyState.tsx` |
| 12 | Add job archiving: auto-archive jobs older than `preferences.archive_after_days`, separate archive view accessible from Jobs page. | `backend/app/services/archive_service.py`, `frontend/app/jobs/page.tsx` |
