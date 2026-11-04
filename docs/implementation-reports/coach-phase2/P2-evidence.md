# P2 evidence — real-interview debrief capture

Task / spec sections / ACs: P2, Wave 0, high-assurance. Spec §7.5 (Times), §7.6, §8.5, §10.1, §11, §12, §14. AC15 (debrief side), AC16, AC17, AC18, AC32, AC33 backend side.

Baseline SHA → head SHA: `eb0464a` (P2 RED contract and owner approval) → head recorded in the commit that adds this report. Protected RED commit: `0161bb7`.

OpenCode version · model ID · effort · switches (with reasons): opencode `2.2.5`; model ID `opencode-go/deepseek-v4.1-flash`; effort not exposed to the agent; no model switch.

Claude Code RED commit (HA only) and untouched-tests check output:

```text
$ git diff --name-only 0161bb7..HEAD -- \
    backend/tests/test_migrations/test_coach_debrief_migration.py \
    backend/tests/test_services/test_coach_debrief.py \
    backend/tests/integration/test_coach_debrief_cascade.py
$ (no output)
```

The three protected test files were not edited or deleted.

Files changed (one line each: responsibility):

- `backend/app/models/coach_readiness.py` — added `CoachInterviewDebrief` with the §11 columns, unique round FK `ON DELETE CASCADE`, and nullable `notes_text`.
- `backend/alembic/versions/20261103_2127_f57c6504bbca_add_coach_interview_debriefs.py` — generated `add coach interview debriefs` revision; parent `9a0421e6f32b`.
- `backend/app/services/coach_readiness/contracts.py` — `DebriefQuestion`, `SaveDebriefCommand`, `DebriefRead`, `ReadinessError`.
- `backend/app/services/coach_readiness/debrief.py` — `DebriefService` get/save/skip with due rules, validation, versioning and round mirroring through `InterviewRepository`.
- `backend/app/services/coach_readiness/questions.py` — linked QB → role family → latest session plan, archived excluded, max 5.
- `backend/app/services/coach_readiness/next_actions.py` — “How did it go?” readiness actions for due rounds.
- `backend/app/repositories/interview_repository.py` — additive `get(interview_id)` (owner-approved).
- `backend/app/schemas/coach_readiness.py` — debrief read/save/skip and next-action contracts; unknown request fields rejected.
- `backend/app/routers/coach_readiness.py` — GET/PUT debrief, POST skip, GET next-actions; safe-code errors and UTC `Z` times.
- `backend/app/config.py` — `HATCH_COACH_DEBRIEF_ENABLED=False`; optional `HATCH_DISPLAY_TIMEZONE` validated as IANA.
- `backend/app/models/__init__.py` — register the new debrief model.
- `backend/tests/runtime/test_schema_migration.py` — kept the dynamic one-head check and restored the `a4b5c6d7e8f9` parent assertion (owner-approved).
- `backend/tests/test_services/test_coach_debrief_rules.py` — question cap/text limits, JSON item shape, soft-deleted application ignored.
- `backend/tests/test_services/test_coach_questions.py` — likely-question order and archived exclusion.
- `backend/tests/test_routers/test_coach_debrief_router.py` — next action, UTC `Z` round time, flag-off reads/writes.
- `frontend/src/lib/coachReadinessApi.ts` — typed debrief and next-action client; HTTP status preserved.
- `frontend/src/lib/formatInterviewTime.ts` — display timezone/abbreviation and browser-local → UTC conversion.
- `frontend/src/components/coach/readiness/DebriefForm.tsx` — checklist first, quick-add, overall rating-only save, 409 keeps draft, labels and keyboard.
- `frontend/src/components/InterviewTimeline.tsx` — render the debrief form on each round and display times through the shared helper.
- `frontend/src/components/ApplicationDetail.tsx` — send `datetime-local` values as UTC.
- `frontend/src/app/today/page.tsx`, `TodayPageClient.tsx`, `components/hatch/screens/TodayScreen.tsx` — request and merge readiness next actions.
- `frontend/src/components/coach/readiness/__tests__/DebriefForm.test.tsx`, `frontend/src/lib/__tests__/formatInterviewTime.test.ts` — frontend contracts.
- `docs/implementation-reports/coach-phase2/P2-evidence.md` — this report.

