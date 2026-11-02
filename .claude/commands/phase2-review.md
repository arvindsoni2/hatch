---
description: Review one Coach Phase 2 task branch or PR against the spec, plan and screen designs
argument-hint: <task id, e.g. P4> [branch or PR number]
---

Review Coach Phase 2 task **$ARGUMENTS**. Read the code and run the checks yourself; do not rely on the implementer's summary.

## 1. Gather

- Find the branch (`coach-p2/<task id>-*`) or PR (`gh pr view` / `gh pr diff` if a number was given). `git fetch`; diff against the merge base with `main`.
- Read the task's plan section, the spec sections it names, `docs/implementation-reports/coach-phase2/<task id>-evidence.md`, and for HA tasks `<task id>-red.md`.
- For P4 onward, confirm P4's evidence records the Wave 1 readiness check (spec §3.2).

## 2. Run

- HA tasks (P2, P6, P9): `git diff --name-only <red-sha>..HEAD -- <paths in task-red.md>` must print nothing. Anything printed is a Critical finding.
- The task's focused tests and listed regressions, `ruff check` on changed backend files, `npm run type-check` and the task's Vitest files if the frontend changed, `python scripts/check_docs.py`, `git diff --check`.
- If there is a migration: `alembic heads` shows one head; upgrade, downgrade and upgrade again on a disposable database.
- Compare what you ran with the evidence report. A claimed result you cannot reproduce is a High finding.

## 3. Check specification compliance

- Every named test in the plan exists and asserts what the plan says.
- Limits, statuses and transitions match spec §§7–8 exactly; illegal transitions return 409 `invalid_state`.
- API paths, request and response shapes, error codes and pagination match spec §12.
- Feature flags default to false and gate creation only (spec §14).
- The task stays inside its listed files; nothing from a later task is half-built.

## 4. Check quality and security

- Privacy: deletion cascades and fences as spec §7.8, §10 and §11 require; no derived text survives source deletion; no raw candidate text in runtime records, events, traces or logs; no DB transaction spans a model call.
- Boundaries: Phase 2 code writes other domains (Question Bank, Stories, interview rounds) only through their services or repositories.
- Tests: no mocking of the unit under test, no weakened or skipped assertions, synthetic data only, real database reload for integration tests.
- AI off: every feature still renders deterministic content.
- Code: small and readable, no new dependency the task does not name, no dead code.

## 5. Check the UI (tasks with frontend changes)

- Compare with `docs/visual-evidence/coach-phase2-design/screens/*.png` and the mapping in that folder's README: structure and order, copy (spec §13.4 glossary), components and tokens (no hex values, no legacy `Badge`/`Textarea`/`Select` styling).
- Run the page (or a Playwright test) in dark and light, at 1440 px and 390 px. Take screenshots and compare them with the reference images.
- Keyboard: every control reachable, visible focus ring, labels on inputs, `aria-label` on icon-only buttons, `aria-live="polite"` for arriving tips.

## 6. Report

Print, in this order:

1. Findings, most severe first: **Critical / High / Medium / Low**, each with `file:line`, expected vs actual, user impact, and the narrowest fix.
2. **Compliance verdict:** PASS or FAIL.
3. **Quality and security verdict:** PASS or FAIL.
4. For P1 and P2: whether the implementer model is qualified for its task class (plan §1.6).
5. What you could not check, and why.

PASS needs zero open Critical or High findings. Do not fix product code. Post the review on the PR (`gh pr review --comment`) only if the owner asks.
