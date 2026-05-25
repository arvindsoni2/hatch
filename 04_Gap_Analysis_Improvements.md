# JobPilot v2 — Gap Analysis & Improvement Spec

**Author:** Arvind Soni
**Date:** 23 May 2026
**Status:** Ready for Claude Code implementation
**Companion to:** `03_UX_Redesign_Spec.md`

---

## Executive Summary

After testing the latest build against the PRD and design documents, three categories of issues have been identified:

1. **No observability** — the user has zero visibility into what agents decided, why they scored a job the way they did, or what actions were taken. The system is a black box.
2. **Resume tailoring module is missing** — the highest-value module from v1 (Tailor) has not been integrated. No ATS scoring, no CV adaptation, no cover letter generation, no feedback rubric.
3. **Bugs** — the pipeline shows "1 Active" with an "Untitled Application" when no real application exists. Count inconsistency between dashboard ("110 discovered") and pipeline ("1 active").

Additionally, market research against tools like Teal, Jobscan, and AIApply reveals several features that would significantly differentiate JobPilot as an open-source alternative.

---

## Part 1 — Observability (your feedback #1)

### The Problem

The home dashboard says "All agents running" and "You're all caught up" — but provides no evidence of what happened. The user cannot answer any of these questions:

- What did the Scout agent do on its last run? How many jobs did it find? How many were duplicates?
- Why was a specific job scored 65% and not 85%? What did the LLM actually say?
- When the Tailor agent generates a CV, what changes did it make? What did it optimise for?
- Did any agent fail? What error did it hit? Did it retry?

This is the classic agentic UX anti-pattern described in recent research: agents that do work invisibly create a trust deficit. Users need **receipts** — evidence of what the agent did and why.

### The Solution: Activity Log + Decision Receipts

Three layers of observability, from surface to deep:

#### Layer 1: Activity Timeline (dashboard surface)

A chronological feed of significant agent actions, visible on the Home page below the action cards. Not every event — only the ones that matter to the user.

```
┌─ Activity ─────────────────────────────────────────────────────┐
│                                                                 │
│  ● 10:02  Scout discovered 8 new jobs from Reed                │
│           (3 duplicates filtered, 5 new)                       │
│                                                                │
│  ● 10:03  Scorer evaluated 5 jobs                              │
│           2 scored above 75%: "Senior DL — Accenture" (91%),   │
│           "PO — DWP Digital" (86%)                             │
│           3 parked below threshold                              │
│                                                                │
│  ● 10:05  Tailor generated CV + cover letter                   │
│           "Senior DL — Accenture" — ATS score: 87%             │
│           → Moved to approval queue                            │
│                                                                │
│  ● 10:06  Tailor generated CV + cover letter                   │
│           "PO — DWP Digital" — ATS score: 82%                  │
│           → Moved to approval queue                            │
│                                                                │
│  ○ 06:02  Scout discovered 12 new jobs from LinkedIn           │
│           (7 duplicates filtered, 5 new)                       │
│                                                                │
│  ▲ 06:01  Scout failed on ContractorUK                         │
│           Error: Rate limited (429). Retry in 4h.              │
│                                                                │
│  [View full log →]                                             │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Backend: `GET /api/v2/activity?limit=20&since=24h` — returns recent activity events
- Events are generated from the existing `agent_events` table, summarised into human-readable messages
- Frontend: `ActivityTimeline` component on the Home page
- Auto-refresh via SSE or 30-second polling

#### Layer 2: Decision Receipts (per-job detail)

When a user clicks on a job, they see the full decision trail — every agent action that touched this job, with the LLM's reasoning visible.

```
┌─ Decision trail: Senior Delivery Lead — Accenture ────────────┐
│                                                                │
│  Step 1: Discovered                                    10:02   │
│  Source: Reed · Discovered by Scout agent                      │
│  Dedup check: no existing match found                          │
│                                                                │
│  Step 2: Triage pre-filter                             10:02   │
│  Model: claude-haiku-4-5-20251001                              │
│  Result: PASS — "Senior delivery role, UK, matches profile"    │
│  Tokens: 180 in / 42 out · Cost: £0.0001                      │
│                                                                │
│  Step 3: Scored                                        10:03   │
│  Model: claude-sonnet-4-20250514                               │
│  ┌──────────────────────────────────────────────────┐          │
│  │ Skill match:      92%  ████████████████████░░░░  │          │
│  │ Experience match: 88%  ██████████████████░░░░░░  │          │
│  │ Rate match:       85%  █████████████████░░░░░░░  │          │
│  │ Location match:  100%  ████████████████████████  │          │
│  │ ──────────────────────────────────────────────── │          │
│  │ Overall:          91%                             │          │
│  └──────────────────────────────────────────────────┘          │
│  Reasoning: "Strong match. Agile delivery and stakeholder      │
│  management are core requirements. Public sector SC             │
│  eligibility is a plus. Rate within target. Newcastle."         │
│  Tokens: 1,840 in / 186 out · Cost: £0.003                    │
│                                                                │
│  Step 4: Shortlisted                                   10:03   │
│  Score 91% ≥ threshold 75% → auto-shortlisted                 │
│                                                                │
│  Step 5: CV tailored                                   10:05   │
│  Model: claude-sonnet-4-20250514                               │
│  Changes made:                                                 │
│  • Moved "Agile delivery" to top of skills section             │
│  • Emphasised stakeholder management in Northern Powergrid     │
│  • Added "SC eligible" to header                               │
│  • Mapped proof points: £500K savings (NPg), 40% TTM (Natoora)│
│  ATS score: 87% (keywords: 14/16 matched)                     │
│  Tokens: 3,200 in / 1,800 out · Cost: £0.010                  │
│  [View tailored CV] [View cover letter]                        │
│                                                                │
│  Step 6: Awaiting approval                             10:06   │
│  → In your approval queue                                      │
│                                                                │
│  Total cost for this job: £0.013                               │
└────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Backend: `GET /api/v2/jobs/{id}/decisions` — returns all agent_events for this job_id, enriched with LLM call metadata
- Store LLM reasoning and token counts in the `agent_events.payload` JSON
- Frontend: `DecisionTrail` component on the Job Detail page
- Collapsible sections — summary visible by default, full LLM response expandable

