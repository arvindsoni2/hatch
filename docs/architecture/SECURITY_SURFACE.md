---
title: Hatch Security Surface
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main
last_verified: 2026-11-27
supersedes: []
superseded_by: []
---

# Hatch Security Surface

This document inventories the HTTP, browser, outbound-request, subprocess, file, parser, template and model-prompt surface read from the code at baseline `4a9e5cfe5f3e0108400b673227976fb9f6a9f623`. It records where controls live and which security-refresh task owns the intended control. It does not contain user data, secrets or runtime observations.

## Trust model

Hatch is a single-user, self-hosted workspace. The intended deployment binds its services to loopback. The threat model considers:

- a malicious web page open in the user's browser;
- a malicious job advert or careers page;
- a malicious uploaded CV, document or audio recording;
- a compromised package or download;
- another device on the local network if a service is bound too widely.

Out of scope: an attacker who already has the user's operating-system account, and multi-tenant hosting.

Trust boundaries: browser ↔ Next.js ↔ FastAPI; FastAPI ↔ SQLite and workspace files; FastAPI ↔ local or cloud model endpoints; FastAPI ↔ job boards, company sites and SMTP; host CLI ↔ host-managed secrets. The intended controls are tracked as H1 (outbound fetch), H2 (browser-to-localhost boundary), H3 (files and paths), H4 (untrusted documents and content), H5 (browser code), H6 (AI, privacy, logs and policy), D4 (CI audits) and X1–X2 (scripts).

## How to read the route table

The table is generated from the FastAPI app with `backend/scripts/security_surface.py`; `backend/tests/test_tools/test_security_surface_contract.py` fails when an app route has no row or a row has no app route. At this baseline the app has 249 `APIRoute` objects and three non-API `Route` objects (`/openapi.json`, `/docs`, `/docs/oauth2-redirect`), giving 255 method/path rows. There are no `Mount` or `WebSocketRoute` entries at this baseline.

- **Auth dependency**: every `/api/*` request passes through the optional bearer-token middleware when `HATCH_AUTH_TOKEN` is set. `/api/health` and `GET /api/app-lock/status` are exempt; non-API docs routes do not use the bearer middleware.
- **App lock before/after setup**: when `HATCH_APP_LOCK_ENABLED` is true (the default), protected routes require a server-side session cookie. "Before setup" means no app-lock password is configured; "after setup" means one is. `Public*` marks the onboarding resume upload, which is allowed without a session only while no password source exists and onboarding is incomplete.
- The bootstrap setup paths stay public after setup by design of the current allow-list; H2 owns the intended session boundary for them.
- **Body/upload limit**: `None` means no route-level limit is declared; the deployment's server or proxy may impose one. Upload limits shown are checked in the route or service.
- **Effect**: direct effects read from the route handler and the services it calls. `DB` is SQLite; `file` is a workspace or configuration file; `outbound` is an HTTP or SMTP request; `model call` is a local or cloud model request; `subprocess` is a child process; `template` is server-side rendering.

