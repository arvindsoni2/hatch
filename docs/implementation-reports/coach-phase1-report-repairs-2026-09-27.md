# Coach Phase 1 readiness repairs: Repair B checkpoint

Execution date: 27 September 2026.

## Scope and status

Repair A PR #69 was confirmed merged before this branch started. This checkpoint implements approved Tasks 3–5: readable report contracts, populated deterministic analytics, and actual report dispatch/recovery. It does not complete the nine-task repair plan, enable rollout, or authorize Coach Phase 2.

All implementation and both review passes were inline, without subagents, as requested. The user has authorized pushing this checkpoint and creating a review PR against `main`, not merging or deploying it. The full tracked V6 specification (7,358 lines) was reread before publication; its SHA-256 remains unchanged. Human review and merge remain required. No rollout enablement or production data mutation is included.

| Baseline | Value |
|---|---|
| Base / merged Repair A | `805a6dd24364892b7e2fbf5a2426f429bd68d8bb`, `origin/main`, PR #69 |
| Branch / target | `fix/coach-phase1-report-repairs` / `main` |
| Checkout | `.worktrees/coach-phase1-report-repairs` |
| Task 3 commit | `e37ea7024beceefccdc5446bf6d9004537250e8f` |
| Task 4 commit | `1653c59a6a68a74c005de71bd74c3e0ae92082d8` |
| Task 5 commit | `bc8cd377d7343fb7c91dc340383eb553cb83ebf4` |
| Publication follow-up | V6 audit-event corrections and fresh verification; final commit/PR recorded in the handoff |
| Migration head | `z3a4b5c6d7e8`; no migration introduced or changed |
| Rollout default | `HATCH_COACH_CONVERSATIONAL_ENABLED = false`, unchanged |
| V6 SHA-256 | `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8` |
| Architecture v8 SHA-256 | `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36` |
| Foundation v2 SHA-256 | `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0` |

The approved repair plan supersedes the obsolete original integration-branch topology because Phase 1 and Repair A are already merged into `main`; V6 remains the technical authority. The root checkout, unrelated untracked review report, and user PDF remain untouched.

## Implemented behavior

### Task 3: Report read contract and current retention

- All nine counts are required and nonnegative: planned total/answered/skipped, follow-ups asked/answered, accepted attempts, retries, unavailable attempts, and presented hints. Counts derive from persisted lifecycle facts, not only scored contributors.
- Report reads use one SQL statement to capture analytical JSON, activity/retention versions, and current attempt retention. Column projections bypass stale ORM identity-cache entries.
- The retention overlay contains attempt identity, audio policy/state, transcript retained/deleted/unavailable state, and cleanup retryability. It exposes no media URI, content hash, transcript body, or source path.
- Actual explicit audio deletion changes the live overlay and retention version without changing stored analytics or activity version. Concurrent cleanup/read tests verify overlay/version coherence.
- The strict read schema rejects missing/unknown analytical fields. GET returns canonical version headers and `Cache-Control: no-store`; reading a completed report creates no job or model call. Legacy routing remains intact.
- Frontend API interfaces mirror required counts, analytical projections, and retention metadata. Product report/progress UI changes are deliberately not included.

### Task 4: Complete deterministic analytics

- Immutable inputs copy accepted-answer levels, counts, reflection, question projections, and evidence findings. Contributions require accepted, owned, current evaluations and matching current transcript pointers. Deleted sources, foreign/stale evaluations, and orphan follow-up contributions are excluded.
- Existing named-level root-bundle aggregation, lower median, and ordered readiness thresholds remain authoritative; unavailable inputs do not acquire fabricated scores.
- Reports now contain deterministic strengths, one or two weakest assessed improvement priorities, separate unassessed areas, question summaries, evidence review items, practice suggestions, and contributor/count/adjustment diagnostics.
- Evidence findings require selected session evidence IDs, valid typed statuses, and matching code-point spans in the current transcript. No raw evidence snapshots or private source paths are copied into report diagnostics.
- Optional narrative enrichment is not introduced. Deterministic actions never invent results or metrics; no model output can alter protected analytics in this implementation.
- The builder validates the full consumer schema before publication, then excludes report-state and live-retention overlays from persisted analytical JSON. Invalid analytical projections fail before an unreadable report can publish.

### Task 5: Durable ownership, production execution, and recovery

