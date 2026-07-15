# First-Run Onboarding and App-Lock Routing Design

## Goal

Make a reset or genuinely new Hatch workspace open onboarding by default, keep password creation as the final onboarding action, and allow the optional Master CV upload before that password creates an app-lock session.

## Confirmed Current Behaviour

- `/` redirects to `/today` unconditionally.
- A locked browser visiting a non-onboarding route is redirected to `/unlock` before `OnboardingGate` can redirect incomplete onboarding to `/onboarding`.
- `/onboarding` is renderable while the app lock is enabled but unconfigured and onboarding is incomplete.
- `POST /api/resume/upload` remains protected by the normal app-lock middleware, so the Skills step receives `423 Hatch is locked` before the final password step.
- Password creation is the final actionable onboarding screen after review; a success confirmation follows it.

## Approaches Considered

### 1. Conditional first-run bootstrap access (selected)

Use the existing app-lock status in the frontend to prioritize onboarding for an unconfigured, incomplete workspace. In the backend, allow the exact resume-upload operation only when the app lock has no configured password and authoritative onboarding state is incomplete.

This preserves the intended screen order and closes bootstrap access automatically once a password exists or onboarding completes.

### 2. Permanently public resume upload

Adding `/api/resume/upload` to the static public-path list is smaller, but would leave a file-writing and parsing endpoint unauthenticated after onboarding. This is rejected.

### 3. Move password creation before Skills

Creating the session earlier would make upload work through the normal protected path, but contradicts the approved requirement that password creation is the final onboarding action. This is rejected.

## Frontend Routing Design

`AppLockGate` remains the owner of lock-aware navigation. When app-lock status says all of the following are true:

- app lock is enabled;
- the configured source is `none`;
- onboarding status is not `complete`;

then any non-onboarding, non-unlock product route redirects to `/onboarding`. This first-run decision takes precedence over the normal redirect to `/unlock`.

The root page may continue to redirect to `/today`; the client gate will deterministically replace it with `/onboarding` once the authoritative status arrives. Existing configured workspaces continue to use `/unlock` when their session is absent.

Direct `/onboarding` access remains supported. Completed onboarding continues to use the existing product-route behaviour.

## Backend Bootstrap Authorization Design

The app-lock middleware will recognize `POST /api/resume/upload` as a conditional onboarding bootstrap operation, not a globally public endpoint.

Before allowing it without a valid session, the middleware will query the same database used by app-lock and onboarding state and require both:

- `AppLockService.configured_source()` returns `none`;
- authoritative onboarding status is not `complete`.

If either condition is false, the ordinary session requirement remains in force and a request without a valid session returns `423`.

No other resume endpoints become bootstrap-accessible. Upload validation, size limits, parsing, and persistence remain owned by the existing resume router.

## Data and Security Boundaries

- Browser/API secrets remain outside this flow.
- The exception is limited by HTTP method and exact path.
- The exception exists only during the unconfigured first-run state.
- Resetting only the app lock on an already completed workspace does not reopen unauthenticated resume upload.
- Existing authenticated upload behaviour is unchanged.

## Error Handling

- Missing or invalid bootstrap state fails closed through the normal `423` path.
- Backend/database errors are not converted into bootstrap permission.
- Frontend status-fetch failures retain the existing backend-unavailable handling and do not guess that the user is new.

## Test Design

Backend middleware tests will prove:

1. An unconfigured, incomplete workspace can post to `/api/resume/upload` without an app-lock session and reaches the downstream route.
2. A completed workspace without a session still receives `423` even if the password was reset.
3. A configured incomplete workspace without a session still receives `423`.
4. Unrelated protected endpoints remain locked.

Frontend tests will prove:

1. A new unconfigured workspace visiting a normal product route is redirected to `/onboarding`.
2. A configured locked workspace is redirected to `/unlock`.
3. Direct onboarding remains renderable during first run.

## Runtime Acceptance Criteria

After a clean onboarding reset and container refresh:

- opening `http://localhost:3000/` lands on `/onboarding` without requiring manual navigation;
- the optional PDF/DOCX upload on Skills succeeds before password creation;
- final review advances to password creation;
- password creation establishes a session and finalization completes;
- after explicitly locking a configured workspace, protected product and resume endpoints require unlock as before.

## Scope

This change does not alter the reset scripts, password policy, onboarding field order, resume parsing implementation, or the semantics of completed-workspace app locking.