| Method | Path | Router module | Auth dependency | App lock before setup | App lock after setup | Body/upload limit | Effect |
|---|---|---|---|---|---|---|---|
| GET | `/openapi.json` | `fastapi.applications` | None (non-API) | Locked | Session | None | Read |
| HEAD | `/openapi.json` | `fastapi.applications` | None (non-API) | Locked | Session | None | Read |
| GET | `/docs` | `fastapi.applications` | None (non-API) | Locked | Session | None | Template |
| HEAD | `/docs` | `fastapi.applications` | None (non-API) | Locked | Session | None | Template |
| GET | `/docs/oauth2-redirect` | `fastapi.applications` | None (non-API) | Locked | Session | None | Template |
| HEAD | `/docs/oauth2-redirect` | `fastapi.applications` | None (non-API) | Locked | Session | None | Template |
| GET | `/api/health` | `app.routers.jobs` | None (exempt) | Public | Public | None | File read |
| POST | `/api/jobs/import-url/preview` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | Outbound; DB read |
| POST | `/api/jobs/import-url/save` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/jobs/stats` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/jobs/filter-counts` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/jobs/` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/jobs` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/jobs/{job_id}` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/jobs/scrape` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | Outbound; DB write |
| POST | `/api/jobs/scrape/{source}` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | Outbound; DB write |
| PATCH | `/api/jobs/{job_id}` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/jobs/{job_id}` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/jobs/rescore-unscored` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read/write |
| POST | `/api/jobs/archive/run` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read/write |
| POST | `/api/jobs/{job_id}/unarchive` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/jobs/{job_id}/decisions` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/jobs/{job_id}/approve` | `app.routers.jobs` | Bearer (optional) | Locked | Session | None | DB write; async model call; file write; subprocess |
| GET | `/api/v2/jobs/{job_id}/gap-analysis` | `app.routers.gap_analysis` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/applications/` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/applications` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/applications/kanban` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/applications/next-actions` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/applications/export` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/applications/from-job/{job_id}` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications/` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications/manual` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/applications/follow-up-reminders` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read; file read |
| GET | `/api/applications/{app_id}` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read |
| PATCH | `/api/applications/{app_id}` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/applications/{app_id}/status` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications/{app_id}/notes` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications/{app_id}/prepare` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write; model call; file write; subprocess |
| GET | `/api/applications/{app_id}/package` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB read; file read |
| POST | `/api/applications/{app_id}/mark-applied` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications/{app_id}/reject` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/applications/{app_id}/revert` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/applications/{app_id}` | `app.routers.applications` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/interviews/` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/interviews/upcoming` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB read |
| PATCH | `/api/interviews/{interview_id}` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/interviews/{interview_id}/complete` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/interviews/{interview_id}` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/interviews/follow-ups` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/interviews/follow-ups/{follow_up_id}/complete` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/interviews/follow-ups/overdue` | `app.routers.interviews` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/v2/interviews/{interview_id}/ical` | `app.routers.interviews_ical` | Bearer (optional) | Locked | Session | None | DB read; template |
| GET | `/api/analytics/dashboard` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/funnel` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/trends` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/sources` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/score-distribution` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/costs/monthly` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/costs/daily` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/agent-performance` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/search-quality` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/skill-gaps` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/ab-testing` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/ats-correlation` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/analytics/skill-frequency` | `app.routers.analytics` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/tailor/templates` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | File read |
| GET | `/api/tailor/review/{application_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/tailor/quality/document/{document_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/tailor/templates/recommend` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | File read |
| POST | `/api/tailor/quality/precheck` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | File read |
| PUT | `/api/tailor/templates/default` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | File write |
| POST | `/api/tailor/analyse/{job_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB write; async model call |
| POST | `/api/tailor/analyse` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB write; async model call; outbound |
| POST | `/api/tailor/generate-cv` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB write; async model call; file write; subprocess |
| POST | `/api/tailor/generate-cl` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB write; async model call; file write; subprocess |
| POST | `/api/tailor/generate` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB write; async model call; file write; subprocess |
| GET | `/api/tailor/generate/stream` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | Model call; file write; subprocess |
| POST | `/api/tailor/regenerate-section` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/tailor/history/{application_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/tailor/document/{document_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/tailor/document/{document_id}/download` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read; file read |
| GET | `/api/tailor/ats-score/{document_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/tailor/ats-optimise/{document_id}` | `app.routers.tailor` | Bearer (optional) | Locked | Session | None | DB read; model call |
| POST | `/api/coach/sessions/{session_id}/commands` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB read/write; queues model work |
| GET | `/api/coach/sessions/{session_id}/live` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/sessions/{session_id}/report` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/conversational-progress` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/sessions/{session_id}/exports` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB read; template |
| POST | `/api/coach/sessions/{session_id}/deletion-commands` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB write; queued file delete |
| GET | `/api/coach/sessions/{session_id}/diagnostics` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/sessions/{session_id}/attempts/{attempt_id}/audio` | `app.routers.coach_conversation` | Bearer (optional) | Locked | Session | 50 MB (configurable) | File write; DB write |
| GET | `/api/coach/readiness/coverage/overview` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read; background model call |
| GET | `/api/coach/readiness/coverage` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read; background model call |
| PUT | `/api/coach/readiness/coverage/{application_id}/overrides` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read/write; background model call |
| GET | `/api/coach/readiness/rounds/{round_id}/debrief` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| PUT | `/api/coach/readiness/rounds/{round_id}/debrief` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/readiness/rounds/{round_id}/debrief/skip` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/readiness/rounds/{round_id}/debrief/extract` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read; model call |
| POST | `/api/coach/readiness/rounds/{round_id}/debrief/proposals/{proposal_id}/accept` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/coach/readiness/next-actions` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/readiness/display-timezone` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/readiness/model-tiers` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | File read |
| GET | `/api/coach/readiness/patterns` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/readiness/patterns/{fingerprint}/why` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/readiness/patterns/{fingerprint}/dismiss` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/coach/readiness/patterns/{fingerprint}/dismiss` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/coach/readiness/focus-areas` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/readiness/focus-areas` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/coach/readiness/focus-areas/{area_id}` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/coach/readiness/plans` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/readiness/plans` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/readiness/plans/{plan_id}/start` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/coach/readiness/plans/{plan_id}/items/{item_id}` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/readiness/patterns/{fingerprint}/tips` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read/write; outbound model call |
| GET | `/api/coach/readiness/operations/{operation_id}` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/readiness/rounds/{round_id}/brief` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read/write; outbound model call |
| POST | `/api/coach/readiness/rounds/{round_id}/brief/tips` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read/write; outbound model call |
| GET | `/api/coach/readiness/memory` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB read |
| DELETE | `/api/coach/readiness/memory/{kind}` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/coach/readiness/memory` | `app.routers.coach_readiness` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/research` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | Outbound; model call; DB write |
| GET | `/api/coach/research/{company_name}` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/sessions` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB write; async model call |
| GET | `/api/coach/sessions` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/sessions/{session_id}` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| DELETE | `/api/coach/sessions/{session_id}` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/sessions/{session_id}/retry` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB write; async model call |
| GET | `/api/coach/sessions/{session_id}/next-question` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/sessions/{session_id}/skip` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/coach/sessions/{session_id}/submit-answer` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB write; async model call |
| POST | `/api/coach/sessions/{session_id}/submit-audio` | `app.routers.coach` | Bearer (optional) | Locked | Session | 50 MB | File write; DB write; async model call |
| POST | `/api/coach/sessions/{session_id}/end` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB write; async model call |
| GET | `/api/coach/sessions/{session_id}/report` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/progress/{application_id}` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/coach/sessions/{session_id}/plan-followup` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read/write |
| GET | `/api/coach/progress/{session_id}/trend` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/coach/capabilities` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | File read |
| POST | `/api/coach/sessions/{session_id}/tts-question` | `app.routers.coach` | Bearer (optional) | Locked | Session | None | DB read; subprocess |
| GET | `/api/digest/preview` | `app.routers.digest` | Bearer (optional) | Locked | Session | None | DB read; template |
| POST | `/api/digest/send` | `app.routers.digest` | Bearer (optional) | Locked | Session | None | DB read; template; outbound (SMTP) |
| GET | `/api/digest/status` | `app.routers.digest` | Bearer (optional) | Locked | Session | None | Config read |
| PATCH | `/api/digest/settings` | `app.routers.digest` | Bearer (optional) | Locked | Session | None | File read/write |
| GET | `/api/emails/pending` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/emails/stats` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/emails/history` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/emails/{email_id}` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB read |
| PATCH | `/api/emails/{email_id}` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB write; template |
| POST | `/api/emails/generate/{application_id}` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB write; async model call |
| POST | `/api/emails/{email_id}/send` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB write; outbound (SMTP) or mailto |
| POST | `/api/emails/{email_id}/skip` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/emails/{email_id}/regenerate` | `app.routers.emails` | Bearer (optional) | Locked | Session | None | DB write; model call |
| GET | `/api/ghost/stats` | `app.routers.ghost` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/ghost/flagged` | `app.routers.ghost` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/ghost/job/{job_id}` | `app.routers.ghost` | Bearer (optional) | Locked | Session | None | DB read/write |
| POST | `/api/ghost/analyse/{job_id}` | `app.routers.ghost` | Bearer (optional) | Locked | Session | None | DB write; background DB write |
| POST | `/api/ghost/analyse-all` | `app.routers.ghost` | Bearer (optional) | Locked | Session | None | DB read; background DB write |
| POST | `/api/ghost/override/{job_id}` | `app.routers.ghost` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/stories` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/stories` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/stories/suggest` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/stories/match` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/stories/{story_id}` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB read |
| PUT | `/api/stories/{story_id}` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/stories/{story_id}` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/stories/{story_id}/rate` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/stories/{story_id}/record-use` | `app.routers.stories` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/agents/status` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/agents/{name}/status` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/agents/{name}/trigger` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | Background model/outbound; DB write |
| POST | `/api/agents/{name}/pause` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | Memory write |
| POST | `/api/agents/{name}/resume` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | Memory write |
| GET | `/api/agents/approvals/pending` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/agents/approvals/{application_id}` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/agents/approvals/{application_id}/approve` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/agents/approvals/{application_id}/reject` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/agents/approvals/{application_id}/notes` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/agents/dashboard/pipeline` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/agents/rate-limit-status` | `app.routers.agents` | Bearer (optional) | Locked | Session | None | Memory read |
| GET | `/api/events/activity` | `app.routers.events` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/events/costs` | `app.routers.events` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/events` | `app.routers.events` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/events/{event_id}` | `app.routers.events` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/events/{event_id}/retry` | `app.routers.events` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/v2/profile` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | File read |
| GET | `/api/v2/profile/validated` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | File read |
| PUT | `/api/v2/profile` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | File write; DB write |
| POST | `/api/v2/profile/validate` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | None |
| GET | `/api/v2/profile/status` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | File read |
| GET | `/api/v2/profile/summary` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | File read |
| POST | `/api/v2/profile/test-connection` | `app.routers.profile` | Bearer (optional) | Locked | Session | None | Outbound |
| GET | `/api/v2/locales` | `app.routers.locales` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/v2/locales/{locale_id}` | `app.routers.locales` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/v2/locales/{locale_id}/boards` | `app.routers.locales` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/v2/locales/{locale_id}/legal-fields` | `app.routers.locales` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/v2/locales/{locale_id}/onboarding-defaults` | `app.routers.locales` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/resume/status` | `app.routers.resume` | Bearer (optional) | Locked | Session | None | File read |
| POST | `/api/resume/upload` | `app.routers.resume` | Bearer (optional) | Public* | Session | 10 MB | File write; parser; model call |
| POST | `/api/resume/confirm` | `app.routers.resume` | Bearer (optional) | Locked | Session | None | File write |
| GET | `/api/resume/json` | `app.routers.resume` | Bearer (optional) | Locked | Session | None | File read |
| PUT | `/api/v2/settings/env` | `app.routers.settings` | Bearer (optional) | Locked | Session | None | None (410) |
| GET | `/api/v2/settings/env/status` | `app.routers.settings` | Bearer (optional) | Locked | Session | None | File read |
| GET | `/api/v2/settings/ollama-models` | `app.routers.settings` | Bearer (optional) | Locked | Session | None | Outbound |
| PUT | `/api/v2/settings/ollama-model` | `app.routers.settings` | Bearer (optional) | Locked | Session | None | File write |
| GET | `/api/system/capabilities` | `app.routers.system` | Bearer (optional) | Locked | Session | None | File read |
| GET | `/api/v2/scoring/insights` | `app.routers.scoring` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/v2/scoring/{job_id}` | `app.routers.scoring` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/async-jobs/{job_id}` | `app.routers.async_jobs` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/async-jobs` | `app.routers.async_jobs` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/debug/llm-traces` | `app.routers.debug` | Bearer (optional) | Locked | Session | None | Memory read |
| DELETE | `/api/debug/llm-traces` | `app.routers.debug` | Bearer (optional) | Locked | Session | None | Memory write |
| GET | `/api/debug/runtime-status` | `app.routers.debug` | Bearer (optional) | Locked | Session | None | Outbound |
| GET | `/api/outcome-learning/summary` | `app.routers.outcome_learning` | Bearer (optional) | Locked | Session | None | DB read |
| GET | `/api/outcome-learning/jobs/{job_id}` | `app.routers.outcome_learning` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/outcome-learning/recompute` | `app.routers.outcome_learning` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/outcome-learning/backfill` | `app.routers.outcome_learning` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/outcome-learning/reset` | `app.routers.outcome_learning` | Bearer (optional) | Locked | Session | None | DB write; file write |
| GET | `/api/app-lock/status` | `app.routers.app_lock` | None (exempt) | Public | Public | None | DB read |
| POST | `/api/app-lock/setup` | `app.routers.app_lock` | Bearer (optional) | Public | Public | None | DB write |
| POST | `/api/app-lock/unlock` | `app.routers.app_lock` | Bearer (optional) | Public | Public | None | DB write |
| POST | `/api/app-lock/lock` | `app.routers.app_lock` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/app-lock/change-password` | `app.routers.app_lock` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/setup/intent` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File write |
| POST | `/api/setup/onboarding/progress` | `app.routers.setup` | Bearer (optional) | Public | Public | None | DB write |
| POST | `/api/setup/onboarding/finalize` | `app.routers.setup` | Bearer (optional) | Locked | Session | None | DB write; file write |
| GET | `/api/setup/status` | `app.routers.setup` | Bearer (optional) | Public | Public | None | DB read |
| GET | `/api/setup/hardware` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| POST | `/api/setup/hardware` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/setup/models/catalog` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/setup/providers` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/setup/models/recommendations` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/setup/models/discovery` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read/write; outbound |
| POST | `/api/setup/ai-mode` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File write |
| POST | `/api/setup/experience` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File write |
| POST | `/api/setup/local-model-selection` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File write |
| POST | `/api/setup/cloud-provider` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File write |
| GET | `/api/setup/capabilities` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| POST | `/api/setup/provider/test` | `app.routers.setup` | Bearer (optional) | Public | Public | None | Outbound; file write |
| POST | `/api/setup/skip-ai` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File write |
| GET | `/api/setup/doctor` | `app.routers.setup` | Bearer (optional) | Public | Public | None | File read |
| GET | `/api/setup/reset/preview` | `app.routers.setup` | Bearer (optional) | Locked | Session | None | DB read; file read |
| POST | `/api/setup/reset/apply` | `app.routers.setup` | Bearer (optional) | Locked | Session | None | DB write; file delete/write |
| GET | `/api/watchlist/companies` | `app.routers.company_watchlist` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/watchlist/companies` | `app.routers.company_watchlist` | Bearer (optional) | Locked | Session | None | DB write |
| PATCH | `/api/watchlist/companies/{item_id}` | `app.routers.company_watchlist` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/watchlist/companies/{item_id}` | `app.routers.company_watchlist` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/watchlist/companies/{item_id}/scan` | `app.routers.company_watchlist` | Bearer (optional) | Locked | Session | None | DB write; outbound |
| POST | `/api/documents/{package_id}/export/pdf` | `app.routers.documents` | Bearer (optional) | Locked | Session | None | DB write; file read/write; subprocess |
| GET | `/api/documents/assets/{asset_id}` | `app.routers.documents` | Bearer (optional) | Locked | Session | None | DB read; file read |
| GET | `/api/question-bank` | `app.routers.question_bank` | Bearer (optional) | Locked | Session | None | DB read |
| POST | `/api/question-bank` | `app.routers.question_bank` | Bearer (optional) | Locked | Session | None | DB write |
| POST | `/api/question-bank/from-interview-answer` | `app.routers.question_bank` | Bearer (optional) | Locked | Session | None | DB write |
| GET | `/api/question-bank/{item_id}` | `app.routers.question_bank` | Bearer (optional) | Locked | Session | None | DB read |
| PATCH | `/api/question-bank/{item_id}` | `app.routers.question_bank` | Bearer (optional) | Locked | Session | None | DB write |
| DELETE | `/api/question-bank/{item_id}` | `app.routers.question_bank` | Bearer (optional) | Locked | Session | None | DB write |
## Frontend surface

