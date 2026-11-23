# P7 evidence — pre-interview brief (M5, S3)

## Carried from P6 review

All three carry-over findings were fixed first in commit `b9a76a4` (`fix(coach): guard tips polling and local-only explain routing`).

- **StrictMode polling:** `PatternCard` now sets `mounted.current = true` on effect mount and false on cleanup. A `<React.StrictMode>` Vitest requests tips (202 then cached 200), sees the operation succeed and renders the tip.
- **Local-only explain routing:** `_route_base_url` uses the profile's base URL only when `llm.provider == "llamacpp"`; otherwise it returns the local `ROUTE_URLS` default. Test: an `openrouter` profile with `base_url=https://openrouter.ai/api/v1` resolves to the local default.
- **Operations cap:** eviction skips `queued`/`running` entries. Test fills 200 terminal entries plus one running entry and asserts the running operation survives.

The carry-over regression suite is `backend/tests/runtime/test_coach_readiness_bindings.py`. It sits in the P7 diff because P6 was already merged when the review findings were fixed; it is P6 explain/tips carry-over scope, not new P7 behaviour. The six P6 protected files are unchanged (`git diff --name-only f58e14d..HEAD -- <protected paths>` prints nothing).

Carry-over gates (real output):

```text
$ python -m pytest -q --no-cov <P6 focused + explain tests + bench suite>
45 passed in 12.28s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness
30 passed (30)

$ npm run type-check
exit 0

$ git diff --check
exit 0
```

## P7

Task / spec sections / ACs: P7, Wave 1. Spec §7.5, §8.4, §10, §13.1–§13.4, §14; AC12–AC15, AC28, AC32, AC33.

Baseline SHA → head SHA: `f58e14d` (P6 merge) → carry-over `b9a76a4` → P7 commits `ed3d48b`, `883d98f`, `39a21ca`, `a29fd7b` → final P7 commit on `coach-p7/p7-brief`.

Model: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`, owner-confirmed 2026-11-05. No switch.

Files changed:

- `backend/app/services/coach_readiness/brief.py` — deterministic 7-section skeleton, enhancement fingerprint/state, enhancement via the same local route resolution and `finalise_generation` with story and round source refs.
- `backend/app/services/coach_readiness/scheduler.py` — 30-minute upcoming-round enhancement job.
- `backend/app/services/coach_readiness/next_actions.py` — brief actions for Today.
- `backend/app/models/coach_readiness.py`, `models/__init__.py` — `coach_interview_briefs`.
- `backend/alembic/versions/20261123_1115_6e209652647a_add_coach_interview_briefs.py` — additive migration.
- `backend/app/routers/coach_readiness.py` — GET brief and POST brief/tips.
- `backend/app/config.py` — `HATCH_COACH_BRIEF_ENABLED=False`.
- `backend/app/main.py` — scheduler job registration.
- `backend/tests/test_services/test_coach_reconciliation.py` — the startup test's scheduler stub implements `add_job`, matching the real APScheduler instance now that lifespan registers the brief job.
- `frontend/src/components/coach/readiness/InterviewBrief.tsx`, `BriefSection.tsx` — 7 sections, print action, no Refresh button, print stylesheet.
- `frontend/src/components/InterviewTimeline.tsx` — Brief/Debrief tabs per round.
- `frontend/src/lib/coachReadinessApi.ts` — typed brief client.
- Tests: `backend/tests/test_services/test_coach_brief.py`, `backend/tests/integration/test_coach_brief_enhancement.py`, `backend/tests/test_services/test_coach_readiness_scheduler.py`, `backend/tests/integration/test_coach_brief_lifecycle.py`, `backend/tests/runtime/test_coach_readiness_bindings.py` (P6 carry-over regression), `frontend/src/components/coach/readiness/__tests__/InterviewBrief.test.tsx`, `frontend/e2e/coach-readiness-brief.spec.ts`.
- `frontend/src/app/coach/readiness/page.tsx`, `frontend/src/app/coach/readiness/__tests__/page.test.tsx` — "Next interview" card (no Refresh button).

GREEN:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_brief.py \
    tests/integration/test_coach_brief_enhancement.py \
    tests/test_services/test_coach_readiness_scheduler.py \
    tests/runtime/test_coach_readiness_bindings.py
26 passed in 6.87s

$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4121 passed, 2 skipped in 642.76s

$ PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test \
    e2e/coach-readiness-brief.spec.ts --project=chromium
1 passed (4.3s)
# generates an A4 PDF and asserts exactly one page; header and all sections print

$ npx vitest run src/components/coach/readiness src/app/coach/readiness
33 passed (33)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app/ tests/
All checks passed!

$ alembic heads
6e209652647a (head)

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```

Migration round trip on a disposable DB: stamp `54f861f6f61d` → upgrade `6e209652647a` → downgrade `54f861f6f61d` → upgrade `6e209652647a`.

Named P7 tests (all passing):

