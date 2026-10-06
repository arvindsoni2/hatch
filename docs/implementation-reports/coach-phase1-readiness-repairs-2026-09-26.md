# Coach Phase 1 readiness repairs: Repair A checkpoint

Execution date: 27 September 2026. The filename follows the approved plan date.

## Status and scope

This is **Repair A, Tasks 1–2**, not completion of the nine-task repair plan or authorization to start Phase 2. Implementation and review were performed inline, without subagents, as requested. The approved plan requires sequential review/merge checkpoints before the next repair branches from updated `main`.

Implemented:

- Normal session detail/list, application history, session chains, live/report/diagnostic/progress/export reads exclude deleting and failed-deletion sessions. Legacy sessions remain visible; the privileged privacy endpoint remains available for receipt replay and a new-command deletion retry.
- A deletion claim serializes competing requests, rechecks identical-command replay, rejects unsupported legacy sessions, and cannot replace a live claim. It fences setup and nonterminal attempt generations, clears old claim pointers, and cancels pending/running setup, attempt, evaluation, independent cleanup and report jobs in the same transaction.
- Historical completed report jobs can retain a detached report copy after their session job pointer clears. The claim also scrubs those payloads using the persisted report's exact session identity, without changing foreign or malformed unowned job payloads.
- The existing conversational-job timeout bounds the deletion lease and execution. Receipt retention is independent of the worker lease.
- The route commits the claim before waking the actual worker. The worker opens an independent database session and owns rollback before fenced failure publication.
- Finalization obtains database write ownership under the complete session/state/generation/job/command/token/expiry fence before touching media, verifies ownership/hash, tolerates already-missing owned files, checks removal success, and repeats the fence in the final SQL deletion. Session content cascades physically; successful jobs/receipts complete atomically with database deletion.
- Failure clears claim fields, records safe terminal job/receipt outcomes and increments state/event versions. Expired claims reach the same idempotent failure path through startup discovery, job polling and bounded periodic recovery. Retry requires a new command; old receipt replay preserves the original failure.
- Completed/failed receipt expiry starts at the terminal timestamp. Startup catch-up and daily bounded cleanup preserve live processing receipts. Scheduler registrations replace existing jobs, coalesce and run at most one instance.
- Added temporary file-backed database integration fixtures and actual route/worker/repository tests. Existing reconciliation tests isolate their external model boundary to exercise deterministic degradation rather than contact an unavailable model endpoint.

No production database, user media, rollout setting, schema, provider routing or remote PR/merge was changed. The root checkout, unrelated untracked review report and user PDF are preserved.

## Baseline and authority

| Item | Value |
|---|---|
| Base | `origin/main`, `56e871765d7085a64d5d184b906b445d4bd7ef1b` |
| Branch | `fix/coach-phase1-readiness-repairs` |
| Target | `main`; the approved repair plan supersedes the obsolete integration-branch topology |
| Checkout | `.worktrees/coach-phase1-readiness-repairs` |
| Rollout default | `HATCH_COACH_CONVERSATIONAL_ENABLED = false`, unchanged |
| Schema | Single migration head `z3a4b5c6d7e8`; no migrations introduced or modified |
| V6 SHA-256 | `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8` |
| Architecture v8 SHA-256 | `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36` |
| Foundation v2 SHA-256 | `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0` |

The V6 deletion schema calls its timestamp `deletion_started_at`; the failure paragraph says `deletion_claimed_at`. The repair uses and clears the existing schema field rather than invent a second timestamp/migration. Tasks 1–2 share one Repair A commit because their route/repository transaction boundaries are coupled; their RED/GREEN evidence remains separate.

## Contract traceability

