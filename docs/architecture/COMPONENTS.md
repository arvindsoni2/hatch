---
title: Hatch Components
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

# Components

This document maps the major current components to their responsibilities, dependencies, and relevant code paths.

## Product Surfaces

- Frontend
  Responsibility: render the single-user Hatch workspace and protected routes.
  Inputs: backend APIs, local app-lock state, route taxonomy.
  Outputs: review actions, configuration changes, workflow navigation.
  Dependencies: `frontend/src/app`, `frontend/src/components`.

- Onboarding
  Responsibility: create the local workspace profile and AI/setup intent.
  Inputs: locale packs, password policy, setup endpoints.
  Outputs: saved profile, backend experience intent, optional AI settings.
  Dependencies: `frontend/src/app/onboarding/page.tsx`, `backend/app/routers/setup.py`.

- Today
  Responsibility: prioritize current work and review queues.
  Inputs: pending approvals, ready applications, watched companies, agent metrics.
  Outputs: review actions and workflow navigation.
  Dependencies: `frontend/src/app/today/*`, `backend/app/routers/agents.py`, `applications.py`.

- Pipeline
  Responsibility: show discovered and scored roles moving toward review.
  Inputs: job discovery and shortlist state.
  Outputs: review and preparation actions.
  Dependencies: `frontend/src/app/stream/*`, jobs and agent APIs.

- Applications
  Responsibility: track roles across the application lifecycle.
  Inputs: application records and package state.
  Outputs: manual moves, notes, preparation, interview status.
  Dependencies: `frontend/src/app/tracker/*`, `backend/app/routers/applications.py`.

- CV Studio
  Responsibility: review grounding, templates, quality checks, and generated documents.
  Inputs: application context, profile evidence, templates, AI runtime.
  Outputs: generated CV and cover-letter packages.
  Dependencies: `frontend/src/app/tailor/*`, `backend/app/routers/tailor.py`, `documents.py`.

- Interview Prep
  Responsibility: create practice sessions, research company context, and reuse saved answers.
  Inputs: application context, question bank, AI runtime.
  Outputs: sessions, reports, reusable answers, calendar exports.
  Dependencies: `frontend/src/app/prep/*`, `frontend/src/app/coach/*`, `backend/app/routers/coach.py`, `question_bank.py`.

- Question Bank
  Responsibility: save, tag, and reuse interview answers.
  Inputs: manual CRUD and save-from-interview workflows.
  Outputs: reusable answer records.
  Dependencies: `frontend/src/app/prep/question-bank/*`, `backend/app/routers/question_bank.py`.

- Company Watchlist
  Responsibility: monitor target employers from the Applications workflow.
  Inputs: saved companies and manual scans.
  Outputs: watchlist scans and discovered roles tied to watched companies.
  Dependencies: `frontend/src/app/tracker/watched-companies/*`, `backend/app/routers/company_watchlist.py`.

## Agents And Runtime Services

- Scout
  Responsibility: discover jobs from sources and import URLs.
  Failure behavior: reduced source coverage when optional browser capability is absent or source parsing fails.

- Scorer
  Responsibility: evaluate fit, thresholds, and ranking signals.
  Failure behavior: can degrade to non-embedding or non-AI paths depending on runtime capability.

- Tailor
  Responsibility: generate and store document packages.
  Failure behavior: returns actionable failure when provider or local model is unavailable.

- Coach
  Responsibility: interview research, questions, answers, follow-up practice, and optional advanced coaching paths.
  Failure behavior: capability-gated features may be unavailable while core prep flows remain usable.

- Local AI services
  Responsibility: primary and triage inference via `llama.cpp`.
  Dependencies: `docker-compose.local-ai.yml`, `${HATCH_HOME}/models` or `./data/models`.

- Cloud-provider integration
  Responsibility: use configured provider secrets from host-managed config.
  Dependencies: setup intent, `scripts/hatch_cli.py`, backend setup and runtime services.

- Persistence layer
  Responsibility: SQLite application state plus local files.
  Dependencies: `./data` and `${HATCH_HOME}` mounts.

- Host CLI and installers
  Responsibility: install, update, probe, manage models, manage secrets, and control capability profiles.
  Dependencies: `install.sh`, `install.ps1`, `install-hatch.cmd`, `scripts/hatch_cli.py`, `hatch`.