#### Layer 3: System Log (settings/developer)

For debugging and power users. The full event log with filters, search, and JSON payloads. This already partially exists in the `agent_events` table — it just needs a frontend.

```
Settings > System > Event Log

[Filter: all agents ▼] [Status: all ▼] [Date range: last 7 days ▼] [Search...]

| Timestamp | Agent | Event | Status | Cost |
|-----------|-------|-------|--------|------|
| 10:06:12 | tailor | cv_tailored | completed | £0.010 |
| 10:05:44 | tailor | cv_tailored | completed | £0.010 |
| 10:03:15 | scorer | job_scored | completed | £0.003 |
| 10:03:14 | scorer | job_scored | completed | £0.003 |
| 10:02:58 | scorer | job_scored | completed | £0.003 |
| 10:02:30 | scout | job_discovered (×5) | completed | — |
| 10:02:05 | scout | scrape_complete | completed | — |

[Export CSV]  [Clear old events]
```

**Implementation:**
- Backend: `GET /api/v2/events` already specified in the design doc — add pagination, filtering, and cost aggregation
- Frontend: `EventLog` component in `Settings > System`
- Include cost tracking: aggregate LLM API cost per agent, per day, per month

### Data Model Additions

Add to the `agent_events.payload` JSON for LLM-calling agents:

```json
{
  "model_used": "claude-sonnet-4-20250514",
  "tokens_in": 1840,
  "tokens_out": 186,
  "cost_estimate": 0.003,
  "reasoning": "Strong match. Agile delivery and stakeholder...",
  "duration_ms": 2340
}
```

Add a new table for cost tracking:

```sql
CREATE TABLE cost_tracking (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    event_id TEXT REFERENCES agent_events(id),
    model TEXT NOT NULL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_estimate REAL,
    currency TEXT DEFAULT 'GBP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_cost_agent_date ON cost_tracking(agent_name, created_at);
```

---

## Part 2 — Resume Tailoring Module (your feedback #2)

### The Problem

The Tailor module — the highest-value feature from the PRD — is not visible in the current build. There is no way to:
- Upload or manage a master CV
- See how a CV was adapted for a specific job
- Get ATS compatibility feedback
- Understand what keywords were matched/missed
- Edit the tailored output before approving

This is the core differentiator for JobPilot. Market research shows ATS compliance is now critical — 90%+ of companies use ATS filtering, and tools like Jobscan and Teal charge £30-50/month for exactly this capability. JobPilot should provide it for free.