Commands below run from `backend`. Logs are retained locally under `.superpowers/sdd/2026-09-26-coach-phase1-readiness-repairs/`; this ignored scratch directory is not a release artifact.

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §29.9 hidden reads and prior-work fencing | Initial visibility/generation regression: 3 failures; application history still listed deleting child; independent cleanup job remained pending | `session_repository.py`, `conversational_session_repository.py`, `routers/coach.py`, `routers/coach_conversation.py` | `uv run python -m pytest -q --no-cov tests/integration/test_coach_report_privacy_flow.py` | Included in 434-test focused GREEN; independent-stage RED and subsequent GREEN retained |
| §29.9 idempotent/competing claim and supported experience | Identical concurrent replay raised receipt UNIQUE error; legacy claim incorrectly succeeded | `conversational_session_repository.py` | Same integration command | Separate database-session replay/competition and legacy rejection pass |
| §29.9 removal of derived report content | A historical completed job retained its report/reflection after deletion was claimed | `conversational_session_repository.py` | Same integration command | Detached-copy RED recorded; owned cleanup and foreign/malformed preservation regression added |
| §§21.10, 29.9 real dispatch, bounded leases, stale finalization | Actual route never completed; stale failure mutated receipt/job; expired claim deleted content | `coach_privacy_queue.py`, `coach_privacy.py`, repository and conversation router | `uv run python -m pytest -q --no-cov tests/integration/test_coach_deletion_recovery.py` | 20 passed, including final adversarial additions |
| §29.9 transaction failure and owned physical deletion | SQLite delete trigger error was swallowed; missing owned media incorrectly failed | Repository and privacy worker/service | Same deletion integration command | SQL rollback/fenced failure, nine content-table cascades, actual media removal/hash mismatch, foreign paths/symlinks and log-canary checks pass |
| §§21.10, 29.9 recovery and receipt lifecycle | Expiry reconciliation returned zero; job polling missed claim; scheduler lacked periodic recovery; cleanup purged live processing receipt | `coach_reconciliation.py`, `coach_privacy_queue.py`, `main.py`, repository | `uv run python -m pytest -q --no-cov tests/test_services/test_coach_privacy.py tests/test_services/test_coach_reconciliation.py tests/integration/test_coach_deletion_recovery.py tests/security/test_coach_conversational_security.py` | Recovery and scheduler assertions included in focused GREEN; completion replay/new-command retry verified |

## Verification evidence

- Baseline privacy/router tests: **271 passed**.
- Initial Task 1 RED: **3 expected assertion failures**; initial GREEN: **274 passed**.
- Initial Task 2 RED: **9 expected failures**; initial GREEN: **13 passed**.
- Additional reproductions: swallowed SQL error, duplicate receipt race, unsupported legacy deletion, hidden application history, missing polling/periodic discovery and independent stage-job cancellation. Each was observed failing before its application repair.
- Final focused Repair A regression: **439 passed in 43.68s**. Command: `uv run python -m pytest -q --no-cov tests/integration tests/test_services/test_coach_privacy.py tests/test_routers/test_coach_conversation_router.py tests/test_services/test_coach_reconciliation.py tests/security/test_coach_conversational_security.py`. Log: `repair-a-complete-green.log`.
- Additional deletion/adversarial suite: **20 passed in 3.38s**, including four later test cases; no subsequent application-code change.
- Earlier broader backend run: **3,786 passed, 2 skipped, 16 warnings in 388.49s**. It started before the last application review fixes and is not the final-tree result.
- Final-tree full backend run: **3,793 passed, 2 skipped, 17 warnings in 327.02s; exit 0**. Command: `uv run python -m pytest -q --no-cov tests --tb=short`, bounded at 600 seconds. Log: `full-backend-privacy-final.log`. Warnings concern existing legacy/mock background coroutines and model-argument configuration; none names the new privacy worker. Existing provider retry/fallback tests are not configured-model acceptance evidence.
- Touched-file `ruff check`, `git diff --check`, and `python scripts/check_docs.py`: **passed**.
- Tests use temporary synthetic databases/media and require execution outside the filesystem sandbox because SQLite-backed tests stalled inside it. Earlier 120s/300s timeouts are retained as unsuccessful runs, not counted as passing evidence.

## Inline review dispositions

