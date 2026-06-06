---
name: company-research
description: Research a target company and synthesise key intelligence for interview preparation and cover letter personalisation
when_to_use: When an application moves to interview stage or when the cover letter needs company-specific personalisation
wraps: CompanyResearchService
---

# Company Research

Produce structured intelligence about the target company: mission, recent news, culture signals, business challenges, and competitive position.

## Process

1. **Scrape public sources** — company website, recent press releases, LinkedIn, Glassdoor summary.
2. **Synthesise with Claude** — produce a structured brief: overview, recent developments, culture cues, likely interview themes, and 2–3 smart questions to ask the interviewer.
3. **Personalisation hooks** — extract 1–2 specific facts to weave into the cover letter ("I noticed your recent expansion into…").

## Output fields

- `overview` — 2–3 sentence company summary.
- `recent_news` — up to 3 notable recent developments.
- `culture_signals` — values, working style, team descriptors from public sources.
- `interview_themes` — likely focus areas based on the role and company stage.
- `questions_to_ask` — 2–3 thoughtful questions for the candidate to ask.

## Constraints

- Flag when scraped content is thin or stale (> 6 months old).
- Do not fabricate news or product details; mark gaps explicitly.
- Keep the brief under 500 words total — this is prep material, not a report.