| Location | Surface | Intended control |
|---|---|---|
| `frontend/src/middleware.ts:middleware` | Adds `Authorization: Bearer $HATCH_AUTH_TOKEN` to `/api/*` requests, except `OPTIONS` and `/api/health`; matcher is `/api/:path*`. | H2 trusted-host and origin checks; the token remains host-configured. |
| `frontend/next.config.js:rewrites` | Proxies `/api/:path*` to `${API_URL}/api/:path*` (default `http://backend:8000`). | H2 trusted-host and origin checks on the proxy and API. |
| `frontend/next.config.js:redirects` | Redirects legacy `/applications` to `/tracker` from `product-routes.json`. | Route mapping only; no security-relevant effect. |
| `frontend/next.config.js:headers` | Adds security headers and a report-only Content-Security-Policy to every route. | H5 enforced policy with a nonce or hash for the theme script. |
| `frontend/src/lib/api.ts:apiFetch` | Client calls use same-origin relative paths through the rewrite; server calls use `API_URL` directly. | H2 boundary; server callers use the cookie/token-aware helper. |
| `frontend/src/lib/server-api.ts:serverApiFetch` | Forwards cookies and the bearer token to `API_URL`; redirects to `/unlock` on 423. | H2 trusted-host and origin checks. |
| `frontend/src/lib/setup.ts`, `coachReadinessApi.ts`, `profileSettings.ts` | Same-origin fetch wrappers for setup, readiness and profile settings. | H2 boundary. |
| `frontend/src/components/coach/FaceCapture.tsx` | Loads MediaPipe tasks-vision from `cdn.jsdelivr.net` at runtime on a camera page. | H5 serve the asset from the app and remove the CDN from the policy. |

