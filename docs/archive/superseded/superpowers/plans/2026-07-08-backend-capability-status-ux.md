---
title: Backend Capability Status UX Implementation Plan
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

# Backend Capability Status UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PR2 from the capability profile spec: a read-only backend capability status API plus a Settings -> System panel that shows profile state and terminal enable commands.

**Architecture:** Backend status is derived from product env/profile truth first, then defensive `importlib.util.find_spec()` checks for optional packages. Frontend consumes one read-only endpoint and renders status rows without any browser mutation or Docker rebuild action.

**Tech Stack:** FastAPI, pytest/httpx, Next.js React client component, Vitest/Testing Library, Docker Compose overrides.

## Global Constraints

- Endpoint is `GET /api/system/capabilities`.
- Env/profile truth uses `HATCH_BACKEND_PROFILE`, `HATCH_BROWSER_AUTOMATION_ENABLED`, `HATCH_LOCAL_EMBEDDINGS_ENABLED`, `HATCH_PERCEPTION_ENABLED`, and `HATCH_ADVANCED_COACH_ENABLED`.
- Missing env vars infer `backend_profile=core` and optional capabilities disabled.
- Optional dependency checks use `importlib.util.find_spec()` only.
- Browser UI is read-only; no Docker rebuild button and no host profile mutation endpoint.
- Settings -> System must show exact `hatch capabilities enable ...` commands for missing optional capabilities.

---

### Task 1: Backend Capability API

**Files:**
- Create: `backend/app/services/backend_capabilities.py`
- Create: `backend/app/routers/system.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routers/test_system_capabilities.py`

**Interfaces:**
- Produces: `build_backend_capability_status() -> dict[str, Any]`
- Produces: `GET /api/system/capabilities` returning `backend_profile`, `ai_mode`, and `capabilities`.

- [ ] **Step 1: Write failing tests for core, browser, local, full, and module checks.**
- [ ] **Step 2: Run `cd backend && pytest -q tests/test_routers/test_system_capabilities.py --no-cov` and confirm endpoint/service failures.**
- [ ] **Step 3: Implement capability status helper and router.**
- [ ] **Step 4: Register the router in `backend/app/main.py`.**
- [ ] **Step 5: Re-run the targeted backend tests and confirm pass.**

### Task 2: Settings System Read-Only Panel

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/settings/system/page.tsx`
- Test: `frontend/src/__tests__/components/SettingsSystemCapabilities.test.tsx`

**Interfaces:**
- Consumes: `getSystemCapabilities()`.
- Renders: `Backend capabilities` panel with profile, AI mode, status rows, and enable commands.

- [ ] **Step 1: Write failing UI tests for status render, missing commands, and soft failure.**
- [ ] **Step 2: Run `cd frontend && npx vitest run src/__tests__/components/SettingsSystemCapabilities.test.tsx` and confirm failure.**
- [ ] **Step 3: Add API types/client wrapper and panel state loading.**
- [ ] **Step 4: Render compact status rows and advisory command blocks using existing tokens.**
- [ ] **Step 5: Re-run the targeted frontend tests and confirm pass.**

### Task 3: Compose Env Contract and Verification

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.easy.yml`
- Modify: `docker-compose.browser.yml`
- Modify: `docker-compose.local-embeddings.yml`
- Modify: `docker-compose.full.yml`

**Interfaces:**
- Compose env exposes PR2 status truth to the backend container.

- [ ] **Step 1: Add the PR2 env names to core/easy and optional override files.**
- [ ] **Step 2: Run compose config validation for core, browser, local-embeddings, and full combinations.**
- [ ] **Step 3: Run backend/frontend targeted tests, compile/type checks, and diff checks.**
- [ ] **Step 4: Commit, push, and open PR.**