Specification/security review preceded code-quality review. Self-review found and repaired the duplicate receipt race, legacy-experience acceptance, application-history/chain visibility, lost-dispatch polling/periodic discovery, independently owned stage/evaluation cancellation and detached historical report payloads. The final failure/logging review verifies stable content-free worker messages and protected media remaining untouched.

Author self-review is weaker than independent review. No independent reviewer, configured-model acceptance, browser acceptance or release approval is claimed. An external review/merge decision remains required at this sequential checkpoint.

Repair A's implemented privacy contracts pass inline specification/security and subsequent code-quality review, and final backend verification is green. The checkpoint is ready to submit for review, not already merged or approved for release. The local commit SHA is recorded in the handoff and execution ledger; no remote mutation has been performed.

Set aside explicitly:

- Report payload/dispatch correctness, complete analytics/progress/UI/export: separate approved Tasks 3–8, not repaired by this privacy checkpoint.
- A genuine backend process restart, typed/audio browser journeys and configured-model standard-profile acceptance: Task 9. Invoking startup discovery against a fresh database session proves that discovery path, not a process-restart journey.
- Runtime extraction and Gates R2–R4: companion readiness plan; unchanged here.
- General generic-job logging/runtime design: not redesigned in Repair A. The new privacy worker logs no raw exception messages or media paths; existing runtime architecture remains independently tracked.

## Remaining approved work

| Tasks | Pending scope |
|---|---|
| 3–5, Repair B | Strict readable report/count/retention contract; complete deterministic analytical projections; real dispatch/recovery for all four report build reasons |
| 6–8, Repair C | Exact-key, per-dimension progress; complete product report/progress UI; permitted populated evidence export |
| 9, acceptance | Real process restart and typed/audio journeys, production-path benchmark regressions, configured-model evidence and exact V6 A–H acceptance matrix |

B1 implementation is addressed by Repair A, subject to review. B2–B4 and B8 remain open for the work above. Phase 2 must not begin on the strength of this partial checkpoint.

## Task 9 acceptance addendum — 5 October 2026 (in progress)

The Repair A–C implementation checkpoints have since merged as PRs #69–#71. This addendum records new application-path evidence from the isolated `fix/coach-phase1-acceptance` branch based on `origin/main` `7ec59bc6aa92932c0c7a2fce6f6420ff29605a4e`. It is **not** a completed Task 9 or a release approval. V6 SHA-256 remains `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`; the approved integration design SHA-256 is `992f9693d82b5146770e5e002f6f8d7f2485d34716e89d0d6a775662c134ece6`.

The actual app path exposed two defects absent from direct-router tests. Both have RED reproductions and GREEN regressions on this branch:

1. The legacy report router won a duplicate `GET /api/coach/sessions/{id}/report` registration and returned HTTP 500 when validating a conversational report as numeric legacy feedback. Version-aware router precedence now serves both formats. Real-process tests verify a conversational versioned read and an unchanged legacy numeric response.
2. After `request_coaching`, the real live endpoint returned HTTP 409 because persisted coaching metadata contained three fields beyond the strict five-field display schema. A bounded stored schema now validates the full value and checks its answer level against the current evaluation before projecting only display fields. A tampered-level regression rejects stale metadata.