There are no Next.js route handlers under `frontend/src/app/**/route.*`; API traffic is handled by the rewrite above.

## Outbound requests

| Location | Purpose | Intended control |
|---|---|---|
| `backend/app/services/jd_analyser.py:_fetch_jd` | Fetches a job advert URL and extracts text. | H1 `services/public_fetch.py`: HTTP(S), global addresses, redirect re-validation, 5-redirect cap, 2 MB limit, content-type and timeouts. |
| `backend/app/services/job_url_importer.py:preview_url` | Fetches a pasted job URL with redirects disabled and validates the public address. | H1 `services/public_fetch.py`; keep the existing public-address check. |
| `backend/app/services/company_watchlist.py:scan_watchlist_item` | Fetches a company careers page and extracts roles. | H1 `services/public_fetch.py`. |
| `backend/app/services/company_researcher.py:research` | Fetches company pages for Coach research. | H1 `services/public_fetch.py`; H6 prompt/output validation. |
| `backend/app/scrapers/*.py` (`adzuna`, `bayt`, `contractoruk`, `cwjobs`, `gulftalent`, `indeed_india`, `irishjobs`, `itjobswatch`, `jobserve`, `jobs_ie`, `linkedin`, `naukri`, `naukrigulf`, `reed`) | Fetches fixed job-board pages and APIs. | H1 decide whether fixed hosts need the same redirect and size guard. |
| `backend/app/services/firecrawl_client.py` | Optional Firecrawl fetch for job pages. | H1 `services/public_fetch.py`. |
| `backend/app/services/model_discovery.py:discover_models` | Queries Hugging Face for model metadata. | H1 fixed-host request limits and timeouts. |
| `backend/app/services/provider_catalog.py:test_provider_connection` | Sends a provider test request. | H1 configured-provider allow-list; H6 redact errors. |
| `backend/app/services/coach_readiness/brief.py`, `coverage.py`, `debrief.py`, `explain.py` | Sends readiness prompts to the configured local or cloud model route. | H6 prompt/output validation; configured model addresses are outside the H1 user-URL guard. |
| `backend/app/services/digest_service.py:send` | Sends the digest through SMTP. | H6 outbound disclosure and error handling. |
| `backend/app/services/email_sender.py:send_smtp` | Sends a follow-up email through SMTP. | H6 outbound disclosure and error handling. |
| `backend/app/services/llm_client.py`, `backend/app/agents/tools/llm_factory.py` | Sends prompts to the configured provider or local model. | H6 prompt/output validation and privacy. |
| `backend/app/agents/tools/context_checker.py` | Reads llama.cpp context metadata. | Configured local endpoint; no H1 user-URL guard. |
| `backend/app/routers/debug.py:_probe_service` | Probes local llama.cpp health endpoints. | Configured local endpoint; H6 redact diagnostics. |
| `backend/app/routers/profile.py:_test_llamacpp_services` | Probes both local llama.cpp health endpoints. | Configured local endpoint; H6 redact errors. |
| `backend/app/routers/settings.py:list_ollama_models` | Queries the configured Ollama `/api/tags`. | Configured local endpoint; H6 fixed error code. |
| `frontend/src/components/coach/FaceCapture.tsx` | Browser loads MediaPipe from a public CDN. | H5 serve locally and enforce the policy. |

