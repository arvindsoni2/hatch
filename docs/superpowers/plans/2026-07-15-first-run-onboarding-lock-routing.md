# First-Run Onboarding and App-Lock Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send new workspaces to onboarding by default and allow the optional CV upload before the final password step without weakening protection for configured or completed workspaces.

**Architecture:** The root server page and `AppLockGate` both derive first-run routing from authoritative lock status and prioritize `/onboarding` before protected product rendering can redirect to `/unlock`. `AppLockMiddleware` keeps resume upload protected by default and grants a narrow method/path exception only after database-backed checks prove the app lock is unconfigured and onboarding is incomplete.

**Tech Stack:** Next.js 15 App Router, React 19, TanStack Query, Vitest/Testing Library, FastAPI 0.136, Starlette middleware, SQLAlchemy async sessions, pytest/httpx.

## Global Constraints

- Password creation remains the final actionable onboarding screen.
- `POST /api/resume/upload` must never become statically public.
- Bootstrap upload permission requires `configured_source == "none"` and onboarding status other than `complete`.
- Missing/invalid state and database errors must never grant bootstrap permission.
- Existing reset scripts, password policy, onboarding fields, and resume parsing remain unchanged.

---

### Task 1: Conditional bootstrap authorization for resume upload

**Files:**
- Modify: `backend/tests/test_middleware/test_app_lock_gate.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `AppLockService.configured_source() -> str`, `OnboardingService.status() -> OnboardingState`, `request.method`, and `request.url.path`.
- Produces: `AppLockMiddleware._is_onboarding_resume_upload(request) -> bool` and middleware behavior that calls the resume route only for the allowed first-run state.

- [x] **Step 1: Add failing middleware tests**

Add tests that send a valid PDF upload through a patched deterministic parser and assert `200` for an unconfigured/incomplete workspace, while completed and configured workspaces receive `423` without a session. Force bootstrap-state lookup to fail and assert that it also returns `423`.

```python
@pytest.mark.asyncio
async def test_unconfigured_incomplete_onboarding_can_reach_resume_upload(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.pdf", b"synthetic pdf", "application/pdf")},
    )

    assert response.status_code == 200
```

Insert `OnboardingState(id=1, status="complete")` for the completed case and `AppLockConfig(id=1, password_hash="hash")` for the configured case, committing before the request. Each must assert status `423` and `{"detail": "Hatch is locked."}`.

- [x] **Step 2: Run the focused backend tests and verify RED**

Run:

```bash
cd backend && python -m pytest tests/test_middleware/test_app_lock_gate.py -q --no-cov
```

Expected: the unconfigured/incomplete upload test fails because the current middleware returns `423` instead of downstream `200`; existing protected-route behavior remains green.

- [x] **Step 3: Implement the minimal conditional exception**

In `AppLockMiddleware`, add an exact matcher:

```python
@staticmethod
def _is_onboarding_resume_upload(request: StarletteRequest) -> bool:
    return request.method == "POST" and request.url.path == "/api/resume/upload"
