# Hatch Route Taxonomy

Hatch keeps the main navigation focused on the daily job-search workflow while preserving advanced and contextual screens for users who need them.

## Primary Routes

Primary routes are safe to show in the main shell or high-level product copy:

- `/today` - daily work queue
- `/jobs` - discovered roles
- `/stream` - Pipeline
- `/tracker` - Applications
- `/tailor` - CV Studio
- `/prep` - Interview Prep
- `/coach` - Interview Coach

## Contextual Routes

Contextual routes should be reached from the workflow that owns them, not promoted as top-level navigation:

- `/tracker/watched-companies`
- `/prep/question-bank`
- `/jobs/[id]`
- `/applications/[id]`
- `/approvals` and `/approvals/[id]`
- `/calendar`
- `/coach/session/[id]`
- `/coach/report/[id]`
- `/coach/stories`, `/coach/stories/[id]`, `/coach/stories/new`

## Advanced Routes

Advanced routes belong under Settings or diagnostics-oriented entry points:

- `/settings`
- `/settings/ai`
- `/settings/preferences`
- `/settings/profile`
- `/settings/resume`
- `/settings/security`
- `/settings/system`

## Developer Routes

Developer routes remain reachable for diagnostics and release tooling, but they should not compete with the primary job-search journey:

- `/agents`
- `/analytics`
- `/readme-preview/[screen]`

## Legacy Redirects

- `/applications` redirects to `/tracker`

The machine-readable source lives in `frontend/src/lib/route-taxonomy.ts`; tests assert that primary product routes and retained legacy redirects stay classified.