## Subprocess calls

| Location | Purpose | Intended control |
|---|---|---|
| `backend/app/services/docx_cv_builder.py:DocxCVBuilder.build` | Runs `node generate_cv_docx.js` to render a CV. | H3 validate the output path; H4 bound the input; H5/H6 no shell interpolation. |
| `backend/app/services/docx_cl_builder.py:DocxCLBuilder.build` | Runs `node generate_cl_docx.js` to render a cover letter. | H3 validate the output path; H4 bound the input. |
| `backend/app/services/pdf_export.py:convert_docx_to_pdf` | Runs `libreoffice`/`soffice` to convert a generated DOCX to PDF. | H3 path checks; H4 input bounds; fixed allow-listed binary. |
| `backend/app/services/tts_service.py:PiperTTSService.synthesise` | Runs the configured `piper` binary to synthesise question audio. | H3 path checks; H6 text and error handling. |

## File writes derived from request data

| Location | Purpose | Intended control |
|---|---|---|
| `backend/app/routers/resume.py:upload_resume` | Writes the uploaded PDF/DOCX to a temporary file and the extracted text to the resume store. | H3 path checks; H4 10 MB and parser limits. |
| `backend/app/routers/resume.py:confirm_cv` | Writes the reviewed master CV JSON and metadata. | H3 path checks; H4 structure validation. |
| `backend/app/routers/coach.py:submit_audio` | Writes the uploaded recording under `data/recordings/<session_id>`. | H3 UUID/path checks; H4 50 MB and audio validation. |
| `backend/app/routers/coach_conversation.py:upload_attempt_audio` | Streams the browser recording into `HATCH_COACH_MEDIA_ROOT` through `coach_media_storage`. | H3 no-follow directory handles; H4 size and hash checks. |
| `backend/app/services/docx_cv_builder.py`, `docx_cl_builder.py` | Writes generated DOCX files under `data/generated`. | H3 resolved-path checks. |
| `backend/app/services/tailor_service.py` | Appends runtime metadata to a generated DOCX zip. | H3 resolved-path checks; H4 zip bounds. |
| `backend/app/services/pdf_export.py:export_package_pdf` | Writes the converted PDF next to the source document. | H3 resolved-path checks. |
| `backend/app/routers/digest.py:update_digest_settings` | Updates the `DIGEST_*` lines in `data/api_keys.env`. | H3 file path; H6 keep secret values out of the response. |
| `backend/app/routers/profile.py:update_profile` | Writes `data/profile.yaml`. | H3 path checks; H6 no secret values. |
| `backend/app/routers/settings.py:set_ollama_model` | Writes the selected Ollama model into `data/profile.yaml`. | H3 path checks. |
| `backend/app/routers/setup.py` (`patch_intent`, `set_ai_mode`, `set_experience`, `select_local_models`, `select_cloud_provider`, `skip_ai`, `finalize_onboarding`) | Writes setup intent and onboarding/profile files. | H3 path checks; H6 no secret values. |
| `backend/app/routers/outcome_learning.py:reset` | Writes the outcome-learning start time into `data/profile.yaml`. | H3 path checks. |
| `backend/app/services/setup_reset.py:apply_reset` | Deletes or copies workspace files during setup reset. | H3 resolved-path checks; H6 confirmation handling. |
| `backend/app/services/coach_media_storage.py` | Creates, renames and deletes Coach media files. | H3 no-follow directory handles; H4 size/hash checks. |
| `backend/app/services/coach_privacy.py`, `coach_privacy_queue.py`, `coach_retention.py` | Deletes Coach-owned data and writes deletion receipts. | H3 path checks; H6 deletion evidence. |