| Test | Location |
|---|---|
| `test_brief_ready_with_ai_off_all_sections` | `tests/test_services/test_coach_brief.py` |
| `test_section_limits_and_source_order` | `tests/test_services/test_coach_brief.py` |
| `test_round_type_maps_to_practice_interview_types` (technical and phone-screen, seeded practice patterns) | `tests/test_services/test_coach_brief.py` |
| `test_brief_next_actions_for_upcoming_and_missing_round` | `tests/test_services/test_coach_brief.py` |
| `test_brief_archives_after_round_time_or_completed`, `test_cancelled_round_archives_brief`, `test_brief_without_round_date` | `tests/test_services/test_coach_brief.py` |
| `test_bad_enhancement_discarded_skeleton_kept` | `tests/integration/test_coach_brief_enhancement.py` |
| `test_successful_enhancement_sources_and_refresh` (story, round and Question Bank source refs; fingerprint change; purged text requeue) | `tests/integration/test_coach_brief_enhancement.py` |
| `test_scheduler_enhances_rounds_in_next_seven_days_only`, `test_scheduler_skips_when_flag_or_ai_is_off` | `tests/test_services/test_coach_readiness_scheduler.py` |
| `test_brief_times_in_display_timezone` | `frontend/src/components/coach/readiness/__tests__/InterviewBrief.test.tsx` |
| `test_print_layout_one_page` | `frontend/e2e/coach-readiness-brief.spec.ts` |

Sections/limits: likely questions ≤ 5, stories ≤ 3, watch-outs ≤ 2, gaps ≤ 2, ask-them ≤ 3; the skeleton is rebuilt on every read and archive follows `scheduled_at + duration`, `completed` and `cancelled`.

Model calls in tests: none live. Brief enhancement uses the same local-only route resolution as Explain and `finalise_generation`; no DB transaction is held during the HTTP call. When the stored fingerprint matches, validated talking points and watch-out sentences are merged into the skeleton; stale or unavailable tips are not shown.

Not run / known limits:

- The Playwright A4 print spec was run against the local dev server on port 3001; CI must provide its own server.
- The P3 bench/acceptance-smoke owner items remain open.

Ready for review: yes.

## Repair cycle 1

Review findings and fixes (commit `a6ea0db` was the pre-repair head):

- **Fingerprint ownership:** `request_enhancement` no longer writes `enhancement_fingerprint`; only `_run_enhancement` sets it, and only after a successful (non-fenced) `finalise_generation`. Re-queueing from `outdated` clears `enhanced_text_id`, so old tips can never read as current while fresh ones generate.
- **Dedupe:** a stored `enhancing` row with no current text reads as `enhancing`; `request_enhancement` returns without queueing then. An in-flight guard keyed on `{round_id}:{fingerprint}` (like `_INFLIGHT` in `explain.py`) closes the commit race; tasks are held in a module `_TASKS` set and discarded on completion.
- **Response shape:** the brief payload no longer leaks `_context`; it matches spec Appendix B, with question sources reported as `question_bank | session_plan` and the enhancement fingerprint exposed as `sha256:…`.
- **InterviewBrief:** polls while `enhancing`/`outdated` and stops on unmount (PatternCard's mounted-ref pattern); tips and watch-out sentences render in an `aria-live="polite"` region with skeleton lines while enhancing; an archived round shows a neutral "Archived" badge and no "Try again". Layout follows the design screen and README table (sentence-case title, sub-line, status line, question source sub-line with "Open answer"/"Draft answer", "Ready story" badge with competency chips, provenance line, watch-out source line, "No story yet" + outline "Draft a story", ask-them source line, When/Where/With/Round logistics).
- **Round tabs** use tokens only with `role="tablist"`/`tab`/`aria-selected` and "Debrief after the interview"; the **Next interview** card shows a brief-state `StatusBadge`, default "Open brief" and outline "Plan my week", and only considers scheduled/rescheduled rounds.

GREEN (real output):

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_brief.py \
    tests/integration/test_coach_brief_enhancement.py \
    tests/test_services/test_coach_readiness_scheduler.py \
    tests/integration/test_coach_brief_lifecycle.py \
    tests/runtime/test_coach_readiness_bindings.py
31 passed in 10.82s

$ python -m pytest -q --no-cov tests/test_services/test_source_events.py \
    tests/integration/test_coach_readiness_cascade.py \
    tests/integration/test_coach_readiness_fencing.py \
    tests/security/test_coach_readiness_canary.py \
    tests/architecture/test_coach_readiness_imports.py \
    tests/runtime/test_coach_readiness_bindings.py \
    tests/test_services/test_coach_grounding.py tests/benchmarks/coach/test_phase2_suite.py
45 passed in 14.98s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness
36 passed (36)

$ npx playwright test e2e/coach-readiness-brief.spec.ts --project=chromium
1 passed (3.6s)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app/ tests/
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0

$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4125 passed, 2 skipped in 862.46s
```

Named repair tests (all passing):

| Test | Asserts |
|---|---|
| `test_fingerprint_change_hides_tips_and_requeues_once` | job description (a fingerprint input that is not a source) changes: read is `outdated` with no tips; the re-queue shows `enhancing`, no old talking point, not current; a second request does not re-queue; the fresh tips land as `current` |
| `test_purged_tips_read_as_none_and_requeue` | purged text reads `none`, then exactly one re-queue (`model_dispatches` 1 → 2) |
| `test_reads_while_enhancing_make_one_model_call` | three GETs of the brief while enhancing produce exactly 1 model call |
| `test_enhancing_row_reads_enhancing` | a stored `enhancing` row with no text reads `enhancing` |