### The Solution: Full Tailor Integration

#### 2.1 Master CV Management

**Page:** `/settings/resume` (new)

```
┌─ Your master CV ───────────────────────────────────────────────┐
│                                                                │
│  [Upload CV]  Drag & drop .docx or .pdf                       │
│                                                                │
│  Last uploaded: master_cv_arvind_2026.docx (23 May 2026)      │
│                                                                │
│  Parsed sections:                                              │
│  ✓ Contact information                                         │
│  ✓ Professional summary                                        │
│  ✓ Work experience (6 roles detected)                          │
│  ✓ Skills (24 skills extracted)                                │
│  ✓ Certifications (5 found)                                   │
│  ✓ Education                                                   │
│  ⚠ Proof points: 4 configured in profile.yaml                 │
│                                                                │
│  [View parsed JSON]  [Edit proof points]  [Re-upload]         │
└────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Backend: CV upload endpoint that parses .docx/.pdf into structured JSON
- Use existing v1 CV parsing logic if available
- Store parsed JSON at `data/master_cv.json`
- Validate against proof points in profile.yaml

#### 2.2 ATS Scoring & Feedback Rubric

When the Tailor agent generates a CV for a shortlisted job, it produces a detailed feedback rubric — not just a score number.

**Rubric structure:**

```
┌─ ATS Analysis: Senior Delivery Lead — Accenture ──────────────┐
│                                                                │
│  Overall ATS Score: 87%                                        │
│  ████████████████████████████░░░░                              │
│                                                                │
│  ┌─ Keywords ─────────────────────────────────────────┐        │
│  │ ✓ Matched (14):                                    │        │
│  │   agile delivery, stakeholder management, public   │        │
│  │   sector, programme management, risk management,   │        │
│  │   PRINCE2, PMP, cloud migration, digital           │        │
│  │   transformation, team leadership, budgets,        │        │
│  │   governance, CI/CD, DevOps                        │        │
│  │                                                    │        │
│  │ ✗ Missing (2):                                     │        │
│  │   SAFe (mentioned 3x in JD — consider adding)      │        │
│  │   Jira Align (mentioned once — lower priority)     │        │
│  └────────────────────────────────────────────────────┘        │
│                                                                │
│  ┌─ Structure ────────────────────────────────────────┐        │
│  │ ✓ Reverse chronological order                      │        │
│  │ ✓ Quantified achievements (4 proof points used)    │        │
│  │ ✓ Clean formatting (no tables, no columns)         │        │
│  │ ✓ Contact info at top                              │        │
│  │ ⚠ Summary could be more role-specific              │        │
│  └────────────────────────────────────────────────────┘        │
│                                                                │
│  ┌─ What was changed ────────────────────────────────┐         │
│  │ • Reordered skills: "Agile delivery" moved to #1  │         │
│  │ • Added "SC eligible" to professional summary     │         │
│  │ • Expanded NPg Smart Timesheet: emphasised        │         │
│  │   stakeholder management angle                    │         │
│  │ • Cover letter: opened with Accenture's Newcastle │         │
│  │   hub expansion (from company research)           │         │
│  └────────────────────────────────────────────────────┘        │
│                                                                │
│  ┌─ Recommendations ─────────────────────────────────┐         │
│  │ 1. Add SAFe experience if you have it — it's      │         │
│  │    mentioned 3 times in the JD                    │         │
│  │ 2. Consider adding a "Key Achievements" section   │         │
│  │    above work history for this senior role         │         │
│  └────────────────────────────────────────────────────┘        │
│                                                                │
│  [Download .docx]  [Edit & regenerate]  [Approve]              │
└────────────────────────────────────────────────────────────────┘
```

#### 2.3 Inline Editing Before Approval

The approval page must allow the user to edit the tailored CV and cover letter before approving. Not just "approve/reject" — but "approve with edits."

```
┌─ Edit tailored CV ─────────────────────────────────────────────┐
│                                                                │
│  [Rich text editor with the tailored CV content]               │
│                                                                │
│  Highlighted changes:                                          │
│  🟢 Added text (green background)                              │
│  🔴 Removed text (red strikethrough)                           │
│  🟡 Reordered sections (yellow border)                         │
│                                                                │
│  [Show diff vs master]  [Revert to master]                     │
│  [Re-score ATS]  [Save & approve]                              │
└────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Frontend: Diff view comparing master CV vs tailored CV
- "Re-score ATS" button runs the scorer again after edits
- Changes saved back to the application record
- Generated .docx available for download