Review of the shared report URL found one further legacy compatibility regression: a missing session changed from HTTP 404 to the conversational HTTP 409. `test_missing_legacy_report_session_keeps_not_found_response` failed with 409 before the fix and passed with 404 and the original safe body after the version-aware reader delegated absent sessions to the legacy service. The focused four-case report-dispatch run passed after that fix. The route remains shared: runtime selects the versioned reader first; OpenAPI's single path still describes the legacy numeric report rather than a discriminated legacy/conversational response. This documentation mismatch is a known API-contract limitation for generated clients, not evidence that the two response shapes are interchangeable.

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §0.6, §42.6 / AC-29 — preserve legacy report and dispatch conversational report | Real-process conversational GET returned 500; missing-session regression returned 409 instead of 404 | `backend/app/main.py`, `backend/app/routers/coach_conversation.py` | `cd backend && pytest -q --no-cov tests/test_routers/test_coach_router.py::test_missing_legacy_report_session_keeps_not_found_response tests/test_routers/test_coach_router.py::test_get_session_report_with_mock_service tests/integration/test_coach_restart_flow.py::test_real_app_routes_conversational_report_to_versioned_reader tests/integration/test_coach_restart_flow.py::test_real_app_preserves_legacy_numeric_report_on_shared_url` | 4 passed, exit 0, 22.85s; numeric report and 404 preserved |
| §26.3–26.5, §30.3 / AC-21 — current coaching review projects strict display data | Scenario C live GET returned 409 after coaching; stored metadata exceeded display schema | `backend/app/schemas/coach_conversation.py`, `backend/app/services/coach_live_view.py` | `cd backend && pytest -q tests/test_services/test_coach_live_view.py` | RED→GREEN and tampered-level rejection; included in full-suite checkpoint below |
| §37.14–37.15 / AC-02, AC-19, AC-20; Scenarios A,C — recover browser authority and accepted attempt | Frontend unit transient-409 test failed before retry; real-browser C stalled on disabled retry control before stored-schema repair | `frontend/src/components/coach/conversation/ConversationSession.tsx`, `frontend/e2e/coach-conversation-integrated.spec.ts` | `cd frontend && npx playwright test --config=playwright.coach-integrated.config.ts` | A/C and backend-path B: 4 passed, 58.0s; B remains partial |
| §38, §42.4 / AC-22 — persisted end-to-end report benchmark | Report builder disconnect and malformed output regressions failed before persistence path was added | `backend/benchmarks/coach/production_adapter.py`, `backend/tests/benchmarks/coach/test_conversational_end_to_end_report.py` | `cd backend && pytest -q tests/benchmarks/coach/test_conversational_end_to_end_report.py` | 3 focused regressions passed; deterministic smoke 32/32, no model-scope attempts |
| §21.10, §29.9, §37.15 / Scenario F — real-process reconciliation and deletion | Harness import absent before implementation; old claim remained pending without restart path | `backend/tests/integration/coach_app_process.py`, `backend/tests/integration/test_coach_restart_flow.py` | `cd backend && pytest -q --no-cov tests/integration/test_coach_restart_flow.py` | Real PID restart, report/deletion claim recovery, owned-media removal and receipt exercised; F remains partial without in-flight audio restart |

The benchmark end-to-end adapter now persists two accepted synthetic attempts, builds and stores a production report, reopens the database, and validates the repository's strict report read snapshot. Three focused regressions cover success, disconnected builder, and malformed report. The final deterministic contract-smoke run (`d3b3b55fc083499ab200df7610d2f867`, `cd backend && uv run python -m benchmarks.coach smoke --suite benchmarks/coach/fixtures/conversational_v1 --profile contract-smoke --output-root /tmp/hatch-coach-task9-contract-final-20261001`) produced 32/32 terminal cases, a valid harness and zero blocking gates. Database/profile protected-state hashes matched before and after. It made zero model-scope attempts and therefore does **not** establish configured-model quality.

| V6 §37.15 scenario | Current application-path evidence | Disposition |
|---|---|---|
| A — Typed interview | Real browser + real Coach API: setup, six typed answers, acceptance, persisted named-level report and rendered report page; combined run passed | Pass for deterministic provider-boundary journey |
| B — Voice/default deletion | Real API upload of generated valid WebM, provider-boundary ASR, evaluation, retained transcript and physical default media removal pass; microphone permission, silence prompt and keep-speaking browser steps remain untested | Partial |
| C — Retry | Two real browser journeys request coaching, retry, choose attempt one or two, finish six questions and assert the chosen ID in the persisted report; combined run passed | Pass for deterministic provider-boundary journey |
| D — Adaptive follow-ups | Existing policy tests only; no complete two-follow-up/third-rejection app journey | Pending |
| E — Transcript edit race | Existing stage/fence tests only; no complete late-worker app journey | Pending |
| F — Restart recovery | Real backend PID restart reconciles persisted report/deletion claims; in-flight audio restart not yet exercised | Partial |
| G — Degraded AI | Existing stage tests only; no complete evaluator-unavailable app journey | Pending |
| H — Legacy regression | Real-process numeric report preserved and legacy router snapshot/video tests pass; full create/submit/report journey not yet exercised here | Partial |

