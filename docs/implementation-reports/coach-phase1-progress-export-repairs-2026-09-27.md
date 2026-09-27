# Coach Phase 1 readiness repairs: Repair C checkpoint

Execution date: 27 September 2026.

## Scope and status

Repair B PR #70 was confirmed merged before this branch started. This checkpoint continues the approved repair plan's Tasks 6–8: compatible dimension-level progress, report/progress UI, and permitted evidence-aware export. Tasks 6–7 are implemented and verified; Task 8 remains pending at this interim record.

Base: `aa567e15c9fa6f9a3eae079a7257503c9aea5b4b`, updated `origin/main`. Branch: `fix/coach-phase1-progress-export-repairs`; target: `main`. Worktree: `.worktrees/coach-phase1-progress-export-repairs`. Inline execution only; no subagents. Root checkout, user PDF, untracked readiness report, and prior worktrees remain untouched. No push, merge, deployment, rollout enablement or Phase 2 work is included in this checkpoint.

V6 remains technical authority. Its current SHA-256 is `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`; approved original integration-design SHA-256 is `992f9693d82b5146770e5e002f6f8d7f2485d34716e89d0d6a775662c134ece6`. The approved readiness repair plan supersedes the original branch topology after Phase 1 and Repairs A/B were merged. Full V6 reread before the next PR remains required.

## Task 6: Compatible dimension-level progress

- Exact mode uses only the persisted compatibility key. Filtered mode requires at least one of application ID, role family, role level or interview type; supplied filters combine with AND. Session/company/title selectors and unfiltered requests return canonical selector conflicts.
- Completed, visible conversational reports are partitioned without cross-key aggregation. Deleted/deleting/failed-deletion, invalidated/nonterminal, legacy, missing-key and unreadable/stale analytical snapshots are excluded. Context derives from the persisted session plan, not mutable filter aliases.
- Each dimension uses its most recent three assessed sessions, or two when only two exist. Unassessed entries are skipped. Current/previous levels and trends are independent per dimension/group; opposite nonzero changes are classified as mixed before the latest comparison.
- Strict typed groups include context, ordered history, all seven current/previous/trend mappings, and the latest valid report's strengths, priorities and evidence review. There is no overall-trend substitute or percentage improvement.
- Sessions sort by completion time then ID ascending. Groups sort by latest completion descending and compatibility key ascending. The configured cap applies after grouping; totals are calculated before truncation. Reads use column projections to avoid stale ORM identity-map values and return `Cache-Control: no-store`.

## Contract traceability

Tests run from `backend` with `env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov` before the listed paths. Existing installed Python dependencies are reused without mutation (see the corrected environment diagnostic below). Logs are ignored scratch under `.superpowers/sdd/2026-09-26-coach-phase1-readiness-repairs/`.

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §§28.1–28.5 exact selectors, complete per-dimension projections and ordering | 12 failed / 12 passed: missing maps, illegal exact mode, accepted empty filter, descending key tie, incomplete groups accepted; `task-6-unit-red.log` | `coach_conversational_progress.py`, `schemas/coach_conversation.py` | `tests/test_services/test_coach_conversational_progress.py tests/test_routers/test_coach_conversation_router.py` | Included in 321-pass focused run; two independent trajectories, missing/unassessed history, lookback, complete-group validation |
| §§28.1–28.3, 28.6 real route/filter/cap/privacy behavior | Four selector failures; corrected populated fixture then failed configured cap (20 versus 1); `task-6-route-fixture-red.log` | Repository, conversation router | Same route suite plus `tests/integration/test_coach_report_privacy_flow.py tests/security/test_coach_conversational_security.py` | 321 passed in 7.57s, exit 0; actual AND filters, exact-key response, invalidated/deleting/active/legacy exclusions, headers |
| §§27.11, 28.6 stale source exclusion | A valid-shaped old activity report was counted as a third group; expected two; `task-6-stale-report-red.log` | Repository | Same focused command | RED→GREEN; old analytics are excluded, not relabelled current |

The first route fixture lacked required counts, then needed two analytical root bundles to be genuinely assessed. Those setup failures were corrected before claiming the route's behavioral RED. Existing tests calling obsolete selectors were migrated without removing their filtering, truncation, privacy or conflict assertions.

## Verification and limitations

Fresh merged baseline: **3,829 passed, 2 skipped, 25 warnings in 371.56s**, exit 0; `repair-c-baseline-backend.log`. Merge `aa567e1` has the same source tree as Repair B `ed696e1`. Extra baseline provider connection warnings do not constitute configured-model acceptance.

