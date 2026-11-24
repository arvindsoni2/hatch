# P9 evidence — What Hatch remembers, acceptance and rollout

Task / spec sections / ACs: P9, Wave 1. Spec §7.8, §10.1, §11, §12, §13.1, §14, K13; AC24, AC25, AC33.

Baseline SHA → head SHA: `cf62d96` (P9 RED contract + owner decisions) → `31ea6b3` (backend) → final implementation commit on `coach-p2/p9-remembers-rollout`.

OpenCode version · model ID: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; owner-confirmed 2026-11-05. No switch.

Claude Code RED commit: `2815de5` (initial contract), tightened in `2337ae7`; spec decision commit `f255955`. The two protected test files and the protected spec are untouched by this branch's implementation (`git diff --name-only 2337ae7..HEAD`, `f255955..HEAD` print nothing).

Files changed (one line each: responsibility):

- `backend/app/services/coach_readiness/privacy.py` — seven memory kinds, inventory counts/last-updated, per-kind deletion (`clear_round_questions` for debriefs through `InterviewRepository.update`), delete-all over the eight §11 tables, source-change listener unchanged.
- `backend/app/routers/coach_readiness.py` — `GET /memory`, `DELETE /memory/{kind}`, `DELETE /memory`; privacy service resolves `app.database.AsyncSessionLocal` at request time.
- `backend/app/schemas/coach_readiness.py` — memory inventory/delete response models.
- `backend/app/main.py` — readiness branch in the `RequestValidationError` handler: `422 {"detail": "invalid_input"}` without echoing input.
- `frontend/src/components/settings/RemembersList.tsx` — the page: Patterns derived row linking to Coach sessions, seven stored kinds (job competencies last) with count and last-updated, per-kind confirm dialogs, the debrief "Also clear questions on the round" option with the whole-list copy, delete-all confirm dialog.
- `frontend/src/app/settings/privacy/remembers/page.tsx`, `frontend/src/app/settings/general/page.tsx`, `frontend/src/components/settings/SettingsShell.tsx` — routes and nav; General shows the display timezone in use (`HATCH_DISPLAY_TIMEZONE`, else "This browser: {zone}").
- `frontend/src/lib/coachReadinessApi.ts` — typed memory client.
- `frontend/src/components/settings/__tests__/RemembersList.test.tsx` — page Vitest coverage.
- `frontend/e2e/coach-readiness.spec.ts` — privacy page and General timezone e2e.

GREEN (real output):

```text
$ python -m pytest -q --no-cov tests/integration/test_coach_readiness_journey.py
5 passed in 2.71s

$ python -m pytest -q --no-cov tests/security/test_coach_readiness_security.py
1 passed in 0.56s

$ python -m pytest -q --no-cov tests/test_services/test_source_events.py \
    tests/integration/test_coach_readiness_cascade.py \
    tests/integration/test_coach_readiness_fencing.py \
    tests/security/test_coach_readiness_canary.py \
    tests/architecture/test_coach_readiness_imports.py \
    tests/runtime/test_coach_readiness_bindings.py
24 passed in 9.70s

$ ruff check app/ tests/
All checks passed!
```

CI-equivalent suite (plan §7):

```text
$ python scripts/check_readme_contract.py
README contract passed.

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0

$ python scripts/dead_code_check.py
Import graph OK — 343 modules, no unreachable modules found.

$ python -m pytest -q --no-cov tests/runtime
482 passed, 1 skipped in 219.12s

$ npx vitest run
120 files passed, 728 tests passed

$ npm run type-check
exit 0

$ npm run build
exit 0

$ alembic heads
6e209652647a (head)

$ python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/phase2_v1
Valid Coach suite coach_phase2_v1: 48 scenarios, 2 models

$ PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test \
    e2e/coach-readiness.spec.ts --project=chromium
2 passed (8.5s)
```

Full backend suites:

```text
$ python -m pytest -q --cov=app tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4152 passed, 2 skipped, 2 failed, coverage 79.71% (required 58%)
# The two failures are coverage-load timing flakes:
#   tests/benchmarks/coach/test_runner.py::test_whole_run_deadline_flushes_partial_progress
#   tests/benchmarks/test_staged_runner.py::test_two_fresh_restart_records_authorize_two_eighty_pair_runs
# Both pass when re-run alone (2 passed in 0.72s).

$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4154 passed, 2 skipped in 754.67s
```

Full Playwright suite against the local dev server: the two new P9 specs pass. The full run also executes pre-existing integration specs that require an unlocked, seeded backend; in this app-locked workspace they fail (67 passed, 5 skipped, 69 failed), independent of P9. The P9 pages themselves are fully mocked and green.

Privacy / deletion / fencing evidence:

- Inventory returns one row per kind in page order, job competencies last, with true counts and the newest timestamp per kind; an emptied kind reports 0 rows and no timestamp.
- Per-kind deletes remove only that kind. Debrief deletion keeps round `questions_asked` by default and clears the whole list only when `clear_round_questions=true`, through `InterviewRepository.update`; rounds without a debrief keep theirs.
- Delete-all empties the eight §11 tables, leaves every Phase 1 row byte-for-byte identical (including round `questions_asked`, stories, Question Bank entries and session audio files), and is idempotent (second call returns all zeros).
- The readiness source-change listener still purges derived text by source; the journey exercises claim + hard-delete, and debriefs survive a deleted practice session.

Migration: no new migration. Heads before/after: `6e209652647a` (P7 brief migration) unchanged.

Model calls in tests: fake only, at the local `…/chat/completions` boundary. No live calls.

Not run / known limits:

- K13 (accepted for 0.20.0): a brief/tips generation already running when delete-all happens may still write its text afterwards; finalise fencing re-checks sources, not deletion events.
- Full Playwright integration specs need the CI seed/unlocked backend; see above.
- P3 bench/acceptance-smoke owner items remain open; owner runs the bench summary review before flags-on rollout.

Ready for review: yes.