## Archive, XML, PDF and DOCX parsers

| Location | Purpose | Intended control |
|---|---|---|
| `backend/app/routers/resume.py:_extract_text_from_docx` | Reads an uploaded DOCX with `python-docx`. | H4 shared size, ratio and entry-count limits. |
| `backend/app/routers/resume.py:_extract_text_from_pdf` | Reads an uploaded PDF with `pypdf`. | H4 page, time and memory limits. |
| `backend/app/services/docx_quality_parser.py` | Reads `word/document.xml` with `zipfile` and `ElementTree`. | H4 shared archive limits; XML parser safe defaults. |
| `backend/app/services/tailor_service.py` | Reads and appends DOCX zip entries. | H4 shared archive limits. |
| `backend/app/services/coach_session_plan.py` | Reads DOCX session-plan sources with `zipfile` and `python-docx`. | H4 shared archive limits. |
| `backend/app/runtime_bindings/migration/cv_tailor.py` | Reads and appends DOCX zip entries in the runtime path. | H4 shared archive limits. |
| `backend/app/services/company_researcher.py`, `jd_analyser.py` | Parses fetched HTML with BeautifulSoup and `lxml`. | H4 parser limits; H1 fetch bounds. |
| `backend/app/scrapers/*.py` | Parses job-board HTML with BeautifulSoup and `lxml`. | H4 parser limits; H1 fetch bounds. |
| `backend/app/services/pdf_export.py` | Converts DOCX to PDF with an allow-listed local binary. | H4 input bounds; fixed binary. |