- All four claim reasons use mandatory post-commit production dispatch: initial completion, manual retry, transcript-deletion rebuild, and reflection-update rebuild. Optional callbacks are separate and invoked only once; idempotent command replay does not create another job.
- Before commit, the existing generic job stores a content-free frozen claim containing session ID, original activity version, build reason, and job ID. A worker opens a fresh database session and accepts only matching persisted authority.
- The original report-start timestamp bounds worker execution and publication. Publication atomically updates the matching session/job/event under activity, job, reason, state, experience, deletion, and deadline fences. Old workers cannot publish or fail replacement owners or hidden sessions.
- On build/publication failure, the worker rolls back first, then records a fenced terminal failure in a clean transaction. SQL NULL physically clears report JSON; Python JSON-null semantics are not mistaken for SQL NULL. Worker messages and job errors remain stable and content-free.
- Lost dispatch, terminal jobs, expired claims, missing generic jobs, and malformed frozen metadata recover through startup/live/report-read/job-poll reconciliation. Recovery fails the current expired shell; it never reconstructs worker authority or automatically creates a retry job.
- Initial failures become an explicit-retry recoverable error. Completed-session rebuild failures keep coarse and conversational state completed. Initial retry requires the matching registered retryable report failure, not missing/non-retryable/unrelated errors.
- Recovery failure events identify their origin as `reconciler`; worker failures retain `worker`. Successful transcript/reflection rebuilds emit `report_rebuild_completed`, while initial/manual completion retains `report_completed`. Fallback event selection remains unchanged.
- Shared export snapshots now use fresh report/retention capture and a fresh SQL version recheck. JSON and Markdown retain the live retention overlay and canonical Hatch version headers; legacy Coach header aliases remain. Full evidence-aware export behavior is still Task 8.

## Contract traceability

Commands run from `backend`, with `UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov` prefixed to the listed test paths. Local logs are under `.superpowers/sdd/2026-09-26-coach-phase1-readiness-repairs/`; they are ignored verification scratch, not release artifacts.

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §§27.7–27.12 readable exact counts and live overlay | Real builder/persist/GET returned HTTP 409: 2 expected failures; strict malformed-count regressions | `schemas/coach_conversation.py`, repository, conversation router, `frontend/src/lib/api.ts` | `tests/integration/test_coach_report_privacy_flow.py tests/test_routers/test_coach_conversation_router.py` | Task 3: 281 passed; actual audio deletion and 20 concurrent reads covered |
| §§27.1–27.10 deterministic populated analysis and priorities | Missing analytical arrays/counts: 6 failures; orphan follow-up, evidence status and missing dimension: 3 more | `coach_conversational_report.py`, repository, schemas, API types | `tests/test_services/test_coach_conversational_report.py tests/integration/test_coach_report_analytics.py tests/integration/test_coach_report_privacy_flow.py tests/test_routers/test_coach_conversation_router.py` | Task 4: 300 passed; populated accepted/current-source fixture, unavailable/unaccepted/deleted/stale exclusions |
| §§21.10, 27.11–27.12, 29.7–29.8 persisted authority and real dispatch | 11 production-flow failures after correcting synthetic event sequencing; actual commands never completed report jobs | `coach_report_queue.py`, commands, report service, repository | `tests/integration/test_coach_report_dispatch.py tests/test_services/test_coach_conversational_report.py tests/test_services/test_coach_reconciliation.py tests/test_routers/test_coach_conversation_router.py` | All four actual command→worker→read flows pass; no test-only completion callback |
| §§21.10, 27.11–27.12 rollback, loss, expiry and deletion fencing | Lost-dispatch/missing-job 2 failures; corrupt metadata 3; hidden initial claim 1; invalid producer projection 1 | Queue, repository, reconciliation, report router/service | Same dispatch suite plus security tests | Stable failure after real SQLite publication trigger; no raw-canary log leak; explicit retry, replay, stale activity/replacement/deletion cases pass |
| §9.9 initial report retry admission | Missing, non-retryable and unrelated errors incorrectly admitted retry: 3 expected failures | `coach_conversation_commands.py` | `tests/integration/test_coach_report_dispatch.py -k initial_report_retry_requires` | All three rejected with no job creation; valid report retry covered by actual dispatch tests |
| §§11.1, 11.3 audit origin and rebuild completion | Three real recovery flows emitted `worker`, not `reconciler`: 3 failures / 1 pass. After origin repair, two successful rebuilds emitted initial-completion event: 2 failures / 6 passes | Repository, reconciliation | `tests/integration/test_coach_report_dispatch.py` | 22 passed in 5.89s; initial/manual versus rebuild event and worker/reconciler origin assertions; `pr-event-actor-red.log`, `pr-event-completion-red.log`, `pr-event-green.log` |
| §§27.7, 27.12; §29.12 shared export version/retention boundary | Cached export version accepted: 1 failure; renderer omitted live overlay: 2 failures | Repository, `coach_report_export.py` | `tests/test_services/test_coach_report_export.py tests/integration/test_coach_report_privacy_flow.py tests/security/test_coach_conversational_dast.py` | Fresh version check, current JSON/Markdown overlay, canonical headers and unchanged private-key exclusions pass; not full Task 8 acceptance |

