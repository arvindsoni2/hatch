# Hatch — instructions for coding agents

Hatch is a self-hosted, human-in-the-loop job-search workspace. Backend: Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, SQLite (WAL), shared runtime in `backend/app/runtime/`. Frontend: Next.js 15, React 18, TypeScript, Tailwind 3, components in `frontend/src/components/ui/`. Local models run in llama.cpp (`llm-primary` :8080, `llm-triage` :8081). Hatch never takes an external action (applying, messaging) without the user.

## Current work: Coach Phase 2 (Interview Readiness Loop)

- Spec (normative): `docs/implementation-specs/active/2026-10-22-coach-phase2-readiness-loop.md`
- Plan (tasks P0–P9, named tests, models): `docs/implementation-notes/2026-10-22-coach-phase2-readiness-loop-plan.md`
- Screens: `docs/visual-evidence/coach-phase2-design/README.md` and `screens/*.png`
- Diagrams (non-normative): `docs/architecture/coach-phase2-readiness-loop.html`

Roles: **OpenCode implements**, one task per PR. **Claude Code reviews** every PR and writes the failing (RED) tests first for high-assurance tasks P2, P6 and P9. The owner merges.

## Task loop (implementer)

1. `git switch main && git pull --ff-only`; record `git rev-parse HEAD`; `git switch -c coach-p2/<task-id>-<short-name>` (for P2, P6, P9 the branch already exists with Claude Code's RED commit: check it out instead).
2. Read the plan section for the task and every spec section it names. Read the files listed under "Read first". If a listed file or interface does not exist or differs from the plan, stop and report; do not redesign.
3. Write the named tests (or, for HA tasks, use the RED tests already committed). Run them and record the failure.
4. Implement the minimum to pass. Keep to the files the task lists. No unrelated refactors, no new dependencies unless the task names them.
5. Run the focused tests and the listed regressions, `ruff check` on changed backend files, `npm run type-check` when the frontend changed, `python scripts/check_docs.py` when docs changed, and `git diff --check`.
6. Fill `docs/implementation-reports/coach-phase2/PN-evidence.md` from the template in plan §6. Report only commands you actually ran, with their real output.
7. Commit exact paths with the plan's commit message. Ask the owner before pushing. Then say "Ready for review" with the branch name and stop. Do not start the next task.

## Hard rules

- Never edit, by any tool or shell command: the spec, the plan, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, anything in `.claude/` or `docs/visual-evidence/coach-phase2-design/`, or any test file listed in `docs/implementation-reports/coach-phase2/PN-red.md`. The reviewer diffs these on every PR. If one of these is wrong, stop and report.
- For HA tasks, implement the **Assumed interfaces** in `PN-red.md` exactly as listed.
- Never read or paste the contents of `data/`, `.env*`, real CVs, transcripts or recordings into a prompt, test or fixture. All fixtures are synthetic.
- Never weaken, skip or delete an existing test to make a change pass. Never mock the unit under test.
- Never merge, force-push, rebase, amend, reset, delete a branch, turn a feature flag on, or promote a model in `model_tiers.json` without the owner. Bring a branch up to date with `git merge main`.
- Dependency direction (spec §5.1): `coach_readiness` → existing domains → `services/source_events.py`. No existing module imports `coach_readiness`; existing domains report changes only through `source_events.notify`.
- Every Phase 2 route lives in `backend/app/routers/coach_readiness.py` (spec §12). Do not change `routers/interviews.py` or `routers/applications.py`; Today merges readiness actions in the frontend.
- Interview round times are UTC in storage and the API; show them in the display timezone (spec §7.5).
- Model output is a proposal. Every feature must still render useful deterministic content with AI mode set to None.
- No raw candidate text in runtime records, events, traces, logs or metric labels. No database write transaction may span a model call.
- UI: use the components and tokens named in the screens README; copy comes from the screenshots and spec §13.4. Both themes, 390 px width and keyboard must work.
- Do not switch models silently. If you change model (Tab to the `argon`, `consult` or `fallback` agent, or `/models`), write the switch and its reason in the evidence report.

## Stop and hand to the reviewer when

- two repair cycles on the same failing test have not fixed it (switch to the `argon` agent once, then stop);
- a RED test written by Claude Code looks wrong;
- the task would need a file outside its list, a schema change the spec does not describe, or a new dependency;
- you are about to touch privacy, deletion or ownership code in a way the task does not describe.

## Verification commands

Repository root: `python scripts/check_readme_contract.py`, `python scripts/check_docs.py`, `git diff --check`

Backend (`cd backend`): `ruff check app/ tests/`, `python -m pytest -q --no-cov <paths>`, `python -m pytest -q --no-cov tests/runtime`, `alembic heads`

Frontend (`cd frontend`): `npx vitest run <paths>`, `npm run type-check`, `npm run build`, `npx playwright test <spec>`
