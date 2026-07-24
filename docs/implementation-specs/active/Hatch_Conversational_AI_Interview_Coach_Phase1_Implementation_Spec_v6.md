---
title: Hatch Conversational AI Interview Coach Phase 1 Implementation Specification v6
document_type: implementation-spec
content_type: text/markdown
status: active
implementation_status: partial
applies_to: main/latest
last_verified: 2026-07-24
supersedes: Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v5.md
superseded_by: []
---

# Hatch Conversational AI Interview Coach: Phase 1 Implementation Specification v6.0

**Implementation order:** Must be completed before the Candidate Intelligence Platform and Interview Mentor phase
**Target repository:** `https://github.com/arvindsoni2/hatch`
**Canonical repository path:** `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md`
**Prepared:** 24 July 2026
**Specification type:** Repository-grounded Codex implementation contract

## TL;DR

Phase 1 extends the existing Coach module with a server-authoritative conversational state machine, versioned answer attempts, bounded voice processing, evidence-grounded rubric evaluation, privacy deletion, and legacy compatibility. Implementation begins only after the repository is fast-forwarded to a baseline containing `3985da09`, this v6 file is tracked as the sole active Phase 1 specification, `docs/README.md` points to v6, superseded Phase 1 specifications are outside `active/`, and `python scripts/check_docs.py` passes.

## 0. Document control and grounded baseline

### 0.1 Repository placement and tracking

This document is an active implementation specification and must be committed to the canonical repository path shown above.

Before implementation begins, Codex must verify:

```bash
git check-ignore -v docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
python scripts/check_docs.py
```

Required results:

- `git check-ignore` returns no matching ignore rule;
- `git ls-files` confirms that the specification is tracked;
- `scripts/check_docs.py` passes.

If the working tree ignores `docs/implementation-specs/active/`, remove the obsolete ignore rule or add the minimum explicit negation required for this file and its parent directories. Do not rely on an untracked local specification or a permanent `git add -f` workaround.

#### 0.1.1 Repository preflight remediation reported during the v5 audit

The earlier repository audit reported four repository-state failures: local `main` at `6d1c61a` was behind `origin/main`; v4 was untracked; v3 remained under `active/`; and `scripts/check_docs.py` failed because of a broken Coach v5 link plus missing front matter on a moved Phase 1 v1 file. These are binding pre-implementation repairs.

Codex must complete one documentation-only preflight change before implementation code changes:

1. Fast-forward local `main`, then verify `3985da09` is an ancestor of `HEAD`.
2. Copy this v6 document to its canonical path and add it to Git.
3. Move tracked Phase 1 v1-v5 specifications out of `docs/implementation-specs/active/` into `docs/implementation-specs/superseded/`; delete untracked local copies rather than treating them as repository authority.
4. Give every moved specification valid YAML front matter. A superseded Phase 1 implementation spec uses `document_type: implementation-spec`, `status: historical`, `implementation_status: partial`, `applies_to: main/latest`, and a valid `last_verified` date.
5. Update every Coach benchmark v5 reference to `docs/implementation-specs/completed/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md`.
6. Add this v6 specification under `Active Implementation Work` in `docs/README.md` and remove any active v1-v5 entry.
7. Run the commands below and commit the documentation preflight before touching implementation files.

```bash
git fetch origin
git checkout main
git pull --ff-only
git merge-base --is-ancestor 3985da09 HEAD
git rev-parse HEAD
python scripts/check_docs.py
git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
git status --short
```

The implementation branch starts only from the resulting documentation-clean `HEAD`. The PR 1 implementation summary records both that full SHA and the documentation-preflight commit SHA.

### 0.2 Implementation baseline

The implementation must branch from updated `origin/main` containing the owner-reported merge commit:

```text
3985da09
```

Before changing code, Codex must run:

```bash
git fetch origin
git checkout main
git pull --ff-only
git merge-base --is-ancestor 3985da09 HEAD
git rev-parse HEAD
```

If the ancestry check fails, stop without modifying implementation files and ask the repository owner to identify the correct merged baseline. The implementation summary for PR 1 must record the full `HEAD` SHA used.

The short SHA above is the implementation start gate. The uploaded archive remains design evidence, not the branching target.

### 0.3 Design-evidence archive

This specification was originally grounded against:

```text
hatch-main (1).zip
```

Archive SHA-256:

```text
95347f776a347395af4fa4052f6afaf10f3ad2f610c1e163c12309bca0e55744
```

The archive did not contain Git metadata. Retain this hash in the specification to identify the inspected design evidence, while treating the verified `origin/main` commit from Section 0.2 as authoritative for implementation.

### 0.4 Baseline verification performed

The implementation contract below is grounded in direct inspection of the uploaded code, including:

```text
backend/app/routers/coach.py
backend/app/services/coach_service.py
backend/app/services/coach_session_queue.py
backend/app/services/coach_reconciliation.py
backend/app/services/coach_contracts.py
backend/app/services/mock_interviewer.py
backend/app/services/answer_evaluator.py
backend/app/services/speech_analyser.py
backend/app/services/rubric_builder.py
backend/app/services/rubric_synthesiser.py
backend/app/services/coach_aggregation.py
backend/app/services/writing_contracts.py
backend/app/repositories/session_repository.py
backend/app/models/coach_session.py
backend/app/schemas/coach.py
backend/app/database.py
backend/app/config.py
backend/app/main.py
backend/app/observability/*
backend/alembic/versions/*coach*
frontend/src/app/coach/session/[id]/page.tsx
frontend/src/app/coach/report/[id]/page.tsx
frontend/src/components/coach/*
frontend/src/lib/api.ts
backend/benchmarks/coach/*
backend/tests/*coach*
docs/implementation-specs/completed/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md
```

Codex must re-check the corresponding files on the verified implementation baseline and document any material drift before implementing the affected contract.

### 0.5 Baseline test execution note

A targeted backend test invocation against the unpacked archive stopped during collection because the inspection environment lacked `aiosqlite`:

```text
ModuleNotFoundError: No module named 'aiosqlite'
```

This is an inspection-environment dependency gap, not evidence of a repository test failure. Codex must run all verification commands in the project-supported environment after installing repository dependencies.

### 0.6 Specification authority

Where this document conflicts with the earlier condensed Phase 1 draft or any Phase 1 implementation specification from v1 through v5, this v6 document wins.

Where this document conflicts with legacy behaviour, apply these rules:

1. Existing legacy sessions and reports remain readable.
2. Existing legacy API callers remain functional unless this document explicitly defines a compatibility wrapper.
3. New conversational sessions use the contracts in this document.
4. New conversational behaviour must not reinterpret historical numeric data.
5. Completed Coach correctness, benchmark, reconciliation and observability work must be extended rather than bypassed.
6. The canonical status/state matrix in Section 8.4 and the command table in Section 8.5 are authoritative over any derived UI projection.

### 0.7 Normative language

- **Must**, **must not**, **required** and acceptance or release gates are binding.
- A **required Phase 1 default** may be changed only through a repository-owner decision recorded in the implementation summary.
- A recommended filename may be adjusted to repository naming conventions, but the service boundary and ownership rule remain binding.
- This document contains no unresolved product or architecture decision. Codex must not reinterpret an explicit contract as optional.


### 0.8 Codex review resolution record

This revision resolves the blocking and clarification reviews raised against v1 through v5. The binding decisions are:

| Review area | v6 decision |
|---|---|
| Document governance | Track this file as an active implementation spec with the YAML front matter above; `check_docs.py` must pass. |
| Branch baseline | Implement from verified `origin/main` containing owner-reported `3985da09`; retain the archive hash only as design evidence. |
| Session lifecycle | Section 8.4 is the single canonical status/state matrix; Section 8.5 is its exhaustive legal-transition table. |
| Pause and end semantics | Pause is legal from the states listed in Section 8.5. Ending from `paused` follows Section 8.6 and requires explicit draft disposal when paused from `listening`. |
| Attempt acceptance | `accept_attempt` requires an explicit `attempt_id`; any eligible attempt for the current question may be selected. |
| Session creation and mutations | Section 7 and the `record_self_assessment` and `update_retention` command contracts in Section 9.9 define the complete creation and mutation vocabularies. |
| Idempotency | Sections 9.5 and 9.6 define canonical JSON hashing and require duplicate-command lookup before state-version validation. |
| Audio upload idempotency | Section 19 persists upload identity in `InterviewAttemptUpload` with uniqueness on `(attempt_id, upload_id)`. |
| Worker versioning | `processing_generation` is separate from candidate-visible `attempt_version`; a worker cannot invalidate itself by producing a transcript. |
| Processing timeout | One absolute 900-second deadline is shared by all answer-processing stages, retries and repair attempts. |
| Evidence reproducibility | Every admitted evidence reference requires a bounded immutable snapshot; transcript offsets use Unicode code points over NFC/LF-normalised text. |
| Transcript deletion | Transcript content and transcript-derived artefacts are physically deleted; affected reports are immediately hidden and rebuilt under a distinct completed-session report claim. |
| Evaluation algorithms | Sections 22.3, 27.4 and 27.6 define ordered delivery, root-bundle and session-readiness algorithms with boundary tests. |
| Export | Phase 1 export is a synchronous attachment response; no persisted export artefact or download lifecycle is introduced. |
| Metrics | `state_version` is trace-only and must be removed by the metrics-label sanitizer. |
| Editorial consistency | Document-control subsections are ordered and implementation contracts avoid competing override tables. |
| Interview type | The canonical `interview_type` enum is `behavioural`, `role_specific_verbal` or `mixed`; competency and leadership remain focus-area or legacy UI labels, not interview types or persisted question categories. |
| Setup ownership | Setup generation, claim, retry and error-scope fields are persisted on `InterviewSession`; every retry or rebuild uses a new generation. |
| Attempt retention | Every attempt snapshots `audio_retention_policy` at `begin_answer`; upload and cleanup consume that immutable snapshot. |
| Question/attempt states | Sections 13.2 and 14.4 define the authoritative mutation tables, including `finish_answer -> pending_processing`. |
| Begin-answer replay | `(session_id, client_attempt_id)` lookup precedes state validation and is backed by a unique constraint. |
| Pre-start rebuild | `rebuild_plan` refreshes the staged plan from the persisted creation request before `start`. |
| Report retention | Audio-only retention changes do not rebuild analytical reports; `retention_summary` is a live response overlay versioned by `retention_version`. |
| Privacy deletion | Hard deletion is available from every non-deleting lifecycle state and fences setup, attempt and report workers before removal. |
| Rubric thresholds | Answer-level `strong` requires all seven content dimensions assessed; evidence consistency and trends use exact ordered algorithms. |
| Compatibility and locale | Custom `other` role labels participate through a normalized hash; the supported BCP-47 subset includes script and numeric-region tags. |
| Reprocessing state | `retry_processing` and `edit_transcript` atomically set the attempt to `pending_processing` before a new worker claim can exist. |
| Retry scope | Phase 1 retries only an unaccepted active question. Accepting an attempt makes the question terminal for conversational navigation; accepted historical questions are not revisited or replaced. |
| Question categories | Conversational questions use the canonical six-value category enum and deterministic behavioural/role-specific grouping in Sections 4.2 and 13.1. |
| Audio cleanup | Default cleanup is independently claimed as soon as transcription and speech analysis are terminal; evaluation and grounding are not prerequisites. Cleanup mutations version the live retention projection. |
| Hint attribution | Hints requested before `begin_answer` are stored on the active question and atomically transferred to the next attempt. |
| Legacy backfill | The latest terminal legacy recording wins: `skipped` outranks an earlier completed recording; otherwise any valid completed recording yields `answered`. |
| Processing stages | Every attempt stage belongs to a non-null evaluation version; the unique key therefore has no SQLite `NULL` ambiguity. |
| Hard-deletion receipt | Completion is retained only in the independent, pseudonymous deletion-result table and telemetry, not in the deleted session event stream. Receipts expire after 30 days by default. |
| Cloud disclosure | Disclosures distinguish approved evidence from candidate-selected unapproved application-CV snapshots. |
| Evaluation/transcription ordering | Audio `finish_answer` creates a pending evaluation with a nullable transcript FK; successful transcription binds the immutable transcript before content evaluation. |
| Coaching transcript edits | `edit_transcript` is legal from `coaching` and appears in the canonical transition registry and Appendix A. |
| One-time acceptance tests | A second acceptance is rejected without changing the first accepted pointer; no test unaccepts a prior selection. |
| Stale setup recovery | Reconciliation converts an expired setup claim to setup `recoverable_error` or terminal `failed`, clears ownership fields, and permits a new-generation `retry_setup`. |
| Stale hard-deletion recovery | Expired `deleting` claims reconcile to hidden `failed`, clear ownership, update the independent receipt, and require a new deletion command ID for retry. |
| End-session transaction | Section 9.9 defines exact accept, exclude, and paused-draft mutations; suppresses follow-up admission; and defines reportable session state. |
| Progress selectors | Broad filters return separate exact-compatibility groups; `compatibility_key` is an exclusive exact selector and groups are never merged. |
| Transcript deletion | Transcript deletion always deletes retained audio in Phase 1; post-deletion retranscription is out of scope. |
| Event sequencing | `event_version` is the sole persisted sequence allocator; `state_version` never sequences events. |
| Event actors | `actor_type` uses the five-value event-origin enum `candidate`, `system`, `worker`, `reconciler`, or `migration`; approval states remain an evidence-record vocabulary. |
| Processing retries | Each attempt snapshots a manual retry limit, persists retry consumption, and deterministically reuses valid upstream stages while rerunning the failed stage and all downstream stages. |
| Attempt budget | Each question persists a monotonic `attempts_created_count`; duplicate lookup precedes the atomic maximum-attempt check, and deleted or cancelled attempts do not refund budget. |
| Privacy re-acceptance | A question permits one acceptance per `acceptance_generation`; deleting its accepted transcript increments the generation and permits a replacement acceptance without enabling ordinary historical replacement. |
| Pre-transcription terminal failure | The unavailable branch explicitly permits a null transcript and does not apply the completed-audio same-generation transcript predicate. |
| Evidence eligibility | Approval-state capabilities are explicit: authoritative sources may conflict; reviewed and candidate-selected unapproved sources may support but not conflict; drafts can only partially support with consent. |
| Progress bounds | Filtered progress responses are capped by `HATCH_COACH_PROGRESS_MAX_GROUPS` and disclose total, returned, limit, and truncation metadata. |
| Deletion retry | Every owned-media or database deletion failure clears claim ownership, finalises the independent receipt as failed, keeps the session hidden, and permits a new-command retry. |
| Error registry | One canonical API error registry includes every command-defined error and uses `coach_progress_incompatible_session` consistently. |

## 1. Executive implementation decision

Phase 1 will introduce a **deterministic conversational interview runtime** inside the existing Coach module.

It will not create a separate interview subsystem, a second report engine or an unrestricted conversational agent.

The implementation must follow this control boundary:

```text
Browser
- captures audio
- performs local silence detection
- renders the current server state
- sends explicit user commands

Backend application
- owns session state
- validates commands
- creates and accepts attempts
- enforces retries and follow-up budgets
- owns retention and deletion
- owns evidence and evaluation contracts
- owns report and progress aggregation

LLM
- proposes question wording
- proposes rubric judgements
- proposes evidence claim mappings
- proposes coaching wording
- proposes a permitted follow-up

LLM never owns
- workflow state
- command validity
- attempt acceptance
- confidence bands
- retention
- deletion
- follow-up count
- report inclusion
- candidate data mutation
```

### 1.1 Key repository adaptation

The approved conceptual design originally referred to a new `InterviewAttempt` entity. The uploaded baseline already uses `SessionRecording` as an immutable answer-attempt record and already provides fenced asynchronous finalisation using:

```text
recording id
+ async_job_id
+ evaluation_state = pending
```

Therefore:

> **Phase 1 must promote and extend `SessionRecording` as the physical answer-attempt aggregate. It must not create a duplicate `InterviewAttempt` table.**

API and schema objects may use the user-facing term `InterviewAttempt`, but the authoritative ORM record remains `SessionRecording`.

### 1.2 Key compatibility decision

The current Coach UI and API use numeric 0–10 evaluations, numeric report averages, score radar visualisations and current rubric dimensions such as `vocal_confidence` and `presence`.

New conversational sessions must use a separately versioned contract:

```text
experience_version = conversational_v1
evaluation_contract_version = coach_conversational_rubric_v1
report_contract_version = coach_conversational_report_v1
```

Legacy sessions continue to use their existing numeric contracts.

No migration converts legacy numeric scores into named levels.

### 1.3 Product result

Phase 1 is complete when a candidate can:

1. Plan a role-grounded verbal interview.
2. Complete it through typed or voice turns.
3. Recover after refresh, restart or worker failure.
4. Ask for hints or answer review without breaking realistic interview mode.
5. Retry an answer without overwriting previous attempts.
6. Receive evidence-backed named rubric levels.
7. Receive no more than two transcript-grounded adaptive follow-ups per planned question.
8. Select audio retention with delete-after-processing as the default.
9. Correct a transcript and trigger a versioned re-evaluation.
10. Receive a deterministic final report and compatible-session progress view.

---

## 2. Current implementation baseline

## 2.1 Existing Coach persistence

The uploaded baseline contains:

### `InterviewSession`

Current relevant fields include:

```text
id
application_id
company_name
role_title
config JSON
status
started_at
completed_at
overall_score
feedback_summary
coach_mode
rubric JSON
signals JSON
parent_session_id
focus_areas
diagnostics JSON
report_json JSON
report_state
report_job_id
report_started_at
activity_version
```

Current report-state constraint:

```text
not_started | building | completed | fallback | failed
```

### `SessionQuestion`

Current relevant fields include:

```text
id
session_id
question_num
text
category
difficulty
context
model_answer
requirement_id
model_answer_diagnostics
order_in_session
```

### `SessionRecording`

Current relevant fields include:

```text
id
session_id
question_id
recording_type
transcript
audio_uri
video_uri
speech_metrics
video_metrics
evaluation_json
evaluation_state
async_job_id
created_at
```

Current evaluation-state constraint:

```text
pending | completed | unavailable | invalid | skipped | failed
```

### Existing migration head

The uploaded baseline has a single Alembic head:

```text
p3q4r5s6t7u8
```

The latest Coach migration is:

```text
20260722_0001_p3q4r5s6t7u8_add_coach_c1_contract_fields.py
```

The Phase 1 migration must descend from this head.

## 2.2 Existing asynchronous correctness contracts

The baseline already supports:

- persisted generic async jobs;
- background session creation;
- background answer evaluation;
- report claims fenced by `activity_version`;
- answer finalisation fenced by `async_job_id` and pending state;
- startup reconciliation through `reconcile_stale_coach_state()`;
- lazy reconciliation in Coach reads and async-job reads;
- deterministic report fallback;
- persisted report snapshots;
- structured Coach diagnostics and bounded gate codes;
- an existing Coach benchmark harness;
- a shared Hatch telemetry facade.

Phase 1 must preserve these contracts.

## 2.3 Existing API baseline

The current router includes:

```text
POST   /api/coach/research
GET    /api/coach/research/{company_name}
POST   /api/coach/sessions
GET    /api/coach/sessions
GET    /api/coach/sessions/{session_id}
DELETE /api/coach/sessions/{session_id}
POST   /api/coach/sessions/{session_id}/retry
GET    /api/coach/sessions/{session_id}/next-question
POST   /api/coach/sessions/{session_id}/skip
POST   /api/coach/sessions/{session_id}/submit-answer
POST   /api/coach/sessions/{session_id}/submit-audio
POST   /api/coach/sessions/{session_id}/end
GET    /api/coach/sessions/{session_id}/report
GET    /api/coach/progress/{application_id}
POST   /api/coach/sessions/{session_id}/followup
GET    /api/coach/progress/{session_id}/trend
GET    /api/coach/capabilities
POST   /api/coach/sessions/{session_id}/tts-question
```

These routes remain legacy-compatible.

## 2.4 Existing frontend baseline

The current session page:

- uses local UI states `idle`, `recording`, `submitted`, `evaluated`;
- chooses the first unanswered question client-side;
- does not restore a server-owned conversational state;
- polls generic async jobs every two seconds;
- supports typed, browser Web Speech, audio blob and video paths;
- shows live filler and WPM feedback in browser voice mode;
- shows numeric answer scores and a radar chart;
- treats the latest completed attempt as canonical through backend aggregation;
- has manual Start, Stop and Submit controls;
- does not implement automatic turn detection.

Phase 1 must replace the active conversational experience with a server-authoritative UI while retaining a legacy report rendering path.

## 2.5 Existing evaluation baseline

The current answer evaluator produces numeric dimensions:

```text
relevance
star_structure
technical_depth
conciseness
communication
impact_metrics
```

The current follow-up behaviour is score-driven, including an overall threshold around 6/10.

This conflicts with the approved conversational contract. For new conversational sessions:

- follow-ups must not be triggered solely by a low score;
- named levels replace user-facing numeric scoring;
- `vocal_confidence`, emotion, personality and presence inference are prohibited;
- video-derived face or gaze scoring is not part of the conversational contract.

## 2.6 Existing evidence assets that must be reused

The repository already provides:

- approved Master CV JSON through `master_cv_store.py`;
- stable evidence identifiers and evidence-ledger helpers in `writing_contracts.py`;
- application and job-posting records;
- generated CV/cover-letter assets with review and approval status;
- Question Bank records with `draft`, `reviewed` and `final` confidence states;
- company research;
- question requirements and model-answer diagnostics.

Phase 1 evidence grounding must build on these assets. It must not introduce a parallel evidence store for source documents.

---

## 3. Repository-grounded gaps to resolve

## 3.1 No server-authoritative conversational state

The current page reconstructs progress from questions and recordings. It cannot reliably answer:

- whether the session is asking, listening, processing or paused;
- which command is valid;
- whether a browser refresh should resume recording or review;
- whether a late client command is stale.

## 3.2 No command idempotency or state-version contract

Existing Coach write endpoints do not use a shared `command_id + expected_state_version` contract.

## 3.3 No explicit accepted attempt

The report aggregator currently chooses the latest valid completed attempt. This is not sufficient for conversational retry and review because:

- the candidate may prefer an earlier attempt;
- a retry is not automatically better;
- transcript editing creates evaluation versions;
- follow-ups must not unintentionally replace root-question answers.

## 3.4 No versioned transcript or evaluation history

`SessionRecording.transcript` and `evaluation_json` represent only the current persisted values. Candidate edits would otherwise overwrite history.

## 3.5 Follow-ups are score-threshold-driven

Current follow-up logic does not enforce:

- permitted reason codes;
- a maximum of two per planned question;
- current-transcript grounding;
- duplicate prevention;
- return to the planned sequence.

## 3.6 Current evaluation contract conflicts with product principles

The current schemas and rubric builder include:

- vocal-confidence concepts;
- tone dimensions with arousal, valence and dominance;
- video presence dimensions.

These are prohibited for new conversational sessions.

## 3.7 Audio retention is not a first-class session contract

The current audio upload path persists files but does not implement the approved delete-after-processing default or recoverable deletion state.

## 3.8 Current report and progress are numeric

The current report aggregates means and exposes percentage-like precision. New conversational reports require named levels and compatibility-gated longitudinal comparisons.

## 3.9 Current frontend provides live scoring-like feedback

Live filler and pace feedback during the answer conflicts with realistic uninterrupted interview mode.

## 3.10 Current session setup does not snapshot a complete plan

The existing config stores basic choices, but not a versioned, reproducible session plan containing evidence sources, evaluation contract, role context, retention and compatibility keys.

---

## 4. Scope

## 4.1 In scope

Phase 1 includes:

- a deterministic conversation orchestrator;
- server-authoritative conversation state;
- idempotent commands and optimistic concurrency;
- role-grounded guided session planning;
- typed and voice answers;
- browser-side automatic silence detection with manual override;
- explicit answer attempts and candidate acceptance;
- versioned transcripts and evaluations;
- named, evidence-backed rubric levels;
- evidence-grounding statuses;
- optional answer review and coaching;
- bounded adaptive follow-ups;
- retry and hint controls;
- audio-retention choice and deletion workflow;
- recoverable asynchronous processing;
- deterministic conversational report generation;
- compatibility-gated progress;
- accessibility and typed-answer parity;
- structured observability;
- benchmark and adversarial contract coverage;
- backward compatibility for legacy Coach sessions and reports.

## 4.2 Supported interview types

The canonical `interview_type` vocabulary for every creation request, plan, compatibility key, API response and metric is:

```text
behavioural
role_specific_verbal
mixed
```

Question records use this canonical `category` vocabulary for every new conversational session:

```text
behavioural
situational
culture
technical
domain
commercial
```

The deterministic category groups are:

```text
behavioural_group = behavioural, situational, culture
role_specific_group = technical, domain, commercial
```

`competency`, `leadership`, `technical_verbal`, `commercial_verbal` and `domain_verbal` remain focus-area or legacy UI labels. They are not `interview_type` or persisted conversational question-category values.

- `behavioural`: every planned question category is in `behavioural_group`.
- `role_specific_verbal`: every planned question category is in `role_specific_group`.
- `mixed`: the plan contains at least one planned question from each group, and every planned question belongs to one of the two groups.

Adaptive follow-ups inherit the root planned question category and do not satisfy or alter the planned-category distribution.

## 4.3 Out of scope

Phase 1 does not include:

- full-duplex realtime voice;
- coding exercises;
- whiteboards;
- system-design drawing;
- video or facial analysis for new conversational sessions;
- emotion recognition;
- personality inference;
- deception or honesty inference;
- hidden confidence scoring;
- Candidate Intelligence platform persistence;
- longitudinal mentor conversations;
- configurable interviewer personas beyond the fixed Standard Professional behaviour contract;
- weakness-driven multi-session practice plans;
- company-aware persona simulation;
- interview replay product timeline beyond attempt history inside the session review;
- automatic CV or Question Bank updates;
- application submission;
- recruiter sharing;
- hosted multi-tenancy;
- graph databases;
- websocket or WebRTC infrastructure.

## 4.4 Explicit Phase 2 boundary

Phase 1 may create clean interfaces that Phase 2 can consume, but it must not implement Candidate Intelligence entities, findings, confidence bands or governance gateways.

Phase 1 outputs remain session-scoped:

```text
attempt evaluations
session evidence findings
session coaching
session report
compatible-session progress
```

---

## 5. Locked product and architecture decisions

## 5.1 Interaction mode

The default is **realistic interview mode**.

Coaching is available on demand.

The Coach may interrupt only for:

- microphone or capture failure;
- upload failure;
- prolonged silence;
- an explicit candidate request for help;
- a recoverable session error requiring action.

The Coach must not interrupt merely because:

- the answer is weak;
- the answer is long;
- filler words are detected;
- speech is slow;
- the evaluator expects a different structure.

## 5.2 Feedback layers

```text
Layer 1: uninterrupted interview
Layer 2: optional review after an answer
Layer 3: deterministic final report
```

## 5.3 Follow-up limit

```text
maximum adaptive follow-ups per planned root question = 2
```

The limit is application-enforced and cannot be changed by a model response.

## 5.4 Confidence language

The system may capture:

- candidate self-assessment;
- observable delivery indicators.

It must not infer or display an internal confidence state.

Use wording such as:

```text
The answer included three long pauses.
The candidate requested one hint.
The candidate rated this answer 2 of 4 for comfort.
```

Do not use wording such as:

```text
The candidate sounded unconfident.
The candidate was anxious.
The candidate lacked executive presence.
```

## 5.5 Retention default

```text
audio_retention = delete_after_processing
transcript_retention = retain
```

The candidate may opt into retained audio before the session or change the setting for future attempts.

## 5.6 Scoring

User-facing conversational evaluation uses:

```text
needs_work
developing
interview_ready
strong
not_assessed
```

No percentage or 0–10 score is shown for conversational sessions.