## Verification evidence

- Baseline: **287 passed**.
- Task 3 full backend: **3,797 passed, 2 skipped, 17 warnings in 331.30s**. This predates a strengthened audio fixture; final focused/checkpoint runs include that fixture.
- Task 4 full backend: **3,806 passed, 2 skipped, 17 warnings in 330.83s**.
- Pre-final Task 5 backend: **3,826 passed, 2 skipped, 18 warnings in 333.09s**. This predates the retry-admission repair and is not final-source evidence.
- Superseded final-code run before the unit-isolation fixture correction: **1 failed, 3,828 passed, 2 skipped, 18 warnings in 386.46s**, exit 1; artifact `repair-b-final-full.log`. The existing unchanged `test_whole_run_deadline_flushes_partial_progress` did not produce a `whole_run` timeout entry. Its real 8ms/10ms limits can expire between iterations while still correctly returning `incomplete_deadline`. The runner path does not use the new report builder/queue. Unchanged diagnostic rerun: `env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov tests/benchmarks/coach/test_runner.py` → **6 passed in 0.37s**, exit 0; artifact `benchmark-timeout-diagnostic.log`. This unsuccessful run is not counted as green verification.
- Final focused backend: **470 passed in 44.43s**, exit 0. Command: `env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov tests/integration/test_coach_report_dispatch.py tests/integration/test_coach_report_analytics.py tests/integration/test_coach_report_privacy_flow.py tests/test_services/test_coach_conversational_report.py tests/test_services/test_coach_reconciliation.py tests/test_services/test_coach_report_export.py tests/test_routers/test_coach_conversation_router.py tests/security/test_coach_conversational_security.py tests/security/test_coach_conversational_dast.py`. Artifact: `task-5-final-focused.log`.
- Existing command-test isolation was extended to suppress report wake-ups, matching its existing attempt/audio handoff boundary. Real report workers remain enabled in integration tests. Verification: `env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py -W error::RuntimeWarning` → **99 passed in 16.70s**, exit 0; artifact `task-5-command-isolation.log`. This fixes a test-harness coroutine warning/default-database escape, not report production behavior.
- Final-tree full backend: **3,829 passed, 2 skipped, 17 warnings in 344.36s**, exit 0. Command: `timeout 900s env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov tests --tb=short`; artifact `repair-b-verified-full.log`. The formerly failing benchmark assertion passes unchanged. No warning names the new report coroutine; remaining warnings concern existing legacy/mock coroutine handling, dependency/deprecation and model argument configuration. Provider retry/fallback tests are not configured-model acceptance evidence.
- Existing skips: `tests/test_tools/test_embedder.py` and `tests/test_tools/test_semantic_scorer.py` use module import-skip for sentence-transformers. An explicit `-rs` rerun reports **2 skipped**, exit 5 (no collected runnable tests), with the existing message `sentence-transformers not installed`; artifact `embedding-skip-reasons.log`. This diagnostic is not counted as passing coverage. The optional telemetry probes separately pass **3 tests in 0.67s**; no telemetry skip is being assumed.
- Frontend type check: `npm run type-check`, exit 0. Artifact: `repair-b-typecheck.log`.
- Frontend suite: `npm test` → **100 files / 649 tests passed in 55.01s**, exit 0. Artifact: `repair-b-frontend-tests.log`. Neither this nor type checking constitutes browser acceptance or a production build.
- Touched-file `ruff check`, `git diff --check`, `python scripts/check_docs.py`, and `python scripts/check_readme_contract.py`: passed; documentation checks are repeated on the finalized report.
- Migration-head inspection: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"` → `['z3a4b5c6d7e8']`.

Tests use isolated temporary file-backed SQLite databases, synthetic candidates/content, and owned temporary media. SQLite suites execute outside the filesystem sandbox because they stall inside it. No destructive or active security test targets production or shared user data. Tool versions: Python 3.14.7, uv 0.11.15, pytest 8.3.3, SQLAlchemy 2.0.50, Ruff 0.15.15, Node 22.23.2, npm 10.9.8. Installed frontend TypeScript/Vitest dependencies were reused; no dependency changes were made.

## Review and security disposition

### Publication verification after the audit-event repairs