The combined local browser command was `cd frontend && npx playwright test --config=playwright.coach-integrated.config.ts`: **4 passed in 58.0s** after both model and ASR test doubles were installed. Its server used a temporary SQLite database and media root. The real process harness additionally verifies PID change, report/deletion claim startup reconciliation, physical owned-media removal and replayable deletion receipt on synthetic data. Frontend `npm test -- --reporter=dot`: **661 passed**; `npm run type-check` and `npm run build`: **passed** (build retains an unrelated existing `AnswerTimer` hook warning). Full backend `cd backend && pytest -q`: **3,914 passed, 2 skipped, 80.12% coverage in 463.87s; exit 0**. The earlier timing-sensitive whole-run benchmark test passed when this run was isolated from heavy concurrent work.

After that first full-suite checkpoint, the new Scenario B backend-path test passed using a generated 0.25-second WebM tone. Both LLM and ASR are now replaced only at the test provider boundaries, and the test backend sets Hugging Face/Transformers offline flags. The initial RED run accidentally invoked the installed faster-whisper provider, made unauthenticated requests to Hugging Face for model files, and failed on the expected transcript/deletion assertion. No real candidate audio or credentials were used; the attempted download may have populated the local model cache. A 464 MB `faster-whisper-small` cache directory exists locally; its pre-run size is unknown and it was not removed. The test was corrected before the passing rerun, which made no Whisper/Hugging Face requests. This is recorded as test-harness scope, not configured-model acceptance.

Post-ASR-fixture static checks passed: frontend `npm run type-check`, backend `ruff check app/ tests/ benchmarks/coach/production_adapter.py`, and `python scripts/check_docs.py`.

Final pre-PR checkpoint on 5 October 2026: `cd backend && pytest -q` passed **3,915 tests, 2 skipped, 133 warnings, 80.13% coverage, exit 0 in 539.26s** after the missing-session route fix and ASR fixture. Log: `/tmp/hatch-coach-acceptance-backend-20261005.log`. `cd frontend && npm test -- --reporter=dot` passed **661/661 tests in 102 files**, exit 0; it emitted existing unrelated React `act(...)` warnings. `npm run type-check` and `npm run build` exited 0; build emitted the pre-existing `AnswerTimer` dependency warning. Ruff, docs validation and staged diff checks passed.

The first final-tree Playwright attempt failed before any test assertions because `next dev` exhausted file watchers (`EMFILE`); the next attempt used `next start` but found that the aborted dev run had removed the production build ID. The test config now runs `npm run build && npm run start` against the same disposable backend and provider doubles. `cd frontend && npx playwright test --config=playwright.coach-integrated.config.ts` then passed **4/4 in 1.9 minutes**, exit 0; log: `/tmp/hatch-coach-acceptance-browser-built-20261005.log`. The standalone-output warning from Next did not prevent the four real-browser journeys. Neither failed attempt is counted as passing evidence.

Inline V6/security compliance review found the PR's changed contracts mapped to RED/GREEN tests, unchanged disabled rollout default, no Phase 2 entities and only synthetic local candidate/media data. The complete §37.15 A–H and configured-model gates remain explicitly open; therefore this is an incremental PR verdict, not a release verdict. Subsequent code-quality self-review found and fixed the missing-session legacy 404 regression. No Critical/High issue was identified in this scoped self-review; the shared OpenAPI path's numeric-only documentation is a medium compatibility limitation explicitly deferred to a follow-up before generated conversational clients or release promotion. Review independence is limited because the user requested inline execution without subagents; repository-owner review remains required before merge. No production or shared-environment security scan was run.