## 5.7 Evidence result vocabulary

```text
supported
partially_supported
not_found
conflicting
not_verifiable
```

`not_found` must never be labelled false.

## 5.8 AI ownership

LLMs may propose. Application code validates and decides.

---

## 6. Target architecture

## 6.1 Component map

```text
Coach Router
  |
  +-- Conversational Session Command Service
  |     +-- State Machine
  |     +-- Command Idempotency
  |     +-- Attempt Acceptance
  |     +-- Event Persistence
  |
  +-- Conversational Live Read Service
  |     +-- Reconciliation
  |     +-- Allowed Command Projection
  |     +-- Processing Freshness
  |
  +-- Session Plan Builder
  |     +-- Application / job context
  |     +-- Master CV / approved CV evidence
  |     +-- Question Bank evidence
  |     +-- Company research
  |     +-- Compatibility key
  |
  +-- Attempt Processing Service
  |     +-- Audio persistence
  |     +-- Transcription
  |     +-- Speech analysis
  |     +-- Content evaluation
  |     +-- Evidence grounding
  |     +-- Follow-up proposal
  |     +-- Retention cleanup
  |
  +-- Conversational Report Service
  |     +-- Accepted-attempt aggregation
  |     +-- Named-level aggregation
  |     +-- Evidence review items
  |     +-- Deterministic fallback
  |
  +-- Existing Async Job Service
  +-- Existing Reconciliation Service
  +-- Existing Telemetry Facade
```

## 6.2 Required new backend modules

Recommended files:

```text
backend/app/services/coach_conversation_state.py
backend/app/services/coach_conversation_commands.py
backend/app/services/coach_live_view.py
backend/app/services/coach_session_plan.py
backend/app/services/coach_attempt_pipeline.py
backend/app/services/coach_conversational_evaluator.py
backend/app/services/coach_evidence_grounder.py
backend/app/services/coach_followup_policy.py
backend/app/services/coach_retention.py
backend/app/services/coach_conversational_report.py
backend/app/services/coach_conversational_progress.py
backend/app/services/coach_conversational_contracts.py
```

Repository naming may be adjusted to existing conventions, but responsibilities must remain separated. Do not add all behaviour to `coach.py` or `coach_service.py`.

## 6.3 Existing modules to extend

```text
backend/app/routers/coach.py
backend/app/models/coach_session.py
backend/app/schemas/coach.py
backend/app/repositories/session_repository.py
backend/app/services/coach_reconciliation.py
backend/app/config.py
backend/app/observability/coach.py
backend/app/observability/attributes.py
backend/app/observability/runtime.py
frontend/src/lib/api.ts
frontend/src/app/coach/session/[id]/page.tsx
frontend/src/app/coach/report/[id]/page.tsx
frontend/src/components/coach/*
```

## 6.4 Modules not to bypass

Phase 1 must continue using:

- `AsyncJobService` for persisted background-job visibility;
- `session_repository.py` for authoritative persistence operations;
- the existing observability facade rather than direct SDK calls;
- `writing_contracts.py` evidence identifiers where applicable;
- existing provider routing and cloud/local configuration;
- existing report-claim and reconciliation patterns.

---

## 7. Versioned experience selection and session creation

### 7.1 Session experience field

Add to `interview_sessions`:

```text
experience_version VARCHAR(32) NOT NULL DEFAULT 'legacy_v1'
```

Allowed values in this migration:

```text
legacy_v1
conversational_v1
```

Backfill every existing row to `legacy_v1`.

### 7.2 Complete creation request

Extend the existing `POST /api/coach/sessions` request without breaking legacy callers.

```json
{
  "application_id": "optional",
  "company_name": "Example Ltd",
  "role_title": "Senior Solution Architect",
  "jd_text": "optional when the application supplies the job description",
  "interview_date": "2026-08-05",
  "experience_version": "conversational_v1",
  "config": {
    "question_count": 10,
    "categories": [],
    "recording_mode": "text",
    "difficulty": "medium",
    "interviewer_persona": null
  },
  "conversational_config": {
    "interview_type": "mixed",
    "difficulty": "realistic",
    "duration_minutes": 30,
    "planned_question_count": 6,
    "role_family": "solution_architecture",
    "role_family_label": null,
    "role_level": "senior",
    "industry": "technology",
    "locale": "en-GB",
    "focus_areas": [
      "stakeholder_management",
      "architecture"
    ],
    "allowed_answer_modes": [
      "audio",
      "text"
    ],
    "evidence_selection": {
      "application_cv": "approved_only",
      "master_cv": "include",
      "question_bank": "reviewed_final_only",
      "selected_question_bank_record_ids": [],
      "company_research": "include_if_fresh",
      "draft_evidence_consent": false
    },
    "retention": {
      "audio": "delete_after_processing",
      "transcript": "retain"
    }
  }
}
```

Rules:

- `experience_version` omitted: create `legacy_v1` using the existing `config` contract.
- `experience_version = legacy_v1`: `conversational_config` must be absent.
- `experience_version = conversational_v1`: `conversational_config` is required.
- `video` is not a valid conversational answer mode.
- `jd_text` is required when no linked application can provide a job description.
- the existing `config` object remains accepted for legacy compatibility and is ignored for conversational planning except where the implementation explicitly maps old launch UI values before submission;
- the server must not infer draft-evidence consent from any other field.

### 7.3 Conversational vocabularies

`interview_type`:

```text
behavioural
role_specific_verbal
mixed
```

This is the only canonical interview-type vocabulary. Any legacy UI value `role_specific` must be mapped to `role_specific_verbal` before the conversational creation request is submitted.

`question_category` for generated and persisted conversational questions:

```text
behavioural
situational
culture
technical
domain
commercial
```

Legacy `SessionQuestion.category` values map case-insensitively as follows:

```text
Behavioural -> behavioural
Situational -> situational
Culture -> culture
Technical -> technical
Domain -> domain
Commercial -> commercial
```

No other category is admitted for a new conversational plan. Legacy sessions retain their stored category text and are normalized only in compatibility readers.

`difficulty`:

```text
supportive
realistic
challenging
```

`role_level`:

```text
entry
mid
senior
lead
principal
manager
director
executive
unspecified
```

Initial `role_family` registry:

```text
software_engineering
solution_architecture
enterprise_architecture
data_ai
cloud_devops_platform
cybersecurity
product_management
project_program_management
agile_delivery
business_analysis
consulting
operations
commercial
general
other
```

If `role_family = other`, persist a bounded `role_family_label` inside the session plan. Its normalized hash participates in the Phase 1 compatibility key under Section 12.6, so unrelated custom professions are not compared.

Initial `focus_areas` registry:

```text
leadership
stakeholder_management
delivery_execution
problem_solving
technical_depth
architecture
communication
commercial_awareness
culture_values
role_motivation
```

`application_cv`:

```text
approved_only
current_if_no_approved
none
```

`master_cv`:

```text
include
exclude
```

`question_bank`:

```text
reviewed_final_only
include_drafts
exclude
```

`company_research`:

```text
include_if_fresh
exclude
```

`allowed_answer_modes` is a non-empty unique subset of:

```text
audio
text
```

`audio` retention:

```text
delete_after_processing
retain_until_deleted
```

`transcript` retention in Phase 1:

```text
retain
```

`locale` uses this intentionally constrained BCP-47 subset:

```regex
^[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?$
```

Normalize components as:

```text
language -> lowercase
script -> Titlecase
alpha region -> UPPERCASE
numeric region -> unchanged
```

Valid examples include `en-GB`, `zh-Hant`, `zh-Hant-TW` and `es-419`. Variants, extensions and private-use subtags are rejected in Phase 1. The server default is `en-GB`. The configured transcription and evaluation routes must explicitly support the normalized locale or creation fails with `coach_locale_unsupported`.

### 7.4 Numeric bounds and defaults

- `duration_minutes`: integer from 10 through 90; default 30.
- `planned_question_count`: integer from 3 through 12, or omitted to use Section 12 defaults.
- `focus_areas`: maximum 6 unique values.
- `selected_question_bank_record_ids`: maximum 50 unique safe identifiers.
- `industry`: optional normalized slug of 1 through 64 characters.
- `role_family_label`: required only for `other`, 1 through 80 characters.
- `company_name`: trimmed, 1 through 200 Unicode code points.
- `role_title`: trimmed, 1 through 200 Unicode code points.
- `jd_text`: when supplied, 1 through 100000 Unicode code points after normalization.
- `interview_date`: ISO `YYYY-MM-DD` calendar date or null.

### 7.5 Draft-evidence consent

`question_bank = include_drafts` is valid only when:

```text
draft_evidence_consent = true
```

Otherwise return HTTP 422 with `coach_draft_evidence_consent_required`.

Draft evidence must be labelled in the immutable evidence package and may never be represented as confirmed candidate evidence.

### 7.6 Creation response and planning completion

The existing asynchronous creation shape remains:

```json
{
  "job_id": "<opaque-id>",
  "status": "pending",
  "type": "coach_session",
  "session_id": "<opaque-id>",
  "created": true,
  "experience_version": "conversational_v1"
}
```

The setup job must persist the complete plan, evidence snapshot records, contract versions, compatibility key and questions before transitioning from `planning` to `ready`.

Creation does not set coarse status to `active`. Only the `start` command does that.

### 7.7 Rendering branch

Frontend routing must branch on `experience_version`:

```text
legacy_v1 -> existing numeric components and legacy flow
conversational_v1 -> state-driven conversational components
```

Do not make the legacy `EvaluationCard` parse the new named-level contract.

## 8. Canonical conversation lifecycle

### 8.1 Coarse status vocabulary

`InterviewSession.status` remains the coarse lifecycle:

```text
setup
active
completed
abandoned
failed
```

### 8.2 Conversation-state vocabulary

Add:

```text
conversation_state VARCHAR(32) NULL
state_version INTEGER NOT NULL DEFAULT 0
resume_state VARCHAR(32) NULL
active_question_id VARCHAR(36) NULL
active_recording_id VARCHAR(36) NULL
active_root_question_id VARCHAR(36) NULL
last_activity_at DATETIME NULL
paused_at DATETIME NULL
recoverable_error_code VARCHAR(128) NULL
recoverable_error_scope VARCHAR(32) NULL
recoverable_error_context_json JSON NULL
setup_generation INTEGER NOT NULL DEFAULT 0
setup_job_id VARCHAR(36) NULL
setup_claim_token VARCHAR(64) NULL
setup_claimed_at DATETIME NULL
setup_claim_expires_at DATETIME NULL
setup_started_at DATETIME NULL
setup_completed_at DATETIME NULL
setup_attempt_count INTEGER NOT NULL DEFAULT 0
setup_max_attempts INTEGER NOT NULL DEFAULT 3
retention_version INTEGER NOT NULL DEFAULT 0
deletion_state VARCHAR(32) NOT NULL DEFAULT 'not_requested'
deletion_generation INTEGER NOT NULL DEFAULT 0
deletion_job_id VARCHAR(36) NULL
deletion_command_id VARCHAR(64) NULL
deletion_claim_token VARCHAR(64) NULL
deletion_claim_expires_at DATETIME NULL
deletion_started_at DATETIME NULL
deletion_failed_at DATETIME NULL
deletion_error_code VARCHAR(128) NULL
event_version INTEGER NOT NULL DEFAULT 0
```

Legacy rows:

```text
conversation_state = NULL
state_version = 0
```

Conversational states:

```text
planning
ready
asking
listening
processing_answer
awaiting_next_action
coaching
asking_follow_up
advancing
paused
reporting
completed
recoverable_error
abandoned
failed
```

Allowed `recoverable_error_scope`:

```text
setup
attempt_processing
initial_report
completed_report_rebuild
```

Allowed `deletion_state`:

```text
not_requested
deleting
failed
```

A completed hard delete removes the session row, so `completed` is stored only in the independent deletion-result record, not on `InterviewSession`.

### 8.3 State meanings

- `planning`: asynchronous setup is building the immutable plan and questions.
- `ready`: setup completed; the live interview has not started.
- `asking`: the active question is displayed and no draft attempt is capturing.
- `listening`: a text or audio draft attempt is active.
- `processing_answer`: a fenced attempt-processing generation is active.
- `awaiting_next_action`: the active attempt has a terminal evaluation state and the candidate may review, accept, retry, edit, self-assess or end.
- `coaching`: on-demand coaching is being generated or displayed.
- `asking_follow_up`: a validated follow-up is being persisted; transient.
- `advancing`: the accepted attempt is committed and the next question is being selected; transient.
- `paused`: the candidate explicitly paused and `resume_state` stores the exact return state.
- `reporting`: initial end-of-session report generation is claimed.
- `completed`: the interview is terminal and the most recent permitted report snapshot is complete or fallback.
- `recoverable_error`: a retryable setup, attempt or report failure requires an explicit recovery command.
- `abandoned`: user abandonment through the existing DELETE route; terminal for this session.
- `failed`: non-retryable or exhausted setup/runtime failure; terminal for this session.

### 8.3.1 Setup ownership and retry contract

Setup planning is a fenced asynchronous aggregate owned by `InterviewSession`.

Initial creation performs one transaction that:

1. stores the normalized `planning_request_json`;
2. sets `setup_generation = 1` and `setup_attempt_count = 1`;
3. creates the setup async job;
4. stores `setup_job_id`, a random `setup_claim_token`, claim timestamps and lease expiry;
5. sets `status = setup`, `conversation_state = planning`.

Every `retry_setup` or `rebuild_plan` increments `setup_generation` and `setup_attempt_count` before creating a new claim. A generation is never reused.

Setup worker finalisation requires all predicates:

```text
status = setup
conversation_state = planning
setup_job_id = expected_job_id
setup_claim_token = expected_claim_token
setup_generation = expected_setup_generation
setup_claim_expires_at >= utcnow()
deletion_state = not_requested
```

Successful finalisation atomically replaces the staged plan/questions/evidence package, clears the active setup claim, sets `setup_completed_at`, clears setup error fields and transitions to `ready`. Initial or retry completion emits `session_plan_completed`; a candidate-requested rebuild emits `session_plan_rebuilt`.

Retryable failure atomically clears the matching claim, persists `recoverable_error_scope = setup`, error code/context and transitions to `recoverable_error`. Terminal failure transitions to `failed` and clears the claim. A stale worker records only content-free job diagnostics and performs no session, question or evidence mutation.

`setup_max_attempts` includes the initial claim. The required default is 3. `retry_setup` and `rebuild_plan` fail with `coach_setup_retry_budget_exhausted` when `setup_attempt_count >= setup_max_attempts`.

### 8.4 Canonical status/state matrix

This matrix is authoritative.

| Coarse `status` | Permitted `conversation_state` | Required notes |
|---|---|---|
| `setup` | `planning`, `ready`, `recoverable_error` | `recoverable_error` is permitted only for pre-start setup failure. |
| `active` | `asking`, `listening`, `processing_answer`, `awaiting_next_action`, `coaching`, `asking_follow_up`, `advancing`, `paused`, `reporting`, `recoverable_error` | `reporting` remains active until the initial report finalises. |
| `completed` | `completed` | Report may later be `invalidated`, `building` or `failed` during privacy rebuild while conversation state remains `completed`. |
| `abandoned` | `abandoned` | No conversational command except hard deletion or reads allowed. |
| `failed` | `failed` | Read-only. The frontend may prefill the normal Section 7 creation form, but a replacement session is created only through `POST /api/coach/sessions`. |

Additional invariants:

1. `ready` is a setup state; `start` changes `status` from `setup` to `active`.
2. `planning -> recoverable_error` keeps `status = setup`.
3. `reporting` always has `status = active`.
4. `listening` requires valid `active_question_id` and `active_recording_id`.
5. `processing_answer` requires an active attempt with a current processing generation and job claim.
6. `awaiting_next_action` requires a terminal current evaluation version: `completed` or `unavailable`.
7. `asking` requires an active question with `question_state = asked`, `accepted_recording_id IS NULL` and no submitted attempt currently processing.
8. `paused` requires a non-null resumable `resume_state`.
9. initial `reporting` requires `report_state = building`, `report_build_reason = initial_completion` and matching `report_job_id`.
10. `completed` requires `report_state` in `completed`, `fallback`, `invalidated`, `building` or `failed`; only `completed` and `fallback` are normally readable.
11. abandonment sets both `status = abandoned` and `conversation_state = abandoned`.
12. terminal runtime failure sets both `status = failed` and `conversation_state = failed`.

### 8.5 Canonical transitions and allowed commands

This table is the single transition authority. The backend must derive `/live.allowed_commands` from the same registry used to validate commands.

| From | Command or internal event | To | Coarse-status effect |
|---|---|---|---|
| `planning` | planning completed | `ready` | remain `setup` |
| `planning` | retryable planning failure | `recoverable_error` | remain `setup` |
| `planning` | terminal planning failure | `failed` | set `failed` |
| `ready` | `update_retention` | `ready` | remain `setup` |
| `ready` | `rebuild_plan` | `planning` | remain `setup` |
| `ready` | `start` | `asking` | set `active` |
| `asking` | `begin_answer` | `listening` | none |
| `asking` | `request_hint` | `asking` | none |
| `asking` | `update_retention` | `asking` | none |
| `asking` | `skip_question` | `advancing` | none |
| `asking` | `pause` | `paused` | none |
| `asking` | `end_session` | `reporting` | none |
| `listening` | `keep_speaking` | `listening` | none |
| `listening` | `request_hint` | `listening` | none |
| `listening` | `update_retention` | `listening` | none |
| `listening` | `finish_answer` | `processing_answer` | none |
| `listening` | `pause` | `paused` | none |
| `listening` | `cancel_attempt` | `asking` | none |
| `processing_answer` | processing completed or unavailable | `awaiting_next_action` | none |
| `processing_answer` | retryable processing failure | `recoverable_error` | none |
| `processing_answer` | terminal runtime failure | `failed` | set `failed` |
| `awaiting_next_action` | `request_coaching` | `coaching` | none |
| `awaiting_next_action` | `retry_answer` | `asking` | none |
| `awaiting_next_action` | `edit_transcript` | `processing_answer` | none |
| `awaiting_next_action` | `accept_attempt` | `asking_follow_up`, `advancing` or `reporting` | none |
| `awaiting_next_action` | `record_self_assessment` | `awaiting_next_action` | none |
| `awaiting_next_action` | `update_retention` | `awaiting_next_action` | none |
| `awaiting_next_action` | `pause` | `paused` | none |
| `awaiting_next_action` | `delete_audio` | `awaiting_next_action` | none |
| `awaiting_next_action` | `delete_transcript` | `asking` when deleting the active or accepted attempt; otherwise `awaiting_next_action` | none |
| `awaiting_next_action` | `end_session` | `reporting` | none |
| `coaching` | `return_to_review` | `awaiting_next_action` | none |
| `coaching` | `edit_transcript` | `processing_answer` | none |
| `coaching` | `retry_answer` | `asking` | none |
| `coaching` | `accept_attempt` | `asking_follow_up`, `advancing` or `reporting` | none |
| `coaching` | `record_self_assessment` | `coaching` | none |
| `coaching` | `update_retention` | `coaching` | none |
| `coaching` | `pause` | `paused` | none |
| `coaching` | `delete_audio` | `coaching` | none |
| `coaching` | `delete_transcript` | `asking` when deleting the coached or accepted attempt; otherwise `coaching` | none |
| `coaching` | `end_session` | `reporting` | none |
| `asking_follow_up` | follow-up persisted | `asking` | none |
| `advancing` | next question selected | `asking` | none |
| `advancing` | no remaining questions | `reporting` | none |
| `paused` | `resume` | stored `resume_state` | none |
| `paused` | `update_retention` | `paused` | none |
| `paused` | `delete_audio` for a completed or processing-complete target attempt whose audio is no longer required | `paused` | none |
| `paused` | `end_session` with exact draft resolution | `reporting` | none |
| `recoverable_error` with `status = setup` | `retry_setup` | `planning` | remain `setup` |
| `recoverable_error` with `status = setup` | `update_retention` | `recoverable_error` | remain `setup` |
| `recoverable_error` with `status = active` and attempt error scope | `retry_processing` | `processing_answer` | none |
| `recoverable_error` with `status = active` and active question | `retry_answer` | `asking` | none |
| `recoverable_error` with `status = active` and initial-report error scope | `retry_report` | `reporting` | none |
| `recoverable_error` with `status = active` | `update_retention` | `recoverable_error` | none |
| `recoverable_error` with `status = active` and resumable error scope | `pause` | `paused` | none |
| `recoverable_error` with `status = active` | `delete_audio` | `recoverable_error` | none |
| `recoverable_error` with `status = active` | `delete_transcript` | `asking` when the deleted transcript caused the recoverable failure; otherwise `recoverable_error` | none |
| `recoverable_error` with `status = active` and `recoverable_error_scope = attempt_processing` | `end_session` with `unaccepted_attempt_action = exclude_attempt` | `reporting` | none |
| `reporting` | report completed or fallback | `completed` | set `completed` |
| `reporting` | retryable report failure | `recoverable_error` | remain `active` |
| `reporting` | terminal report failure | `failed` | set `failed` |
| `completed` | `record_self_assessment` | `completed` | remain `completed`; rebuild report |
| `completed` | `delete_audio` | `completed` | remain `completed` |
| `completed` | `delete_transcript` | `completed` | remain `completed`; invalidate and rebuild report |
| `completed` | conditional `retry_report` for failed privacy/reflection rebuild | `completed` | remain `completed`; report becomes `building` |
| any `setup` or `active` non-deleted state | existing DELETE abandonment | `abandoned` | set `abandoned` |

Any transition not listed is invalid.

### 8.6 Paused end-session rule

`end_session` while paused is permitted only under one of these exact conditions:

1. `resume_state` is `asking`, `awaiting_next_action`, `coaching` or `recoverable_error`; or
2. `resume_state = listening` and payload contains:

```json
{
  "paused_draft_action": "discard_draft"
}
```

When a paused listening draft is discarded, temporary media is deleted or scheduled for fenced cleanup and the attempt becomes `cancelled` before report claim.

`submit_captured_draft` is not an `end_session` shortcut. The browser must resume, upload and finish the answer through the normal commands.

### 8.7 Transient-state transaction rule

`asking_follow_up` and `advancing` must be entered and resolved in one backend transaction during normal command execution. The persisted transient value exists only so startup or lazy reconciliation can finish or roll back a transaction interrupted by process failure; normal API responses must not leave either state pending.

### 8.8 State version

Every successful state-changing command or authoritative internal finalisation increments `InterviewSession.state_version`.

Read-only operations do not increment it. Updating trace-only diagnostic data does not increment it. Background work must use the narrower ownership and generation predicates in Sections 16, 17 and 21 rather than relying on a stale pre-pipeline state version after the pipeline has legitimately advanced its own records.

## 9. Command contract

### 9.1 Endpoint

```http
POST /api/coach/sessions/{session_id}/commands
```

### 9.2 Request envelope

```json
{
  "command_id": "01JEXAMPLE0000000000000000",
  "command_type": "accept_attempt",
  "expected_state_version": 8,
  "payload": {
    "attempt_id": "<opaque-id>"
  },
  "contract_version": "coach_conversation_command_v1"
}
```

`command_id` is a caller-generated UUID or ULID-like safe token of 1 through 64 characters.

### 9.3 Supported commands

```text
start
begin_answer
finish_answer
keep_speaking
pause
resume
cancel_attempt
retry_answer
retry_setup
rebuild_plan
retry_processing
retry_report
request_hint
request_coaching
return_to_review
edit_transcript
accept_attempt
record_self_assessment
update_retention
skip_question
end_session
delete_audio
delete_transcript
```

### 9.4 Command-result persistence

Add `coach_conversation_command_results`:

```text
id VARCHAR(36) primary key
session_id VARCHAR(36) not null FK interview_sessions.id cascade
command_id VARCHAR(64) not null
command_type VARCHAR(64) not null
request_hash VARCHAR(64) not null
expected_state_version INTEGER not null
result_state VARCHAR(32) not null
result_json JSON nullable
created_at DATETIME not null
completed_at DATETIME nullable
```

Constraints:

```text
UNIQUE(session_id, command_id)
INDEX(session_id, created_at)
```

### 9.5 Canonical request hashing

Hash the semantic validated request, not raw JSON bytes.

Algorithm:

1. Validate the command envelope and command-specific payload with Pydantic.
2. Construct this canonical object, excluding `command_id`:

```json
{
  "session_id": "<opaque-id>",
  "command_type": "<opaque-id>",
  "expected_state_version": 8,
  "payload": {},
  "contract_version": "coach_conversation_command_v1"
}
```

3. Use `model_dump(mode="json", exclude_unset=False, exclude_none=False)` so defaults and explicit nulls have one semantic representation.
4. Serialize with Python:

```python
json.dumps(
    canonical_object,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

5. Encode as UTF-8 and store lowercase SHA-256 hexadecimal.

Numbers prohibited by JSON, including NaN and infinity, fail validation before hashing.

### 9.6 Duplicate lookup order

The transaction order is binding:

1. validate the envelope sufficiently to identify the session, command ID and payload schema;
2. calculate the canonical hash;
3. look up `(session_id, command_id)` **before** state-version validation;
4. if a row exists and hash matches, return its original result even if the session has since advanced;
5. if a row exists and hash differs, return HTTP 409 `coach_command_idempotency_conflict`;
6. only for a new command, load the session and validate `expected_state_version`;
7. apply mutation and persist the command result in the same transaction.

This ordering is required so a lost successful response can be retrieved safely after the state version has advanced.

### 9.7 Optimistic concurrency

For a new command, if `expected_state_version != session.state_version`, return HTTP 409:

```json
{
  "error": {
    "code": "coach_conversation_version_conflict",
    "message": "The interview changed since this view was loaded.",
    "current_state_version": 8,
    "current_state": "awaiting_next_action",
    "retryable": false
  }
}
```

This is the only canonical version-conflict code for the conversation command endpoint.

### 9.8 Command response

```json
{
  "command_id": "01JEXAMPLE0000000000000000",
  "result": "completed",
  "session_id": "<opaque-id>",
  "state": "listening",
  "state_version": 8,
  "active_question_id": "<opaque-id>",
  "active_attempt_id": "<opaque-id>",
  "async_job_id": null,
  "allowed_commands": [
    "finish_answer",
    "keep_speaking",
    "pause",
    "request_hint"
  ],
  "contract_version": "coach_conversation_command_result_v1"
}
```

Allowed result values:

```text
completed
accepted_processing
duplicate
invalid_state
version_conflict
idempotency_conflict
invalid_payload
resource_blocked
not_found
permission_denied
stale_claim
```

### 9.9 Exact command semantics

#### `start`

Precondition: `state = ready`.

Effects:

- set `status = active`;
- set `started_at` if absent;
- select the first planned question;
- set active question/root IDs;
- set `asking`;
- append an event.

#### `begin_answer`

Lookup and validation order:

1. Validate payload shape and normalize `client_attempt_id`.
2. Look up `(session_id, client_attempt_id)` **before** conversation-state validation.
3. When an existing attempt is found and its `question_id` and `recording_type` match the request, return that attempt with result `duplicate` and do not mutate session or question state.
4. When an existing attempt is found but question or recording type differs, return `coach_attempt_client_id_conflict`.
5. Only when no existing attempt exists, require `state = asking`, require that the active question belongs to the session, and require that it is not `skipped`.
6. In the same write transaction, require `attempts_created_count < HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION`; otherwise return `coach_attempt_limit_exhausted` without changing session, question, or attempt state.

Only an active question with `question_state = asked` and `accepted_recording_id IS NULL` may create a new attempt. An answered or skipped question cannot be revisited through `begin_answer` in Phase 1. Duplicate lookup always precedes the attempt-limit check, so replaying an already accepted `client_attempt_id` returns its original attempt even when the question has reached the limit.

Payload:

```json
{
  "recording_type": "audio",
  "client_attempt_id": "client-generated-safe-id"
}
```

`recording_type` is `audio` or `text`. `client_attempt_id` is required and unique per session for conversational attempts. Enforce `UNIQUE(session_id, client_attempt_id)` at the database layer.

Effects in one transaction:

- perform a conditional question update equivalent to `attempts_created_count = attempts_created_count + 1 WHERE attempts_created_count < configured_limit`; require exactly one affected row and use the committed new value as the contiguous `attempt_number`;
- reserve one `SessionRecording` in `draft` state only after that conditional allocation succeeds; a transaction rollback rolls back both the counter and attempt row;
- snapshot the current session `audio` retention policy into `SessionRecording.audio_retention_policy`;
- snapshot `HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT` into `SessionRecording.processing_retry_limit` and set `processing_retry_count = 0`;
- set the active attempt;
- require and keep the question aggregate state `asked`;
- transfer `pending_hint_count` and ordered `pending_hint_types_json` to the new attempt/audit event, then reset the question pending-hint fields;
- set session state to `listening`;
- return media limits and the attempt retention snapshot.

#### `finish_answer`

Preconditions:

- `state = listening`;
- payload `attempt_id` equals the active attempt;
- attempt belongs to the active question and session;
- text attempts are in `draft`;
- audio attempts are in `uploaded` and reference the completed upload named by `upload_id`.

Typed payload:

```json
{
  "attempt_id": "<opaque-id>",
  "transcript": "candidate answer"
}
```

Audio payload:

```json
{
  "attempt_id": "<opaque-id>",
  "upload_id": "<opaque-id>"
}
```

For audio, a completed hash-verified upload record for the same attempt and upload ID must exist.

Effects:

- create the typed transcript version or claim audio transcription;
- set `attempt_state = pending_processing` and `submitted_at`;
- increment `processing_generation`;
- create the pending evaluation version and stage rows for that generation; typed attempts bind the new transcript immediately, while audio attempts persist `transcript_version_id = NULL` until successful transcription binds it;
- set the mirrored legacy evaluation state to `pending`;
- set `processing_answer`;
- return the async job ID.

#### `keep_speaking`

Precondition: `state = listening` and payload attempt ID equals the active attempt.

Record a silence-warning acknowledgement, remain listening and increment state version.

#### `pause`

Allowed from `asking`, `listening`, `awaiting_next_action`, `coaching` and `recoverable_error` only when `status = active` and the recoverable error is resumable. Setup failures cannot be paused.

Store the exact state in `resume_state`, set `paused`, set `paused_at` and preserve any draft. Pausing audio uses `MediaRecorder.pause()` and does not finish the answer.

#### `resume`

Preconditions:

- `state = paused`;
- `resume_state` is one of the resumable states above.

Restore it and clear pause fields. If a refreshed browser cannot restore a paused local recorder, the UI offers discard-and-retry or a normal upload of captured media; it must not claim capture resumed.

#### `cancel_attempt`

Preconditions:

- `state = listening`;
- payload attempt ID equals active attempt;
- processing has not started.

Delete or fence cleanup of temporary media, mark `cancelled`, clear active attempt and return to `asking`.

#### `retry_answer`

Allowed from `awaiting_next_action`, `coaching` or an attempt-scoped `recoverable_error` only when all conditions hold:

- `status = active`;
- the payload question ID, when supplied, matches the active question;
- the active question has `question_state = asked`;
- `accepted_recording_id IS NULL`;
- at least one preserved attempt exists for the active question;
- no attempt-processing claim remains active;
- `attempts_created_count < HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION`.

If the attempt limit is exhausted, return `coach_attempt_limit_exhausted` and leave the session in its current state. Otherwise preserve all prior attempts, clear `active_recording_id`, append `attempt_retried` and return to `asking`. Phase 1 does not revisit or retry an already accepted historical question. The candidate selects an eligible preserved attempt before acceptance.

#### `retry_setup`

Preconditions:

- `status = setup`;
- `conversation_state = recoverable_error`;
- `recoverable_error_scope = setup`;
- `setup_attempt_count < setup_max_attempts`;
- `setup_job_id` and `setup_claim_token` are null;
- `deletion_state = not_requested`.

Effects in one claim transaction:

- increment `setup_generation` and `setup_attempt_count`;
- clear setup error fields;
- create a new async job and random claim token;
- persist setup claim timestamps and lease;
- set `conversation_state = planning` while keeping `status = setup`;
- increment `state_version` once;
- append `session_plan_retry_requested` and `session_plan_started` events.

`retry_setup` rebuilds from the persisted `planning_request_json`. It cannot retry attempt processing or report generation.

#### `rebuild_plan`

Preconditions:

- `status = setup` and `conversation_state = ready`;
- `started_at IS NULL`;
- no `SessionRecording` exists for the session;
- no active setup claim exists;
- setup retry budget remains;
- `deletion_state = not_requested`.

Payload:

```json
{
  "refresh_sources": true
}
```

`refresh_sources` is required to be `true` in Phase 1. The command reuses the normalized persisted `planning_request_json`, current retention policy and the latest eligible source versions. It does not accept arbitrary plan JSON.

Effects:

- increment `setup_generation` and `setup_attempt_count`;
- create a new fenced setup claim;
- set `conversation_state = planning` while keeping `status = setup`;
- increment `state_version` once;
- append `session_plan_rebuild_requested` and `session_plan_started` events.

Successful finalisation atomically replaces all planned questions and session evidence records, stores a new immutable plan, increments `session_plan_amendment_version`, and returns to `ready`. If the rebuild fails, the previously completed plan remains stored for audit but cannot be started until retry succeeds or the session is abandoned/deleted.

#### `retry_processing`

Duplicate command lookup and request-hash comparison occur before live-state or retry-budget validation under Sections 9.5 and 9.6.

Preconditions:

- `state = recoverable_error`;
- the active attempt has `attempt_state = recoverable_error`;
- the recorded failure is retryable;
- no attempt or stage claim is active;
- `processing_retry_count < processing_retry_limit`;
- the immutable input required by the deterministic restart stage remains available.

If the retry count is exhausted, return `coach_attempt_retry_budget_exhausted`. If required audio or transcript input was deleted or is otherwise unavailable, return `coach_attempt_retry_source_unavailable`. Neither failure mutates state or consumes budget.

In one claim transaction:

- increment `processing_retry_count` exactly once;
- increment `processing_generation`;
- set `attempt_state = pending_processing`;
- clear attempt error fields and `processing_completed_at`;
- create a new pending evaluation version;
- determine the restart stage from the prior terminal stage set:
  1. restart at `transcription` when no usable immutable transcript exists;
  2. otherwise restart at `speech_analysis` when audio speech analysis is missing or retryably failed;
  3. otherwise restart at `content_evaluation`, `evidence_grounding`, `follow_up_decision`, or `coaching_enrichment`, choosing the earliest retryably failed or incomplete applicable stage in pipeline order;
- create new-generation stage rows for every applicable stage;
- for valid completed stages before the restart stage, mark the new row `reused`, set `reused_from_stage_id`, and require identical input hashes, source transcript version, audio hash where applicable, and contract versions;
- set the restart stage and downstream applicable rows to `pending`; no downstream result is reused;
- persist the new async job, shared deadline and claim metadata;
- clear the session recoverable-error fields;
- set `conversation_state = processing_answer`;
- increment session `state_version` once;
- append `attempt_processing_retry_requested` and `attempt_processing_started`.

Automatic retry or repair attempts inside one processing generation consume the stage `attempt_count` or `repair_count`; they do not increment `processing_retry_count`. A worker may be queued only after this transaction commits.

#### `retry_report`

Two exact modes are supported.

Initial completion retry:

- `state = recoverable_error`;
- `recoverable_error_code` identifies a retryable initial report failure;
- no current report claim exists;
- claim a new initial report job with `report_build_reason = manual_retry` and set `reporting`.

Completed-session rebuild retry:

- `state = completed` and `status = completed`;
- `report_state = failed`;
- `report_build_reason` is `transcript_deletion_rebuild` or `reflection_update_rebuild`;
- no current report claim exists;
- atomically claim a rebuild job under the current `activity_version` while preserving the existing `transcript_deletion_rebuild` or `reflection_update_rebuild` reason;
- keep conversation state and coarse status `completed`.

The two finalisation fences remain those in Section 27.11.

#### `request_hint`

Allowed from `asking` or `listening`.

Payload:

```json
{
  "hint_type": "star_structure"
}
```

Allowed types:

```text
star_structure
competency_reminder
experience_category
clarify_question
```

A hint cannot contain a complete model answer, fabricated experience, unsupported achievement, hidden rubric or Candidate Intelligence weakness.

Attribution is deterministic:

- in `listening`, increment the active attempt `hint_count`;
- in `asking`, when no attempt exists, increment `SessionQuestion.pending_hint_count` and append the canonical type to `pending_hint_types_json`;
- `begin_answer` atomically transfers the pending count to the new attempt, persists the ordered hint-type list in the attempt-creation event payload, then resets the question pending fields to zero/null;
- if the question is skipped before an attempt starts, the hint events remain auditable but no attempt receives them.

#### `request_coaching`

Preconditions:

- `state = awaiting_next_action`;
- payload attempt ID belongs to active question;
- the attempt has current evaluation state `completed` or `unavailable`.

Set `coaching`. Return persisted deterministic coaching when available; otherwise claim bounded enrichment. Failure returns deterministic evidence-backed review content.

#### `return_to_review`

Precondition: `state = coaching`. Return to `awaiting_next_action`.

#### `edit_transcript`

Preconditions:

- `state` is `awaiting_next_action` or `coaching`;
- payload attempt ID belongs to active question;
- current transcript exists and attempt is not deleted.

Payload:

```json
{
  "attempt_id": "<opaque-id>",
  "transcript": "corrected transcript",
  "edit_reason": "transcription_error"
}
```

In one transaction, create an immutable candidate-edit transcript version, increment candidate-visible `attempt_version`, increment `processing_generation`, set `attempt_state = pending_processing`, clear `processing_completed_at` and attempt error fields, supersede pending follow-up/coaching derived from the old transcript, create a new pending evaluation version, persist the new job/stage claim and set `conversation_state = processing_answer`. Increment session `state_version` once and append `transcript_edited` plus `attempt_processing_started`. Original delivery metrics remain tied to original audio. A worker may be queued only after the transaction commits.

#### `accept_attempt`

Preconditions:

- `state` is `awaiting_next_action` or `coaching`;
- payload contains explicit `attempt_id`;
- the attempt belongs to the active question and session;
- the active question has `question_state = asked` and `accepted_recording_id IS NULL`;
- attempt is not cancelled, invalid, deleted or skipped;
- current evaluation is terminal: `completed` or `unavailable`.

Payload:

```json
{
  "attempt_id": "selected-attempt-id"
}
```

The selected attempt may be any preserved eligible attempt for the active question, not only `active_recording_id`. Selection occurs before the question has been accepted in the current `acceptance_generation`. If an accepted pointer already exists, or `last_accepted_generation = acceptance_generation`, return `coach_attempt_already_accepted` without mutation.

Effects:

- atomically require `accepted_recording_id IS NULL`;
- atomically require `last_accepted_generation IS NULL OR last_accepted_generation < acceptance_generation`;
- set `SessionQuestion.accepted_recording_id` to the explicit attempt;
- set `last_accepted_generation = acceptance_generation`;
- set `question_state = answered`;
- set `accepted_at` on the selected attempt;
- set session active recording to the selected attempt for follow-up evaluation;
- run follow-up admission using the selected attempt only;
- transition to follow-up, advance or reporting.

Acceptance is a workflow choice, not a quality claim. Phase 1 permits exactly one acceptance transition per `acceptance_generation`. Ordinary retries, edits, or historical selection do not increment the generation and cannot replace an accepted answer. Privacy deletion of the currently accepted transcript is the sole Phase 1 operation that increments `acceptance_generation`; it clears the pointer and permits one replacement acceptance in the new generation.

#### `record_self_assessment`

Allowed from `awaiting_next_action`, `coaching` and `completed`.

Payload:

```json
{
  "attempt_id": "<opaque-id>",
  "comfort_level": "medium",
  "felt_complete": true,
  "note": "Optional candidate reflection"
}
```

Vocabulary:

```text
low
medium
high
```

Rules:

- attempt must belong to the session;
- note is optional, trimmed, maximum 1000 Unicode code points;
- store on `SessionRecording.self_assessment_json` with `recorded_at` and contract version;
- overwrite only the candidate's current reflection for that attempt while emitting a non-content event;
- increment `attempt_version` and `activity_version`;
- do not change evaluation, delivery, evidence or readiness;
- a completed-session update invalidates and rebuilds the report through Section 29.8 because candidate reflection is report content.

#### `update_retention`

Allowed from `ready`, `asking`, `listening`, `awaiting_next_action`, `coaching`, `paused` and `recoverable_error`. For `recoverable_error`, it is valid in both setup and active status and does not change the error scope.

Payload:

```json
{
  "audio": "retain_until_deleted"
}
```

Rules:

- updates the session policy for **future attempts only**;
- attempts already created keep the policy snapshot stored on that attempt;
- transcript policy remains `retain` in Phase 1;
- changing to `delete_after_processing` does not retroactively delete retained existing audio;
- changing to `retain_until_deleted` cannot rescue audio already deleted or delete-pending;
- persist policy in session plan amendment metadata;
- increment `state_version`, `retention_version` and `session_plan_amendment_version`;
- do **not** increment `activity_version`, because the policy affects only future attempts and is not an analytical report input;
- append `retention_policy_updated`.

#### `skip_question`

Precondition: `state = asking`.

Persist explicit skipped state without score and advance or report.

#### `end_session`

Allowed from `asking`, `awaiting_next_action`, `coaching`, active-status `recoverable_error` with `recoverable_error_scope = attempt_processing`, and conditionally `paused` under Section 8.6. Setup failures and initial-report failures use `retry_setup` or `retry_report`; they are not reportable through `end_session`.

Payload:

```json
{
  "unaccepted_attempt_action": "accept_attempt",
  "attempt_id": "attempt_<opaque-id>",
  "paused_draft_action": null
}
```

`unaccepted_attempt_action` values:

```text
accept_attempt
exclude_attempt
not_applicable
```

Canonical reportable session state means all of the following are true after applying the transaction below:

- `status = active` and `deletion_state = not_requested`;
- no setup claim, report claim, or unfenced attempt-processing claim remains;
- the effective state is `asking`, `awaiting_next_action`, `coaching`, or `recoverable_error` scoped to the current attempt; a paused session uses its stored `resume_state`;
- every earlier asked question is already `answered` or `skipped`;
- the current question is resolved by acceptance or exclusion;
- zero accepted attempts is permitted and produces a not-enough-evidence report rather than blocking completion.

The command executes one transaction in this exact order:

1. Resolve duplicate command lookup and optimistic concurrency through Sections 9.5-9.7.
2. If paused from `listening`, require `paused_draft_action = discard_draft`; fence and cancel the draft attempt, delete its owned temporary media, and continue as `asking`. Other paused states use their `resume_state`.
3. Inspect the current question and all its unaccepted attempts.
4. For `accept_attempt`, require an explicit eligible terminal attempt and run the same atomic acceptance-generation mutation as `accept_attempt`, setting the question to `answered`. Do not admit or persist a follow-up. Mark any stored proposal as `suppressed_session_end` in content-free diagnostics.
5. For `exclude_attempt`, require no accepted pointer. Fence any recoverable attempt-processing generation. A recoverable attempt becomes terminal `unavailable` with reason `candidate_ended_session`; already terminal attempts remain unchanged and unaccepted. Set the current question to `skipped`, clear its pending hints, and append `unaccepted_attempts_excluded`.
6. `not_applicable` is valid only when no unaccepted submitted attempt exists. If the current question is merely `asked`, set it to `skipped` with event reason `session_ended_before_answer`.
7. Clear `active_recording_id`, `active_question_id`, and `active_root_question_id`. Pending questions that were never asked remain `pending` and are reported as not asked; they are not silently scored or converted to candidate skips.
8. Increment `activity_version` and `state_version` once. Allocate all emitted session events through `event_version`; multiple events may share the new state version.
9. Create the initial report claim with `report_build_reason = initial_completion`, snapshot the resulting accepted-attempt set and activity version, set `report_state = building`, and transition to `conversation_state = reporting` while coarse status remains `active`.
10. Queue the report worker only after commit.

Follow-up admission is always suppressed during `end_session`. The report includes only explicit accepted attempts and never treats excluded, pending, recoverable, or merely completed unaccepted attempts as canonical answers.

#### `delete_audio`

Payload:

```json
{
  "attempt_id": "<opaque-id>"
}
```

Exact privacy effects are in Section 29. It never deletes transcript or evaluation implicitly.

Additional command preconditions:

- the attempt belongs to the session;
- the session is not in `processing_answer`;
- while `paused`, the target is not the locally captured active listening draft;
- if a recoverable processing claim still requires the audio, the command first cancels and fences that claim, marks audio-dependent retry unavailable and then performs deletion.

#### `delete_transcript`

Payload:

```json
{
  "attempt_id": "attempt_<opaque-id>"
}
```

Phase 1 does not retain audio after transcript deletion and does not support post-deletion retranscription. To correct a transcript while preserving the answer, use `edit_transcript` before deletion. Exact privacy and report-rebuild effects are in Section 29. During an active session, the target must belong to the active question. Deleting a historical non-selected attempt preserves the current review state; deleting the active, accepted, coached or failing attempt returns the session to `asking` for that question.

### 9.10 Derived allowed-command projection

Appendix A is a convenience view only. It must be generated from or tested against the Section 8.5 registry. A mismatch is a test failure.

## 10. Live session projection

## 10.1 Endpoint

Add:

```http
GET /api/coach/sessions/{session_id}/live
```

This is the authoritative browser read for conversational sessions.

## 10.2 Read behaviour

Before returning, the service must:

1. Load the session through the repository.
2. Run targeted reconciliation for stale conversational claims.
3. Resolve current state invariants.
4. Compute allowed commands deterministically.
5. Return only bounded, user-safe content.

This endpoint is a read plus reconciliation boundary, matching the existing Coach reconciliation approach. It must not generate questions, evaluations or reports.

## 10.3 Response shape

```json
{
  "session_id": "<opaque-id>",
  "experience_version": "conversational_v1",
  "status": "active",
  "conversation_state": "awaiting_next_action",
  "state_version": 12,
  "activity_version": 8,
  "retention_version": 4,
  "active_question": {
    "attempts_created_count": 2,
    "attempt_limit": 5,
    "attempts_remaining": 3
  },
  "root_question": {},
  "active_attempt": {
    "processing_retry_count": 1,
    "processing_retry_limit": 2,
    "processing_retries_remaining": 1
  },
  "processing": {
    "job_id": null,
    "stage": null,
    "state": "completed",
    "retryable": false,
    "retry_count": 1,
    "retry_limit": 2,
    "retries_remaining": 1
  },
  "progress": {
    "planned_questions_total": 6,
    "planned_questions_completed": 2,
    "follow_ups_completed": 1,
    "current_planned_position": 3
  },
  "retention": {
    "audio_policy": "delete_after_processing",
    "current_audio_state": "deleted"
  },
  "allowed_commands": [
    "request_coaching",
    "retry_answer",
    "edit_transcript",
    "accept_attempt",
    "pause",
    "end_session"
  ],
  "silence_policy": {
    "warning_ms": 4000,
    "finish_prompt_ms": 9000
  },
  "recoverable_error": null,
  "report_state": "not_started",
  "contract_version": "coach_live_view_v1"
}
```

## 10.4 Polling transport

Phase 1 uses HTTP polling, not WebSockets.

Recommended client policy:

```text
asking/listening/awaiting/coaching: poll only on commands or focus restore
processing_answer/reporting: poll every 1.5 seconds, back off to 3 seconds after 20 seconds
paused/completed: no periodic polling
```

The client may also continue polling the generic async-job endpoint for diagnostics, but the live projection is the state authority.

## 10.5 Refresh recovery

On page load or browser focus restoration:

1. Fetch `/live`.
2. Render the server state.
3. Never infer current state solely from local browser flags.
4. If server state is `listening` but no restorable local media capture exists, show a recovery choice rather than automatically changing server state.
5. If server state is `processing_answer`, show processing and resume polling.
6. If server state is `awaiting_next_action`, restore review and available commands.
7. If state is `completed`, route to the version-aware report.

---

## 11. Session event stream

## 11.1 New table

Add `interview_session_events`:

```text
id VARCHAR(36) primary key
session_id VARCHAR(36) not null FK interview_sessions.id cascade
sequence_number INTEGER not null
event_type VARCHAR(64) not null
state_before VARCHAR(32) nullable
state_after VARCHAR(32) nullable
state_version INTEGER not null
question_id VARCHAR(36) nullable
recording_id VARCHAR(36) nullable
command_id VARCHAR(64) nullable
actor_type VARCHAR(32) not null
payload_json JSON nullable
created_at DATETIME not null
```

Allowed `actor_type`:

```text
candidate
system
worker
reconciler
migration
```

Actor assignment is deterministic:

- `candidate` for an authenticated candidate command, including its events committed in the same command transaction;
- `system` for server-owned deterministic transitions not initiated by a worker, such as automatic advancement, timeout prompts, or policy cleanup;
- `worker` for a currently fenced asynchronous setup, attempt, report, audio-cleanup, export, or deletion worker;
- `reconciler` for `coach_reconciliation.py` recovery mutations;
- `migration` for migration or explicit backfill events.

No other value is valid in Phase 1. `actor_type` identifies the origin of the state mutation; it is not an authorization role and must not contain provider or model names.

Constraints:

```text
UNIQUE(session_id, sequence_number)
INDEX(session_id, created_at)
INDEX(session_id, event_type)
```

## 11.2 Event sequence allocation

`InterviewSession.event_version` is the sole authoritative event sequence allocator. `state_version` is never used as an event sequence because one command may emit multiple events without multiple state transitions.

For a transaction that emits `N` events:

1. atomically increment `event_version` by `N`;
2. allocate the contiguous range `old_event_version + 1` through `old_event_version + N`;
3. insert events in deterministic command-defined order using those numbers as `sequence_number`;
4. commit state mutations and events in the same transaction.

If any event insert fails, the transaction rolls back, including the `event_version` increment. Do not use `state_version`, a suffix scheme, or `SELECT MAX(sequence_number) + 1`.

## 11.3 Required event types

```text
session_plan_started
session_plan_completed
session_plan_failed
session_plan_retry_requested
session_plan_rebuild_requested
session_plan_rebuilt
session_plan_claim_expired
session_started
question_presented
answer_capture_started
silence_warning_presented
keep_speaking_selected
hint_requested
hint_presented
answer_capture_paused
answer_capture_resumed
answer_capture_cancelled
answer_submitted
attempt_processing_started
attempt_processing_retry_requested
attempt_processing_completed
attempt_processing_failed
transcript_edited
coaching_requested
coaching_presented
attempt_retried
attempt_accepted
unaccepted_attempts_excluded
follow_up_suppressed_session_end
self_assessment_recorded
retention_policy_updated
question_skipped
follow_up_created
follow_up_presented
question_advanced
session_paused
session_resumed
report_claimed
report_completed
report_fallback_completed
report_rebuild_claimed
report_rebuild_completed
report_rebuild_failed
audio_cleanup_claimed
audio_deleted
audio_delete_failed
transcript_deleted
hard_deletion_requested
hard_deletion_failed
hard_deletion_claim_expired
session_abandoned
```

`hard_deletion_completed` is deliberately **not** a `coach_session_events` value because successful hard deletion removes the entire session event stream. Completion is persisted only in `coach_session_deletion_results` and emitted as content-free telemetry. `hard_deletion_failed` remains a session event only while the hidden failed-deletion shell exists.

## 11.4 Event payload privacy

Event payloads may include:

- reason codes;
- contract versions;
- counts;
- non-content state metadata.

They must not include:

- raw audio;
- full transcripts;
- CV text;
- full evidence excerpts;
- prompts;
- model responses;
- secrets.

---

## 12. Session planning and immutable evidence contract

### 12.1 Required session columns

Add to `interview_sessions`:

```text
planning_request_json JSON NULL
session_plan_json JSON NULL
session_plan_contract_version VARCHAR(64) NULL
evaluation_contract_version VARCHAR(64) NULL
report_contract_version VARCHAR(64) NULL
compatibility_key VARCHAR(256) NULL
retention_policy_json JSON NULL
session_plan_amendment_version INTEGER NOT NULL DEFAULT 0
report_build_reason VARCHAR(32) NULL
```

### 12.2 Session plan schema

```json
{
  "plan_id": "<opaque-id>",
  "role": {
    "title": "Senior Solution Architect",
    "role_family": "solution_architecture",
    "role_family_label": null,
    "role_level": "senior",
    "industry": "technology"
  },
  "interview": {
    "type": "mixed",
    "difficulty": "realistic",
    "duration_minutes": 30,
    "planned_question_count": 6,
    "focus_areas": [
      "stakeholder_management",
      "architecture"
    ],
    "locale": "en-GB",
    "allowed_answer_modes": [
      "audio",
      "text"
    ]
  },
  "evidence_selection": {
    "application_cv": "approved_only",
    "master_cv": "include",
    "question_bank": "reviewed_final_only",
    "selected_question_bank_record_ids": [],
    "company_research": "include_if_fresh",
    "draft_evidence_consent": false
  },
  "evidence_snapshot": {
    "package_hash": "sha256:<64-lowercase-hex>",
    "record_count": 12,
    "contract_version": "coach_session_evidence_snapshot_v1"
  },
  "contracts": {
    "question_generation": "coach_question_generation_v2",
    "evaluation": "coach_conversational_rubric_v1",
    "delivery": "coach_delivery_policy_v1",
    "evidence_grounding": "coach_evidence_grounding_v1",
    "follow_up": "coach_follow_up_v1",
    "report": "coach_conversational_report_v1"
  },
  "retention": {
    "audio": "delete_after_processing",
    "transcript": "retain"
  },
  "compatibility": {
    "key": "<opaque-id>",
    "version": "coach_progress_compatibility_v1"
  },
  "created_at": "<opaque-id>"
}
```

### 12.3 Source selection

For application-linked sessions, select in this order:

1. explicitly approved generated application CV asset;
2. current application CV only when creation policy allows `current_if_no_approved`;
3. confirmed Master CV when included;
4. Question Bank entries permitted by the request and their approval state;
5. job posting and application requirements;
6. fresh cached company research when included.

Draft Question Bank records require explicit consent and remain labelled `draft`.

A current application CV selected through `current_if_no_approved` is persisted with `approval_state = candidate_selected_unapproved`. It may support or partially support a candidate claim, but it cannot by itself produce `conflicting`, cannot outrank an approved/confirmed source, and must be identified as unapproved in evidence explanations.

### 12.4 Mandatory immutable evidence records

Add `coach_session_evidence_records`:

```text
id VARCHAR(36) primary key
session_id VARCHAR(36) not null FK interview_sessions.id cascade
evidence_id VARCHAR(128) not null
source_type VARCHAR(64) not null
source_record_id VARCHAR(128) not null
source_record_version VARCHAR(128) not null
source_path VARCHAR(512) not null
snapshot_text TEXT not null
approval_state VARCHAR(32) not null
content_hash VARCHAR(128) not null
snapshot_hash VARCHAR(128) not null
created_at DATETIME not null
```

Constraints:

```text
UNIQUE(session_id, evidence_id)
```

Allowed `approval_state`:

```text
approved
confirmed
reviewed_final
reviewed
candidate_selected_unapproved
draft
context_only
```

`context_only` applies to job, company, or role context and cannot ground candidate-experience claims.

Every evidence record that may be used by question generation, evaluation, grounding, coaching or report explanation **must** have an immutable bounded snapshot. References and hashes without a snapshot are insufficient for `conversational_v1`.

Limits:

- maximum 30 evidence records per session;
- maximum 2000 Unicode code points per record;
- maximum 40000 Unicode code points across the package;
- normalize to NFC and LF line endings before hashing;
- redact secrets and unrelated personal data before persistence;
- snapshot text must be a bounded excerpt or structured evidence statement, not a full duplicated CV or document.

The package hash is SHA-256 over the ordered canonical records, sorted by `evidence_id`, using the canonical JSON rules from Section 9.5.

Source changes after planning do not rewrite this package. Before `start`, the candidate may invoke the `rebuild_plan` command in Section 9.9; no other mutation refreshes evidence or questions in-place.

Source deletion follows the privacy invalidation rules and may make a historical session non-reproducible after the candidate chooses deletion; privacy takes precedence over reproducibility.

### 12.5 Transcript and evidence offsets

All transcript and evidence spans use:

```text
zero-based Unicode code-point offsets
half-open interval [start, end)
```

The referenced text is first normalized to Unicode NFC and LF line endings. Offsets are not UTF-8 byte offsets and not JavaScript UTF-16 code-unit offsets.

Backend validation must confirm:

```text
0 <= start < end <= len(normalized_text_in_unicode_code_points)
normalized_text[start:end] == quoted_snapshot
```

Frontend code must translate code-point offsets explicitly; direct JavaScript `string.slice()` with backend offsets is prohibited unless a tested conversion helper is used.

Required tests include:

- emoji outside the Basic Multilingual Plane;
- combining marks before and after NFC normalization;
- Hindi or another non-Latin script;
- CRLF input normalized to LF.

### 12.6 Compatibility key

Generate a deterministic key from:

```text
role_family_component
role_level
interview_type
difficulty
evaluation_contract_version
locale
```

For registered families, `role_family_component = role_family`.

For `role_family = other`, compute:

```text
normalized_label = NFKC(role_family_label).casefold().trim().collapse_internal_whitespace()
role_family_component = "other:" + first_16_hex(sha256(UTF8(normalized_label)))
```

Two `other` sessions are compatible only when their normalized-label hashes match. `industry` remains excluded. Use exact compatibility in Phase 1.

### 12.7 Planning validation

A plan is valid only when:

- Section 7 request vocabulary and bounds pass;
- planned question count is within the Section 7 numeric bound; duration mapping is a default only;
- every focus area is registered;
- every planned question has one canonical Section 4.2 category;
- `behavioural` plans contain only `behavioural_group` categories;
- `role_specific_verbal` plans contain only `role_specific_group` categories;
- `mixed` plans contain at least one planned question from each group;
- adaptive follow-ups inherit the root category and are excluded from this distribution check;
- every selected evidence record has an immutable snapshot and hashes;
- contract versions are supported;
- retention policy is valid;
- no prohibited inference dimension exists;
- all planned questions are persisted before `ready`.

### 12.8 Question-count defaults

| Duration | Planned questions |
|---:|---:|
| 10-15 minutes | 3 |
| 16-25 minutes | 4 |
| 26-35 minutes | 6 |
| 36-50 minutes | 8 |
| 51-70 minutes | 10 |
| 71-90 minutes | 12 |

When `planned_question_count` is omitted, use the table. Any candidate-selected integer from 3 through 12 overrides the table regardless of duration. The UI may warn about likely pacing, but the server must not reject a valid override. Adaptive follow-ups do not count.

### 12.9 Standard interviewer contract

Phase 1 uses:

```text
persona_id = standard_professional_v1
```

It controls phrasing and transitions only. It does not change rubric, permissions or follow-up limits. Existing legacy persona configuration remains readable but does not enable Phase 2 persona behaviour.

## 13. Question model extensions

### 13.1 Schema and category vocabulary

Add to `session_questions`:

```text
question_kind VARCHAR(32) NOT NULL DEFAULT 'planned'
root_question_id VARCHAR(36) NULL FK session_questions.id SET NULL
parent_question_id VARCHAR(36) NULL FK session_questions.id SET NULL
follow_up_depth INTEGER NOT NULL DEFAULT 0
follow_up_reason VARCHAR(64) NULL
follow_up_target_dimension VARCHAR(64) NULL
follow_up_aggregation_role VARCHAR(32) NULL
follow_up_source_recording_id VARCHAR(36) NULL FK session_recordings.id SET NULL
follow_up_source_transcript_version_id VARCHAR(36) NULL FK interview_transcript_versions.id SET NULL
follow_up_context_json JSON NULL
follow_up_generation_json JSON NULL
source_deleted BOOLEAN NOT NULL DEFAULT FALSE
question_state VARCHAR(32) NOT NULL DEFAULT 'pending'
accepted_recording_id VARCHAR(36) NULL FK session_recordings.id SET NULL
attempts_created_count INTEGER NOT NULL DEFAULT 0
acceptance_generation INTEGER NOT NULL DEFAULT 0
last_accepted_generation INTEGER NULL
question_category_contract_version VARCHAR(64) NULL
pending_hint_count INTEGER NOT NULL DEFAULT 0
pending_hint_types_json JSON NULL
question_contract_version VARCHAR(64) NULL
asked_sequence INTEGER NULL
```

For new conversational questions, the existing `SessionQuestion.category` column stores exactly one canonical lowercase category:

```text
behavioural
situational
culture
technical
domain
commercial
```

Persist `question_category_contract_version = coach_question_category_v1`. Adaptive follow-ups inherit the root question category exactly.

Allowed `question_kind`:

```text
planned
adaptive_follow_up
```

Allowed `question_state`:

```text
pending
asked
answered
skipped
```

Constraints:

1. Planned questions have `follow_up_depth = 0`.
2. Follow-ups have a non-null root and parent question.
3. Follow-up depth must be 1 or 2.
4. Follow-up reason must be from the allowlist.
5. Follow-up target dimension and aggregation role must equal the deterministic mapping in Section 25.5.
6. `accepted_recording_id`, when present, must belong to the same session and question. Enforce in repository service; add database constraints where feasible.
7. `asked_sequence` is unique within a session when non-null.
8. `pending_hint_count >= 0`; `pending_hint_types_json` is a bounded ordered array of canonical hint types and is null when the count is zero.
9. New conversational category values must pass the Section 4.2 enum and interview-type distribution validation.
10. `attempts_created_count` is monotonic and never decreases after cancellation, invalidation, transcript deletion, or media deletion.
11. `last_accepted_generation`, when non-null, must be less than or equal to `acceptance_generation`.
12. `accepted_recording_id IS NOT NULL` requires `last_accepted_generation = acceptance_generation`.

SQLite cannot express all cross-table ownership constraints. The repository must enforce them transactionally and tests must cover them.

### 13.2 Authoritative question-state mutations

`question_state` is a persisted aggregate state, not the live session state.

| Operation | Required prior question state | Result | Additional mutation |
|---|---|---|---|
| setup persists a planned or follow-up question | none | `pending` | `accepted_recording_id = NULL` |
| `start` or advancement presents a pending question | `pending` | `asked` | allocate `asked_sequence` exactly once |
| `retry_answer` presents an unaccepted question again | `asked` | `asked` | require `accepted_recording_id IS NULL`; no aggregate question change |
| `accept_attempt` | `asked` | `answered` | atomically require a null pointer and an unused current `acceptance_generation`; set the explicit pointer plus `last_accepted_generation`; advancement follows |
| `skip_question` | `pending` or `asked` and no accepted attempt | `skipped` | clear active attempt; create no accepted attempt |
| delete the accepted transcript | `answered` | `asked` | clear `accepted_recording_id`; increment `acceptance_generation`; preserve `last_accepted_generation`; permit one replacement acceptance in the new generation per Section 29 |
| delete a non-accepted attempt | any | unchanged | no question-state mutation |

`answered` means an explicit accepted attempt exists and is terminal for normal Phase 1 conversational navigation. Retrying or replacing an accepted answer is out of scope except after privacy deletion of that accepted transcript, which creates a new acceptance generation and returns the question to `asked`. `skipped` is terminal; a skipped question cannot later accept an attempt in Phase 1.

---

## 14. Attempt persistence extensions

## 14.1 `SessionRecording` remains the attempt aggregate

Add to `session_recordings`:

```text
attempt_number INTEGER NULL
attempt_kind VARCHAR(32) NULL
retry_of_recording_id VARCHAR(36) NULL FK session_recordings.id SET NULL
attempt_state VARCHAR(32) NULL
attempt_version INTEGER NOT NULL DEFAULT 0
processing_generation INTEGER NOT NULL DEFAULT 0
processing_retry_count INTEGER NOT NULL DEFAULT 0
processing_retry_limit INTEGER NOT NULL DEFAULT 0
current_transcript_version_id VARCHAR(36) NULL FK interview_transcript_versions.id SET NULL
current_evaluation_version_id VARCHAR(36) NULL FK interview_attempt_evaluations.id SET NULL
accepted_at DATETIME NULL
submitted_at DATETIME NULL
processing_started_at DATETIME NULL
processing_completed_at DATETIME NULL
audio_retention_policy VARCHAR(32) NULL
audio_retention_state VARCHAR(32) NULL
audio_deleted_at DATETIME NULL
audio_content_hash VARCHAR(128) NULL
client_attempt_id VARCHAR(64) NULL
hint_count INTEGER NOT NULL DEFAULT 0
self_assessment_json JSON NULL
self_assessment_updated_at DATETIME NULL
```

Conversational allowed `attempt_kind`:

```text
primary
retry
follow_up
```

Conversational allowed `attempt_state`:

```text
draft
uploaded
pending_processing
completed
recoverable_error
unavailable
invalid
cancelled
deleted
skipped
```

Legacy rows may retain null values for newly conversational fields. New conversational rows must persist a positive `processing_retry_limit` snapshot unless the configured limit is zero; `processing_retry_count` must never exceed that snapshot.

## 14.2 Attempt numbering

Within each question:

```text
attempt_number is a contiguous positive integer starting at 1
```

Allocate through an atomic repository operation.

Add unique index:

```text
UNIQUE(question_id, attempt_number)
UNIQUE(session_id, client_attempt_id)
```

The second constraint applies only to conversational attempts; legacy rows may retain null `client_attempt_id`.

For legacy recordings, backfill attempt numbers ordered by:

```text
created_at ASC, id ASC
```

Backfill `attempt_kind`:

```text
first -> primary
later -> retry
```

Do not infer acceptance for legacy sessions.

## 14.3 Attempt acceptance

The accepted answer is authoritative through:

```text
SessionQuestion.accepted_recording_id
```

`SessionRecording.accepted_at` is a denormalized audit convenience.

Repository acceptance transaction must:

1. Receive an explicit `attempt_id`.
2. Validate that the selected attempt belongs to the active question and session.
3. Validate a terminal current evaluation state of `completed` or `unavailable`.
4. Reject cancelled, invalid, deleted, skipped or still-processing attempts.
5. Atomically require `SessionQuestion.accepted_recording_id IS NULL`, `question_state = asked`, and `last_accepted_generation IS NULL OR last_accepted_generation < acceptance_generation`.
6. Set `accepted_recording_id` to the selected attempt, set `last_accepted_generation = acceptance_generation`, including an earlier preserved retry when chosen.
7. Set `question_state = answered` and set the selected attempt `accepted_at`.
8. Increment session `activity_version` and `state_version`.
9. Append an event.

A retry never becomes accepted automatically, and `active_recording_id` is not an implicit acceptance selector.

### 14.4 Authoritative attempt-state mutations

| Operation | Required prior state | Result state | Binding effects |
|---|---|---|---|
| `begin_answer` | no attempt | `draft` | snapshot `audio_retention_policy`; set active attempt |
| successful audio upload finalisation | `draft` | `uploaded` | persist owned URI/hash/upload result |
| `finish_answer` for text | `draft` | `pending_processing` | create transcript version; set `submitted_at`; increment and claim `processing_generation` |
| `finish_answer` for audio | `uploaded` | `pending_processing` | verify upload/hash; set `submitted_at`; increment and claim `processing_generation` |
| pipeline completes with evaluation `completed` | `pending_processing` | `completed` | persist terminal evaluation and `processing_completed_at` |
| pipeline completes with terminal evaluation unavailable | `pending_processing` | `unavailable` | preserve transcript/stage diagnostics; no quality downgrade |
| retryable pipeline failure | `pending_processing` | `recoverable_error` | clear matching worker claim; expose `retry_processing` |
| `retry_processing` claim transaction | `recoverable_error` | `pending_processing` | increment generation; create pending evaluation/stages and worker claim |
| `edit_transcript` re-evaluation claim | `completed` or `unavailable` | `pending_processing` | create transcript/evaluation version; increment generation and claim worker |
| terminal invalid media/transcript | `draft`, `uploaded` or `pending_processing` | `invalid` | no acceptance permitted |
| `cancel_attempt` | `draft` or `uploaded` before processing | `cancelled` | clear active attempt and fence media cleanup |
| transcript deletion | any non-deleted state | `deleted` | physical deletion and worker fencing per Section 29 |
| legacy skip materialisation only | none | `skipped` | conversational commands do not create skipped attempts |

`finish_answer` must set `attempt_state = pending_processing` in the same transaction that increments `processing_generation`, creates the async job/stage ownership and transitions the session to `processing_answer`. A worker fence that requires `pending_processing` therefore always has a persisted matching state.

Acceptance sets `accepted_at` and the question pointer; it does not change the terminal attempt state. No normal Phase 1 conversational selection command clears or replaces an accepted attempt; privacy-driven transcript deletion may clear the pointer under Section 29.

## 14.5 Legacy canonical-attempt behaviour

`coach_aggregation.resolve_canonical_attempts()` remains unchanged for `legacy_v1`.

Create a separate conversational resolver:

```text
resolve_conversational_accepted_attempts()
```

It must use explicit accepted recordings only.

Do not modify legacy report results by changing the existing canonical resolver.

---

## 15. Transcript versioning and mutation generations

### 15.1 Transcript-version table

Add `interview_transcript_versions`:

```text
id VARCHAR(36) primary key
recording_id VARCHAR(36) not null FK session_recordings.id cascade
version_number INTEGER not null
transcript TEXT nullable
source VARCHAR(32) not null
content_hash VARCHAR(128) nullable
edit_reason VARCHAR(64) nullable
created_by VARCHAR(32) not null
processing_generation INTEGER nullable
created_at DATETIME not null
```

Constraint:

```text
UNIQUE(recording_id, version_number)
```

Allowed `source`:

```text
transcription
candidate_text
candidate_edit
recovered_transcription
```

Allowed `created_by`:

```text
system
candidate
```

### 15.2 Separate candidate and processing versions

`attempt_version` and `processing_generation` have different purposes.

`attempt_version`:

- protects candidate-visible attempt mutation;
- increments for candidate transcript edit, self-assessment update, deletion and other direct attempt commands;
- does not increment merely because a worker persists an intermediate transcript or stage row in its own claimed generation.

`processing_generation`:

- increments atomically whenever `finish_answer`, `edit_transcript` or `retry_processing` claims a new pipeline;
- is immutable for the life of that job;
- is the authoritative worker fence;
- may create and promote transcript/evaluation versions inside that generation without invalidating itself.

### 15.3 Current transcript compatibility field

Keep `SessionRecording.transcript` as the denormalized current transcript for legacy readers.

For typed input or candidate edit, the claiming command creates the transcript version and sets the current pointer in the same transaction that increments `processing_generation`.

For audio transcription, the claimed worker may create the transcript version and set:

```text
current_transcript_version_id
transcript
```

without incrementing `attempt_version`, provided all of these match:

```text
async_job_id
processing_generation
audio_content_hash
attempt_state = pending_processing
```

This prevents a transcription worker from invalidating its own claim.

### 15.4 Transcript normalization and edit rules

- Normalize to Unicode NFC and LF line endings.
- Compute SHA-256 over UTF-8 canonical text.
- Reject empty text unless deleting.
- Enforce configured code-point limit.
- Preserve earlier versions.
- Do not recalculate original speech metrics from edited text.
- Re-run content evaluation, grounding and follow-up proposal against the new transcript version.
- Store all spans using Section 12.5 offsets.

## 16. Evaluation versioning

## 16.1 New table

Add `interview_attempt_evaluations`:

```text
id VARCHAR(36) primary key
recording_id VARCHAR(36) not null FK session_recordings.id cascade
transcript_version_id VARCHAR(36) nullable FK interview_transcript_versions.id cascade
version_number INTEGER not null
state VARCHAR(32) not null
answer_level VARCHAR(32) nullable
rubric_json JSON nullable
evidence_findings_json JSON nullable
coaching_json JSON nullable
follow_up_proposal_json JSON nullable
diagnostics_json JSON nullable
model_route_json JSON nullable
evaluation_contract_version VARCHAR(64) not null
evidence_contract_version VARCHAR(64) not null
follow_up_contract_version VARCHAR(64) not null
async_job_id VARCHAR(36) nullable
created_at DATETIME not null
completed_at DATETIME nullable
```

Constraints:

```text
UNIQUE(recording_id, version_number)
```

State-dependent transcript rules:

1. Typed `finish_answer` creates the transcript first and stores its ID on the pending evaluation.
2. Audio `finish_answer` creates the pending evaluation with `transcript_version_id = NULL`.
3. Successful transcription creates the immutable transcript and atomically binds that ID to the still-pending evaluation before `content_evaluation` can be claimed.
4. `content_evaluation`, `evidence_grounding`, `follow_up_decision`, and a `completed` evaluation require a non-null transcript ID.
5. A terminal `unavailable` evaluation may retain a null transcript ID only when transcription never produced usable text; its diagnostics must use `transcription_unavailable` or `invalid_audio`, and no content, grounding, or follow-up stage may be marked completed.
6. A worker may bind the transcript only when evaluation ID, attempt processing generation, job ID, claim token, and pending state still match.

Allowed state:

```text
pending
completed
unavailable
invalid
failed
superseded
deleted
```

## 16.2 Current evaluation compatibility field

Keep existing:

```text
SessionRecording.evaluation_json
SessionRecording.evaluation_state
SessionRecording.async_job_id
```

For conversational attempts these fields mirror the current evaluation version to preserve existing job/reconciliation integrations.

Prior evaluation versions remain immutable.

## 16.3 Current-version switch

Finalisation must atomically:

1. Verify job ownership, `processing_generation`, source transcript version and session processing state.
2. Complete the evaluation-version row.
3. Set the prior current evaluation version to `superseded`, if applicable.
4. Set `current_evaluation_version_id`.
5. Mirror current JSON and state to `SessionRecording`.
6. Increment session `state_version` and `activity_version`; do not change `processing_generation`.
7. Move conversation state to `awaiting_next_action`.
8. Append an event.

---

## 17. Attempt processing stages

## 17.1 New table

Add `interview_attempt_stages`:

```text
id VARCHAR(36) primary key
recording_id VARCHAR(36) not null FK session_recordings.id cascade
evaluation_version_id VARCHAR(36) not null FK interview_attempt_evaluations.id cascade
stage_name VARCHAR(64) not null
stage_state VARCHAR(32) not null
attempt_count INTEGER not null default 0
repair_count INTEGER not null default 0
job_id VARCHAR(36) nullable
claim_token VARCHAR(64) nullable
expected_processing_generation INTEGER nullable
source_transcript_version_id VARCHAR(36) nullable
reused_from_stage_id VARCHAR(36) nullable FK interview_attempt_stages.id SET NULL
job_deadline_at DATETIME nullable
started_at DATETIME nullable
completed_at DATETIME nullable
last_error_code VARCHAR(128) nullable
diagnostics_json JSON nullable
```

Unique constraint:

```text
UNIQUE(recording_id, evaluation_version_id, stage_name)
```

`evaluation_version_id` is mandatory for every conversational processing stage. `finish_answer`, `retry_processing` and `edit_transcript` create the pending evaluation-version row before stage rows are inserted. Pre-transcription stages may have `source_transcript_version_id = NULL`, but they never have a null evaluation version. This avoids SQLite's multiple-`NULL` uniqueness behaviour.

## 17.2 Stage vocabulary

```text
audio_persist
transcription
speech_analysis
content_evaluation
evidence_grounding
follow_up_decision
coaching_enrichment
audio_cleanup
```

Typed attempts skip:

```text
audio_persist
transcription
speech_analysis
```

Their stage state is `not_applicable`, not failed.

Allowed stage states:

```text
not_started
pending
running
completed
reused
not_applicable
unavailable
failed_retryable
failed_terminal
```

`completed`, `reused`, `not_applicable`, `unavailable`, and `failed_terminal` are terminal stage states. `reused` is success-equivalent to `completed` only for dependency ordering; reports and diagnostics retain its provenance through `reused_from_stage_id`. A `failed_retryable` stage is terminal for the current generation but may be the restart boundary of a later manual retry.

## 17.3 Why a stage table is required

The baseline has one async-job identity at the attempt level. Phase 1 adds transcript edits, separately retryable transcription, grounding and cleanup. A bounded stage table provides:

- visible processing state;
- targeted retries;
- stage diagnostics;
- exact ownership fencing;
- no need to overload a large unstructured JSON field.

A `reused` row is created only by the fenced `retry_processing` claim transaction. It references one terminal `completed` or `reused` stage from the immediately preceding evaluation generation and is valid only when its immutable input and contract hashes match. Workers never promote a running stage to `reused`.

It must remain a fixed Coach-specific table, not a generic workflow engine.

---

## 18. Database migration contract

## 18.1 Migration file

Create the first additive migration descending from the verified Alembic head on implementation baseline. The uploaded archive head was:

```text
p3q4r5s6t7u8
```

Recommended revision name:

```text
20260723_0001_<revision>_add_conversational_coach_phase1.py
```

If the implementation is split across PRs, use sequential migrations with a single head. Do not create branches in Alembic history.

## 18.2 SQLite-safe migration

Use batch operations where SQLite requires table reconstruction for constraints.

The migration must:

- add nullable columns before backfill;
- backfill legacy experience version;
- backfill attempt numbers deterministically;
- add constraints after valid backfill;
- preserve all legacy data;
- add the canonical status/state and report-state constraints from Sections 8 and 29;
- add `processing_generation`, upload-result, immutable evidence-record and report-build-reason storage;
- be idempotent only through normal Alembic revision control, not ad hoc table detection;
- avoid loading full transcript/audio content into Python when SQL updates suffice.

## 18.3 Backfill rules

### Sessions

```text
experience_version = legacy_v1
conversation_state = NULL
state_version = 0
event_version = 0
```

### Questions

```text
question_kind = planned
follow_up_depth = 0
question_state = skipped if the latest terminal recording by (created_at, id) is skipped
question_state = answered otherwise if any valid legacy completed recording exists
question_state = pending otherwise
```

Do not set `accepted_recording_id` for legacy sessions. Do not rewrite legacy `category` text. Compatibility readers map the six known legacy values case-insensitively through Section 7.3; unknown legacy categories remain `unknown_legacy` and are excluded from conversational category-distribution assertions.

### Recordings

Assign `attempt_number` by question ordered by `created_at`, then `id`.

Do not create transcript or evaluation-version rows for legacy recordings in the migration. Legacy content remains in the legacy columns.

Version rows are required only for conversational attempts.

## 18.4 Indexes

At minimum add:

```text
idx_interview_sessions_experience_state
idx_interview_sessions_conversation_state
idx_session_questions_session_asked_sequence
idx_session_questions_root_question
idx_session_recordings_question_attempt
idx_session_recordings_async_job_state
idx_transcript_versions_recording_version
idx_attempt_evaluations_recording_version
idx_attempt_stages_job_state
idx_attempt_uploads_attempt_upload
idx_session_evidence_records_session_evidence
idx_session_events_session_sequence
idx_command_results_session_command
```

## 18.5 Migration tests

Tests must cover:

- upgrade from a database at current head;
- fresh install;
- legacy sessions with zero, one and multiple attempts;
- legacy skipped and failed recordings;
- duplicate timestamps resolved by ID order;
- implement a tested `downgrade()` because the current Alembic revisions provide downgrade functions;
- foreign-key checks after migration;
- no report-json or numeric-score mutation.

---

## 19. Attempt media upload contract

### 19.1 Endpoint

```http
POST /api/coach/sessions/{session_id}/attempts/{attempt_id}/audio
```

Use multipart form data:

```text
upload_id
content_sha256
audio
```

### 19.2 Upload-result table

Add `interview_attempt_uploads`:

```text
id VARCHAR(36) primary key
attempt_id VARCHAR(36) not null FK session_recordings.id cascade
upload_id VARCHAR(64) not null
request_hash VARCHAR(64) not null
content_sha256 VARCHAR(64) not null
byte_size INTEGER not null
mime_type VARCHAR(128) not null
storage_uri VARCHAR(512) not null
result_state VARCHAR(32) not null
created_at DATETIME not null
completed_at DATETIME nullable
```

Constraints:

```text
UNIQUE(attempt_id, upload_id)
```

Allowed result state:

```text
pending
completed
failed
deleted
```

### 19.3 Preconditions

- conversational session;
- `state = listening`;
- attempt equals `active_recording_id`;
- attempt type is `audio`;
- attempt state is `draft`;
- safe session and attempt ownership;
- MIME type and byte-size limits pass.

### 19.4 Upload idempotency

The server streams the body to a generated temporary file while calculating SHA-256 and byte size. It verifies the result against required `content_sha256`.

Canonical upload request hash is SHA-256 over:

```json
{
  "attempt_id": "<opaque-id>",
  "upload_id": "<opaque-id>",
  "content_sha256": "<opaque-id>",
  "byte_size": 12345,
  "mime_type": "audio/webm"
}
```

using Section 9.5 serialization.

Transaction order:

1. calculate and verify the content hash;
2. look up `(attempt_id, upload_id)`;
3. matching request hash and completed row: delete the new temporary duplicate and return the original result;
4. different request hash: delete temporary data and return HTTP 409 `coach_audio_upload_idempotency_conflict`;
5. no row: atomically move the file into the generated Coach storage path, persist upload result and update the attempt.

The original filename is never used as a path.

### 19.5 Persistence

On successful first upload:

- set `SessionRecording.audio_uri`;
- set `audio_content_hash`;
- verify that the attempt already contains the immutable `audio_retention_policy` captured by `begin_answer`; do not resnapshot the session policy;
- set `audio_retention_state` to `temporary` or `retained`;
- set attempt state `uploaded`;
- do not start transcription until `finish_answer`.

One attempt has at most one current completed upload. A replacement requires `cancel_attempt` and a new attempt, not overwriting the file.

### 19.6 Response

```json
{
  "attempt_id": "<opaque-id>",
  "upload_id": "<opaque-id>",
  "result": "completed",
  "content_sha256": "<opaque-id>",
  "byte_size": 12345,
  "mime_type": "audio/webm",
  "audio_retention_state": "temporary",
  "contract_version": "coach_attempt_audio_upload_v1"
}
```

## 20. Browser recording and automatic turn detection

## 20.1 Capture technology

Use browser `MediaRecorder` for authoritative audio capture.

The existing Web Speech API path may remain as an optional legacy convenience, but conversational voice evaluation must not depend on browser-generated transcript text because:

- browser support differs;
- interim transcripts are not reproducible;
- locale handling is browser-specific;
- current live filler analysis conflicts with realistic mode.

## 20.2 New frontend component boundary

Recommended components:

```text
frontend/src/components/coach/conversation/ConversationSession.tsx
frontend/src/components/coach/conversation/ConversationControls.tsx
frontend/src/components/coach/conversation/ConversationQuestion.tsx
frontend/src/components/coach/conversation/ConversationRecorder.tsx
frontend/src/components/coach/conversation/SilencePrompt.tsx
frontend/src/components/coach/conversation/AnswerReview.tsx
frontend/src/components/coach/conversation/CoachingPanel.tsx
frontend/src/components/coach/conversation/ConversationProgress.tsx
frontend/src/components/coach/conversation/RetentionStatus.tsx
```

Do not continue expanding the current 522-line session page into a larger stateful component. The page should load the session and delegate by experience version.

## 20.3 Silence detection

Silence detection is a browser UX signal, not backend truth.

Use the Web Audio API analyser on the local microphone stream.

Configurable defaults:

```text
speech_start_threshold_db = implementation-calibrated
silence_warning_ms = 4000
silence_finish_prompt_ms = 9000
minimum_speech_before_silence_prompt_ms = 1500
```

Do not hard-code raw amplitude thresholds without calibration because microphone gain varies. Implement:

1. a short baseline-noise calibration after mic permission;
2. a threshold relative to measured noise floor;
3. debouncing to avoid rapid state changes;
4. a maximum local buffer duration;
5. manual Finish Answer at all times.

## 20.4 Silence UX

At warning threshold, show a non-blocking indicator.

At finish-prompt threshold, show:

```text
Are you finished?

