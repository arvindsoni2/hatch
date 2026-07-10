---
title: Outcome Learning Reconnaissance
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# Outcome Learning Reconnaissance

Date: 2026-06-15

## Repository baseline

- Branch: `main`
- Baseline commit: `cca53a1 feat(tracker): add guided application workflow`
- Alembic head: `j5k6l7m8n9o0`
- Backend: FastAPI, async SQLAlchemy, SQLite, Pydantic v2, Alembic
- Frontend: Next.js 14 App Router, React 18, TypeScript, Vitest, Playwright
- OpenCode is not installed in the current environment, so Codex is executing the bounded tasks directly.

## Verified integration points

- Application lifecycle: `ApplicationService.update_status()` and the generic application PATCH route.
- Interview creation: `POST /api/interviews/` currently writes through `InterviewRepository`.
- Profile settings: raw profile CRUD through `/api/v2/profile`.
- Job listing: `JobRepository.list_with_filters()` performs bulk score enrichment.
- Stream: client component loads jobs through `fetchJobs()`.
- Analytics: server component performs independent API requests in parallel.
- Coach video: MediaPipe runs in the browser and submits numeric summaries with audio.

## Plan reconciliations

- Fit scores already use the required `0.0..1.0` unit.
- Outcome learning defaults to enabled; Stream remains sorted by newest by default.
- Confidence is low below effective sample size 20, medium from 20 through 49, and high from 50 when raw resolved count is at least 75.
- Disabling learning clears and hides cached opportunity scores; re-enabling triggers recomputation.
- Variant copy describes recent applications, not statistically comparable applications.
- Coach & Privacy controls and presence-feedback wiring are included.
- No multimodal LLM is introduced; browser-derived metrics remain numeric inputs.

## Safety constraints

- No automatic application submission.
- No protected or inferred personal characteristics.
- No company, recruiter, free-text notes, rejection text, CV text, or cover-letter text in learning signals.
- No LLM or embedding call in opportunity-score calculation.
