# Coach Phase 1 PR2 Task 10 Contract Addendum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two user-approved V6 contracts that block PR2: candidate-visible retry for failed cancelled-upload cleanup, and an idempotent persisted ten-minute capture-limit event.

**Architecture:** Extend V6 first, then implement each contract as an independently reviewed task. Cancellation cleanup reuses `delete_audio` and exposes only one exact failed cancelled-attempt identifier through live retention state; reconciliation never automatically reclaims a terminal failure. The hard-stop path adds a dedicated versioned command that records one technical event while leaving the conversation in `listening` and the captured blob under candidate control.

**Tech Stack:** FastAPI/Pydantic, SQLAlchemy async repositories/services, Next.js 15/React 19/TypeScript, Vitest/Testing Library, Pytest, Playwright.

## Global Constraints

- V6 remains the sole active Phase 1 implementation specification and is updated before application code.
- No migration or new dependency is permitted for this addendum.
- No PR3, PR4, Phase 2, scoring, confidence, facial, emotion, or automatic-submission behavior.
- Every command uses the existing `coach_conversation_command_v1` envelope, semantic request hashing, persisted command receipt, exact `expected_state_version`, and duplicate replay behavior.
- Filesystem deletion continues to use the existing root-confined inode/hash-safe deletion authority.
- Tests follow strict RED/GREEN TDD; each task receives independent spec-and-quality review before the next task.
- Do not modify the inherited reconciliation fixture race as part of these contracts.

---

### Task 1: Bind the approved contracts in V6

**Files:**
- Modify: `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md`
- Modify: `docs/superpowers/plans/2026-07-25-coach-phase1-pr2-capture-processing-retention.md`
- Modify if it contains the tracked canonical digest: the existing documentation ledger identified by `rg`.

**Interfaces:**
- Produces command `record_capture_hard_stop` with payload `{attempt_id}`.
- Produces event `answer_capture_hard_limit_reached` with server-authored `limit_ms: 600000`.
- Extends `ConversationLiveView.retention` with nullable `retryable_audio_cleanup_attempt_id`, discovered in stable `(created_at, id)` keyset pages of 20 and bounded to 36 × 20 = 720 attempts/session; invalid authority rows are skipped and only one exact valid candidate is projected.
- Reuses existing `delete_audio` for the exact surfaced cancelled attempt. A cancelled terminal `delete_failed` is excluded from general default-cleanup eligibility and is retried only by that command. Its generation is the unique persisted `AsyncJob(type=coach_cancelled_upload_cleanup).id` plus claim token/deadline and fence digest over expected attempt version, URI/hash, and upload receipt; no numeric schema field is added.

- [ ] **Step 1: Add the exact command and event contracts**

Document that `record_capture_hard_stop` is admissible only for the active audio attempt while the session is `active/listening`; it leaves state `listening`, increments normal command/activity authority once, appends one candidate-authored technical event, never submits or scores, and replays idempotently.

- [ ] **Step 2: Add the failed-cancellation retry contract**

Document that `/live.retention.retryable_audio_cleanup_attempt_id` is non-null only for one authoritative cancelled audio attempt in `delete_failed`; discovery uses stable `(created_at, id)` keyset pages of 20, scans at most 36 × 20 = 720 attempts/session, skips invalid authority rows, and projects only one exact valid candidate. `delete_audio` is advertised in `asking` only when this value is present and may claim only that exact attempt. A cancelled terminal failure is excluded from general default-cleanup eligibility. A new command creates a fresh persisted `AsyncJob(type=coach_cancelled_upload_cleanup).id` with a new claim token/deadline and expected attempt-version/URI/hash/upload-receipt fence digest; finalisation requires the exact current job and claim, without adding a numeric schema field. Startup/lazy reconciliation recover `delete_pending` claims but never automatically reclaim terminal `delete_failed` rows.

- [ ] **Step 3: Add race and acceptance requirements**

Require exact-once terminal events/version increments, stable command replay, no stale replacement deletion, invalid early candidates not starving later due work, 409 refresh behavior, hard-stop blob preservation, and no automatic submission.

- [ ] **Step 4: Update plan traceability and run docs checks**

Run `python scripts/check_docs.py`, calculate the new V6 SHA-256, and update the tracked digest ledger if present. Run `git diff --check`.

### Task 2: Expose and retry cancelled-upload cleanup failure