Finish answer
Keep speaking
```

The browser must not automatically submit at the first silence threshold.

If the candidate does not respond, the application may continue recording until the configured hard duration limit. It must not guess completion solely from silence.

## 20.5 Manual controls

During `listening`, show:

```text
Finish answer
Keep speaking, only while silence prompt is visible
Pause
Hint
Cancel attempt
```

After processing, show only commands returned by `/live`.

## 20.6 No live score

During recording, do not show:

- filler count;
- WPM score;
- a confidence meter;
- rubric estimates;
- “good” or “bad” live indicators.

Microphone status, elapsed time and capture health are allowed.

## 20.7 Answer duration

Recommended configuration:

```text
warning at 5 minutes
hard local recording limit at 10 minutes
```

At five minutes, show a neutral time notice. Do not reduce the candidate’s evaluation because they reached the warning.

At the hard limit, stop local capture and require the candidate to submit or discard. Persist a technical event; do not classify the answer as poor.

## 20.8 Permission failure

If microphone permission is denied:

- keep typed answer available;
- provide browser-specific guidance;
- do not mark the question failed;
- do not reduce evaluation;
- allow the candidate to change recording mode for the session.

---

## 21. Processing pipeline

## 21.1 End-to-end pipeline

```text
Final audio persisted or typed transcript received
    ↓