Approved extra files / deviations:

- `backend/app/repositories/interview_repository.py` — owner-approved additive `get` only; no other change.
- `backend/tests/runtime/test_schema_migration.py` — owner-approved parent assertion restoration; dynamic head check retained.
- `frontend/src/app/today/page.tsx`, `TodayPageClient.tsx` and `TodayScreen.tsx` are the existing Today merge surface required by §7.5; no new route was added.
- `frontend/src/components/CalendarView.tsx` — D1, uses `parseInterviewTime`/display zone for interview dates and times.
- `frontend/src/app/today/page.tsx` — D1, `daysUntil` uses `parseInterviewTime`; L2 adds `.catch(() => [])` on the readiness actions fetch only.
- `GET /api/coach/readiness/display-timezone` — D2, read-only and readable whatever the debrief flag.
- `frontend/src/lib/useDisplayTimeZone.ts` — D2 hook; `formatInterviewTime.ts` and the cached `fetchDisplayTimeZone` loader hold the runtime value without any `NEXT_PUBLIC_` variable.

Owner decisions (4 Nov 2026):

- D1 (M1) Approved extra files: `frontend/src/components/CalendarView.tsx` and `frontend/src/app/today/page.tsx` (daysUntil) use the shared UTC parsing and display helper.
- D2 (M2) The backend serves the display timezone at runtime. New read-only route `GET /api/coach/readiness/display-timezone` → `{"display_timezone": "<IANA name>" | null}` (owner-approved addition to spec §12). No `NEXT_PUBLIC_` variable.
- D3 (L1) The debrief save MERGES asked questions into `InterviewRound.questions_asked`; it never replaces them.

RED → GREEN:

```text
$ /tmp/p2-py312/bin/python -m pytest -q --no-cov \
    tests/test_migrations/test_coach_debrief_migration.py \
    tests/test_services/test_coach_debrief.py \
    tests/integration/test_coach_debrief_cascade.py
9 passed
```

The RED contract had failed with the missing revision/module/contract names recorded in `P2-red.md`; all nine protected tests now pass.

Own tests:

```text
$ /tmp/p2-py312/bin/python -m pytest -q --no-cov \
    tests/test_services/test_coach_debrief_rules.py \
    tests/test_services/test_coach_questions.py \
    tests/test_routers/test_coach_debrief_router.py
11 passed
```

GREEN: commands, exit codes, counts:

```text
cd backend
/tmp/p2-py312/bin/python -m pytest -q --no-cov tests/runtime                # exit 0, 471 passed, 1 skipped
/tmp/p2-py312/bin/python -m pytest -q --no-cov tests/test_routers tests/test_services \
  tests/integration                                                          # exit 0, 1980 passed
ruff check <changed backend files>                                          # exit 0, All checks passed
/tmp/p2-py312/bin/alembic heads                                             # exit 0, f57c6504bbca (head)
cd ../frontend
npx vitest run src/components/coach/readiness/__tests__/DebriefForm.test.tsx \
  src/lib/__tests__/formatInterviewTime.test.ts \
  src/lib/__tests__/useDisplayTimeZone.test.ts                              # exit 0, 11 passed
npx vitest run                                                              # exit 0, 678 passed
npm run type-check                                                          # exit 0
npm run build                                                               # exit 0
```

Disposable-DB migration:

```text
alembic stamp 9a0421e6f32b   -> stamp_revision 9a0421e6f32b
alembic upgrade head         -> upgrade 9a0421e6f32b -> f57c6504bbca
alembic downgrade -1         -> downgrade f57c6504bbca -> 9a0421e6f32b
alembic upgrade head         -> upgrade 9a0421e6f32b -> f57c6504bbca
```

Timezone finding: `ApplicationDetail` sent `datetime-local` values to `createInterview` unchanged, i.e. browser-local text without an offset. The fix is in the frontend form only: `localDateTimeToUtcIso` converts before sending (Vitest covers the conversion). The interviews API returns stored UTC strings without an offset; `parseInterviewTime` now appends `Z` when no offset is present, and `CalendarView`/Today use it. No stored rows or existing routers changed.