#### 2.4 Cover Letter with Company Intelligence

The cover letter should reference company research — not just be a generic template.

```
Elements the cover letter should include:
1. Opening: reference a specific company initiative (from Coach's company research)
2. Body: map 2-3 proof points to the JD's top requirements
3. Closing: mention location alignment and availability
4. Tone: match the JD's formality level (formal for public sector, conversational for startups)
```

---

## Part 3 — Bugs (your feedback #3)

### Bug 1: Pipeline shows "1 Active" with "Untitled Application"

**Symptom:** Pipeline page shows 1 Active application in the "Discovered" column, labelled "Untitled Application / Today / Normal" — but no actual job was tracked.

**Root cause hypotheses:**
1. A seed record or migration created a placeholder application
2. The scraper created an application record without a linked job
3. The application count query doesn't filter for valid (non-null title) records

**Fix:**
- Add validation: applications must have a non-null `job_id` and the linked job must have a non-null `title`
- Clean up orphaned records: `DELETE FROM applications WHERE job_id IS NULL OR NOT EXISTS (SELECT 1 FROM job_postings WHERE id = applications.job_id)`
- Add a migration to enforce the foreign key constraint
- The "Active" count should only include applications with status NOT IN ('archived', 'rejected', 'withdrawn')

### Bug 2: Count inconsistency

**Symptom:** Home dashboard shows "110 discovered" in the pipeline bar. Pipeline page shows "1 Active, 0 Applied, 0.0% Response Rate". These reference different data — "discovered" counts all jobs, "active" counts applications. The labelling is confusing.

**Fix:**
- Dashboard pipeline bar: label should say "110 jobs discovered" (jobs, not applications)
- Pipeline page: "Active" should only count applications that were deliberately created (by the Tailor agent or manually), not raw discovered jobs
- Add a clear distinction in the UI: "Jobs" (what Scout finds) vs "Applications" (what the user is actively pursuing)

---

## Part 4 — Missing Features (from market research)

Based on research into what Teal, Jobscan, AIApply, and Resume Worded offer, here are features that would make JobPilot a compelling open-source alternative:

### 4.1 Daily Digest Email/Notification

**Priority: Should**

A daily summary sent at a configurable time:

```
Subject: JobPilot Daily: 3 new matches, 1 approval pending

Good morning,

🔍 Yesterday's activity:
• Scout discovered 17 new jobs across Reed and LinkedIn
• 3 scored above your 75% threshold
• 1 CV has been tailored and is awaiting your review

📋 Pending actions:
• 1 application needs approval: "Senior DL — Accenture" (91% match)
• 1 follow-up is overdue: "PO — DWP Digital" (applied 12 days ago)

📊 Pipeline: 142 discovered → 23 shortlisted → 12 applied → 3 interviewing

Open JobPilot: http://localhost:3000
```

**Implementation:**
- Backend: Scheduled job (APScheduler, configurable time)
- Template: HTML email via `emails` library or Jinja2 template
- Configuration in profile.yaml: `notifications.daily_digest: true`, `notifications.digest_time: "08:00"`
- Support: Email (SMTP config) or desktop notification via Web Push API

### 4.2 Follow-Up Reminder Engine

**Priority: Must (in PRD but not implemented)**

Track application age and remind the user to follow up:

```
┌─ Follow-ups due ──────────────────────────────────────────────┐
│                                                                │
│  ⏰ Overdue (2):                                               │
│  • PO — DWP Digital: applied 12 days ago (follow-up was due   │
│    at day 10). [Draft follow-up email] [Snooze 5 days]        │
│  • SA — NTT DATA: applied 15 days ago (2nd follow-up due).    │
│    [Draft follow-up email] [Mark as no response]              │
│                                                                │
│  📅 Upcoming (1):                                               │
│  • DL — Accenture: applied 3 days ago. Follow-up in 7 days.  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Backend: Query applications by status and age against `profile.yaml → preferences.follow_up_days: [5, 10, 15]`
- Frontend: Section on Home dashboard (below action cards) and in Pipeline page
- Optional: Coach agent auto-drafts follow-up email text

### 4.3 Application Analytics

**Priority: Should**

Track outcomes over time to help the user refine their approach:

```
This month:
• Applied: 12 · Response rate: 25% · Interview rate: 8%
• Avg ATS score of successful applications: 89%
• Top matching skill: "Agile delivery" (appeared in 10/12 shortlisted JDs)
• Weakest dimension: Rate match (avg 72% — consider adjusting range)