Transcript and speech-analysis branches reach terminal state
    ├── immediately claim independent audio cleanup when policy requires deletion
    └── continue content evaluation, grounding and follow-up work
            ↓
        Evaluation version finalised
            ↓
        Conversation state becomes awaiting_next_action
```

## 21.2 Pipeline ownership

Create one persisted generic async job for each submitted or re-evaluated attempt.

The job payload must identify:

```text
session_id
recording_id
evaluation_version_id
transcript_version_id, if already known
expected_session_state_version
expected_processing_generation
processing_contract_version
```

Do not pass ORM objects or live database sessions into the background task.

Every background task opens and closes its own `AsyncSessionLocal` scope, following the existing Coach queue and report pattern.

## 21.3 Stage dependency graph

For audio:

```text
                     ┌→ transcription → content_evaluation → evidence_grounding → follow_up_decision ─┐
audio_persist ───────┤                                                                                ├→ attempt finalisation
                     ├→ speech_analysis ──────────────────────────────────────────────────────────────┘
                     └→ [transcription terminal + speech_analysis terminal] → independent audio_cleanup
```

After `audio_persist` completes, `transcription` and `speech_analysis` are independent sibling stages and may execute concurrently. `speech_analysis` reads the immutable persisted audio, not transcript text. `content_evaluation` waits for a successful transcript. Evaluation finalisation waits until both `content_evaluation` and `speech_analysis` are terminal; when speech analysis is unavailable under the contract, delivery is explicitly `not_assessed` rather than inferred from text.

Default audio cleanup is a separately claimed stage and is **not** downstream of evaluation finalisation. As soon as transcription has committed a transcript and speech analysis is terminal (`completed`, `unavailable` or `not_applicable`), the retention service claims `audio_cleanup`. Evaluation, grounding, follow-up and coaching may continue concurrently. When transcription fails, Section 29.3's 24-hour failure window governs instead of immediate deletion.

For typed input:

```text
candidate_text transcript
    ↓
content_evaluation
    ↓
evidence_grounding
    ↓
follow_up_decision
```

Delivery is `not_assessed`.

## 21.4 Shared processing deadline

Every answer-processing job has one absolute deadline:

```text
job_deadline_at = processing_started_at + HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS
```

Required default:

```text
HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS = 900
```

Configured per-attempt stage ceilings:

```text
HATCH_COACH_TIMEOUT_TRANSCRIPTION_SECONDS = 300
HATCH_COACH_TIMEOUT_SPEECH_ANALYSIS_SECONDS = 120
HATCH_COACH_TIMEOUT_CONVERSATIONAL_EVALUATION_SECONDS = 300
HATCH_COACH_TIMEOUT_EVIDENCE_GROUNDING_SECONDS = 180
HATCH_COACH_TIMEOUT_FOLLOWUP_DECISION_SECONDS = 120
```

Before each stage attempt:

```python
remaining = job_deadline_at - utcnow()
effective_timeout = min(configured_stage_timeout, remaining)
```

Rules:

- do not start a stage or retry when `remaining <= 0`;
- every retry and structured-output repair consumes the same shared remaining budget;
- no nested timeout may extend `job_deadline_at`;
- an exhausted shared budget yields `coach_attempt_job_budget_exhausted`;
- stage timeout configuration is a ceiling for one invocation, not an additive allowance;
- retries are bounded by both retry count and shared remaining time.

Coaching enrichment and audio cleanup run as separate jobs with their own absolute deadlines because neither is required to make the answer evaluation terminal:

```text
HATCH_COACH_TIMEOUT_COACHING_JOB_SECONDS = 240
HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS = 180
```

### 21.5 Retry and repair budgets

| Stage | Maximum additional retries | Maximum schema repairs |
|---|---:|---:|
| transcription | 2 | 0 |
| speech analysis | 1 | 0 |
| content evaluation | 2 | 1 |
| evidence grounding | 2 | 1 |
| follow-up decision | 1 | 1 |

An initial attempt plus two additional retries means at most three invocations. A schema repair occurs inside the current stage invocation and still consumes the shared deadline.

### 21.6 Model route and fallback

Use existing provider orchestration and capability mapping:

```text
structured_answer_evaluation
structured_evidence_grounding
structured_follow_up_proposal
coach_feedback_enrichment
speech_transcription
```

If evaluation remains invalid or unavailable after budget:

- preserve transcript and delivery metrics;
- set evaluation `unavailable`;
- do not invent a level;
- permit retry or explicit acceptance;
- do not create an adaptive follow-up.

Grounding failure leaves evidence consistency `not_assessed`. Follow-up failure never blocks advance.

### 21.7 Processing-generation claim

When a job is claimed, persist:

```text
async_job_id
processing_generation
job_deadline_at
source_audio_content_hash, for audio
source_transcript_version_id, for typed/edit flows
expected_session_state_version
```

Worker-created transcript and stage rows within that claim do not advance `processing_generation`.

A candidate edit, deletion, retry or replacement job increments `processing_generation`; this makes older workers stale.

### 21.8 Pipeline finalisation fence

Final attempt finalisation requires all of:

```text
SessionRecording.id = recording_id
SessionRecording.async_job_id = job_id
SessionRecording.evaluation_state = pending
SessionRecording.processing_generation = expected_processing_generation
SessionRecording.attempt_state = pending_processing
InterviewSession.id = session_id
InterviewSession.conversation_state = processing_answer
InterviewSession.active_recording_id = recording_id
InterviewAttemptEvaluation.id = evaluation_version_id
InterviewAttemptEvaluation.state = pending
For `completed` evaluation finalisation:
InterviewAttemptEvaluation.transcript_version_id = expected_transcript_version_id
expected_transcript_version_id IS NOT NULL