Repair cycle 1:

- H1 flag gating — `get_debrief` returns 404 for a due-but-unstored debrief when the flag is off, `next-actions` returns `[]` when off, stored saved/skipped rows remain readable, and PUT/skip remain 403. Extended `test_flag_off_blocks_writes_but_allows_reads`.
- H2 offset-less times — `parseInterviewTime` treats strings without `Z`/offset as UTC; `formatInterviewTime` uses it. `formatInterviewTime.test.ts` covers `2026-11-20T04:30:00` in `Asia/Kolkata` → `10:00` and the `GMT+5:30`/`IST` abbreviation.
- M1 (D1) — `CalendarView` parses and displays with the shared helper/hook; Today `daysUntil` uses `parseInterviewTime`.
- M2 (D2) — added read-only `GET /api/coach/readiness/display-timezone`, the cached `fetchDisplayTimeZone` loader, and `useDisplayTimeZone`; `formatInterviewTime` takes an explicit zone. Tests cover configured, null/browser fallback, and abbreviation.
- M3 — DebriefForm now uses the exact copy and order required: checklist first, per-ticked-question 36 px rating buttons, Story select over active stories with None, 200-char note with the specified placeholder, 44 px overall/expectation controls, “Another question”, “Added by you”, the two renamed free-text fields, status words, and the post-save polite line.
- M4 — on 409 the form keeps every field, shows “Reload and re-apply”, re-fetches only the version, and the next save sends the new `expected_version` (`DebriefForm.test.tsx`).
- M5 — edits use `UPDATE … WHERE id = :id AND version = :expected` and zero rows raises `version_conflict`; first insert/skip catches `IntegrityError` inside `begin_nested` and raises `version_conflict`. Covered by stale-edit and concurrent-first-save tests.
- L1 (D3) — save merges asked texts into the existing round questions, case-insensitive with collapsed whitespace, never removes unticked questions, and skips the patch when nothing new is added. Covered in `test_save_merges_asked_questions_into_round`.
- L2 — only the Today readiness fetch gets `.catch(() => [])`.
- L3 — covered by the M2 tests and the display-timezone route test.

Model calls in tests: fake / live: none. P2 is deterministic and makes no model call.

Privacy / deletion / fencing evidence: all fixtures are synthetic. Debriefs are user-authored and stored only in `coach_interview_debriefs`; practice-session hard deletion leaves them intact (protected cascade test). Round and physical application deletion cascade via FKs. No `data/`, `.env`, CV, transcript or recording was read. No raw candidate text enters logs, events or traces.

Migration: heads before/after: `9a0421e6f32b` → `f57c6504bbca` (one head). The full chain from empty SQLite still fails at pre-existing `c30577e861e2`; the P2 revision was verified with the disposable stamp method above (and the protected migration test does the same).

Plan §1.6 qualification:

```json
{"harness":"opencode","opencode_version":"2.2.5","model_id":"opencode-go/deepseek-v4.1-flash","effort":"not exposed to the agent","task_class":"high_assurance","qualifying_task":"P2","review_verdict":null,"baseline_sha":"eb0464a6ed38276f88b4fbcd704b8858463a269c","date":"2026-11-03"}
```

Reviewer fills `review_verdict`.

Not run / known limits:

- No live model call; no P3 bench.
- The full migration chain from empty SQLite remains blocked by the pre-existing `c30577e861e2` revision; P2’s additive revision is verified in isolation.
- Tests were run on Python 3.12.16 using `/tmp/p2-py312` because the previous 3.14 interpreter was removed from the environment.
- The owner’s untracked `docs/implementation-specs/active/hatch-coach-phase2-handoff/` stays in place; docs checks run on a clean export.

Ready for review: yes — repair cycle 1 addresses H1, H2, M1–M5 and L1–L3; protected tests untouched and green, own tests green, runtime and full service/router/integration suites green, one migration head, frontend green.