## Template renderers

| Location | Purpose | Intended control |
|---|---|---|
| `backend/app/prompts/__init__.py:render_prompt` | Renders Jinja2 model prompts with autoescape disabled. | H6 output validation; prompts are not HTML. |
| `backend/app/services/digest_service.py` | Renders `daily_digest.html` with Jinja2 autoescape for HTML. | H4 escaping; H6 output validation. |
| `backend/app/services/email_generator.py` | Renders follow-up email HTML and plain text with Jinja2 autoescape disabled. | H4 escape HTML, subject and header values; H6 output validation. |
| `backend/app/services/coach_report_export.py:render_report_export` | Renders JSON and Markdown report exports. | H6 keep audio and filesystem paths out of exports. |
| `backend/app/services/docx_cv_builder.py`, `docx_cl_builder.py` | Renders DOCX through Node templates. | H3 output path; H4 input bounds. |
| `backend/app/services/tailor_service.py` | Appends runtime metadata to the DOCX package. | H3 path checks; H4 zip bounds. |

## Model prompts containing third-party text

| Location | Third-party text | Intended control |
|---|---|---|
| `backend/app/services/jd_analyser.py` | Job advert text fetched from a URL. | H6 output validation; H1 fetch bounds. |
| `backend/app/services/job_classifier.py` | Job advert title and description. | H6 output validation. |
| `backend/app/services/cv_parser.py` | Uploaded CV text. | H6 output validation; H4 parser bounds. |
| `backend/app/services/cv_tailor.py` | Job description and CV evidence. | H6 output validation. |
| `backend/app/services/cl_generator.py` | Job description and CV evidence. | H6 output validation. |
| `backend/app/services/ats_optimiser.py` | Job description and CV text. | H6 output validation. |
| `backend/app/services/company_researcher.py` | Fetched company and careers-page text. | H6 output validation; H1 fetch bounds. |
| `backend/app/services/question_generator.py` | Job description, CV and company context. | H6 output validation. |
| `backend/app/services/answer_evaluator.py` | Interview answer transcript and question. | H6 output validation. |
| `backend/app/services/feedback_generator.py` | Session transcript. | H6 output validation. |
| `backend/app/services/model_answer_gen.py` | Job description and question. | H6 output validation. |
| `backend/app/services/coach_coaching.py` | Transcript, evidence and coaching context. | H6 output validation. |
| `backend/app/services/coach_conversational_evaluator.py` | Transcript and selected evidence. | H6 output validation. |
| `backend/app/services/coach_evidence_grounder.py` | CV and transcript evidence. | H6 output validation. |
| `backend/app/services/coach_attempt_pipeline.py` | Attempt transcript and evaluation context. | H6 output validation. |
| `backend/app/services/technical_drills.py` | Job description and drill context. | H6 output validation. |
| `backend/app/services/coach_readiness/brief.py`, `coverage.py`, `debrief.py`, `explain.py` | Job, company, round and debrief text. | H6 output validation. |
| `backend/app/services/email_generator.py` | Job, application and interview text. | H6 output validation; H4 escaping. |
| `backend/app/runtime_bindings/migration/scoring.py` | Job advert and CV evidence. | H6 output validation. |
| `backend/app/agents/tools/scoring_contract.py` | Job advert and profile evidence. | H6 output validation. |