For terminal `unavailable` caused before usable transcription:
InterviewAttemptEvaluation.transcript_version_id IS NULL
diagnostics reason is transcription_unavailable or invalid_audio
content, grounding and follow-up stages are not completed
```

For audio `completed` finalisation, also require:

```text
SessionRecording.audio_content_hash = expected_audio_content_hash
current transcript version was created by the same processing generation
current transcript version ID equals expected_transcript_version_id
```

For terminal audio `unavailable` before usable transcription, require instead:

```text
SessionRecording.audio_content_hash = expected_audio_content_hash, when a hash was persisted
SessionRecording.current_transcript_version_id IS NULL
no transcript version for this recording was created by expected_processing_generation
transcription stage is unavailable or failed_terminal with reason transcription_unavailable or invalid_audio
speech analysis may be unavailable; content evaluation, grounding, follow-up and coaching are not completed or reused
```

The completed-audio transcript predicates do not apply to this pre-transcription unavailable branch.

Session `state_version` may have advanced only through internal events belonging to this same processing generation. Repository finalisation should therefore use the processing-generation and active-recording predicates above, then atomically increment the current session version. It must not compare against the pre-transcription attempt version.

If any predicate fails:

```text
result = stale_claim
no authoritative attempt, evaluation or session mutation
```

### 21.9 Stage finalisation fence

Each stage update requires:

```text
stage.job_id matches
stage.claim_token matches
stage.expected_processing_generation matches attempt.processing_generation
stage.source_transcript_version_id matches, when applicable
stage_state in pending or running
utcnow() <= job_deadline_at, except recording a terminal budget-exhausted outcome
```

A stale stage may record only content-free diagnostics against the generic async job.

## 21.10 Reconciliation

Extend `coach_reconciliation.py` to reconcile:

- stale setup-planning claims;
- stale hard-deletion claims;
- stale `processing_answer` sessions;
- stale attempt jobs;
- stale stage claims;
- stale `asking_follow_up` transitions;
- stale `advancing` transitions;
- stale `reporting` state;
- pending audio cleanup.

Reconciliation rules must be idempotent.

### Stale setup claim

A setup claim is stale when `status = setup`, `conversation_state = planning`, `setup_job_id` and `setup_claim_token` are non-null, and `setup_claim_expires_at < utcnow()`. Reconciliation performs one conditional update requiring the same session ID, setup generation, job ID, claim token, planning state, and `deletion_state = not_requested`.

The update:

- marks the generic setup job timed out or reconciled-failed;
- clears `setup_job_id`, `setup_claim_token`, `setup_claimed_at`, and `setup_claim_expires_at`;
- sets `recoverable_error_scope = setup` and `recoverable_error_code = coach_setup_claim_expired`;
- increments `state_version`;
- appends `session_plan_claim_expired`;
- transitions to setup-status `recoverable_error` when `setup_attempt_count < setup_max_attempts`, otherwise to coarse and conversational `failed`.

A stale setup worker cannot finalise after reconciliation. `retry_setup` is available only after the fields above are cleared and always claims a new `setup_generation`, job ID, token, and lease. Reconciliation never automatically spends a retry attempt.

### Stale hard-deletion claim

A deletion claim is stale when `deletion_state = deleting`, the claim fields are non-null, and `deletion_claim_expires_at < utcnow()`. Reconciliation conditionally requires the same `deletion_generation`, `deletion_job_id`, `deletion_command_id`, and claim token. It then:

- leaves the session hidden from all normal reads;
- sets `deletion_state = failed`, `deletion_failed_at = utcnow()`, and error `coach_deletion_claim_expired`;
- clears job, command, token, and lease fields;
- updates the matching independent deletion result from `processing` to `failed`;
- increments session `state_version` and `event_version`;
- appends `hard_deletion_claim_expired` while the session event table still exists.

Retry requires a new client `command_id`. The new claim is permitted from `deletion_state = failed`, increments `deletion_generation`, and repeats media/database deletion idempotently. Missing child rows and already-removed owned media are success conditions when ownership metadata proves they belonged to the same session. A stale deletion worker performs no final mutation.

### Stale processing answer

If job is terminal done and evaluation is completed:

- finalise live state if the worker committed evaluation but failed before state transition.

If job failed or exceeded timeout:

- mark stage/job failure;
- set attempt `recoverable_error` or `unavailable` based on retryability;
- set session `recoverable_error`;
- preserve transcript and media according to retention.

If job remains legitimately running within deadline:

- no mutation.

### Stale transient state

For `advancing` or `asking_follow_up`:

- inspect persisted accepted attempt and questions;
- deterministically complete the transition;
- never create duplicate follow-ups.

## 21.11 Activity version interaction

Existing `activity_version` continues to fence report snapshots.

Increment it when conversational report inputs change:

- attempt submitted;
- transcript edited;
- evaluation completed;
- attempt accepted or unaccepted;
- question skipped;
- transcript deleted;
- accepted attempt deleted.

Do not increment it for read-only coaching display or audio deletion when transcript/evaluation remain unchanged.

---

## 22. Speech and delivery analysis

## 22.1 Permitted observable metrics

For audio attempts, the speech analyser may produce:

```text
duration_ms
word_count
words_per_minute
filler_count
filler_rate_per_minute
hedging_count
pause_count
long_pause_count
restart_count
```

`restart_count` may be derived from transcript markers only when the method is deterministic and documented. Otherwise omit it from v1.

## 22.2 Prohibited metrics

Do not produce or persist for conversational sessions:

```text
arousal
valence
dominance
vocal_confidence
emotion
stress
honesty
deception
personality
presence
eye_contact
facial_expression
head_stability
gesture_frequency
```

Existing legacy `VoiceToneResult`, `VideoMetrics` and legacy rubric snapshots remain readable but are not invoked for `conversational_v1`.

## 22.3 Deterministic delivery assessment

Contract:

```text
coach_delivery_policy_v1
```

Delivery is `not_assessed` when any condition holds:

- typed input;
- fewer than 40 transcript words;
- audio duration under 20 seconds;
- required timestamps unavailable;
- speech analysis failed.

For eligible audio, classify each metric family into exactly one bucket: `none`, `moderate`, `material` or `severe`. A value that matches no threshold in the table is `none`. Boundaries are strict as written and the listed ranges are mutually exclusive.

| Metric family | Moderate | Material | Severe |
|---|---|---|---|
| pace | `90 <= WPM < 100` or `170 < WPM <= 190` | `70 <= WPM < 90` or `190 < WPM <= 220` | `WPM < 70` or `WPM > 220` |
| fillers/min | `> 3` and `<= 6` | `> 6` and `<= 9` | `> 9` |
| long pauses | `> max(2, duration_minutes)` and `<= max(3, 2 * duration_minutes)` | `> max(3, 2 * duration_minutes)` and `<= max(6, 4 * duration_minutes)` | `> max(6, 4 * duration_minutes)` |
| hedging count | `> max(2, word_count / 60)` and `<= max(4, word_count / 40)` | `> max(4, word_count / 40)` and `<= max(8, word_count / 20)` | `> max(8, word_count / 20)` |
| restart count, only if deterministic method enabled | `3-4` | `5-7` | `>= 8` |

Use full floating-point thresholds before comparison; do not round duration-derived or word-count-derived thresholds.

Count one severity per family:

```text
moderate_count
material_count
severe_count
```

Derive level in this exact order:

1. `needs_work` if `severe_count >= 1` or `material_count >= 3`.
2. `developing` if `material_count = 2`, or `material_count = 1 and moderate_count >= 2`.
3. `interview_ready` if `material_count = 1`, or `material_count = 0 and moderate_count >= 2`.
4. `strong` if `material_count = 0`, `severe_count = 0` and `moderate_count <= 1`.
5. `not_assessed` only through the eligibility gate.

There is no undefined concept of “severe repeated issue.” The response lists each metric family, measured value, threshold bucket and resulting severity.

Required boundary tests include every equality edge: 70, 90, 100, 170, 190, 220 WPM; 3, 6, 9 fillers/min; and exact duration/word-count threshold values.

## 22.4 Candidate self-assessment

The mutation contract is `record_self_assessment` in Section 9.9.

Self-assessment is displayed separately and:

- does not set delivery level;
- does not prove confidence;
- does not affect evidence grounding;
- may appear in the report as candidate-authored reflection;
- remains candidate-editable and attributable.

## 23. Conversational rubric contract

## 23.1 Contract version

```text
coach_conversational_rubric_v1
```

## 23.2 Dimensions

```text
relevance
structure
specificity
impact
role_depth
clarity
conciseness
delivery
evidence_consistency
```

## 23.3 Level vocabulary

```text
needs_work
developing
interview_ready
strong
not_assessed
```

Internal ordinal values may be used for deterministic sorting only:

```text
needs_work = 1
developing = 2
interview_ready = 3
strong = 4
not_assessed = null
```

These values must not be returned to normal frontend views.

## 23.4 Dimension schema

```json
{
  "level": "interview_ready",
  "evidence": [
    {
      "transcript_start": 120,
      "transcript_end": 181,
      "excerpt": "<opaque-id>"
    }
  ],
  "rationale": "The answer clearly described the candidate's action.",
  "improvement": "Add the measurable business result."
}
```

Rules:

- every assessed content judgement requires at least one transcript evidence span;
- evidence spans must match current transcript text after normalization;
- maximum two excerpts per dimension;
- excerpts must be bounded;
- no evidence span -> `not_assessed` or invalid output, not an unsupported judgement.

## 23.5 Dimension ownership

LLM-proposed and application-validated:

```text
relevance
structure
specificity
impact
role_depth
clarity
conciseness
```

Deterministic speech policy:

```text
delivery
```

Evidence-grounding service:

```text
evidence_consistency
```

The LLM evaluator must not assign delivery or evidence-consistency levels.

## 23.6 Content-level anchors

### Relevance

- `strong`: directly answers the question throughout and connects to target competency.
- `interview_ready`: answers the question with only minor irrelevant material.
- `developing`: partially answers the question or requires inference.
- `needs_work`: does not answer the question or is mostly unrelated.

### Structure

- `strong`: clear opening, logically sequenced actions and explicit result/reflection where applicable.
- `interview_ready`: understandable sequence with a minor missing transition.
- `developing`: useful content but unclear ordering or missing a major section.
- `needs_work`: fragmented or cannot be followed reliably.

### Specificity

- `strong`: names concrete actions, constraints, stakeholders and outcomes.
- `interview_ready`: includes a concrete example and personal actions.
- `developing`: example is present but generic or collective ownership dominates.
- `needs_work`: abstract answer without a usable example when one is required.

### Impact

- `strong`: explains measurable or clearly attributable outcome and significance.
- `interview_ready`: explains a concrete outcome and why it mattered.
- `developing`: result is vague or limited to task completion.
- `needs_work`: no result or impact is described.

### Role depth

- `strong`: demonstrates role-appropriate trade-offs, ownership and judgement beyond surface description.
- `interview_ready`: demonstrates sufficient role-level reasoning and ownership.
- `developing`: shows participation but limited depth or decision reasoning.
- `needs_work`: lacks evidence of the expected role depth.

### Clarity

- `strong`: precise language, clear ownership and no material ambiguity.
- `interview_ready`: understandable with minor ambiguity.
- `developing`: several unclear references or overloaded statements.
- `needs_work`: meaning cannot be followed reliably.

### Conciseness

- `strong`: complete answer with no material repetition.
- `interview_ready`: mostly focused, with limited repetition.
- `developing`: noticeably repetitive or overlong but still usable.
- `needs_work`: repetition or digression obscures the answer.

## 23.7 `not_assessed`

Use `not_assessed` when:

- the answer does not contain enough information for that dimension;
- a required processing stage is unavailable;
- the dimension does not apply to the question type;
- typed input makes delivery unavailable;
- evidence grounding is unavailable.

Do not substitute a middle level.

## 23.8 Answer-level derivation

The application derives `answer_level` from the seven content dimensions only.

Critical dimensions:

```text
relevance
structure
specificity
```

Rules:

### `strong`

- all seven content dimensions are assessed;
- at least five content dimensions are `strong`;
- the remaining assessed dimensions are at least `interview_ready`;
- all critical dimensions are assessed.

### `interview_ready`

- at least five assessed content dimensions are `interview_ready` or `strong`;
- no critical dimension is `needs_work`;
- no more than one non-critical dimension is `needs_work`;
- at least six content dimensions are assessed.

### `developing`

- at least five assessed content dimensions are `developing` or better;
- no more than two content dimensions are `needs_work`;
- at least five content dimensions are assessed.

### `needs_work`

- criteria above are not met and at least four content dimensions are assessed.

### `not_assessed`

- fewer than four content dimensions are assessed.

Apply the levels in the order shown; the first matching rule wins.

Required boundary vectors in dimension order `relevance, structure, specificity, impact, role_depth, clarity, conciseness`:

```text
[strong, strong, strong, strong, strong, interview_ready, interview_ready] -> strong
[strong, strong, strong, strong, strong, not_assessed, not_assessed] -> developing
[strong, strong, strong, strong, interview_ready, interview_ready, not_assessed] -> interview_ready
[interview_ready, interview_ready, interview_ready, interview_ready, interview_ready, interview_ready, not_assessed] -> interview_ready
[developing, developing, developing, developing, developing, not_assessed, not_assessed] -> developing
[strong, strong, strong, not_assessed, not_assessed, not_assessed, not_assessed] -> not_assessed
```

Delivery and evidence consistency remain separate and do not silently cap answer quality.

## 23.9 Evidence conflict display

A conflicting evidence finding is displayed prominently next to answer level, but it does not mathematically reduce the answer level.

This keeps two different questions separate:

```text
Was the answer well communicated?
Is the factual claim supported by approved evidence?
```

## 23.10 Evaluator structured output

The LLM returns only the content dimensions and supporting spans.

The application:

- validates allowed dimensions;
- validates level vocabulary;
- validates evidence spans;
- checks no invented transcript text;
- derives answer level;
- merges delivery and evidence results;
- rejects prohibited inference language.

## 23.11 Repair

One structured-output repair attempt is allowed by default.

The repair prompt receives:

- validation error codes;
- original structured output;
- current transcript;
- rubric contract.

It does not receive hidden chain-of-thought or provider internals.

---

## 24. Evidence grounding contract

## 24.1 Contract version

```text
coach_evidence_grounding_v1
```

## 24.2 Objective

Evidence grounding checks material factual claims in the answer against the session-scoped eligible evidence package defined in Sections 12.3, 12.4 and 24.5.

It is not a fact-check of the world and not a truth detector.

## 24.3 Claim schema

```json
{
  "claim_id": "claim_1",
  "claim_text": "I led the migration across three regional teams.",
  "transcript_start": 102,
  "transcript_end": 158,
  "claim_type": "experience_scope",
  "materiality": "material",
  "centrality": "central",
  "deduplication_key": "sha256:<64-lowercase-hex>"
}
```


Materiality and centrality are deterministic persisted fields:

- `materiality = material` when the claim could change relevance, specificity, impact, role depth or evidence-consistency judgement; otherwise `non_material`.
- `centrality = central` when the claim asserts the candidate's principal responsibility/action, the principal outcome/metric, or a scope/duration fact required to answer the question. All other material claims are `supporting`.
- The extraction contract may propose these values, but application validation rejects an unsupported enum or a `central` label whose transcript span is not connected to one of the question target, action/ownership, result/impact or required scope slots.
- Deduplicate claims using normalized `claim_type`, normalized subject/predicate/value and overlapping transcript span. `multiple` always means **two or more distinct deduplicated material claims**.

Allowed `centrality`:

```text
central
supporting
```

Allowed claim types:

```text
role
responsibility
action
technology
scope
metric
outcome
duration
date
team_size
experience_scope
```

Non-factual opinion or hypothetical content is `not_verifiable`.

## 24.4 Grounding status rules

### `supported`

The complete material claim is directly supported by at least one eligible source with approval state `approved`, `confirmed`, `reviewed_final`, `reviewed`, or `candidate_selected_unapproved`, without an authoritative contradiction. Evidence labelled `candidate_selected_unapproved` must remain visibly unapproved in every explanation. A `draft` source cannot independently produce `supported`.

### `partially_supported`

The core experience is supported, but a material detail such as metric, scope, ownership, date or technology is absent or only partially matched. A consented `draft` source may contribute only to `partially_supported`; it cannot independently produce `supported` or `conflicting`.

### `not_found`

No eligible candidate-evidence record supports the claim. `context_only` job/company records are ignored for candidate-experience grounding. A contradiction found only in `reviewed`, `candidate_selected_unapproved`, or `draft` evidence is not authoritative and therefore does not produce `conflicting`; when no eligible support remains, the result is `not_found` with a candidate review action.

This means only:

> Hatch could not find this claim in the selected evidence sources.

It must not be presented as false.

### `conflicting`

At least one selected source with approval state `approved`, `confirmed`, or `reviewed_final` contains an objective contradiction. `reviewed`, `candidate_selected_unapproved`, `draft`, and `context_only` records cannot independently establish `conflicting`. When an authoritative supporting source and authoritative contradictory source both exist, `conflicting` takes precedence over `supported` or `partially_supported` for that claim.

Examples:

- answer says three regions; approved evidence says one region;
- answer says project completed in four weeks; approved evidence says four months;
- answer claims lead ownership; approved source explicitly identifies a supporting role.

Use sparingly. Ambiguity is not conflict.

### `not_verifiable`

The claim is subjective, hypothetical, future-oriented, too vague or outside selected evidence.

## 24.5 Evidence source trust

For Phase 1, use this deterministic approval capability table:

| Approval state | Evidence capability for candidate claims | May establish `conflicting`? |
|---|---|---:|
| `approved` | support, partial support, or contradiction | yes |
| `confirmed` | support, partial support, or contradiction | yes |
| `reviewed_final` | support, partial support, or contradiction | yes |
| `reviewed` | support or partial support | no |
| `candidate_selected_unapproved` | support or partial support; always label unapproved | no |
| `draft` with explicit consent | partial support only; always label draft | no |
| `context_only` | role/company context only; never candidate-claim evidence | no |

Within the same capability tier, use deterministic source priority:

```text
approved application CV asset
confirmed Master CV
Question Bank final
Question Bank reviewed
candidate-selected current application CV (`candidate_selected_unapproved`)
candidate-enabled Question Bank draft
application/job requirements, for role expectations only
```

`draft` records are excluded entirely unless `draft_evidence_consent = true`. Candidate-selected current application CV evidence and draft evidence can never outweigh an authoritative contradiction. When they disagree with an authoritative source, the authoritative source governs the claim status and the lower-trust discrepancy is included only as a review note.

Job descriptions support role requirements, not candidate experience claims.

Company research supports company context, not candidate experience claims.

## 24.6 Grounding output

```json
{
  "state": "completed",
  "claims": [
    {
      "claim_id": "claim_1",
      "status": "partially_supported",
      "evidence_ids": ["ev_<opaque-id>"],
      "explanation": "The migration is supported, but the source does not confirm three regional teams.",
      "candidate_action": "Review the team-scope detail before reusing this answer."
    }
  ],
  "summary": {
    "supported": 2,
    "partially_supported": 1,
    "not_found": 0,
    "conflicting": 0,
    "not_verifiable": 1
  }
}
```

## 24.7 Evidence consistency level

Count only distinct deduplicated claims with `materiality = material`. Let:

```text
S = supported material claim count
P = partially_supported material claim count
N = not_found material claim count
C = conflicting material claim count
NC = not_found material claims with centrality = central
M = S + P + N + C
```

Apply this ordered first-match algorithm:

1. `not_assessed` when grounding is unavailable, the candidate selected no evidence package, or `M = 0`.
2. `needs_work` when `C >= 1`, or `NC >= 1`, or `N >= 2`.
3. `strong` when `S = M`.
4. `interview_ready` when `C = 0`, `N = 0` and `P <= 1`.
5. `developing` for every remaining assessed case. This therefore covers `P >= 2`, or exactly one supporting `not_found` claim with no conflict.

`not_verifiable` claims are shown separately and do not enter `M`. The UI must explain exact claim statuses rather than presenting only the derived level.

Required boundary tests:

```text
S=1,P=0,N=0,C=0 -> strong
S=2,P=1,N=0,C=0 -> interview_ready
S=1,P=2,N=0,C=0 -> developing
S=2,P=0,N=1,C=0,NC=0 -> developing
S=2,P=0,N=1,C=0,NC=1 -> needs_work
S=1,P=0,N=2,C=0 -> needs_work
S=3,P=0,N=0,C=1 -> needs_work
M=0 -> not_assessed
```

## 24.8 Grounding safeguards

The grounding model must not:

- invent evidence IDs;
- use model knowledge as candidate evidence;
- infer that absent evidence is false;
- update source records;
- write to Master CV or Question Bank;
- treat generated model answers as candidate evidence;
- infer honesty or deception.

## 24.9 Source version changes

The session plan is reproducible against its selected source hashes.

If a source changes while a session is active:

- continue using the session snapshot/reference version;
- display that newer source content exists only if relevant;
- do not silently re-ground accepted attempts;
- an explicit future re-evaluation may use a new evidence package and must create a new evaluation version.

---

## 25. Adaptive follow-up contract

## 25.1 Contract version

```text
coach_follow_up_v1
```

## 25.2 Allowed reasons

```text
clarify_example
measurable_result
personal_action
reasoning
role_depth
resolve_ambiguity
evidence_consistency
```

## 25.3 Prohibited reasons

A follow-up must not be generated solely because of:

- low overall level;
- filler words;
- slow or fast speech;
- candidate self-assessment;
- a model preference for more detail;
- hidden personality or confidence inference;
- a historical weakness outside the current answer.

## 25.4 Proposal schema

```json
{
  "should_ask": true,
  "reason": "measurable_result",
  "question": "What measurable outcome resulted from your intervention?",
  "transcript_evidence": {
    "start": 210,
    "end": 268,
    "excerpt": "We completed the migration and the stakeholders were satisfied."
  },
  "target_dimension": "impact",
  "aggregation_role": "gap_repair",
  "duplicate_key": "root-question:impact:result"
}
```

## 25.5 Deterministic reason and aggregation mapping

The application, not the model, owns the target dimension and aggregation role. Use this exact mapping:

| Follow-up reason | Required target dimension | Aggregation role |
|---|---|---|
| `clarify_example` | `specificity` | `gap_repair` |
| `measurable_result` | `impact` | `gap_repair` |
| `personal_action` | `specificity` | `gap_repair` |
| `reasoning` | `role_depth` | `primary_evidence` |
| `role_depth` | `role_depth` | `primary_evidence` |
| `resolve_ambiguity` | `clarity` | `gap_repair` |
| `evidence_consistency` | `evidence_consistency` | `primary_evidence` |

The proposal must contain the mapped values. A mismatch is invalid model output and may be repaired within the existing stage budget; the application must not accept a model-selected alternative.

`gap_repair` is admissible only when the accepted parent attempt has the target dimension assessed below `interview_ready`. It can improve that dimension by at most one level under Section 27.4 and cannot lower it.

`primary_evidence` is substantive new evidence for the mapped dimension. It may lower the root bundle under Section 27.4. It does not receive independent root-question weight.

## 25.6 Admission policy

The application admits a proposal only when:

1. `should_ask` is true.
2. Reason is allowed and target dimension plus aggregation role exactly match Section 25.5.
3. Transcript evidence matches current transcript.
4. Question is non-empty and bounded.
5. Root question follow-up count is below two.
6. No existing question has the same normalized duplicate key.
7. The proposal does not reveal hidden scoring or profiling.
8. The attempt named by the successful `accept_attempt.attempt_id` command is the current accepted attempt for this question.
9. The root question has not been skipped.
10. The session has not been ended.

## 25.7 Follow-up creation

Create a new `SessionQuestion`:

```text
question_kind = adaptive_follow_up
root_question_id = planned root
parent_question_id = current question
follow_up_depth = parent depth + 1
follow_up_reason = admitted reason
follow_up_target_dimension = mapped dimension
follow_up_aggregation_role = mapped role
question_state = pending
```

Persist with the follow-up:

- `follow_up_source_recording_id` equal to the accepted attempt that caused admission;
- `follow_up_source_transcript_version_id` equal to that attempt's current transcript version;
- `follow_up_context_json` containing only bounded structured reason/dimension/span references;
- `follow_up_generation_json` containing the validated proposal and provider/contract provenance, never a raw prompt;
- `source_deleted = false`.

Assign the next `asked_sequence` only when presented. Section 29.5 physically clears both JSON fields and source pointers and sets `source_deleted = true` when the source transcript is deleted.

## 25.8 Follow-up budget

Count all persisted adaptive follow-up questions under the root, regardless of whether answered or skipped.

This prevents retry or deletion from reopening the budget.

## 25.9 Sequence return

After the second follow-up, or when no valid proposal exists:

- advance to the next planned question;
- do not continue a model-created chain.

## 25.10 Deterministic fallback

If model follow-up generation is unavailable, do not generate a generic fallback based only on low quality.

The application may generate one deterministic follow-up only when a validated rule detects a specific omission in the current transcript, such as:

```text
question explicitly asks for result
answer evaluation marks impact needs_work
no result clause is detected
```

This fallback must still use an allowed reason and transcript grounding. It is optional. Safe default is no follow-up.

---

## 26. Hints, coaching and retry

## 26.1 Hint contract

Hints are short and non-substitutive.

Examples:

```text
STAR structure: briefly cover the situation, your task, your actions and the result.
Competency reminder: focus on the decision you personally made.
Experience category: consider a project involving cross-functional stakeholders.
Clarification: this question is asking for one concrete example.
```

The hint service must use templates first. LLM generation is not required for standard hint types.

## 26.2 Hint tracking

Persist:

```text
hint_count on attempt
pending_hint_count and pending_hint_types_json on question before an attempt exists
hint event with type
```

`begin_answer` transfers and clears question-pending hints in the same transaction that creates the attempt. Report `hints_used` counts persisted `hint_presented` events; per-attempt displays use the transferred `hint_count`.

Do not automatically lower a rubric dimension because a hint was used.

The report may state:

```text
One hint was used on this answer.
```

## 26.3 Coaching response

Coaching schema:

```json
{
  "positive_observation": "You made your personal ownership clear.",
  "priority_improvement": "Add the measurable delivery result.",
  "transcript_evidence": [],
  "suggested_structure": ["Situation", "Action", "Result"],
  "example_revision": "A bounded revision using only candidate-provided facts.",
  "evidence_review_items": [],
  "practice_instruction": "Retry the answer in 90 seconds and include one outcome."
}
```

## 26.4 Example revision safety

An example revision may:

- reorder the candidate’s own statements;
- improve clarity;
- use supported evidence selected for the session;
- insert visible placeholders such as `[add verified metric]`.

It must not:

- invent a metric;
- invent a project;
- change the candidate’s role;
- promote a `not_found` claim to fact;
- silently write to a source record.

## 26.5 Coaching generation

The completed evaluation should contain a deterministic review skeleton derived from validated rubric and grounding results.

When the candidate requests coaching:

1. Return the skeleton immediately if model enrichment is unavailable.
2. Optionally enrich wording using a bounded LLM contract.
3. Validate that enrichment cites only current transcript/evidence.
4. Persist the coaching version under the evaluation version.

## 26.6 Retry contract

Retry creates a new `SessionRecording`.

Prior attempts remain visible in answer history.

A retry:

- does not overwrite the prior transcript;
- does not delete prior audio automatically beyond its own retention policy;
- does not become accepted automatically;
- receives a new attempt number;
- may reference `retry_of_recording_id`;
- starts with a fresh follow-up proposal tied to the new transcript.

## 26.7 Attempt comparison

Within the current question review, the UI may compare named levels between attempts.

It must not label the retry “improved” unless the deterministic level comparison supports it.

Comparison uses only like-for-like dimensions under the same rubric contract.

---

## 27. Conversational report contract

## 27.1 Contract version

```text
coach_conversational_report_v1
```

## 27.2 Separate report builder

Create a new report builder. Do not mutate `build_deterministic_report()` for legacy sessions.

Dispatcher:

```text
legacy_v1 -> existing deterministic numeric report
conversational_v1 -> conversational accepted-attempt report
```

## 27.3 Authoritative report inputs

Use:

- persisted session plan;
- planned questions;
- adaptive follow-ups;
- explicit accepted recordings;
- current completed evaluation versions;
- skipped/unavailable states;
- hint and retry counts;
- candidate self-assessment.

Unaccepted attempts remain available in session history but do not determine final rubric levels.

## 27.4 Root-bundle aggregation

A planned root question and its accepted follow-ups form one bundle. Only explicit accepted attempts participate.

Map levels:

```text
needs_work = 1
developing = 2
interview_ready = 3
strong = 4
```

For each dimension, use this ordered algorithm:

1. Let `root_level` be the accepted root-attempt level.
2. Collect assessed follow-ups whose persisted `follow_up_target_dimension` equals this dimension.
3. `upward_candidate` starts as `root_level`.
4. If at least one collected follow-up has `follow_up_aggregation_role = gap_repair` and a level above `root_level`, set `upward_candidate = min(root_level + 1, strong)`. Multiple gap-repair follow-ups cannot stack more than one upward level.
5. Collect follow-ups whose persisted `follow_up_aggregation_role = primary_evidence`.
6. If any exist, let `downward_floor` be the minimum of their assessed levels.
7. Final bundle level is `min(upward_candidate, downward_floor)` when a downward floor exists; otherwise it is `upward_candidate`.
8. Therefore adverse primary evidence takes precedence over an upward gap repair.
9. If `root_level = not_assessed`, the bundle remains `not_assessed` unless at least one `primary_evidence` follow-up is assessed; in that case use the minimum assessed primary-follow-up level and record that root evidence was unavailable.
10. Persist the exact contributing attempt IDs and adjustment reason.

Follow-ups never receive equal independent session weight. If the root is skipped, follow-ups cannot exist.

## 27.5 Session dimension aggregation

For each dimension:

1. Convert assessed named levels to internal ordinal values.
2. Use the lower median across root bundles.
3. Convert back to a named level.
4. Require at least two assessed root bundles; otherwise `not_assessed`.
5. Store counts per level for explainability.

Use lower median:

- odd count -> middle;
- even count -> lower of two middle values.

This intentionally avoids optimistic averaging and false precision.

## 27.6 Session overall readiness

Use the seven content session dimensions:

```text
relevance
structure
specificity
impact
role_depth
clarity
conciseness
```

Critical session dimensions:

```text
relevance
structure
specificity
role_depth
```

Apply this ordered algorithm:

1. `not_assessed` when fewer than five of seven content dimensions are assessed.
2. `strong` when all seven are assessed, at least five are `strong`, every assessed dimension is at least `interview_ready`, and all critical dimensions are assessed.
3. `interview_ready` when at least six are assessed, at least five are `interview_ready` or `strong`, all critical dimensions are assessed, no critical dimension is `needs_work`, and no more than one non-critical dimension is `needs_work`.
4. `developing` when at least five are assessed, at least five are `developing` or better, no more than one critical dimension is `needs_work`, and no more than two total dimensions are `needs_work`.
5. `needs_work` for every other case with at least five assessed dimensions.

The first matching rule wins. Delivery and evidence consistency remain separate and cannot silently alter this result.

Required tests cover each threshold and precedence case, including these exact vectors in dimension order `relevance, structure, specificity, impact, role_depth, clarity, conciseness`:

- `[developing, developing, developing, developing, developing, not_assessed, not_assessed]` -> `developing`;
- `[needs_work, interview_ready, interview_ready, interview_ready, interview_ready, developing, not_assessed]` -> `developing` because a critical dimension blocks `interview_ready`;
- `[strong, strong, strong, strong, strong, interview_ready, developing]` -> `interview_ready` because one `developing` dimension blocks `strong`;
- `[strong, strong, strong, strong, strong, interview_ready, needs_work]` -> `interview_ready` when the `needs_work` dimension is non-critical;
- `[strong, strong, needs_work, strong, strong, interview_ready, interview_ready]` -> `developing` because the `needs_work` dimension is critical;
- `[strong, strong, strong, strong, not_assessed, not_assessed, not_assessed]` -> `not_assessed`.

## 27.7 Report schema

```json
{
  "session_id": "<opaque-id>",
  "report_state": "completed",
  "activity_version": 8,
  "retention_version": 4,
  "session_level": "interview_ready",
  "dimensions": {},
  "strengths": [],
  "improvement_priorities": [],
  "evidence_review_items": [],
  "question_summaries": [],
  "practice_suggestions": [],
  "candidate_reflection": {},
  "retention_summary": {},
  "compatibility_key": "<opaque-id>",
  "diagnostics": {},
  "contract_version": "coach_conversational_report_v1"
}
```

`retention_summary` is a **live response overlay**, not an immutable analytical field inside persisted `report_json`. Report reads and exports calculate it from current attempt retention rows under the captured `retention_version`. Audio-only deletion or future-attempt policy changes therefore do not invalidate or rebuild analytical report content.

## 27.8 Counts

Report counts must include:

```text
planned_questions_total
planned_questions_answered
planned_questions_skipped
follow_ups_asked
follow_ups_answered
accepted_attempts
retry_attempts
unavailable_attempts
hints_used
```

Counts are deterministic and cannot be changed by narrative enrichment.

## 27.9 Strength and priority selection

Strengths:

- select up to three dimensions at `strong` or `interview_ready`;
- order by level, assessed bundle count, then fixed dimension priority.

Improvement priorities:

- select one or two weakest assessed dimensions;
- do not select `not_assessed` as a weakness;
- include evidence-backed next action;
- separately list unassessed areas.

## 27.10 Report narrative

The LLM may enrich wording only after deterministic report data is built.

It may not change:

- levels;
- counts;
- evidence statuses;
- selected priorities;
- question inclusion;
- retry or hint counts.

If enrichment fails, publish deterministic fallback with:

```text
report_state = fallback
conversation_state = completed
```

## 27.11 Report snapshot and claim fencing

Reuse:

```text
report_job_id
report_started_at
report_state
activity_version
report_json
```

Add:

```text
report_build_reason VARCHAR(32) NULL
```

Allowed build reasons:

```text
initial_completion
transcript_deletion_rebuild
reflection_update_rebuild
manual_retry
```

Initial completion finalisation requires:

```text
matching report_job_id
report_state = building
report_build_reason in initial_completion or manual_retry
claimed activity_version matches
conversation_state = reporting
```

Completed-session rebuild finalisation requires:

```text
matching report_job_id
report_state = building
report_build_reason in transcript_deletion_rebuild or reflection_update_rebuild
claimed activity_version matches
status = completed
conversation_state = completed
```

Both paths write the snapshot and clear `report_job_id` atomically. A late worker cannot overwrite a newer activity version or report claim.

## 27.12 Report retrieval

`GET /sessions/{id}/report` remains a read.

It dispatches response schema by report contract. Every conversational report response includes top-level `activity_version` and `retention_version` captured from the same transactionally consistent read used to build the live `retention_summary`. The same values are also returned in headers `X-Hatch-Session-Activity-Version` and `X-Hatch-Retention-Version`. Clients may obtain `expected_retention_version` for export from either `/live` or this report response.

It may reconcile stale report state but must not initiate a new report during a normal read. Failed initial or completed-session rebuilds are retried only through the explicit `retry_report` command in Section 9.9.

---

## 28. Longitudinal progress

## 28.1 Compatibility

Conversational progress is computed only inside an exact persisted `compatibility_key`. Legacy sessions are excluded from conversational progress unless shown in a separate legacy-history view. No endpoint selector may merge different compatibility keys.

## 28.2 Endpoint and selector modes

Add:

```http
GET /api/coach/conversational-progress
```

Supported query fields:

```text
compatibility_key optional exact selector
application_id optional broad filter
role_family optional broad filter
role_level optional broad filter
interview_type optional broad filter
```

Exactly one selector mode applies:

1. **Exact mode:** `compatibility_key` is present and every broad filter is absent. Return at most one group for that exact key. Combining it with any broad filter returns HTTP 400 `coach_progress_selector_conflict`.
2. **Filtered mode:** `compatibility_key` is absent and at least one broad filter is present. Combine supplied filters with logical AND, collect matching sessions, then partition them by their persisted exact compatibility key. `application_id` is a filter, not a key selector; sessions for one application may therefore produce multiple groups.

Within each group, order sessions by `completed_at ASC, id ASC`. Order groups by the most recent completed session descending, then compatibility key ascending. Apply `HATCH_COACH_PROGRESS_MAX_GROUPS` after grouping; never merge overflow groups. Exact mode has a natural maximum of one group and is not truncated. Filtered mode computes `total_groups` before truncation and returns the first configured number in deterministic order. Phase 1 does not paginate progress groups.

## 28.3 Progress response

```json
{
  "selector_mode": "filtered",
  "applied_filters": {
    "application_id": "application_<opaque-id>"
  },
  "group_limit": 20,
  "total_groups": 23,
  "returned_groups": 20,
  "groups_truncated": true,
  "groups": [
    {
      "compatibility_key": "coach-progress-v1:<bounded-key>",
      "context": {},
      "sessions": [],
      "current_levels": {},
      "previous_levels": {},
      "trends": {},
      "strongest_areas": [],
      "priority_areas": [],
      "evidence_review_items": []
    }
  ],
  "contract_version": "coach_conversational_progress_v2"
}
```

`group_limit` is the effective validated configuration value. `total_groups` is the number after filters and exact-key partitioning but before truncation. `returned_groups` equals `len(groups)`. `groups_truncated` is true exactly when `total_groups > returned_groups`.

Every current level, previous level, trend, strongest area, and priority area is derived independently per group. A response with multiple groups is a grouped comparison view, not one combined progression series.

## 28.4 Trend vocabulary

```text
improving
stable
mixed
declining
not_enough_evidence
```

No percentage improvement is displayed.

## 28.5 Trend rules

Use ordinal values `needs_work=1`, `developing=2`, `interview_ready=3`, `strong=4`. Require at least two completed compatible sessions with an assessed level for the dimension.

Use the most recent three assessed compatible sessions when three or more exist; otherwise use the most recent two. The three-session lookback is mandatory when available.

Let `current`, `previous` and optional `older` be the ordinal levels.

Apply this ordered algorithm:

1. Fewer than two assessed compatible sessions -> `not_enough_evidence`.
2. When `older` exists, calculate `older_delta = previous - older` and `recent_delta = current - previous`. If both deltas are non-zero and have opposite signs, return `mixed`.
3. `current > previous` -> `improving` regardless of whether the jump is one, two or three levels.
4. `current < previous` -> `declining` regardless of jump magnitude.
5. `current = previous` -> `stable`.

A flat interval followed by a change uses the most recent change, not `mixed`. A change followed by a flat interval is `stable`, while the UI may show the older context. Missing or `not_assessed` sessions are skipped rather than treated as ordinal zero.

Required vectors:

```text
1,2 -> improving
1,4 -> improving
4,2 -> declining
2,2 -> stable
1,3,2 -> mixed
3,1,2 -> mixed
1,1,3 -> improving
1,3,3 -> stable
```

Do not display percentage improvement.

## 28.6 Deleted sessions

Deleted sessions and sessions whose report was invalidated are excluded from progress.

Audio deletion alone does not remove a session from progress.

---

## 29. Privacy, retention, deletion and synchronous export

### 29.1 Session retention policy

Persist:

```json
{
  "audio": "delete_after_processing",
  "transcript": "retain"
}
```

Audio values:

```text
delete_after_processing
retain_until_deleted
```

The `update_retention` command changes only future-attempt policy. Every attempt snapshots the policy at creation.

### 29.2 Audio retention state

```text
not_applicable
temporary
retained
delete_pending
deleted
delete_failed
```

### 29.3 Default audio deletion

Audio becomes eligible after:

- transcript version committed;
- speech analysis completed or terminal unavailable;
- file path and hash ownership verified;
- attempt still references the same file and hash;
- the attempt-snapshotted policy is `delete_after_processing`;
- retention state is `temporary` or `delete_failed`.

Evaluation and grounding do not delay default deletion. The retention service must claim `audio_cleanup` immediately after the transcription and speech-analysis terminal predicates become true, using a dedicated stage job/claim and deadline that is independent of the 900-second evaluation budget. Claiming atomically changes state to `delete_pending` and appends `audio_cleanup_claimed`.

Failed transcription retains temporary audio for the configured failure window, required default 24 hours, unless the candidate deletes it earlier. A delayed cleanup claim is scheduled for the end of that window and uses the same ownership predicates.

Successful default cleanup atomically:

- removes the owned file;
- clears `audio_uri`;
- sets retention state `deleted` and `audio_deleted_at`;
- increments attempt `attempt_version` plus session `state_version` and `retention_version` exactly once;
- does not increment `activity_version`;
- appends `audio_deleted` with reason `default_cleanup`.

A cleanup failure sets `delete_failed`, increments attempt `attempt_version` plus session `state_version` and `retention_version` exactly once for that terminal attempt, appends `audio_delete_failed`, and exposes retry. Reconciliation must not repeatedly increment versions for the same persisted failure generation.

Cleanup requires exact URI, content hash, attempt policy, cleanup claim and retention-state predicates. A stale worker cannot delete a replacement file.

### 29.4 `delete_audio`

For the explicit attempt ID:

- remove the owned file;
- clear `audio_uri`;
- set `deleted` and timestamp;
- keep transcript, delivery metrics already persisted, evaluation and analytical report;
- increment the attempt `attempt_version` plus session `state_version` and `retention_version`, but not `activity_version`;
- make subsequent report/list/export responses recompute the live `retention_summary` overlay;
- append `audio_deleted`;
- be idempotent.

Failure sets `delete_failed`, increments attempt `attempt_version` plus session `state_version` and `retention_version` once for that deletion attempt, appends `audio_delete_failed` and exposes retry.

### 29.5 Exact transcript deletion behaviour

`delete_transcript` means **physical deletion**, not optional redaction, for transcript and transcript-derived payloads.

Within one transaction for the selected attempt:

1. physically delete all `interview_transcript_versions`;
2. physically delete all `interview_attempt_evaluations` and transcript-derived evidence/coaching payloads;
3. clear `SessionRecording.transcript`, current transcript/evaluation IDs, mirrored evaluation JSON and state;
4. increment `attempt_version` and `processing_generation` so older workers become stale;
5. when `accepted_recording_id` points to the attempt, atomically clear it, set the question to `asked`, increment `acceptance_generation`, and preserve `last_accepted_generation`; this creates exactly one replacement-acceptance opportunity and is the only Phase 1 mutation that does so;
6. mark attempt `deleted`;
7. delete the owned audio unconditionally; already-deleted audio is an idempotent success, and no post-deletion retranscription path exists in Phase 1;
8. redact transcript-derived adaptive follow-up question text to the fixed literal `[Deleted follow-up question]`;
9. set `follow_up_source_recording_id = NULL`, `follow_up_source_transcript_version_id = NULL`, `follow_up_context_json = NULL` and `follow_up_generation_json = NULL`, and delete transcript-derived evidence excerpts;
10. set `source_deleted = true` and exclude that follow-up bundle from report/progress;
11. retain only structural IDs, category, follow-up depth/reason enum and content-free deletion events.

A root transcript deletion does not silently delete a separate follow-up answer transcript. It does exclude the entire root bundle from aggregation because the initiating question context was deleted. The UI offers separate deletion for remaining follow-up answer content.

### 29.6 Active-session transcript deletion

After Section 29.5, apply this ordered state algorithm:

1. The target attempt must belong to the active question; otherwise reject with `coach_attempt_not_active`.
2. Determine whether the target is any of:
   - `active_recording_id`;
   - `accepted_recording_id`;
   - the attempt currently displayed in `coaching`;
   - the attempt identified by the current recoverable processing error.
3. If any condition in step 2 is true:
   - clear the matching active, accepted, coaching and failure references;
   - set `conversation_state = asking` for the same root question;
   - expose no transcript-derived review or coaching from the deleted attempt.
4. Otherwise the target is a preserved historical attempt for the active question:
   - keep `awaiting_next_action`, `coaching` or `recoverable_error` unchanged;
   - preserve the currently selected attempt and its view.
5. Increment session state and activity versions once.
6. Do not claim a report.

This algorithm is the exact meaning of the conditional destinations in Section 8.5.

### 29.7 Completed-session report invalidation and rebuild

Add report state:

```text
invalidated
```

For a completed session:

1. perform Section 29.5 deletion and increment `activity_version`;
2. set `report_state = invalidated`, `report_json = NULL`, `report_job_id = NULL`;
3. normal report reads and progress exclude the session immediately;
4. create an async report job;
5. atomically claim it with:

```text
report_state = invalidated
activity_version = expected_activity_version
status = completed
conversation_state = completed
```

6. set `report_state = building`, `report_build_reason = transcript_deletion_rebuild`, `report_job_id` and `report_started_at`;
7. rebuild only from remaining valid accepted attempts;
8. if none remain, publish `completed` with `session_level = not_assessed` and a content-free explanation;
9. finalise under Section 27.11 completed-session rebuild fence.

If claim creation fails, leave `invalidated`. If the worker fails after claim, set `report_state = failed`, clear the matching job ID and keep the report hidden. The explicit retry action is the `retry_report` command defined in Section 9.9; it creates a new completed-session rebuild claim without changing `status = completed` or `conversation_state = completed`. Startup and lazy reconciliation must support this completed-session `building` state without changing conversation status/state.

### 29.8 Candidate-reflection report rebuild

Recording or changing self-assessment after completion uses the same completed-session rebuild flow with:

```text
report_build_reason = reflection_update_rebuild
```

No transcript or evaluation is re-run.

### 29.9 Hard-delete session

Keep existing `DELETE /api/coach/sessions/{session_id}` as abandonment for `setup` or `active` sessions.

Add:

```http
POST /api/coach/sessions/{session_id}/deletion-commands
```

Hard deletion is available from **every** conversational lifecycle state: `setup`, `active`, `completed`, `abandoned` and `failed`, including `planning`, `ready`, `listening`, `processing_answer`, `reporting` and either `recoverable_error` scope. The candidate does not need to abandon or recover a session first.

Request:

```json
{
  "command_id": "01JEXAMPLE0000000000000000",
  "confirmation": "DELETE",
  "contract_version": "coach_session_hard_delete_v1"
}
```

Add the session-independent table:

```text
id VARCHAR(36) primary key
session_key_hash VARCHAR(64) not null
command_id VARCHAR(64) not null
request_hash VARCHAR(64) not null
result_state VARCHAR(32) not null  # processing, failed or completed
error_code VARCHAR(128) null
created_at DATETIME not null
completed_at DATETIME null
expires_at DATETIME not null
UNIQUE(session_key_hash, command_id)
```

`session_key_hash = SHA256(UTF8("coach-session-deletion-v1:" + session_id))`; the raw session ID is not retained after deletion. The domain-separated hash avoids introducing a new secret-management dependency while making the stored value unsuitable as a direct session identifier. The table stores no session title, company, role, transcript, finding, evidence or media path. The required retention is 30 days after `completed_at` or the latest failed retry, configurable from 7 through 90 days. A daily cleanup deletes expired rows. After expiry, replaying the old command is no longer guaranteed idempotent and returns normal not-found semantics.

Execution contract:

1. Create or reuse a `coach_session_deletion_results` row keyed by `(session_key_hash, command_id)`. A new claim sets `result_state = processing`; successful finalisation sets `completed`; worker or reconciliation failure sets `failed`. The row provides bounded idempotency after the session row is removed.
2. The claim transaction requires `deletion_state IN ('not_requested','failed')`, requires no current claim fields, increments `deletion_generation`, sets `deletion_state = deleting`, stores `deletion_job_id`, `deletion_command_id`, a random `deletion_claim_token` and lease expiry, and hides the session from normal list, live, report, progress and export reads.
3. Increment `setup_generation`; clear setup claim fields; increment every non-terminal attempt `processing_generation`; clear attempt/report job IDs; and mark their jobs cancelled or stale. This fences all setup, attempt and report workers.
4. Resolve or discard an active browser draft; no further conversational command is accepted.
5. Delete all owned media using exact URI/hash ownership checks.
6. Finalisation requires matching `deletion_generation`, `deletion_job_id`, `deletion_command_id`, `deletion_claim_token`, `deletion_state = deleting` and an unexpired claim. It then deletes transcripts, evaluations, uploads, stages, events, command results, evidence snapshots, questions, recordings, report/plan snapshots and session, and marks the independent deletion result `completed` without storing personal content. Emit content-free telemetry `coach.hard_deletion.completed`; do not attempt to append a session event after the event table has been deleted.
7. If owned-media removal or the transactional database finalisation fails, execute a conditional failure-finalisation update requiring the same deletion generation, job ID, command ID, claim token, and `deletion_state = deleting`. The update must:
   - keep the session hidden from every normal Coach read;
   - set `deletion_state = failed`, `deletion_failed_at`, and a stable error code;
   - clear `deletion_job_id`, `deletion_command_id`, `deletion_claim_token`, `deletion_claimed_at`, and `deletion_claim_expires_at`;
   - update the independent `coach_session_deletion_results` row from `processing` to `failed`, persist only the stable error code, set `completed_at` to the failure time, and set `expires_at` from that time;
   - increment `state_version` and `event_version` and append `hard_deletion_failed` while the session event table exists;
   - permit a new claim only through a new client command ID from `deletion_state = failed`.

Already removed owned media and missing child rows are success conditions on retry when ownership metadata proves they belonged to the same session. If the failure-finalisation fence no longer matches, record content-free stale-worker diagnostics and perform no session mutation.

A duplicate identical command returns the persisted deletion result. Reusing the command ID with a different request hash returns `coach_command_idempotency_conflict`. A failed or reconciled deletion is retried with a new command ID; reusing the failed command ID returns its original failed result. Failed sessions are read-only for conversational work but always allow this privacy deletion endpoint. Section 21.10 defines stale-`deleting` reconciliation and idempotent retry.

### 29.10 Cloud disclosure

Before start, disclose configured local/cloud routes and every selected data category that may be sent: audio, transcript, job description, approved evidence snapshots, and candidate-selected unapproved application-CV snapshots when `current_if_no_approved` selected such a source. Unapproved evidence must be labelled as such in the disclosure. Do not expose secrets.

### 29.11 Logging

Never log transcript text, evidence snapshots, CV text, prompt/model bodies or user-controlled paths.

### 29.12 Synchronous export contract

Add:

```http
POST /api/coach/sessions/{session_id}/exports
```

Request:

```json
{
  "format": "markdown",
  "expected_activity_version": 12,
  "expected_retention_version": 4,
  "include_transcript": false,
  "include_evidence_details": false,
  "include_attempt_history": false,
  "include_candidate_reflection": true,
  "contract_version": "coach_report_export_v1"
}
```

Formats:

```text
json
markdown
```

This endpoint is read-only and returns the attachment synchronously. It does not create an export row, server artefact, later download endpoint or expiry job.

Preconditions:

- `status = completed` and `conversation_state = completed`;
- `report_state` is `completed` or `fallback`;
- `expected_activity_version` and `expected_retention_version` match before rendering and immediately before response commit;
- every requested include flag is permitted by current retention and deletion state.

When the report is `invalidated`, `building` or `failed`, return HTTP 409 `coach_report_unavailable` and do not export an older snapshot.

Response headers:

```text
Content-Type: application/json; charset=utf-8
or
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="hatch-coach-<safe-session-id>.<ext>"
Cache-Control: no-store
ETag: "<sha256-of-response-bytes>"
X-Hatch-Session-Activity-Version: <version>
X-Hatch-Retention-Version: <version>
```

Build all bytes from one captured `(activity_version, retention_version)` pair. Before returning, confirm both still match. Otherwise return HTTP 409 `coach_export_source_changed`.

Repeated identical requests at the same activity and retention versions are naturally idempotent and must produce byte-identical output and ETag.

The export:

- uses persisted report and current permitted content;
- never re-evaluates;
- never embeds or links raw audio;
- labels evidence as Hatch source matching, not independent verification;
- returns 409 when `report_state` is not `completed` or `fallback`.

Browser print view remains:

```http
GET /coach/report/{session_id}/print
```

Server PDF generation remains deferred.

## 30. Security contract

## 30.1 Untrusted content

Treat as untrusted:

- transcripts;
- job descriptions;
- company research;
- CV content;
- Question Bank answers;
- candidate transcript edits;
- uploaded filenames and MIME types.

## 30.2 Prompt injection

Model prompts must separate:

```text
system contract
structured trusted metadata
untrusted transcript/evidence content
```

Untrusted text cannot:

- alter rubric dimensions;
- increase follow-up count;
- execute tools;
- mark evidence supported;
- reveal prompts;
- change retention;
- update candidate records;
- invoke commands.

## 30.3 Structured output

Every AI stage uses strict schemas and application validation.

Model prose cannot directly mutate state.

## 30.4 Session ownership

Use existing application authentication/lock boundaries.

All session, question, attempt and media operations must validate parent ownership and safe IDs using existing `_require_safe_id` patterns.

## 30.5 Media path safety

- never trust original filename for storage path;
- generate server path from validated opaque IDs;
- prevent traversal;
- restrict file permissions;
- reject symlinks where storage helpers allow;
- delete through resolved paths under configured Coach storage root only.

## 30.6 Size and content limits

Add configurable limits:

```text
max transcript characters
max coaching response characters
max evidence claims per answer
max evidence excerpt characters
max audio bytes
max answer duration
max attempts per question
max total questions including follow-ups
```

Recommended defaults:

```text
transcript: 30,000 characters
claims: 20
excerpt: 300 characters
attempts per question: 5
planned questions: 12
follow-ups per root: 2
total questions: 36 absolute defensive cap
```

A candidate may end the session before reaching limits.

## 30.7 Prohibited output scan

Before persisting evaluation/coaching, reject or repair output containing unsupported internal-state judgements such as:

```text
anxious
unconfident
emotionally unstable
dishonest
deceptive
culture fit
personality type
```

The scan must use contextual rules and benchmark cases, not a simplistic list that blocks legitimate transcript quotations. Prohibited judgements in model-authored fields are the target.

---

## 31. Observability contract

## 31.1 Extend the shared facade

Do not instantiate OpenTelemetry SDK objects in Coach services.

Extend:

```text
backend/app/observability/coach.py
backend/app/observability/attributes.py
backend/app/observability/runtime.py
```

## 31.2 New span names

```text
coach.conversation.command
coach.conversation.live_read
coach.session_plan
coach.answer.capture_reserve
coach.answer.audio_persist
coach.answer.transcription
coach.answer.speech_analysis
coach.answer.content_evaluation
coach.answer.evidence_grounding
coach.answer.follow_up_decision
coach.answer.finalise
coach.answer.coaching
coach.answer.audio_cleanup
coach.conversation.advance
coach.conversational_report
coach.conversational_progress
coach.transcript.edit
coach.retention.delete
```

## 31.3 Safe attributes

```text
hatch.coach.experience_version
hatch.coach.conversation_state
hatch.coach.state_version  # trace attribute only; prohibited as metric label/dimension
hatch.coach.command_type
hatch.coach.command_result
hatch.coach.recording_type
hatch.coach.attempt_kind
hatch.coach.attempt_number
hatch.coach.stage
hatch.coach.stage_state
hatch.coach.evaluation_contract_version
hatch.coach.report_contract_version
hatch.coach.follow_up_reason
hatch.coach.follow_up_depth
hatch.coach.retention_policy
hatch.coach.retention_state
hatch.coach.evidence_status
hatch.coach.compatibility_version
```

Do not use session IDs, question IDs, transcripts or evidence strings as metric labels.

`hatch.coach.state_version` is trace-only. The bounded Coach metric-attribute sanitizer must reject or drop it from counters, histograms and gauges. Add a regression test to the existing C3 sanitization suite.

## 31.4 Counters

```text
hatch.coach.conversation.commands
hatch.coach.conversation.command_conflicts
hatch.coach.attempts.reserved
hatch.coach.attempts.completed
hatch.coach.attempts.retried
hatch.coach.followups.proposed
hatch.coach.followups.admitted
hatch.coach.followups.rejected
hatch.coach.transcript.edits
hatch.coach.audio.deletions
hatch.coach.audio.deletion_failures
hatch.coach.stale_claim_rejections
hatch.coach.conversational_reports
```

## 31.5 Histograms

```text
hatch.coach.conversation.command.duration
hatch.coach.attempt.pipeline.duration
hatch.coach.transcription.duration
hatch.coach.evidence_grounding.duration
hatch.coach.audio_cleanup.duration
hatch.coach.conversational_report.duration
```

## 31.6 Gauges or observable state

Where the current facade supports it safely:

```text
pending conversational jobs
recoverable-error sessions
pending audio cleanup
reporting sessions
```

## 31.7 Diagnostics and canonical error registry

The following list is the sole canonical registry for new conversational API and stable gate errors. Commands, routers, diagnostics, tests, frontend handling, and documentation must import or derive from the same registry in `coach_conversational_contracts.py`; no second independently maintained list is permitted.

```text
coach_conversation_not_enabled
coach_conversational_command_required
coach_conversation_invalid_state
coach_conversation_version_conflict
coach_command_idempotency_conflict
coach_contract_unsupported
coach_setup_claim_expired
coach_setup_retry_budget_exhausted
coach_plan_rebuild_not_allowed
coach_attempt_not_active
coach_attempt_client_id_conflict
coach_attempt_already_accepted
coach_attempt_limit_exhausted
coach_attempt_upload_required
coach_attempt_upload_conflict
coach_attempt_upload_missing
coach_attempt_upload_hash_mismatch
coach_audio_upload_idempotency_conflict
coach_attempt_retry_budget_exhausted
coach_attempt_retry_source_unavailable
coach_attempt_job_budget_exhausted
coach_attempt_stale_claim
coach_transcript_deleted
coach_transcript_version_conflict
coach_transcript_schema_invalid
coach_evaluation_unavailable
coach_evaluation_evidence_span_invalid
coach_evaluation_prohibited_inference
coach_grounding_evidence_id_invalid
coach_grounding_source_unavailable
coach_draft_evidence_consent_required
coach_followup_budget_exhausted
coach_followup_reason_invalid
coach_followup_transcript_ungrounded
coach_followup_duplicate
coach_audio_already_deleted
coach_audio_cleanup_failed
coach_audio_deletion_failed
coach_export_source_changed
coach_report_unavailable
coach_report_not_ready
coach_report_invalidated
coach_report_conversational_snapshot_stale
coach_conversational_session_retry_unsupported
coach_progress_selector_conflict
coach_progress_incompatible_session
coach_locale_unsupported
coach_session_deletion_in_progress
coach_session_deletion_failed
coach_deletion_claim_expired
```

Internal diagnostics may attach a content-free reason detail, but the top-level code must come from this registry. `coach_progress_incompatible_session` is the only incompatibility code; `coach_session_incompatible_for_progress` is prohibited. Every code must have one HTTP-status mapping, retryability classification, frontend-safe message, and test in the stable contract registry.

---

## 32. API schema changes

## 32.1 Keep legacy schemas

Do not change the meaning of:

```text
AnswerEvaluation
SessionFeedbackReport
RubricDimension
SessionRubric
```

They remain legacy numeric schemas.

## 32.2 Add conversational schemas

Recommended Pydantic models:

```text
ConversationCommandRequest
ConversationCommandResult
ConversationLiveView
ConversationalSessionPlan
ConversationalQuestionRead
InterviewAttemptRead
TranscriptVersionRead
ConversationalRubricDimension
ConversationalAnswerEvaluation
EvidenceFinding
FollowUpProposal
CoachAnswerReview
ConversationalSessionReport
ConversationalProgressResponse
RetentionPolicy
RetentionStatus
```

## 32.3 Union dispatch

Session and report endpoints may use discriminated unions:

```json
{
  "experience_version": "conversational_v1",
  "<opaque-id>": "<opaque-id>"
}
```

If FastAPI response-model unions create OpenAPI instability, use separate conversational routes for detailed views while keeping common list summaries stable.

## 32.4 Session list item

Extend `SessionListItem` with optional:

```text
experience_version
conversation_state
session_level
retention_summary
```

Legacy values remain null where not applicable.

## 32.5 Capabilities endpoint

Extend `/api/coach/capabilities` with:

```json
{
  "conversational_interview": true,
  "typed_answers": true,
  "audio_upload": true,
  "automatic_turn_detection": "browser",
  "transcription": {
    "available": true,
    "provider_type": "local|cloud|none"
  },
  "evaluation": {
    "available": true,
    "provider_type": "local|cloud|none"
  },
  "audio_retention_default": "delete_after_processing",
  "video_analysis_for_conversational": false,
  "contract_version": "coach_capabilities_v2"
}
```

Browser microphone permission remains a frontend readiness check.

---

## 33. Frontend implementation contract

## 33.1 Page dispatch

Refactor current page into:

```text
session/[id]/page.tsx
  -> load session summary
  -> LegacyCoachSession for legacy_v1
  -> ConversationalCoachSession for conversational_v1
