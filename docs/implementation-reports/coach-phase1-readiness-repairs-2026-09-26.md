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
