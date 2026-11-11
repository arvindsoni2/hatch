# P5 evidence — focus areas and interview-aware practice plans (M2, M3)

Task / spec sections / ACs: P5, Wave 1. Spec §6.1, §7.2, §7.3, §8.2, §8.3, §11, §12, §13.1–§13.4, §14; AC06–AC09, AC31.

Baseline SHA → head SHA: `974c395` (P4 merged) → the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode (harness-reported model ID `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`, owner-confirmed 2026-11-05). Effort is not exposed to the agent. No model switch during the task.

Claude Code RED commit (HA only): not applicable; P5 is not high-assurance.

Files changed (one line each: responsibility):

- `backend/app/models/coach_readiness.py`, `backend/app/models/__init__.py` — `CoachFocusArea` and `CoachPracticePlan` with the §11 checks/indexes.
- `backend/alembic/versions/20261111_1139_f4f4b2b410de_add_coach_focus_areas_and_practice_plans.py` — additive migration on `ebfc0afaf8c9`.
- `backend/app/services/coach_readiness/focus.py` — criterion status, active-slot allocation, auto-completion and plan expiry.
- `backend/app/services/coach_readiness/plan.py` — pure `build_plan` (rules 1–5, template wording, budgets).
- `backend/app/services/coach_readiness/contracts.py` — focus/plan DTOs and error code.
- `backend/app/schemas/coach_readiness.py` — focus and plan HTTP contracts with unknown-field rejection.
- `backend/app/routers/coach_readiness.py` — focus + plan routes, status/version/limit handling.
- `frontend/src/lib/coachReadinessApi.ts` — typed focus/plan client.
- `frontend/src/components/coach/readiness/FocusAreas.tsx`, `FocusAreaEditor.tsx`, `PracticePlan.tsx` — the M2/M3 screens.
- `frontend/src/app/coach/readiness/page.tsx` — section order Focus areas → This week's plan → Patterns, editor wiring and "Work on this".
- `frontend/src/components/coach/readiness/PatternCard.tsx`, `PatternGroup.tsx` — "Work on this" callback and plan entry points.
- `frontend/src/app/coach/page.tsx`, `frontend/src/app/coach/stories/page.tsx` — Readiness tab links and launcher query prefill.
- `frontend/src/components/coach/SessionLauncher.tsx` — optional role/difficulty prefill props.
- Tests: `backend/tests/test_services/test_coach_focus.py`, `test_coach_plan.py`, `backend/tests/integration/test_coach_focus_concurrency.py`, `backend/tests/test_routers/test_coach_focus_plan_router.py`, `frontend/src/components/coach/readiness/__tests__/FocusAreas.test.tsx`, `FocusAreaEditor.test.tsx`, `PracticePlan.test.tsx`, the readiness page test and the CoachPage test.
- `docs/implementation-reports/coach-phase2/P5-evidence.md` — this report.

Deviations recorded rather than guessed:

- The spec §12 route table has no plan read route, but the page must show the active/draft plan. Added read-only `GET /api/coach/readiness/plans` returning `{active, draft}`.
- The spec gives no storage for a plan's unallocated minutes; the API derives it from `minutes - sum(item minutes)` on read.
- `FocusAreaEditor` is also used for title edits; criterion edits are creation-only in P5.
- The existing `SessionLauncher` creates `legacy_v1` sessions, not `conversational_v1`. The prefilled launcher therefore starts a session that does **not** feed patterns or auto-tick practice items. This is a known follow-up for the Phase 1 launcher, not a P5 failure.

RED: test names and failure output (short):

The named tests were authored before the implementation. The first captured run was after the modules existed and failed on behaviour, not collection:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_focus.py tests/test_services/test_coach_plan.py
FAILED test_stale_version_conflict_keeps_state
FAILED test_plan_due_at_round_minus_two_hours
```

Both were fixed before the GREEN run.

GREEN: commands, exit codes, counts:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_focus.py \
    tests/test_services/test_coach_plan.py \
    tests/integration/test_coach_focus_concurrency.py \
    tests/test_routers/test_coach_focus_plan_router.py
19 passed in 1.61s

$ python -m pytest -q --no-cov tests/test_services/test_coach_focus.py \
    tests/test_services/test_coach_plan.py \
    tests/integration/test_coach_focus_concurrency.py \
    tests/test_routers/test_coach_focus_plan_router.py \
    tests/test_services/test_coach_patterns.py tests/test_repositories/test_load_learning_snapshots.py \
    tests/test_routers/test_coach_patterns_router.py tests/integration/test_readiness_ai_setup_gate.py \
    tests/test_services/test_coach_conversational_progress.py \
    tests/test_repositories/test_conversational_session_repository.py \
    tests/test_services/test_coach_debrief.py tests/test_services/test_coach_debrief_rules.py \
    tests/test_services/test_coach_questions.py tests/test_routers/test_coach_debrief_router.py \
    tests/integration/test_coach_debrief_cascade.py tests/test_migrations/test_coach_debrief_migration.py \
    tests/runtime
679 passed, 1 skipped in 136.30s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness \
    src/__tests__/components/CoachPage.test.tsx \
    src/components/coach/conversation/__tests__/ConversationalProgress.test.tsx \
    src/components/coach/conversation/__tests__/ConversationalReport.test.tsx
34 passed (11 files)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app tests <migration>
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```