Insights:
• Applications with ATS score > 85% had 3x higher response rate
• Jobs from Reed had better match scores than LinkedIn (avg 82% vs 71%)
```

### 4.4 Job Description Comparison

**Priority: Could**

When a user is deciding between multiple shortlisted jobs, show a side-by-side comparison:

```
┌─ Compare ──────────────────────────────────────────────────────┐
│                                                                │
│  │ Accenture DL      │ DWP PO            │ NTT DATA SA       │
│  ├────────────────────┼───────────────────┼───────────────────│
│  │ Score: 91%         │ Score: 86%        │ Score: 79%        │
│  │ £650/day           │ £600/day          │ £700/day          │
│  │ Newcastle          │ Remote UK         │ London (hybrid)   │
│  │ Outside IR35       │ Outside IR35      │ Outside IR35      │
│  │ ATS: 87%           │ ATS: 82%         │ ATS: 78%          │
│  ├────────────────────┼───────────────────┼───────────────────│
│  │ Unique reqs:       │ Unique reqs:      │ Unique reqs:      │
│  │ SAFe, Jira Align   │ GDS standards     │ TOGAF, ArchiMate  │
│  └────────────────────┴───────────────────┴───────────────────┘
│                                                                │
│  Common requirements across all 3:                             │
│  Agile delivery, stakeholder management, cloud, public sector  │
└────────────────────────────────────────────────────────────────┘
```

### 4.5 Ghost Job Detection

**Priority: Could**

Flag jobs that are likely stale/ghost listings:

```
Signals:
• Job has been reposted 3+ times in 6 months
• Same JD text appears on multiple boards with different dates
• Company has had this role open for > 60 days
• Glassdoor/LinkedIn shows no recent hires for this role

Display: Orange "⚠ Possible ghost listing" badge on job card
```

### 4.6 Salary/Rate Benchmarking

**Priority: Could**

Compare the offered rate against market data:

```
£650/day for Delivery Lead in Newcastle:
• ITJobsWatch median: £625/day
• Your rate range: £550-700/day
• This offer is in the 72nd percentile

[Adjust your rate range in settings]
```

---

## Part 5 — Implementation Order for Claude Code

These are ordered by user impact, with bugs first:

| # | Category | Prompt summary | Priority |
|---|----------|---------------|----------|
| 1 | **Bug** | Fix orphaned "Untitled Application" — add validation, clean up orphan records, enforce FK constraint, fix active count query. | Critical |
| 2 | **Bug** | Fix count inconsistency — differentiate "jobs discovered" from "applications active" in both dashboard and pipeline. Add clear labels. | Critical |
| 3 | **Observability** | Add LLM call metadata (model, tokens, cost, reasoning) to agent_events payload. Create cost_tracking table. Update all agents to log this data. | High |
| 4 | **Observability** | Create Activity Timeline component on Home page — human-readable feed of recent agent actions. Backend endpoint + SSE. | High |
| 5 | **Observability** | Create Decision Trail component on Job Detail page — full audit trail of every agent action for a specific job, with score breakdown and LLM reasoning. | High |
| 6 | **Observability** | Create Event Log page in Settings > System — filterable, searchable, with cost aggregation and CSV export. | Medium |
| 7 | **Tailor** | Create Master CV upload and management page at /settings/resume. Parse .docx/.pdf to structured JSON. Validate against profile proof points. | High |
| 8 | **Tailor** | Integrate Tailor agent into the pipeline — auto-generate tailored CV + cover letter for shortlisted jobs. Save .docx files linked to application. | High |
| 9 | **Tailor** | Create ATS scoring rubric — keyword match analysis, structure checks, change summary, recommendations. Display on approval detail page. | High |
| 10 | **Tailor** | Add inline editing to approval page — diff view, re-score button, save & approve flow. | Medium |
| 11 | **Feature** | Follow-up reminder engine — query by application age, display on dashboard, configurable schedule. | Medium |
| 12 | **Feature** | Daily digest notification — scheduled summary email with activity, pending actions, pipeline stats. | Low |
| 13 | **Feature** | Application analytics — response rates, ATS score correlation, skill frequency, dimension insights. | Low |