- Final-source backend: `timeout 900s env UV_CACHE_DIR=/tmp/jobpilot-uv-cache uv run python -m pytest -q --no-cov tests --tb=short` → **3,829 passed, 2 skipped, 17 warnings in 376.60s**, exit 0; `pr-final-backend.log`. This includes the corrected audit events and strengthened assertions.
- Pre-audit publication baseline: **3,829 passed, 2 skipped, 17 warnings in 430.29s**, exit 0; `pr-preflight-backend.log`. It predates the audit repairs and is not final-source evidence.
- Frontend preflight: **1 failed, 648 passed in 63.99s**, exit 1; `pr-preflight-frontend.log`. Calendar synchronization diagnosis and unchanged reruns are recorded below.
- Final frontend: `npm run type-check` → exit 0; `npm test` → **100 files / 649 tests passed in 58.27s**, exit 0; `pr-final-typecheck.log`, `pr-final-frontend.log`.
- Final touched-file Ruff, documentation and README validators, and whitespace checks passed. Migration head remains `z3a4b5c6d7e8`; rollout default remains false. Specification hashes were recomputed and match the baseline table.

### Inline review findings

Specification/security review preceded code-quality review. Reviews covered deletion racing publication, committed claims losing wake-up, populated producer→read/export compatibility, strict fields versus empty defaults, malformed job metadata, source/version ownership, idempotency, explicit retry, and content-free failure logs. Review discoveries were reproduced RED before repair and are mapped above.

The publication V6 reread found two audit-contract mismatches, reproduced before repair: reconciler-originated report failures were marked as worker-originated, and completed-session rebuilds used the initial-report completion event. The follow-up changes only event origin/selection, preserving job ownership, atomic publication, fallback selection, and stale/deletion fences. Subsequent inline quality review inspected both callers, the shared event validation, and actual four-reason completion/failure assertions.

Author self-review is weaker than independent review. No independent reviewer, browser acceptance, configured-model acceptance, benchmark release gate, or complete Phase 1 release approval is claimed. Human review/merge remains required before Repair C branches from updated `main`.

No critical/high or undispositioned medium finding remains within this checkpoint's implemented boundaries. Existing progress/UI/evidence-export omissions retain their approved Repair C owners; they remain Phase 1 readiness blockers, not waived requirements. Real restart/browser/model acceptance remains Task 9. Existing generic async-job logging/runtime architecture is not redesigned here; new report-worker messages and injected private-error canaries were checked separately.

## Rulings made

1. Use the approved repair plan and current `main`, not the obsolete original integration topology. Technical V6 unchanged. Cost if wrong: correct the PR target.
2. Execute and review inline without subagents, as requested. Cost if wrong: author review has weaker independence.
3. Keep deterministic wording without optional narrative enrichment (§27.10). Cost if wrong: optional wording remains absent, not incorrectly scored.
4. Use a separate populated analytics integration module and align frontend types during Task 4. Cost if wrong: test-file organization differs from the plan.
5. Freeze ownership in existing `AsyncJob.result_json` before commit. Cost if wrong: an internal content-free pending-job payload shape differs; no schema/public version change.
6. Use V6's `report_rebuild_failed` event and existing registered retryable snapshot-stale code, not invented public events/errors. Cost if wrong: naming needs a later approved contract refinement.
7. Allow reconciliation to fail expired malformed/missing-job shells under a full current-owner fence, never to reconstruct worker authority. Cost if wrong: malformed internal claims require explicit retry instead of silent resumption.
8. Repair shared live export overlays and fresh version rechecks in B without implementing evidence-export Task 8. Cost if wrong: exports gain content-free retention metadata/canonical headers; legacy aliases remain.
9. Leave the unrelated real-clock benchmark assertion unchanged and track its timing sensitivity with Task 9's benchmark-reliability owner. A green unchanged full suite is still required for this checkpoint. Cost if wrong: intermittent CI timing failures may recur before acceptance repairs.

Publication diagnostics also exposed an unchanged Calendar test synchronization race: `AnalyticsCalendarPage.test.tsx` waits for the always-visible Calendar heading, then synchronously asserts the asynchronously loaded empty state. The failed full run showed `Loading Calendar`, not an API failure; the unchanged isolated suite passed 2 tests in 2.34s, and the fresh unchanged full suite passed 649 tests in 58.27s. No unrelated Calendar code or assertion was changed. This intermittent CI risk is disclosed for follow-up; it does not establish browser acceptance or waive Repair B regression requirements.

## Remaining approved work

| Checkpoint | Pending scope |
|---|---|
| Repair B integration | Push/PR authorized and full V6 reread completed; external review and merge remain required |
| Repair C, Tasks 6–8 | Exact compatibility-key/AND-filter selectors; independent per-dimension trends; complete report/progress UI; permitted populated evidence exports with source/provenance/consent and full format/precondition/filename checks |
| Acceptance, Task 9 | Genuine backend process restart, typed/audio browser journeys, production-path benchmark regressions, configured-model evidence, exact V6 A–H acceptance matrix |
| Companion readiness plan | Runtime extraction and Gates R2–R4, followed by acceptance rerun |

Repair C must start from reviewed/merged Repair B, not this unmerged sibling. Phase 2 must not begin based on this partial checkpoint.