Task 6 focused: **321 passed in 7.57s**, exit 0; `task-6-final-focused.log`. Full Task 6 backend: **3,847 passed, 2 skipped, 16 warnings in 347.88s**, exit 0; `task-6-full-backend.log`. Existing optional dependency skips and legacy warnings remain disclosed. Synthetic candidates/reports and isolated databases only; no active tests target production or real-user data. This backend has no `pyproject.toml`; the initial `UV_PROJECT_ENVIRONMENT`/`--no-sync` settings do not select a virtualenv here. The runs use existing installed Python dependencies, not a newly installed B-worktree virtualenv. Reproduction from `backend`: `env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov tests --tb=short`.

Frontend pre-UI baseline type-check passed with reused root dependencies. The initial sandbox build failed with webpack errors; the unchanged build outside the sandbox passed, with an existing `AnswerTimer` hook warning. Installed Next.js was 15.5.19 while the merged lock pins 15.5.26. The temporary dependency symlink was removed before a successful worktree-local `npm ci` (661 packages); root dependencies, manifest and lock remain untouched. Locked baseline: 649 tests / 100 files passed in 49.97s.

## Task 7: Complete report and progress UI

- Reports render all nine counts, strengths, priorities, unassessed areas, question summaries, literal evidence findings, practice suggestions and optional reflection. Empty arrays have explicit empty states; unassessed dimensions are not invented priorities. Findings retain persisted claim text/status/action and selected source IDs, with an explicit Hatch source-matching disclaimer; the UI does not slice JavaScript UTF-16 offsets or inject raw source HTML.
- Each compatibility group has its own previous/current/trend table, context, strongest/priority areas, findings and keyboard-accessible report history. Named levels replace neither legacy numeric reporting nor source provenance. No percentage, overall-trend substitute or Mentor action was introduced.
- The existing client Coach page requires a completed conversational context selection. Exact requests contain only the persisted key; application requests contain only a real application ID. Loading, safe error/retry, empty and unlinked-application states are independent of history. Effect cleanup ignores obsolete selection results. Capability discovery preserves existing conversational read access when new-session rollout is disabled. The report's server-fetch architecture is unchanged.
- Existing Hatch styles/tokens/components were retained. React guidance influenced primitive effect dependencies and cleanup guards, not a page-architecture rewrite. Frontend design guidance preserved the product UI, not a landing-page redesign.

RED: five component failures (missing analytical sections/separate dimension tables), three page wiring failures, and a separate conversational-history numeric-score failure. GREEN: nine page/component tests passed; full final-source suite **658 passed / 102 files in 64.84s**, exit 0 (`task-7-final-full-frontend.log`); final type-check exit 0. Three Chromium mocked HTTP UI checks passed in 16.2s (`task-7-browser.log`). Those browser tests are explicitly UI-only, not integrated privacy, restart or configured-model acceptance.

An initial changed-source build passed. A later build failed at trace collection with a missing `.next/.../page.js.nft.json` after a development server was started in the same build directory; the owned server was stopped and the final serialized build passed, exit 0 (`task-7-serialized-build.log`). Existing `AnswerTimer` hook warning and test-suite warnings remain disclosed. Mocked browser routes used a loopback-only unreachable backend, so unrelated shell proxy requests failed locally; no production endpoint was contacted.

Task 7 specification/security review checked required analytical fields, legal selectors, independent groups, named levels, no invented priorities, safe literal rendering and no injected HTML/links. Subsequent quality review checked actual helper/component call sites, primitive effect dependencies/cleanup, accessible native controls/history links and error/retry isolation. No critical/important issue remains in this task's scope. Both reviews were inline author reviews, not independent reviews. No behavior was silently declined; integrated acceptance and full source-export provenance remain explicitly assigned to Tasks 9 and 8 respectively.

Task 8 and the final Repair C review remain pending. Task 9 real restart/browser/configured-model/benchmark acceptance and companion runtime Gates R2–R4 remain readiness blockers. Completion of this checkpoint alone cannot authorize Phase 2.

## Rulings

1. Continue sequentially from updated `main`, not the obsolete original integration topology. Cost if wrong: correct PR target.
2. Execute/review inline under the existing approved V6/repair plan, with no subagents. Cost if wrong: author review has weaker independence.
3. Replace undocumented session/company/title/unfiltered selector aliases with V6's exact key or required broad filter. Cost if wrong: old undocumented callers need migration.
4. Read context from the persisted plan; exclude corrupted/unreadable/stale analytical snapshots rather than fabricate empty scores. Cost if wrong: corrupted reports require repair before appearing in progress.
5. Enforce the configured route cap, rejecting unsupported client limit overrides; invalid limit inputs remain bounded by existing validation. Cost if wrong: undocumented limit callers need migration.
6. Use latest valid report strengths/priorities/findings per group while deriving dimension histories independently. Cost if wrong: historical strengths absent from the latest report are not repeated as latest priorities.
7. Verify against worktree-local locked frontend dependencies without manifest/lock/root changes. Cost if wrong: installation time and disk use only.
