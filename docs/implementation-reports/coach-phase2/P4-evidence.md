# P4 evidence — practice patterns (M1)

## STEP 0 — Wave 1 readiness check (spec §3.2)

Recorded on `main` at `81f902e` before any P4 code.

1. **Phase 1 acceptance, privacy and recovery suites** — exit 0:

```text
$ cd backend && python -m pytest -q --no-cov \
    tests/benchmarks/coach/test_conversational_acceptance_smoke.py \
    tests/integration/test_coach_report_privacy_flow.py \
    tests/integration/test_coach_deletion_recovery.py \
    tests/integration/test_coach_audio_restart_recovery.py \
    tests/test_services/test_coach_privacy.py \
    tests/test_observability/test_coach_conversation_privacy.py
62 passed in 92.32s
```

2. **Runtime and the Job Score gateway binding** — exit 0:

```text
$ python -m pytest -q --no-cov tests/runtime
472 passed, 1 skipped in 95.34s

$ python -m pytest -q --no-cov tests/runtime/test_job_score_agent_integration.py
18 passed in 6.25s
```

3. **Open branches touching the Phase 2 seam files** — no unique patches remain:
   - `fix/coach-phase1-progress-export-repairs` — aggregate patch-id equals squash commit `7ec59bc` (`git patch-id --stable` on `main...branch` vs `git show 7ec59bc`).
   - `fix/coach-phase1-report-repairs` — aggregate patch-id equals squash commit `aa567e1`.
   - `phase1/pr4-report-privacy-hardening` — aggregate patch-id equals squash commit `56e8717` (PR #68).
   - `fix/coach-phase1-readiness-repairs` — `git cherry main origin/fix/coach-phase1-readiness-repairs` marks its tip commit `ef8d6cf` as already present on `main` (patch equivalent); no unique patches. Owner accepts it as merged.
   - No branch was deleted.
4. **P0–P3 merged** — P0 (#82), P1 (#83), P2 (`4d072bf`), P3 (`81f902e`, PR #84). Owner decision: the P3 bench report is accepted as it stands; the bench runs and the Phase 1 `acceptance-smoke` rerun on b12124 remain **pending owner items**, not a failure. Incumbent Qwen models stay in `model_tiers.json`.

Gate verdict: **PASS** — P4 code starts.

## Task record

Task / spec sections / ACs: P4, Wave 1. Spec §3.2, §5.3, §7.1 (incl. §7.1.6), §7.7, §12, §13.4, §14, Appendix A. AC01–AC05, AC37.

Baseline SHA → head SHA: `81f902e` → the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode (harness-reported model ID `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`, owner-confirmed 2026-11-05). Effort is not exposed to the agent. No model switch during the task.

Claude Code RED commit (HA only): not applicable; P4 is not a high-assurance task.

Files changed (one line each: responsibility):

- `backend/app/services/coach_conversational_progress.py` — `evaluation_contract_version` and `difficulty` on `ProgressSnapshot`, defaulted so existing callers are unchanged.
- `backend/app/repositories/conversational_session_repository.py` — new `load_learning_snapshots(*, limit=1000)` only; existing methods untouched.
- `backend/app/services/coach_readiness/patterns.py` — grouping, latest-three rule, difficulty guard, fingerprints, stale marking, deterministic Why excerpts.
- `backend/app/services/coach_readiness/contracts.py` — pattern, group, support, policy and Why DTOs.
- `backend/app/models/coach_readiness.py`, `backend/app/models/__init__.py` — `CoachPatternDismissal` model and registration.
- `backend/alembic/versions/20261110_1241_ebfc0afaf8c9_add_coach_pattern_dismissals.py` — additive `coach_pattern_dismissals` table.
- `backend/app/config.py` — `HATCH_COACH_READINESS_ENABLED=False`, `HATCH_COACH_PATTERN_WINDOW_DAYS=90`.
- `backend/app/schemas/coach_readiness.py` — pattern list/group/card/why HTTP contracts.
- `backend/app/routers/coach_readiness.py` — patterns list, why, dismiss and undo routes (spec §12).
- `frontend/src/app/coach/readiness/page.tsx` — Readiness page with the Patterns section and Older disclosure.
- `frontend/src/components/coach/readiness/PatternCard.tsx`, `PatternGroup.tsx`, `WhyPanel.tsx` — pattern cards, group headers, deterministic Why panel.
- `frontend/src/lib/coachReadinessApi.ts` — typed pattern calls (not named in the plan but required by the page).
- Tests: `backend/tests/test_services/test_coach_patterns.py`, `backend/tests/test_repositories/test_load_learning_snapshots.py`, `backend/tests/test_routers/test_coach_patterns_router.py`, `frontend/src/components/coach/readiness/__tests__/PatternCard.test.tsx`.
- `docs/implementation-reports/coach-phase2/P4-evidence.md` — this report.

File deviations: `models/__init__.py` registers the new model; `coachReadinessApi.ts` is the typed client the page needs. The Sessions/Stories pages were not modified (the plan's P4 file list has no navigation file), so `/coach/readiness` has its own tab row but no link from the Sessions page yet.

RED: test names and failure output (short):

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_patterns.py \
    tests/test_repositories/test_load_learning_snapshots.py \
    tests/test_routers/test_coach_patterns_router.py
E   ImportError: cannot import name 'dismiss_readiness_pattern' from
    'app.routers.coach_readiness'

$ npx vitest run src/components/coach/readiness/__tests__/PatternCard.test.tsx
Test Files  1 failed (1)  Tests  no tests
```

GREEN: commands, exit codes, counts:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_patterns.py \
    tests/test_repositories/test_load_learning_snapshots.py \
    tests/test_routers/test_coach_patterns_router.py
12 passed

$ python -m pytest -q --no-cov tests/test_services/test_coach_patterns.py \
    tests/test_repositories/test_load_learning_snapshots.py \
    tests/test_routers/test_coach_patterns_router.py \
    tests/test_services/test_coach_conversational_progress.py \
    tests/test_repositories/test_conversational_session_repository.py tests/runtime
630 passed, 1 skipped in 128.89s

$ npx vitest run src/components/coach/readiness/__tests__/PatternCard.test.tsx
5 passed

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check <changed backend files>
All checks passed!
```

Regressions run:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_conversational_progress.py \
    tests/test_repositories/test_conversational_session_repository.py
146 passed in 15.58s

$ npx vitest run src/components/coach/conversation/__tests__/ConversationalProgress.test.tsx \
    src/components/coach/conversation/__tests__/ConversationalReport.test.tsx
5 passed (2 files)
```

Model calls in tests: fake / live: none. P4 derives patterns and Why deterministically; no model call and no runtime binding.

Privacy / deletion / fencing evidence: synthetic fixtures only; no `data/`, `.env`, CV, transcript or recording was read. Sessions with `deletion_state != 'not_requested'` are excluded from pattern sources; dismissals store fingerprints only.

Migration: `coach_pattern_dismissals`; heads before/after and disposable upgrade/downgrade/upgrade:

```text
$ alembic heads
f57c6504bbca (head)          # before
ebfc0afaf8c9 (head)          # after

$ DATABASE_URL=sqlite+aiosqlite:////tmp/opencode/p4-migration.db
$ alembic stamp f57c6504bbca   -> stamp_revision  -> f57c6504bbca
$ alembic upgrade head         -> upgrade f57c6504bbca -> ebfc0afaf8c9
$ alembic downgrade -1        -> downgrade ebfc0afaf8c9 -> f57c6504bbca
$ alembic upgrade head         -> upgrade f57c6504bbca -> ebfc0afaf8c9
# sqlite3 .schema coach_pattern_dismissals
CREATE TABLE coach_pattern_dismissals (
  fingerprint VARCHAR(64) NOT NULL,
  dismissed_at DATETIME NOT NULL,
  PRIMARY KEY (fingerprint)
);
```

Not run / known limits:

- No model call: P4 and the Why panel are deterministic.
- No live screenshot comparison was run; the new page is covered by the component test, type-check and production build. The reviewer still needs to compare both themes at 390 px.
- The P3 owner bench items and the Phase 1 `acceptance-smoke` rerun on b12124 remain open (not P4 failures).
- Dismissals still store fingerprints only (spec §11); `seen_again` is re-derived in memory from earlier support sets, never stored.

Ready for review: yes — Wave 1 gate recorded; named tests, regressions, runtime, migration and frontend gates pass.


## Repair cycle 1 (10 Nov 2026)

Review findings addressed:

- **H1a** — the page filters `dismissed` patterns out of `visibleGroups`; a reload no longer renders them. The just-dismissed pattern keeps the undo banner until undo or the next load. Page test: `frontend/src/app/coach/readiness/__tests__/page.test.tsx`.
- **H1b** — `derive_patterns` re-derives each non-dismissed pattern's same group x dimension over its assessed history with the newest 1..n sessions removed (latest 3 each time, same kind rule and fingerprint). A match in `dismissed` sets `seen_again=True`. Added `seen_again: bool = False` to `Pattern` and `PatternRead`; the card shows "Seen again since you dismissed it". Deviation from the P4 plan: this field is required by AC05 but was not in the original plan/contract list.
- **M1** — named test `test_existing_progress_trend_unchanged` added; it proves `get_progress` output is identical with the new snapshot fields at defaults and at explicit values.
- **M2** — dismiss validates `^[0-9a-f]{64}$` (422 `invalid_input`), requires a currently derived fingerprint (404 `not_found`), and catches `IntegrityError` so a duplicate insert is idempotent. Tests cover all three.
- **L1** — `GET /patterns/{fingerprint}/why` with the flag off returns 403 `disabled`.
- **L2** — `Why?` and the dismiss/undo control moved to the card header's right side; "Older patterns (N)" is a `<details>` inside each group.
- **L3** — `PatternGroup` title-cases `role_family` as well as `interview_type`.

Named tests are listed separately from extra tests below.

Named tests (plan P4 table): `test_attempts_in_one_session_do_not_recur`, `test_difficulty_not_in_group`, `test_contract_versions_never_merge`, `test_latest_three_kept_regardless_of_age_then_marked_stale`, `test_dismissal_reappears_on_new_support`, `test_trend_labels_respect_difficulty`, `test_load_learning_snapshots_all_groups_and_unspecified_role`, `test_load_learning_snapshots_excludes_sessions_being_deleted`, `test_why_is_deterministic_and_uses_stored_excerpts_only`, `test_existing_progress_trend_unchanged`, `PatternCard.test.tsx`.

Extra tests added in this repair: `test_dismiss_rejects_invalid_fingerprint`, `test_dismiss_unknown_fingerprint_returns_not_found`, `test_dismiss_is_idempotent`, `test_why_flag_off_returns_disabled`, page test `does not render a dismissed pattern after reload`, card test `says when a new support set follows a dismissal`.

Repair gates:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_patterns.py \
    tests/test_repositories/test_load_learning_snapshots.py \
    tests/test_routers/test_coach_patterns_router.py
17 passed in 1.49s

$ python -m pytest -q --no-cov tests/test_services/test_coach_patterns.py \
    tests/test_repositories/test_load_learning_snapshots.py \
    tests/test_routers/test_coach_patterns_router.py \
    tests/test_services/test_coach_conversational_progress.py \
    tests/test_repositories/test_conversational_session_repository.py tests/runtime
635 passed, 1 skipped in 146.42s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness \
    src/components/coach/conversation/__tests__/ConversationalProgress.test.tsx \
    src/components/coach/conversation/__tests__/ConversationalReport.test.tsx
19 passed (6 files)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check <changed files>
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```

Ready for review: yes.