No approved configured provider/model endpoint or metadata was available for the required standard-profile synthetic benchmark; no model-scope quality or cost gate, owner acceptance, security disposition or Phase 2 authorization is claimed. Task 9 remains open. Companion architecture Gates R2–R4 and the tracked Phase 2 specification/approval also remain independent prerequisites.

## Acceptance continuation — 6 October 2026

PR #72 merged at `f8fe14d7e665d34ebf3852c01507dc32f277c954` with CI and CodeQL checks successful. The follow-up branch starts at that exact `origin/main` commit. V6 and integration-design SHA-256 values remain those recorded above. This slice adds no production behavior, rollout change or Phase 2 code; it closes two previously unexecuted deterministic application-path scenarios with real HTTP dispatch and disposable SQLite/media.

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §37.15 Scenario H, §42.6 — legacy open, submit, numeric report without conversational aggregation; AC-29 before/after baseline parity remains separate | Initial real-process run waited on a configured local model retry; after provider isolation, strengthened numeric assertion failed because the synthetic evaluator was unavailable and score was null | `backend/tests/integration/test_coach_legacy_journey.py`, `coach_legacy_test_server.py`, `coach_app_process.py` | `cd backend && pytest -q --no-cov --tb=short tests/integration/test_coach_legacy_journey.py` | One real-process test passed: opened a pre-existing legacy session, submitted via legacy route, ended, read a 7.0 numeric report, and found no conversational transcript/evaluation rows. This follows Scenario H's **open**, not a new legacy-create journey. |
| §37.15 Scenario G, §42.4 / AC-28 — evaluator failure cannot invent a level or discard transcription | With the normal synthetic evaluator, the new real-audio test failed because evaluation was `completed`, not `unavailable` | `backend/tests/integration/test_coach_degraded_ai_journey.py`, `coach_degraded_test_server.py`, `coach_app_process.py` | `cd backend && pytest -q --no-cov --tb=short tests/integration/test_coach_degraded_ai_journey.py` | One real-process test passed: valid synthetic WebM uploaded, provider-boundary ASR transcript retained, evaluator failed, review was `unavailable`/`not_assessed`, and candidate explicitly accepted the unassessed attempt to continue. |

The first Scenario H reproduction reached the default configured local LLM endpoint with only a synthetic transcript and no provider credentials, then timed out after retries. The test was corrected to replace the legacy answer-evaluation and rubric-enrichment provider boundaries; a subsequent RED log assertion caught remaining rubric model retries, then passed after the rubric boundary was isolated. Final H/G runs contain no `openai._base_client` retry evidence; G also checks that real faster-whisper was not loaded. Neither test is configured-model acceptance. The root checkout, prior worktree and user data remain untouched.

The complete backend command, `cd backend && pytest -q`, exited 0: 3,917 passed, 2 skipped, 140 warnings in 481.00 seconds; total coverage 80.13% exceeded the 58% gate. `ruff check app/ tests/ benchmarks/coach/production_adapter.py`, `python scripts/check_docs.py`, and `git diff --check` also passed. This follow-up did not rerun the frontend type/unit/build/browser suite, the configured-model benchmark, or an independent security scan. Review of the test-only boundary found no changed production route, storage policy, rollout default, or Phase 2 entity; the tests use only synthetic candidates and disposable local storage. No Critical/High finding was identified in scoped inline self-review; independent repository-owner review is still required before merge.

Current §37.15 disposition for this deterministic application-path slice: A and C passed in PR #72; G and H now pass as above; B remains partial (browser microphone/silence/keep-speaking), D and E pending, F partial (no in-flight audio restart). AC-29's before/after baseline comparison, configured-model standard-profile quality/cost, final frontend/browser baseline, owner/security acceptance and architecture Gates R2–R4 remain open. Do not infer Phase 1 completion or Phase 2 authorization from these tests.