```

In `dispatch`, keep the existing public allowlists unchanged. After checking for a valid session, query bootstrap state only when the session is absent and the matcher is true. Call downstream only when `AppLockService.configured_source()` is `"none"` and `(await OnboardingService(db).status()).status != "complete"`. Otherwise return the existing `423` response. Roll back and return `423` if the conditional state lookup fails.

- [x] **Step 4: Run focused and neighboring backend tests and verify GREEN**

Run:

```bash
cd backend && python -m pytest tests/test_middleware/test_app_lock_gate.py tests/test_routers/test_app_lock.py tests/test_routers/test_resume_router.py -q --no-cov
```

Expected: all selected tests pass.

- [x] **Step 5: Commit the backend behavior**

```bash
git add backend/app/main.py backend/tests/test_middleware/test_app_lock_gate.py
git commit -m "fix(onboarding): allow guarded bootstrap CV upload"
```

---

### Task 2: Prioritize onboarding over unlock for new workspaces

**Files:**
- Modify: `frontend/src/__tests__/components/AppLockGateState.test.tsx`
- Modify: `frontend/src/components/AppLockGate.tsx`
- Create: `frontend/src/__tests__/pages/root-routing.test.ts`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- Consumes: existing `AppLockStatus` query data and `usePathname()`.
- Produces: a direct root-server redirect and client route replacement to `/onboarding`; configured locked route replacement to `/unlock?next=...` remains unchanged.

- [x] **Step 1: Add failing routing tests**

Extend `AppLockGateState.test.tsx` with an unconfigured/incomplete `/today` status and assert `router.replace("/onboarding")`. Add an explicit configured/incomplete case and assert `router.replace("/unlock?next=%2Ftoday")`. Add root-page tests proving first-run `/onboarding`, configured `/today`, and backend-unavailable `/today` behavior.

- [x] **Step 2: Run the focused frontend test and verify RED**

Run:

```bash
cd frontend && npm test -- src/__tests__/components/AppLockGateState.test.tsx
```

Expected: the first-run test fails because the current gate requests `/unlock?next=%2Ftoday`.

- [x] **Step 3: Implement the minimal redirect precedence**

Derive a primitive boolean from existing query data:

```typescript
const isFirstRun = data?.enabled
  && data.configured_source === "none"
  && data.onboarding?.status !== "complete";
```

In the navigation effect, redirect a non-onboarding, non-unlock first-run route to `/onboarding` first. Apply the existing `/unlock` redirect only when `isFirstRun` is false. Include the derived boolean in the effect dependency list and reuse it for the locked-onboarding render exception. In the root server page, fetch `/api/app-lock/status` and redirect the same first-run state directly to `/onboarding` before `/today` can render protected data.

- [x] **Step 4: Run focused and neighboring frontend tests and verify GREEN**

Run:

```bash
cd frontend && npm test -- src/__tests__/components/AppLockGateState.test.tsx src/__tests__/components/OnboardingGate.test.tsx src/__tests__/components/AppShell.test.tsx
npm run type-check
```

Expected: all selected tests and TypeScript checks pass.

- [x] **Step 5: Commit the frontend behavior**

```bash
git add frontend/src/components/AppLockGate.tsx frontend/src/__tests__/components/AppLockGateState.test.tsx
git commit -m "fix(onboarding): route first-run users before unlock"
```

---

### Task 3: Full verification, publication, and runtime refresh

**Files:**
- Verify: all modified source, tests, design, and plan files.

**Interfaces:**
- Consumes: committed frontend/backend behavior.
- Produces: pushed GitHub branch and refreshed `hatch-backend`/`hatch-frontend` containers with live acceptance evidence.

- [x] **Step 1: Run repository validation**

Run each command separately and stop on failure:

```bash
cd backend && python -m pytest tests/ -q
cd frontend && npm test
cd frontend && npm run type-check
cd frontend && npm run build
python3 scripts/check_docs.py
git diff --check
```

Expected: every command exits zero.

- [x] **Step 2: Review the final diff and commit any plan bookkeeping**

Confirm only scoped files changed, no secrets are present, and tests prove both allowed and denied states. Mark plan checkboxes complete and commit the plan update if it changes.

- [x] **Step 3: Push the feature branch**

```bash
git push -u origin fix/first-run-onboarding-lock-routing
```

Expected: GitHub accepts the branch and reports the upstream tracking reference.

- [x] **Step 4: Rebuild and recreate affected containers**

```bash
docker compose build --pull backend frontend
docker compose up -d --force-recreate backend frontend
```

If the Docker CLI cannot see the Podman Compose project, use the repository's working Podman Compose path with the same service scope and preserve the registry-backed LLM containers.

- [x] **Step 5: Verify live health and first-run behavior**

Run:

```bash
docker compose ps -a
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:3000/onboarding >/dev/null
docker compose logs --tail 30 backend frontend
```

Then verify against a controlled incomplete/unconfigured state that an unauthenticated unsupported resume upload reaches `422`, while completed/configured states remain `423`. Confirm the browser root route reaches `/onboarding` using the existing end-to-end tooling or an equivalent browser check.

- [x] **Step 6: Report publication and runtime evidence**

Provide the branch, commit hashes, push result, container status, health responses, and any remaining limitation. Do not claim success without current command output.