```

Preserve legacy test fixtures.

## 33.2 Server state

The conversational page uses `/live` as source of truth.

Local state is limited to:

- current unsent text;
- local recorder object;
- local capture elapsed time;
- local silence analyser state;
- pending command UI state;
- recoverable unsent media blob.

It must not locally decide that a question is accepted, completed or advanced.

## 33.3 Command helper

Add typed API helper:

```typescript
sendCoachConversationCommand(sessionId, command)
```

Requirements:

- generates or accepts stable `command_id`;
- includes current state version;
- does not silently retry 409 conflicts;
- refreshes live view after conflict;
- retries network failures only when command id remains identical;
- distinguishes accepted processing from completion.

## 33.4 Question display

Show:

- question text;
- planned progress;
- follow-up label when applicable;
- optional read-aloud control;
- current mode: Interview, Review or Coaching.

Do not show hidden target weakness or score while asking.

## 33.5 Processing view

Show bounded stage labels:

```text
Uploading answer
Creating transcript
Reviewing answer
Checking evidence
Preparing next step
```

Do not expose model chain details or internal gate codes in normal mode.

Advanced diagnostics may show error codes without personal content.

## 33.6 Review view

Separate panels:

```text
Answer quality
Delivery observations
Evidence check
Your reflection
```

Actions come from `allowed_commands`.

## 33.7 Named levels

Provide accessible badges with text labels. Do not rely on colour alone.

Do not reuse `ScoreRadar` for conversational sessions.

## 33.8 Attempt history

For the active question, show prior attempts in a collapsed history:

```text
Attempt 1 - Developing - not accepted
Attempt 2 - Interview-ready - accepted
```

Transcript/audio visibility follows retention.

## 33.9 Transcript correction

The edit UI must explain:

```text
Editing corrects transcription and re-runs answer and evidence review.
Delivery observations remain based on the original audio.
```

## 33.10 Accessibility

Required:

- keyboard-accessible controls;
- ARIA live region for state changes without excessive announcements;
- visible focus;
- button labels that include action and state;
- text equivalents for level comparisons;
- typed-answer parity;
- no automatic focus theft when polling updates arrive;
- reduced-motion compliance;
- captions/transcript display where available.

## 33.11 Navigation safety

Before leaving during `listening`, warn if an unsent local recording exists.

Do not block navigation when state is server-persisted `processing_answer` or later.

---

## 34. Legacy compatibility contract

## 34.1 Legacy APIs

Existing endpoints continue to work for `legacy_v1`.

For a conversational session, legacy submit endpoints should return a clear conflict rather than partially execute old logic:

```text
409 coach_conversational_command_required
```

Optional compatibility wrappers may translate only where semantics are exact:

- legacy text submit cannot safely represent begin/finish/accept, so do not auto-translate;
- legacy end may translate to `end_session` only when no ambiguous unaccepted attempt exists.

## 34.2 Legacy media

Existing video recordings and video metrics remain readable for legacy sessions.

New conversational session creation rejects `recording_mode = video` or maps it to audio only after explicit frontend explanation. Prefer rejection with a clear message.

## 34.3 Legacy reports

No recalculation, migration or named-level mapping.

## 34.4 Legacy progress

Existing application progress and trend routes remain numeric for legacy sessions.

Conversational progress uses the new endpoint and contract.

## 34.5 Retry-session endpoint

Current `/sessions/{id}/retry` creates a follow-up session chain. Preserve for legacy.

For `experience_version = conversational_v1`, `POST /api/coach/sessions/{id}/retry` is not supported in Phase 1 and must return HTTP `409` with error code `coach_conversational_session_retry_unsupported`. The frontend must offer **Create another session** and prefill the normal Section 7 creation form from the prior session plan; creation still occurs only through `POST /api/coach/sessions`. No compatibility wrapper may silently clone a conversational session.

---

## 35. Error contract

Use a consistent error body for new routes:

```json
{
  "error": {
    "code": "coach_conversation_invalid_state",
    "message": "This action is not available while the answer is processing.",
    "retryable": false,
    "current_state": "processing_answer",
    "current_state_version": 9,
    "correlation_id": "<opaque-id>",
    "details": {}
  }
}
```

The canonical new error codes are defined only in Section 31.7. Router schemas must reference that registry and must not duplicate or rename its values.

Do not expose:

- stack traces;
- prompts;
- provider secret details;
- restricted evidence;
- filesystem paths.

---

## 36. Configuration and feature flags

## 36.1 Feature flags

Add settings:

```text
HATCH_COACH_CONVERSATIONAL_ENABLED = false initially
HATCH_COACH_AUTO_TURN_DETECTION_ENABLED = true
HATCH_COACH_EVIDENCE_GROUNDING_ENABLED = true
HATCH_COACH_CONVERSATIONAL_PROGRESS_ENABLED = true
```

The stable rollout may change the default after acceptance evidence exists.

Disabling conversational mode:

- prevents creation of new conversational sessions;
- keeps existing conversational sessions readable;
- does not disable retention cleanup;
- does not expose legacy submit endpoints as a substitute.

## 36.2 Limits and timing

Add:

```text
HATCH_COACH_SILENCE_WARNING_MS = 4000
HATCH_COACH_SILENCE_FINISH_PROMPT_MS = 9000
HATCH_COACH_MAX_ANSWER_DURATION_SECONDS = 600
HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION = 5
HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT = 2
HATCH_COACH_PROGRESS_MAX_GROUPS = 20
HATCH_COACH_MAX_FOLLOWUPS_PER_ROOT = 2
HATCH_COACH_MAX_TRANSCRIPT_CHARACTERS = 30000
HATCH_COACH_MAX_EVIDENCE_CLAIMS = 20
HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS = 24
```

Configuration validation requires `HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION` from 1 through 20, `HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT` from 0 through 5, and `HATCH_COACH_PROGRESS_MAX_GROUPS` from 1 through 100. The effective attempt retry limit is snapshotted into each new attempt; later configuration changes do not alter an existing attempt's budget. The progress group limit is read at request time and disclosed in the response.

The backend returns silence and duration policy through the live/capability contract, even though detection is browser-side.

## 36.3 Contract versions

Centralize constants in `coach_conversational_contracts.py`:

```text
CONVERSATION_COMMAND_CONTRACT
LIVE_VIEW_CONTRACT
SESSION_PLAN_CONTRACT
RUBRIC_CONTRACT
EVIDENCE_GROUNDING_CONTRACT
FOLLOW_UP_CONTRACT
REPORT_CONTRACT
PROGRESS_CONTRACT
DELIVERY_POLICY
```

Do not scatter literal version strings across services.

---

## 37. Test strategy

The implementation is incomplete without unit, service, concurrency, router, frontend, E2E and benchmark evidence.

## 37.1 New backend test files

Recommended:

```text
backend/tests/test_services/test_coach_conversation_state.py
backend/tests/test_services/test_coach_conversation_commands.py
backend/tests/test_services/test_coach_live_view.py
backend/tests/test_services/test_coach_session_plan.py
backend/tests/test_services/test_coach_attempt_pipeline.py
backend/tests/test_services/test_coach_conversational_evaluator.py
backend/tests/test_services/test_coach_evidence_grounder.py
backend/tests/test_services/test_coach_followup_policy.py
backend/tests/test_services/test_coach_retention.py
backend/tests/test_services/test_coach_conversational_report.py
backend/tests/test_services/test_coach_conversational_progress.py
backend/tests/test_repositories/test_conversational_session_repository.py
backend/tests/test_routers/test_coach_conversation_router.py
backend/tests/test_routers/test_coach_conversation_async.py
backend/tests/test_migrations/test_conversational_coach_migration.py
```

## 37.2 State-machine unit tests

Test every legal transition and representative illegal transitions.

Required cases:

- start only from ready;
- begin only from asking;
- finish requires active attempt and payload/media;
- coaching only after completed evaluation;
- accept only terminal valid evaluation;
- pause/resume preserves state;
- stale expected state version rejected;
- follow-up transient state recovers;
- completed session rejects commands except deletion/read operations;
- legacy session rejects conversational commands.

## 37.2.1 Error-registry contract tests

- every error code referenced by a conversational command, route, reconciliation path, or frontend branch exists in the Section 31.7 registry;
- every registry code has exactly one HTTP-status mapping, retryability value, and frontend-safe message;
- `coach_session_incompatible_for_progress` is rejected as an unknown legacy alias;
- generated OpenAPI examples and diagnostics use `coach_progress_incompatible_session` consistently.

## 37.3 Command idempotency tests

- duplicate identical command returns original result;
- duplicate command after application restart returns original result;
- same ID/different payload returns conflict;
- network retry does not create duplicate attempt;
- duplicate accept does not create duplicate follow-up;
- duplicate end does not create duplicate report job;
- `end_session` acceptance suppresses follow-up persistence; exclusion sets the current question to skipped; zero accepted attempts produces a not-enough-evidence report.

## 37.4 Attempt tests

- deterministic numbering;
- concurrent begin-answer claims create at most one active attempt;
- retry preserves prior attempt;
- duplicate `client_attempt_id` returns the original attempt before limit validation;
- the atomic sixth attempt is rejected when the configured limit is five, including concurrent creation races;
- cancelled, invalid, unavailable and privacy-deleted attempts continue to consume the monotonic per-question attempt budget;
- `retry_answer` at the limit returns `coach_attempt_limit_exhausted` without moving to `asking`;
- accepted attempt explicit;
- a second acceptance in the same `acceptance_generation` is rejected with `coach_attempt_already_accepted`, and the original accepted pointer and `accepted_at` remain unchanged;
- deleting the accepted transcript increments `acceptance_generation`, clears the pointer, and permits exactly one replacement acceptance in the new generation;
- follow-up attempt cannot be accepted for root question;
- legacy canonical resolver unchanged.

## 37.5 Transcript/evaluation version tests

- initial transcript version creation;
- candidate edit creates version 2;
- original remains unchanged;
- speech metrics unchanged after text edit;
- new evaluation references version 2;
- stale evaluation worker for version 1 rejected;
- current compatibility fields mirror version 2;
- delete transcript removes derived evaluation safely.

## 37.6 Pipeline tests

- typed happy path;
- manual retry count is snapshotted, incremented once per accepted retry command, and never consumed by duplicate commands;
- retry budget exhaustion returns `coach_attempt_retry_budget_exhausted` without mutation;
- missing retry source returns `coach_attempt_retry_source_unavailable` without mutation;
- valid upstream stages are represented by `reused` rows and the earliest failed stage plus all downstream stages rerun;
- reused stages require matching immutable inputs and contract versions;
- audio happy path;
- transcription unavailable;
- speech analysis unavailable but content evaluation succeeds;
- evidence grounding unavailable;
- follow-up generation unavailable;
- invalid structured output repaired;
- exhausted repair marks evaluation unavailable;
- job timeout reconciles to recoverable error;
- expired setup claim reconciles to setup recoverable error or terminal failed and allows only a new-generation retry;
- expired hard-deletion claim reconciles to hidden failed and a new command ID can retry idempotently;
- restart after persisted observation/job;
- audio cleanup occurs after transcript/metrics, before content evaluation completes if independently safe.

## 37.7 Ownership and race tests

Required races:

- two workers finalise same attempt;
- transcript edit while old worker running;
- retry while stale evaluation completes;
- end session while attempt processing;
- accept attempt while report claim starts;
- audio retention changed before cleanup finalises;
- delete transcript while evaluation worker runs;
- report rebuild after transcript deletion races old report worker;
- two follow-up proposals for same root;
- duplicate `client_attempt_id` after the first request moved the session to `listening`;
- setup retry/rebuild stale worker after a newer setup generation;
- hard deletion while setup, attempt or report workers are running;
- duplicate transient-state reconciliation;
- `retry_processing` and `edit_transcript` commit `pending_processing` before worker dispatch;
- cleanup finalisation after evaluation has already moved the session to `awaiting_next_action`;
- cleanup success and `delete_failed` each increment retention/state versions once per cleanup generation.

Every stale worker must perform no authoritative mutation.

## 37.8 Rubric tests

- every judgement requires valid transcript span;
- invalid span rejected;
- missing dimension becomes invalid or not assessed per contract;
- delivery and evidence cannot be assigned by evaluator model;
- answer-level gates exact;
- no user-facing numeric values;
- typed input delivery not assessed;
- prohibited confidence wording rejected;
- technical failure creates no low level.

## 37.9 Evidence tests

- approved CV supports claim;
- partial metric support;
- absent evidence returns not found, not false;
- objective conflict;
- opinion not verifiable;
- invented evidence ID rejected;
- job description cannot support candidate experience;
- draft Question Bank excluded by default;
- model answer cannot support candidate claim;
- source hash mismatch detected.

## 37.10 Follow-up tests

- max two per root;
- retry does not reset budget;
- deletion does not reset budget;
- reason allowlist;
- score-only proposal rejected;
- filler-only proposal rejected;
- ungrounded proposal rejected;
- duplicate proposal rejected;
- return to planned sequence;
- follow-up failure does not block progression;
- behavioural, role-specific and mixed category-distribution validation;
- adaptive follow-ups inherit their root category.

## 37.11 Report tests

- explicit accepted attempts only;
- unaccepted retry excluded;
- follow-up bundle adjustment at most one level;
- lower-median aggregation exact;
- named session-level gates exact;
- evidence conflicts listed separately;
- no numeric score in conversational schema;
- deterministic fallback preserves levels/counts;
- report snapshot read is stable;
- stale report worker rejected;
- transcript deletion invalidates and rebuilds report;
- legacy report fixtures unchanged.

## 37.12 Retention tests

- default delete-after-processing;
- retained-audio option;
- deletion fence verifies path/hash/policy;
- stale cleanup cannot delete replacement;
- failed cleanup visible and retryable;
- failure grace cleanup after configured hours;
- delete audio leaves transcript/evaluation;
- delete transcript removes derived content;
- hard-delete removes files and rows;
- completion is stored only in the pseudonymous deletion receipt and telemetry;
- deletion receipts expire at the configured retention boundary;
- abandoned is not represented as deleted.

## 37.13 Router tests

- command schema;
- live view;
- audio upload;
- version conflicts;
- safe ID validation;
- legacy/cross-contract route rejection;
- pre-attempt hint transfer and question pending-hint reset;
- retry of an accepted question is rejected;
- capabilities;
- report union/dispatch;
- progress compatibility;
- cloud disclosure fields;
- error body redaction.

## 37.14 Frontend tests

Recommended files:

```text
frontend/src/components/coach/conversation/__tests__/ConversationSession.test.tsx
frontend/src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx
frontend/src/components/coach/conversation/__tests__/AnswerReview.test.tsx
frontend/src/components/coach/conversation/__tests__/TranscriptEditor.test.tsx
frontend/src/components/coach/conversation/__tests__/ConversationalReport.test.tsx
frontend/src/components/coach/conversation/__tests__/RetentionControls.test.tsx
```

Required assertions:

- server state wins after refresh;
- 409 refreshes without duplicate command;
- no live scoring;
- silence prompt offers finish/keep speaking;
- mic denied retains typed option;
- accepted attempt not inferred locally;
- retry keeps history;
- named level labels accessible;
- Observed delivery facts do not use confidence language;
- transcript edit disclosure visible;
- processing failures separate from performance;
- legacy session still renders numeric UI.

## 37.15 E2E scenarios

### Scenario A - Typed interview

1. Create conversational session.
2. Start.
3. Type answer.
4. Process.
5. Review.
6. Accept.
7. Complete remaining questions.
8. Generate named-level report.

### Scenario B - Voice and default deletion

1. Grant microphone.
2. Begin answer.
3. Silence prompt appears.
4. Keep speaking.
5. Finish.
6. Audio uploads and transcribes.
7. Audio deletes after processing prerequisites.
8. Transcript/evaluation remain.

### Scenario C - Retry

1. Submit attempt one.
2. Request coaching.
3. Retry.
4. Submit attempt two.
5. Send `accept_attempt` with the explicit `attempt_id` of attempt one.
6. Repeat in a separate test selecting attempt two.
7. Each report uses only the selected attempt for that run.

### Scenario D - Adaptive follow-ups

1. Answer omits measurable result.
2. Valid grounded follow-up is proposed.
3. Candidate accepts root answer.
4. Follow-up asked.
5. Second follow-up allowed.
6. Third rejected and planned sequence resumes.

### Scenario E - Transcript edit race

1. Audio evaluation completes.
2. Candidate edits transcript.
3. New job starts.
4. Old late worker cannot restore previous evaluation.
5. Delivery remains original.

### Scenario F - Restart recovery

1. Submit audio.
2. Restart backend during processing.
3. Startup reconciliation resolves state.
4. Candidate returns to review or recoverable retry.
5. No duplicate attempt.

### Scenario G - Degraded AI

1. Transcription succeeds.
2. evaluator unavailable.
3. Transcript is preserved.
4. No level invented.
5. Candidate can retry or continue/skip.

### Scenario H - Legacy regression

1. Open legacy session.
2. Submit through legacy path.
3. Numeric report unchanged.
4. Conversational tables do not alter canonical legacy aggregation.

---

## 38. Benchmark contract

## 38.1 Extend existing Coach benchmark

Do not build a separate generic benchmark framework.

Extend:

```text
backend/benchmarks/coach/
```

Use existing manifest, diagnostics, timeout and profile conventions from the completed Coach benchmark specification.

## 38.2 New benchmark suite version

Recommended:

```text
coach_conversational_v1
```

## 38.3 Benchmark profiles

```text
contract_smoke
acceptance_smoke
standard
extended
```

`acceptance_smoke` must remain runnable on constrained local infrastructure and prove contracts rather than prose quality.

## 38.4 Synthetic data

Use synthetic candidate/job/interview content only.

No personal repository-owner data may be embedded in benchmark fixtures.

## 38.5 Required scenario groups

### Rubric

- strong structured answer;
- vague generic answer;
- relevant but no impact;
- typed answer delivery not assessed;
- technical failure no low score;
- transcript evidence-span fidelity.

### Evidence grounding

- fully supported;
- partially supported metric;
- not found;
- objective conflict;
- not verifiable opinion;
- malicious prompt inside evidence.

### Follow-up

- clarify example;
- measurable result;
- role depth;
- low level with no specific gap -> no follow-up;
- filler-heavy but complete answer -> no follow-up;
- duplicate and third follow-up blocked deterministically.

### Coaching

- no invented metric;
- placeholder used where metric absent;
- candidate facts preserved;
- evidence conflict disclosed correctly.

### Prohibited inference

- asks model to label anxiety;
- asks for confidence score;
- asks for personality type;
- asks for culture fit;
- asks to infer deception;
- transcript contains instruction to ignore contract.

### End-to-end

- plan -> questions -> answer -> evaluation -> grounding -> follow-up -> report.

## 38.6 Hard gates

A benchmark run is invalid or failed when:

- output schema invalid after repair budget;
- transcript evidence span does not match;
- invented evidence ID;
- user-facing numeric conversational score;
- prohibited inference persisted;
- follow-up reason invalid;
- follow-up not grounded in transcript;
- more than two follow-ups admitted;
- not-found evidence described as false;
- technical failure lowers rubric;
- model answer becomes candidate evidence;
- stale worker changes final state in concurrency harness.

## 38.7 Quality metrics

Track:

```text
schema_validity_rate
evidence_span_precision
evidence_id_validity
prohibited_inference_rate
unsupported_claim_rate
follow_up_admission_precision
follow_up_budget_violations
repair_count
fallback_rate
stage_timeout_rate
```

Do not rank invalid outputs as if they were valid prose samples.

## 38.8 Manifest

Record:

```text
suite version
profile
model route
model identifier
provider
contract versions
prompt versions
timeouts
repair budgets
fixture hashes
repository baseline hash
run timestamp
```

---

## 39. Pull request topology

Implement in four sequential PRs. Each PR must be independently reviewable and keep the existing application usable.

## PR 1 - Conversational foundation and persistence

Scope:

- migrations;
- experience-version dispatch;
- state machine;
- command result table;
- session event table;
- attempt/question extensions;
- transcript/evaluation/stage tables;
- repository methods;
- command endpoint;
- live endpoint;
- reconciliation for state/transient claims;
- legacy compatibility tests;
- feature flag default off.

Acceptance evidence:

- state-machine tests;
- idempotency tests;
- migration tests;
- stale command/worker tests;
- legacy report regression.

Do not implement final LLM evaluation in this PR. Use deterministic stub/test service behind an interface where required.

Recommended Codex model:

```text
strongest available reasoning model
reasoning level: high
```

Rationale: schema, concurrency and migration correctness are the highest-risk work.

## PR 2 - Capture, processing and retention

Scope:

- conversational frontend shell;
- MediaRecorder capture;
- silence detection;
- audio upload;
- typed answer path;
- transcript versions;
- speech metrics;
- stage processing;
- timeouts/retries;
- audio retention and cleanup;
- refresh recovery;
- accessibility for capture controls.

Acceptance evidence:

- typed and audio E2E;
- default audio deletion;
- pause/resume;
- restart recovery;
- no live score;
- stale cleanup protection.

Recommended Codex model:

```text
strong reasoning model
reasoning level: high for backend/recovery; medium-high for frontend
```

## PR 3 - Evaluation, evidence, coaching and follow-ups

Scope:

- named rubric contract;
- conversational evaluator;
- delivery policy;
- evidence package and grounder;
- follow-up policy;
- coaching skeleton/enrichment;
- transcript editing and re-evaluation;
- explicit attempt acceptance;
- answer review UI;
- benchmark extensions for contract smoke and acceptance smoke.

Acceptance evidence:

- rubric hard gates;
- evidence statuses;
- prohibited inference cases;
- two-follow-up maximum;
- transcript-edit stale-worker race;
- no invented coaching facts.

Recommended Codex model:

```text
strongest available reasoning model
reasoning level: high
```

## PR 4 - Report, progress, privacy completion and production hardening

Scope:

- conversational report builder;
- report UI;
- compatible progress;
- deletion workflows;
- JSON and Markdown report exports plus the browser print view;
- observability extensions;
- full benchmark standard profile;
- security/adversarial tests;
- support diagnostics;
- documentation;
- feature-flag rollout.

Acceptance evidence:

- report deterministic aggregation;
- deletion/rebuild;
- progress compatibility;
- benchmark manifests;
- full backend/frontend/E2E suite;
- backup/restore smoke if project release process requires it.

Recommended Codex model:

```text
strong reasoning model
reasoning level: high
```

## 39.1 No mixed Phase 2 work

Do not add Candidate Intelligence tables or mentor persona systems in these PRs.

## 39.2 PR sequencing

```text
PR 1 must merge before PR 2
PR 2 must merge before PR 3
PR 3 must merge before PR 4
```

Parallel feature branches may be prepared, but migration and contract dependencies remain sequential.

---

## 40. Exact implementation file map

## 40.1 Backend models and migration

Modify:

```text
backend/app/models/coach_session.py
backend/app/models/__init__.py, if explicit exports exist
backend/alembic/versions/<new conversational revision>.py
```

Potentially create model files if repository style supports splitting, but avoid circular relationship imports.

## 40.2 Schemas

Modify:

```text
backend/app/schemas/coach.py
```

If it becomes too large, split new schemas into:

```text
backend/app/schemas/coach_conversation.py
```

and re-export stable names where needed.

## 40.3 Repository

Modify:

```text
backend/app/repositories/session_repository.py
```

If conversational operations make it unmanageably large, create:

```text
backend/app/repositories/conversational_session_repository.py
```

with explicit transaction methods. Do not duplicate legacy CRUD logic unnecessarily.

Required repository operations include:

```text
create_conversational_session_stub
persist_session_plan
persist_session_evidence_records
claim_conversation_command
append_session_event
reserve_conversational_attempt
persist_audio_upload_result
update_future_retention_policy
record_attempt_self_assessment
create_transcript_version
create_evaluation_version
claim_attempt_processing
finalise_attempt_processing
accept_attempt
create_follow_up_question
advance_question
claim_conversational_report
claim_completed_session_report_rebuild
finalise_conversational_report
finalise_completed_session_report_rebuild
invalidate_report_for_deleted_input
delete_attempt_audio
delete_attempt_transcript
```

## 40.4 Services

Create the bounded services listed in section 6.

Refactor shared helpers from current services only when required. Do not perform unrelated Coach redesign.

## 40.5 Router

Modify:

```text
backend/app/routers/coach.py
```

The router already approaches 1,000 lines. Strongly prefer extracting conversational endpoints to:

```text
backend/app/routers/coach_conversation.py
```

mounted under the same `/api/coach` prefix.

Shared dependency/service construction should remain consistent.

## 40.6 Reconciliation

Modify:

```text
backend/app/services/coach_reconciliation.py
backend/app/main.py only if startup registration changes
```

Keep one startup Coach reconciliation entry point.

## 40.7 Frontend

Modify:

```text
frontend/src/app/coach/session/[id]/page.tsx
frontend/src/app/coach/report/[id]/page.tsx
frontend/src/lib/api.ts
```

Create new conversation components and tests.

Keep legacy components:

```text
EvaluationCard
ScoreRadar
FeedbackReport
```

for legacy rendering.

## 40.8 Documentation

Update:

```text
README.md, only feature summary where appropriate
docs/user-guide/INTERVIEW_PREP.md
docs/architecture/ or existing architecture location
docs/implementation-specs/active/ with this spec or its repository copy
```

Document:

- conversational vs legacy sessions;
- privacy defaults;
- cloud disclosure;
- typed mode;
- no emotion/confidence inference;
- recovery behaviour;
- feature flags.

---

## 41. Verification commands

Codex must run commands from the repository-supported environment.

## 41.1 Backend targeted

```bash
cd backend
python -m pytest -q --no-cov \
  tests/test_services/test_coach_conversation_state.py \
  tests/test_services/test_coach_conversation_commands.py \
  tests/test_services/test_coach_attempt_pipeline.py \
  tests/test_services/test_coach_conversational_evaluator.py \
  tests/test_services/test_coach_evidence_grounder.py \
  tests/test_services/test_coach_followup_policy.py \
  tests/test_services/test_coach_retention.py \
  tests/test_services/test_coach_conversational_report.py \
  tests/test_routers/test_coach_conversation_router.py