**Files:**
- Modify: `backend/app/schemas/coach_conversation.py`
- Modify: `backend/app/services/coach_conversation_state.py`
- Modify: `backend/app/services/coach_command_projection.py`
- Modify: `backend/app/services/coach_live_view.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/services/coach_retention.py`
- Modify: `backend/app/services/coach_reconciliation.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/coach/conversation/RetentionStatus.tsx`
- Modify: `frontend/src/components/coach/conversation/ConversationSession.tsx`
- Test: nearest backend command/live/retention/reconciliation tests and frontend conversation retention/session tests.

**Interfaces:**
- Consumes the cancellation claim/finalisation worker already added during Task 10.
- Produces nullable live field `retryable_audio_cleanup_attempt_id` and reuses `delete_audio` with its existing payload.

- [ ] **Step 1: Write and verify backend RED tests**

Cover live projection of exactly one failed cancelled attempt, absence when no authoritative candidate exists, `delete_audio` admission only for the surfaced ID, duplicate replay, stale ID/hash/job rejection, one new cleanup generation, no repeated reconciliation failure event/version increment, and keyset continuation past invalid early rows.

- [ ] **Step 2: Implement the minimal backend contract**

Resolve the retryable candidate with an exact deterministic query and current ownership fences. Advertise `delete_audio` only when that same snapshot is claimable. Exclude `delete_failed` from automatic cleanup reconciliation; retry only through a new accepted `delete_audio` command. Keep expired `delete_pending` recovery bounded and keyset-paged.

- [ ] **Step 3: Write and verify frontend RED tests**

Cover truthful failed-cleanup copy, server-gated retry control, exact attempt ID and expected version, new command ID for a distinct retry, stable envelope on transport retry, pending disablement, 409 refresh, and control disappearance after refreshed success.

- [ ] **Step 4: Implement the minimal frontend control**

Render the retry from server authority only; do not infer it from stale local state or expose cancelled answer content.

- [ ] **Step 5: Run focused and affected suites**

Run the backend command/live/retention/reconciliation modules, frontend conversation suites, type-check, Ruff/lint, and diff checks.

### Task 3: Persist the ten-minute hard-stop technical event

**Files:**
- Modify: `backend/app/schemas/coach_conversation.py`
- Modify: `backend/app/services/coach_conversation_state.py`
- Modify: `backend/app/services/coach_command_projection.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/coach/conversation/ConversationSession.tsx`
- Modify: `frontend/src/components/coach/conversation/ConversationRecorder.tsx`
- Test: nearest backend command/event tests and frontend recorder/session tests.

**Interfaces:**
- Produces command `record_capture_hard_stop` and event `answer_capture_hard_limit_reached`.
- Payload contains only `attempt_id`; `limit_ms: 600000` is server-authored event data.

- [ ] **Step 1: Write and verify backend RED tests**

Cover active audio/listening acceptance, typed/wrong/replaced attempt rejection, state remaining `listening`, one state/activity/event increment, exact sanitized event payload, duplicate replay, stale expected version, and no submission/evaluation/job mutation.

- [ ] **Step 2: Implement the minimal backend command**

Add the discriminated payload/command, transition and contextual projection. Append the event in the command transaction and return the normal persisted result.

- [ ] **Step 3: Write and verify frontend RED tests**

At the monotonic 600,000 ms boundary, assert local recording stops, blob remains submit/discard capable, one command is sent with the active attempt and stable command ID, transport retry reuses the envelope, 409 performs authoritative refresh, duplicate timer/focus callbacks do not emit twice, and failures preserve the blob/unload guard.

- [ ] **Step 4: Implement the minimal recorder/session bridge**

Emit the technical command once from the existing hard-stop transition. Do not pause, submit, discard, score, or clear local capture.

- [ ] **Step 5: Run focused and affected suites**

Run backend command/event tests, frontend recorder/session suites, type-check, Ruff/lint, and diff checks.

### Task 4: Re-run Task 10 binding and release gates

**Files:**
- Modify only test/report files required by reviewed gate corrections.

- [ ] **Step 1: Request independent task reviews**

Require CLEAN spec-and-quality verdicts for Tasks 2 and 3 and a binding V6 re-review.

- [ ] **Step 2: Run final repository verification**

Run docs checks, focused security/race suites, backend and frontend test gates, type-check, lint, production build, Task 9 Chromium E2E, Ruff, and diff checks. Record the inherited SQLite fixture and direct Alembic environment disposition truthfully.

- [ ] **Step 3: Commit reviewed changes by reviewable concern**

Create separate commits for the bounded Task 10 test correction, the V6 contract addendum, cancelled-cleanup retry, and hard-stop technical event. Do not open PR2 until every binding blocker is closed.