Migration (disposable DB):

```text
$ alembic heads
f4f4b2b410de (head)

$ DATABASE_URL=sqlite+aiosqlite:////tmp/opencode/p5-migration.db
$ alembic stamp ebfc0afaf8c9  -> stamp_revision  -> ebfc0afaf8c9
$ alembic upgrade head         -> upgrade ebfc0afaf8c9 -> f4f4b2b410de
$ alembic downgrade -1        -> downgrade f4f4b2b410de -> ebfc0afaf8c9
$ alembic upgrade head         -> upgrade ebfc0afaf8c9 -> f4f4b2b410de
# sqlite index:
CREATE UNIQUE INDEX uq_coach_practice_plans_one_active
  ON coach_practice_plans (status) WHERE status = 'active'
```

Model calls in tests: fake / live: none. P5 is deterministic; no runtime binding.

Privacy / deletion / fencing evidence: synthetic fixtures only; no `data/`, `.env`, CV, transcript or recording was read. Focus and plan rows are user-authored; plan item completion is derived on read from completed sessions and never writes transcripts or media.

Not run / known limits:

- No live screenshot comparison at 390 px was run; component and page tests plus the production build cover the routes.
- The launcher-gap note above: Phase 1 launcher sessions are `legacy_v1` and do not feed patterns or auto-tick.
- P3 bench/acceptance-smoke owner items remain open.

Ready for review: yes.

## Repair cycle 1 (11 Nov 2026)

Review findings addressed:

- **H1** — todo plan items now show an outline "Open" button:
  - `practice_session` → `/coach?launch=1&role=<group role family>&difficulty=<mapped>`, using the latest difficulty in that group from `load_learning_snapshots` (default `realistic`); mapping supportive→easy, realistic→medium, challenging→hard.
  - `story_work` → the existing `/coach/stories/new?competency=…` route, which already prefills the editor.
  - `review_answer` → `/prep/question-bank?item=<id>` (the Question Bank client now opens the item from the query).
  - `build_plan` persists `story_competency`, `question_id` and `difficulty`; `PlanItemRead` exposes them.
  - The first likely question without an answer is selected (Question Bank `answer_draft` empty; session-plan questions with no QB answer are accepted without an item link).
  - Both PatternGroup "Practise this role" links use the same launch target and latest difficulty.
- **H2** — FocusAreas now offers Pause, Resume, Archive, Edit and Reopen, all through PATCH with `expected_version`; archived areas are hidden; Edit passes the area to the editor. A 409 keeps the editor draft and shows "Reload and re-apply".
- **M1** — a practice criterion counts only `done` items whose `completed_at` is at or after the area's creation. New older-plan test.
- **M2** — `patch_plan_item` accepts only an active plan; drafts return 409 `invalid_state`.
- **M3** — creating a focus area with an unknown `application_id` returns 404 `not_found`; test added.
- **M4** — `PlanItemPatch` carries `expected_version`; a versioned UPDATE is the first write and a mismatch returns 409 `version_conflict`; the frontend sends `plan.version`.
- **M5** — with an active plan, "Plan my week" remains available; a new draft shows Start, and starting it supersedes the active plan.
- **L1** — skipped items render "Skipped" with Undo; done→skipped is allowed, skipped→done returns 409 `invalid_state`.
- **L2** — the level criterion says "Interview ready", not the raw enum.
- **L3** — removed the no-op SELECT in `start_plan`.
- **L4** — `GET /focus-areas` takes `limit` (default 20, max 100) and `offset`, ordered by `created_at, id`.
- **L5** — the editor carries the pattern group's `contract_version` into creation.
- **L6** — concurrent-start test starts two drafts at once and asserts exactly one active row (the other superseded).
- **L7** — the round picker uses `formatInterviewTime` with the display timezone and abbreviation.

Repair gates:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_focus.py \
    tests/test_services/test_coach_plan.py \
    tests/integration/test_coach_focus_concurrency.py \
    tests/test_routers/test_coach_focus_plan_router.py
25 passed in 1.93s

$ python -m pytest -q --no-cov <full regression batch from the evidence above>
685 passed, 1 skipped in 139.89s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness \
    src/__tests__/components/CoachPage.test.tsx \
    src/components/coach/conversation/__tests__/ConversationalProgress.test.tsx \
    src/components/coach/conversation/__tests__/ConversationalReport.test.tsx
36 passed (11 files)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app tests
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```

Ready for review: yes.