```

## 41.2 Backend full

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

## 41.3 Migration

```bash
cd backend
alembic heads
alembic upgrade head
alembic current
```

Verify exactly one head.

Run migration tests against a copy of a database at the uploaded baseline head.

## 41.4 Frontend

```bash
cd frontend
npm run type-check
npm test
npm run build
npm run test:e2e
```

## 41.5 Repository CI

```bash
make ci
```

Use repository target definitions as authoritative if commands have changed during implementation.

## 41.6 Benchmark

The exact CLI must follow the existing Coach benchmark command style. Add documented examples for:

```text
contract_smoke
acceptance_smoke
standard
```

The acceptance evidence attached to PR 3 or PR 4 must include the manifest and gate summary, not only a console claim that the run passed.

---

## 42. Release gates

Phase 1 is not complete until every gate below passes.

## 42.1 Architecture gates

- New conversational sessions use a deterministic server-owned state machine.
- Browser local state cannot advance a session independently.
- `SessionRecording` is extended, not duplicated by a second attempt table.
- Commands are idempotent and versioned.
- Attempts, transcripts and evaluations preserve versions.
- Existing async/reconciliation patterns are reused.
- Legacy and conversational report builders remain separate.

## 42.2 State and concurrency gates

- Every command validates state and expected version.
- Duplicate begin-answer creates one attempt.
- Late evaluation cannot overwrite an edited transcript.
- Late report cannot overwrite a newer activity version.
- Follow-up creation is idempotent.
- Audio cleanup is ownership-fenced.
- Startup reconciliation resolves every supported stale state.

## 42.3 Product gates

- Typed and voice interviews work end to end.
- Automatic silence prompt works with Finish Answer and Keep Speaking.
- Pause and resume work without silently submitting.
- Review and coaching are optional.
- Retry preserves prior attempts.
- Candidate chooses accepted attempt.
- Follow-ups never exceed two per root question.
- Follow-ups are grounded in current transcript.
- Final report uses named levels.
- Compatible progress uses named trends.

## 42.4 AI-quality gates

- Every assessed content level has transcript evidence.
- Evidence IDs are valid.
- Not-found claims are not labelled false.
- No model-generated metric or experience is presented as candidate fact.
- Technical failures produce unavailable/not-assessed, not low performance.
- Invalid model output cannot partially persist.
- Prohibited inference benchmark passes.

## 42.5 Privacy gates

- Default audio policy deletes after processing prerequisites.
- Retained-audio choice works.
- Delete audio leaves transcript/evaluation intact.
- Delete transcript removes transcript-derived evaluation/evidence.
- Deletion failures are visible.
- Logs/metrics contain no transcript/evidence text.
- Cloud processing disclosure is visible before session start.
- Hard delete is distinguishable from abandon.

## 42.6 Compatibility gates

- All legacy Coach tests pass.
- Legacy report values and schemas remain unchanged.
- Existing video records remain readable.
- Existing progress routes remain functional.
- Old API callers omitting experience version still create legacy sessions.
- Conversational sessions reject semantically unsafe legacy write routes.

## 42.7 Accessibility gates

- Entire typed interview is keyboard accessible.
- Voice controls are keyboard accessible.
- State changes are announced appropriately.
- Level badges include text.
- No information depends solely on colour.
- Audio is not required for review/report/progress.

## 42.8 Operational gates

- One Alembic head.
- Backend full test suite passes.
- Frontend type-check, unit, build and E2E pass.
- Benchmark acceptance smoke passes.
- Stale-worker race suite passes.
- Feature flag disables creation safely while preserving reads/cleanup.

---

## 43. Acceptance criteria

The following are binding acceptance criteria.

### AC-01 - Session planning

Given a valid conversational session request, the backend persists a versioned session plan, evidence references, contract versions, retention policy and compatibility key before returning state `ready`.

### AC-02 - State authority

After browser refresh at any non-terminal point, the UI restores from `/live` and does not infer progression from local question/recording arrays.

### AC-03 - Idempotent command

Re-sending an identical `begin_answer` command ID returns the same attempt and does not create another row.

### AC-04 - Stale client

A command with an old state version returns 409 and no mutation.

### AC-05 - Typed parity

A typed answer completes evaluation, grounding, coaching, follow-up and report flow with delivery `not_assessed`.

### AC-06 - Voice capture

A voice answer can be recorded, paused, resumed, uploaded and processed without browser Web Speech being required.

### AC-07 - Silence prompt

Prolonged silence prompts the candidate to Finish or Keep Speaking and does not auto-score or auto-submit at the warning threshold.

### AC-08 - Default audio deletion

With default policy, successful transcription and speech-analysis terminal state cause audio deletion while transcript and evaluation remain.

### AC-09 - Retained audio

With retained policy, cleanup does not delete audio.

### AC-10 - Transcript versioning

A candidate transcript correction creates a new transcript and evaluation version, preserving the original and keeping original delivery metrics.

### AC-11 - Late worker

A worker for a superseded transcript/evaluation fails its finalisation predicate and performs no authoritative mutation.

### AC-12 - Named rubric

Conversational evaluation returns only the specified named levels and no user-facing numeric score.

### AC-13 - Evidence spans

Every assessed content dimension contains at least one validated current-transcript evidence span.

### AC-14 - Evidence status

A claim absent from selected evidence returns `not_found`, with wording that does not assert falsehood.

### AC-15 - Evidence conflict

An objective contradiction returns `conflicting` and remains separate from answer communication quality.

### AC-16 - No confidence inference

No conversational evaluation, report or UI exposes vocal confidence, emotion, personality, deception or presence judgements.

### AC-17 - Follow-up grounding

Every adaptive follow-up has an allowed reason and a matching span in the current accepted transcript.

### AC-18 - Follow-up budget

No root planned question can create more than two adaptive follow-up rows, including after retry, deletion or recovery.

### AC-19 - Retry preservation

Retry creates a new attempt and does not overwrite or automatically accept either attempt.

### AC-20 - Explicit acceptance

Only the recording referenced by `accepted_recording_id` contributes as the root answer to the conversational report.

### AC-21 - Optional coaching

The interview can proceed without requesting coaching. Requesting coaching does not change rubric levels.

### AC-22 - Report determinism

The conversational report derives counts, named levels, accepted attempts and priorities deterministically before optional narrative enrichment.

### AC-23 - Report fallback

Narrative/model failure yields a usable fallback report and completed session, without changing deterministic values.

### AC-24 - Compatible progress

Only sessions with matching compatibility keys are compared.

### AC-25 - No false precision

Conversational UI, report and progress contain no readiness percentage or 0–10 score.

### AC-26 - Delete audio

Candidate can delete audio independently and receives truthful success/failure state.

### AC-27 - Delete transcript

Candidate can delete transcript; dependent evaluation/report data is invalidated and rebuilt or removed safely.

### AC-28 - Technical isolation

Transcription, evaluator, grounding or cleanup failure never reduces a candidate rubric level.

### AC-29 - Legacy preservation

A baseline legacy fixture produces the same numeric report before and after Phase 1.

### AC-30 - Observability privacy

Automated tests verify that logs, attributes, metrics and support diagnostics contain no transcript/evidence content.

---

## 44. Known implementation risks and mandated mitigations

## 44.1 ORM relationship complexity

Adding `accepted_recording_id` creates a second relationship between question and recording.

Mitigation:

- specify `foreign_keys` explicitly in SQLAlchemy relationships;
- test mapper configuration at import;
- avoid ambiguous backrefs;
- consider storing only the FK without an ORM relationship if simpler.

## 44.2 SQLite concurrency

SQLite serializes writers and does not provide row-level `SELECT FOR UPDATE` semantics comparable to PostgreSQL.

Mitigation:

- use conditional UPDATE predicates;
- verify affected row count;
- keep transactions short;
- use existing WAL/foreign-key configuration;
- avoid max+1 allocation without an atomic session counter.

## 44.3 Router and schema size

Current files are already large.

Mitigation:

- split conversational router/schemas/services;
- retain import compatibility;
- do not create a new generic framework.

## 44.4 Deletion complexity

Transcript deletion affects report and progress.

Mitigation:

- hide invalidated report immediately;
- use existing report claim/rebuild pattern;
- keep deletion idempotent;
- test completed-session deletion explicitly.

## 44.5 Model variability

Named-level evaluation and grounding may be difficult for weak local models.

Mitigation:

- strict structured contracts;
- one repair;
- deterministic validation;
- unavailable state rather than invented score;
- benchmark by capability/profile;
- no lowering of standards for fallback model.

## 44.6 Browser media recovery

A browser cannot always restore a live `MediaRecorder` after refresh.

Mitigation:

- backend preserves draft state;
- frontend truthfully distinguishes local unsent media from persisted media;
- recovery offers discard/retry or upload existing blob where available;
- never claim capture resumed automatically.

---

## 45. Codex implementation instructions

Codex must follow this sequence for each PR:

1. Read this entire specification.
2. Inspect the current files named in the PR scope.
3. Confirm the uploaded-baseline contracts still match the working branch.
4. If the working branch has materially changed, document the delta before coding.
5. Write or update tests first for the relevant deterministic contracts.
6. Implement the smallest bounded service changes that satisfy them.
7. Run targeted tests.
8. Run full regression tests for touched layers.
9. Run migration and one-head checks where applicable.
10. Produce acceptance evidence with command output and benchmark manifest where required.

Codex must not:

- invent a second attempt table;
- replace the existing Coach async/reconciliation framework;
- convert legacy numeric reports;
- add emotion/confidence inference;
- implement Candidate Intelligence early;
- make model output authoritative;
- weaken a contract to make a local model pass;
- silently omit a required release gate;
- report completion without verification output.

## 45.1 Clarification policy

This specification intentionally resolves the architectural direction and technical contracts.

Codex should ask only when:

- the working branch materially contradicts the uploaded baseline;
- a named existing integration no longer exists;
- a data-loss decision would exceed this deletion contract;
- provider capabilities make an explicitly required feature impossible.

Minor implementation choices should follow repository conventions and the locked decisions here.

---

## 46. Definition of done

Phase 1 is done only when:

```text
Conversational interview creation works.
Server-owned state survives refresh and restart.
Typed and voice turns complete.
Attempts and edits are versioned.
Candidate explicitly accepts answers.
Named rubric levels are evidence-backed.
Evidence grounding is attributable and non-accusatory.
Follow-ups are grounded and capped.
Coaching cannot invent experience.
Audio deletes by default and retention is truthful.
Report and progress avoid false precision.
Legacy Coach remains stable.
Concurrency, recovery, privacy and adversarial suites pass.
```

After Phase 1 is merged and its stable release gates pass, implementation planning may proceed for:

```text
Hatch Candidate Intelligence Platform & Interview Mentor Architecture Specification v1.0
```

Phase 2 must consume Phase 1’s versioned attempts, transcript/evaluation history, evidence findings, session plan and compatibility context through explicit interfaces rather than reading legacy blobs heuristically.

---

# Appendix A: Derived allowed-command projection

This appendix is derived from Section 8.5 and must be covered by a parity test.

| State | Allowed commands |
|---|---|
| `planning` | none; abandonment through existing session DELETE only |
| `ready` | `start`, `rebuild_plan`, `update_retention` |
| `asking` | `begin_answer`, `request_hint`, `skip_question`, `pause`, `end_session`, `update_retention` |
| `listening` | `finish_answer`, `keep_speaking`, `request_hint`, `pause`, `cancel_attempt`, `update_retention` |
| `processing_answer` | none |
| `awaiting_next_action` | `request_coaching`, `retry_answer`, `edit_transcript`, `accept_attempt`, `record_self_assessment`, `update_retention`, `pause`, `end_session`, `delete_audio`, `delete_transcript` |
| `coaching` | `return_to_review`, `edit_transcript`, `retry_answer`, `accept_attempt`, `record_self_assessment`, `update_retention`, `pause`, `end_session`, `delete_audio`, `delete_transcript` |
| `asking_follow_up` | none |
| `advancing` | none |
| `paused` | `resume`, `update_retention`, `end_session` under Section 8.6, `delete_audio` only for a non-draft target satisfying Section 9.9 |
| `reporting` | none; report-status read only |
| `completed` | `record_self_assessment`, conditional `retry_report` for failed rebuild, `delete_audio`, `delete_transcript`, hard-delete session and export/report reads |
| `recoverable_error` with `status = setup` | `retry_setup`, `update_retention` |
| `recoverable_error` with `status = active` | only the scope-compatible subset of `retry_processing`, `retry_answer`, `retry_report`, `update_retention`, `pause`, `end_session`, `delete_audio` and `delete_transcript` defined in Sections 8.5 and 9.9 |
| `abandoned` | hard-delete and reads only |
| `failed` | reads and hard-delete only; replacement creation uses the normal Section 7 endpoint |

The backend computes this list from the same registry used for validation. The frontend has no independent transition table. `retry_answer` appears in review states only when the active question is still `asked` and has no accepted recording; `accept_attempt` appears only under the same one-time-acceptance predicate. Hard deletion uses the separate Section 29.9 endpoint and is available from every row in this appendix.

# Appendix B - Fixed dimension priority

Use this deterministic priority for ties:

```text
relevance
structure
specificity
impact
role_depth
clarity
conciseness
delivery
evidence_consistency
```

This is not a claim that earlier dimensions are universally more important. It is only a stable tie-breaker for report selection.

---

# Appendix C - Follow-up reason definitions

| Reason | Definition |
|---|---|
| clarify_example | The current answer references an example but essential context is ambiguous. |
| measurable_result | The answer describes action but omits the requested or material result. |
| personal_action | The answer uses collective language and does not explain the candidate’s action. |
| reasoning | The answer states a decision without explaining why or which trade-off was considered. |
| role_depth | The answer remains below the depth explicitly required by the role/question. |
| resolve_ambiguity | A material phrase has more than one plausible interpretation. |
| evidence_consistency | A current material claim is partial, not found or conflicting and a neutral clarification can resolve it. |

---

# Appendix D - Evidence wording guide

Use:

```text
Supported by your approved CV.
Partially supported: the project is present, but the metric is not recorded.
Not found in the evidence selected for this session.
Conflicting detail: the approved source records a different project duration.
Not verifiable from the selected evidence.
```

Do not use:

```text
True.
False.
You lied.
This claim is suspicious.
The model thinks this did not happen.
```

---

# Appendix E - Conversational report example

```json
{
  "session_id": "session_123",
  "report_state": "completed",
  "session_level": "interview_ready",
  "dimensions": {
    "relevance": {
      "level": "strong",
      "assessed_root_bundles": 5
    },
    "structure": {
      "level": "interview_ready",
      "assessed_root_bundles": 5
    },
    "specificity": {
      "level": "interview_ready",
      "assessed_root_bundles": 5
    },
    "impact": {
      "level": "developing",
      "assessed_root_bundles": 4
    },
    "role_depth": {
      "level": "interview_ready",
      "assessed_root_bundles": 5
    },
    "clarity": {
      "level": "strong",
      "assessed_root_bundles": 5
    },
    "conciseness": {
      "level": "interview_ready",
      "assessed_root_bundles": 5
    },
    "delivery": {
      "level": "interview_ready",
      "assessed_root_bundles": 4
    },
    "evidence_consistency": {
      "level": "developing",
      "assessed_root_bundles": 4
    }
  },
  "improvement_priorities": [
    {
      "dimension": "impact",
      "reason": "Three accepted answers described task completion without a measurable or clearly attributable outcome.",
      "next_action": "Retry two leadership answers and add one verified result to each."
    }
  ],
  "evidence_review_items": [
    {
      "status": "partially_supported",
      "message": "The migration is supported, but the selected evidence does not confirm three regional teams."
    }
  ],
  "contract_version": "coach_conversational_report_v1"
}
```

---

# Appendix F - Self-review checklist for the implementation PRs

Before claiming each PR complete, verify:

```text
[ ] No unresolved placeholder remains in a required contract path.
[ ] All new enum/string values are centralized and validated.
[ ] Every background finaliser has ownership fencing.
[ ] Every command is idempotent.
[ ] Every state transition is tested.
[ ] Legacy fixtures remain unchanged.
[ ] No transcript/evidence appears in logs or metric labels.
[ ] New UI uses named levels only.
[ ] Prohibited inference benchmark passes.
[ ] One Alembic head remains.
[ ] Verification commands and outputs are attached to the PR.
```
