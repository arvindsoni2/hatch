# P1 evidence — story coverage map (M4)

Task / spec sections / ACs: P1, Wave 0. Spec §7.4 (M4), AC10 and AC11. Coverage DTOs only; `StoryMatcher` is not used.

Baseline SHA → head SHA: `b7274a6` (plan baseline) → `f84a097` (main with P0 merged) → head recorded in the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode `2.2.5`; model ID `opencode-go/deepseek-v4.1-flash`; effort not exposed to the agent; no model switch.

Claude Code RED commit (HA only) and untouched-tests check output: not applicable (P1 is not HA). No `PN-red.md` exists for P1.

Files changed (one line each: responsibility):

- `backend/app/services/coach_readiness/__init__.py` — package marker.
- `backend/app/services/coach_readiness/contracts.py` — coverage DTOs, statuses and actions.
- `backend/app/services/coach_readiness/coverage.py` — match key, competency order/dedupe/cap, containment scoring, thresholds, overrides and overview.
- `backend/app/services/coach_readiness/stopwords_en.txt` — copied benchmark stoplist; a test keeps the copies identical.
- `backend/app/models/coach_readiness.py` — `coach_competency_overrides` only.
- `backend/alembic/versions/20261103_1238_9a0421e6f32b_add_coach_competency_overrides.py` — generated revision `add coach competency overrides`; one head.
- `backend/app/schemas/coach_readiness.py` — coverage, overview and override HTTP contracts (`extra=forbid` on writes).
- `backend/app/routers/coach_readiness.py` — coverage read, overview and override write routes only.
- `backend/app/config.py` — coverage flag (`False`) and thresholds 0.67 / 0.34.
- `backend/app/main.py` — register the readiness router.
- `backend/app/models/__init__.py` — register the new ORM model for Alembic.
- `backend/tests/test_services/test_coach_coverage.py` — the named service tests and the hand-labelled calibration check.
- `backend/tests/test_routers/test_coach_coverage_router.py` — route shapes, overview and flag-off read/write behaviour.
- `backend/tests/fixtures/coach_coverage/pairs.json` — 10 synthetic JD/story pairs, 20 labelled competency outcomes.
- `frontend/src/lib/coachReadinessApi.ts` — typed coverage client.
- `frontend/src/components/coach/readiness/CoverageMap.tsx` — three statuses with icon + text, story links, draft link.
- `frontend/src/components/coach/readiness/CoverageStrip.tsx` — Stories strip summary.
- `frontend/src/components/coach/readiness/__tests__/CoverageMap.test.tsx` — status rendering, prefilled draft link, keyboard focus.
- `frontend/src/app/coach/stories/page.tsx` — render the coverage strip.
- `frontend/src/components/ApplicationDetail.tsx` — load and render the application coverage panel.
- `docs/implementation-reports/coach-phase2/P1-evidence.md` — this report.

File deviation: `backend/app/models/__init__.py` is outside the plan's P1 list but is required so `alembic env.py` sees the new model and autogenerate/revision metadata stays complete.

RED: test names and failure output (short):

Run against a clean worktree at `f84a097` with only the new tests and fixture copied in:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_coverage.py tests/test_routers/test_coach_coverage_router.py
ERROR collecting tests/test_services/test_coach_coverage.py
E   ModuleNotFoundError: No module named 'app.models.coach_readiness'
1 error in 0.18s
```

The same first failure applies to `app.services.coach_readiness.coverage`; both modules and the routes did not exist at the baseline.

GREEN: commands, exit codes, counts:

```text
cd backend
python -m pytest -q --no-cov tests/test_services/test_coach_coverage.py \
  tests/test_routers/test_coach_coverage_router.py                         # exit 0, 15 passed
python -m pytest -q --no-cov tests/test_services                            # exit 0, 1332 passed
python -m pytest -q --no-cov tests/test_routers                             # exit 0, 531 passed
/tmp/p0-py312/bin/python -m pytest -q --no-cov tests/test_services/test_coach_coverage.py \
  tests/test_routers/test_coach_coverage_router.py                         # exit 0, 15 passed (Python 3.12.16)
/tmp/p0-py312/bin/python -m pytest -q --no-cov tests/test_services           # exit 0, 1332 passed
/tmp/p0-py312/bin/python -m pytest -q --no-cov tests/test_routers            # exit 0, 531 passed
ruff check app/services/coach_readiness app/models/coach_readiness.py \
  app/schemas/coach_readiness.py app/routers/coach_readiness.py app/config.py \
  app/main.py app/models/__init__.py tests/test_services/test_coach_coverage.py \
  tests/test_routers/test_coach_coverage_router.py \
  alembic/versions/20261103_1238_9a0421e6f32b_add_coach_competency_overrides.py  # exit 0, All checks passed
cd ../frontend
npx vitest run                                                              # exit 0, 103 files, 666 tests passed
npx vitest run src/components/coach/readiness/__tests__/CoverageMap.test.tsx  # exit 0, 2 passed
npm run type-check                                                          # exit 0
npm run build                                                               # exit 0
```

The plan's listed regressions `tests/test_services/test_story*` and `tests/test_routers/test_stories*` do not exist in this repository; the full service and router suites above replace them. `tests/test_routers/test_applications_router.py` and `tests/test_routers/test_coach_router.py` (80 tests) also pass.

Regressions run: full backend service (1332) and router (531) suites on Python 3.14.8 and 3.12.16; full frontend Vitest suite (666) and Next build.

Model calls in tests: fake / live: none. P1 is deterministic; no model is called.

Calibration: `backend/tests/fixtures/coach_coverage/pairs.json` holds 10 synthetic JD/story pairs (20 labelled outcomes). With the defaults 0.67 / 0.34, `test_calibration_fixtures_match_hand_labels` matches 20/20. Treating `covered` as the positive class: TP 10, FP 0, FN 0, TN 10 → precision 1.00, recall 1.00. No default changed.

Privacy / deletion / fencing evidence: all fixtures are synthetic; no `data/`, `.env`, CV, transcript or recording was read. Coverage reads active stories through `StoryRepository.list_all_active_orm` and writes only `coach_competency_overrides`. The override model cascades from `applications.id` on delete. No model output is stored.

Migration: heads before/after, downgrade/upgrade result: before `a4b5c6d7e8f9 (head)`; after `9a0421e6f32b (head)` — one head. Disposable SQLite check (Created with `Base.metadata.create_all`, dropped `coach_competency_overrides`, stamped `a4b5c6d7e8f9`):

```text
alembic stamp a4b5c6d7e8f9   -> stamp_revision a4b5c6d7e8f9
alembic upgrade head         -> Running upgrade a4b5c6d7e8f9 -> 9a0421e6f32b
alembic downgrade -1         -> Running downgrade 9a0421e6f32b -> a4b5c6d7e8f9
alembic upgrade head         -> Running upgrade a4b5c6d7e8f9 -> 9a0421e6f32b
```

Not run / known limits:

- The repository's full migration chain from an empty database still fails at the pre-existing `c30577e861e2` revision (`NoSuchTableError: applications`); this is unrelated to P1 and existed before this branch. The new revision was verified with the disposable stamp method above.
- The plan's named story regression tests do not exist; broader suites were run instead.
- `coverage_overview` counts gaps by original competency and does not apply per-application renames/hides; §7.4 only defines the overview across applications.
- Docs checks must run on a clean export of tracked files because the owner's untracked `docs/implementation-specs/active/hatch-coach-phase2-handoff/` remains in the working tree and is not ours to move.

Ready for review: yes — named tests green on Python 3.12 and 3.14, frontend green, one migration head, and no protected file changed.