## Secret locations

Names and paths only; values are never read or printed.

| Location | Secret |
|---|---|
| `backend/app/config.py` | `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`, `REED_API_KEY`, `ADZUNA_APP_KEY`, `SMTP_PASS`, `SERPAPI_KEY`, `HATCH_AUTH_TOKEN`, `HATCH_APP_PASSWORD`. |
| `data/api_keys.env` | Host-managed provider keys loaded into the process environment; file mode 0600 when written by the host CLI. |
| `${HATCH_CONFIG_DIR}` (default `/hatch-home/config`) | Setup intent, provider test evidence and model-discovery cache. |
| `data/profile.yaml` | User profile and model selection; no provider keys are accepted through the browser. |
| Host environment | `HATCH_APP_PASSWORD`, `HATCH_AUTH_TOKEN`, `SMTP_PASS`, provider and scraper keys. |

Sensitive user-data paths (not secrets): `data/master_cv.json`, `data/generated/`, `data/recordings/`, `HATCH_COACH_MEDIA_ROOT` (default `data/coach-media`), and `data/profile.yaml`.

## CodeQL alerts

All 26 open alerts at the baseline, with a disposition. Dismissal is the owner's action.

| Alert | Rule | File | Disposition |
|---|---|---|---|
| 15 | `py/full-ssrf` | `backend/app/services/jd_analyser.py` | Fix in H1. |
| 3 | `py/incomplete-url-substring-sanitization` | `backend/app/services/assisted_apply.py` | Fix in H6. |
| 4 | `py/incomplete-url-substring-sanitization` | `backend/app/services/assisted_apply.py` | Fix in H6. |
| 14 | `py/incomplete-url-substring-sanitization` | `backend/app/routers/resume.py` | False positive: the match is text inside a CV, not a URL host check. |
| 19 | `py/path-injection` | `backend/app/services/docx_cv_builder.py` | Fix in H3. |
| 20 | `py/path-injection` | `backend/app/services/docx_cv_builder.py` | Fix in H3. |
| 21 | `py/path-injection` | `backend/app/services/docx_cv_builder.py` | Fix in H3. |
| 31 | `py/path-injection` | `backend/app/routers/coach.py` | Fix in H3. |
| 32 | `py/path-injection` | `backend/app/routers/coach.py` | Fix in H3. |
| 33 | `py/path-injection` | `backend/app/routers/coach.py` | Fix in H3. |
| 34 | `py/path-injection` | `backend/app/routers/coach.py` | Fix in H3. |
| 35 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: paths use server-generated identifiers and no-follow directory file descriptors. |
| 36 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 37 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 38 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 39 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 40 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 41 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 42 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 43 | `py/path-injection` | `backend/app/services/coach_media_storage.py` | False positive: same no-follow directory-handle pattern. |
| 44 | `py/path-injection` | `backend/app/services/tailor_service.py` | Fix in H3. |
| 7 | `py/stack-trace-exposure` | `backend/app/routers/settings.py` | Fix in H6. |
| 12 | `actions/missing-workflow-permissions` | `.github/workflows/ci.yml` | Fix in D4. |
| 25 | `actions/missing-workflow-permissions` | `.github/workflows/ci.yml` | Fix in D4. |
| 27 | `actions/missing-workflow-permissions` | `.github/workflows/ci.yml` | Fix in D4. |
| 28 | `actions/missing-workflow-permissions` | `.github/workflows/ci.yml` | Fix in D4. |

## Maintenance

Refresh the generated columns with:

```text
cd backend
python -m scripts.security_surface
```

Paste the output over the route table, then run `python -m pytest -q --no-cov tests/test_tools/test_security_surface_contract.py` and `python scripts/check_docs.py`.
