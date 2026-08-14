---
title: Hatch Conversational AI Interview Coach Phase 1 Implementation Specification v1
document_type: implementation-spec
status: historical
implementation_status: partial
applies_to: main/latest
last_verified: 2026-07-24
supersedes: Hatch_Conversational_AI_Interview_Coach_Phase1_Spec_v1.md
superseded_by: Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v2.md
---

# Hatch Conversational AI Interview Coach — Phase 1 Implementation Specification v1.0

> Historical specification. Superseded by `Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v2.md`; do not implement from this version.

**Status:** Superseded
**Implementation order:** Must be completed before the Candidate Intelligence Platform & Interview Mentor phase
**Target repository:** Hatch
**Target branch:** current implementation branch selected by the repository owner
**Prepared:** 23 July 2026
**Specification type:** Repository-grounded Codex implementation contract
**Supersedes:** the earlier condensed `Hatch_Conversational_AI_Interview_Coach_Phase1_Spec_v1.md`

---

## 0. Document control and grounded baseline

### 0.1 Source baseline

This specification was prepared against the uploaded repository archive:

```text
hatch-main (1).zip
```

Archive SHA-256:

```text
95347f776a347395af4fa4052f6afaf10f3ad2f610c1e163c12309bca0e55744
```

The archive does not contain Git metadata. Therefore, the archive hash—not an inferred commit hash—is the authoritative baseline identifier for this specification.

### 0.2 Baseline verification performed

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

### 0.3 Baseline test execution note

A targeted backend test invocation was attempted against the unpacked archive. The local execution environment lacked `aiosqlite`, and test collection stopped before repository tests ran:

```text
ModuleNotFoundError: No module named 'aiosqlite'
```

This is an execution-environment dependency gap, not evidence of a repository test failure. Codex must run the verification commands in the project-supported environment after installing the backend dependencies.

### 0.5 Normative language

- **Must**, **must not**, **required** and acceptance/release gates are binding.
- A **recommended initial value** is the required Phase 1 default unless the working branch already contains an equivalent centralized setting that satisfies the same contract.
- A recommended filename may be adjusted to repository naming conventions, but the service boundary and ownership rule are binding.
- This document contains no unresolved product or architecture decision. Codex must not reinterpret an explicit contract as an optional suggestion.

### 0.4 Specification authority

Where this document conflicts with the earlier condensed Phase 1 draft, this document wins.

Where this document conflicts with legacy behaviour in the uploaded baseline, the rules are:

1. Existing legacy sessions and reports remain readable.
2. Existing legacy API callers remain functional unless this document explicitly introduces a compatibility wrapper.
3. New conversational sessions use the new contracts in this document.
4. New conversational behaviour must not silently reinterpret historical numeric data.
5. The completed Coach C1/C2/C3 correctness, benchmark, reconciliation and observability work remains authoritative and must be extended rather than bypassed.

---

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
rubric_contract_version = coach_conversational_rubric_v1
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

```text
behavioural
competency
leadership
role_specific_verbal
technical_verbal
commercial_verbal
domain_verbal
```

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

## 7. Versioned experience selection

## 7.1 Session experience field

Add to `interview_sessions`:

```text
experience_version VARCHAR(32) NOT NULL DEFAULT 'legacy_v1'
```

Allowed values in this migration:

```text
legacy_v1
conversational_v1
```

Backfill every existing row to:

```text
legacy_v1
```

## 7.2 API creation behaviour

Extend the session-create request with:

```json
{
  "experience_version": "conversational_v1"
}
```

Compatibility rule:

- omitted field from existing API clients -> `legacy_v1`;
- new conversational launcher -> explicitly sends `conversational_v1`;
- no server default silently changes existing third-party behaviour in the migration PR.

A later product release may make the frontend launcher default conversational after release gates pass.

## 7.3 Rendering branch

Frontend routing must branch on `experience_version`:

```text
legacy_v1 -> existing numeric components and legacy flow
conversational_v1 -> new state-driven conversational components
```

Do not make legacy `EvaluationCard` parse the new level contract.

---

## 8. Conversation state machine

## 8.1 Coarse session status remains

The existing `InterviewSession.status` remains the coarse lifecycle:

```text
setup
active
completed
abandoned
failed
```

The database constraint should be made explicit if it is not already enforced.

## 8.2 New conversation state

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
event_version INTEGER NOT NULL DEFAULT 0
```

For legacy rows:

```text
conversation_state = NULL
state_version = 0
```

For new conversational rows, allowed states are:

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
```

## 8.3 State meanings

### `planning`

Session setup job is building the immutable session plan and planned questions.

### `ready`

Plan and questions are persisted. The candidate has not started the live interview.

### `asking`

The active question is presented. No answer capture is currently active.

### `listening`

A current attempt exists and the candidate is typing or recording.

### `processing_answer`

The answer is finalised for processing and the attempt pipeline is active.

### `awaiting_next_action`

Evaluation is terminal. The candidate may accept, retry, request coaching, edit the transcript or end the session.

### `coaching`

On-demand answer review is being generated or displayed.

### `asking_follow_up`

A validated adaptive follow-up is being attached and prepared. This is a short-lived application state.

### `advancing`

The accepted attempt is committed and the application is selecting the next question. This is a short-lived application state.

### `paused`

The session is explicitly paused. `resume_state` stores the valid return state.

### `reporting`

Session completion is claimed and a conversational report is being created.

### `completed`

A terminal conversational report snapshot exists, including deterministic fallback if enrichment failed.

### `recoverable_error`

The session remains usable, but the candidate must retry, delete the current draft or resume from the last stable state.

## 8.4 State invariants

For every conversational session:

1. `status = setup` implies `conversation_state = planning`.
2. `status = active` implies one of `ready`, `asking`, `listening`, `processing_answer`, `awaiting_next_action`, `coaching`, `asking_follow_up`, `advancing`, `paused`, `recoverable_error`.
3. `status = completed` implies `conversation_state = completed`.
4. `conversation_state = listening` requires `active_question_id` and `active_recording_id`.
5. `conversation_state = processing_answer` requires an active recording with a pending processing job.
6. `conversation_state = awaiting_next_action` requires a terminal current evaluation version.
7. `conversation_state = asking` requires an active unanswered question.
8. `conversation_state = paused` requires non-null `resume_state`.
9. `conversation_state = reporting` requires `report_state = building` and matching `report_job_id`.
10. `conversation_state = completed` requires `report_state` in `completed` or `fallback`.

## 8.5 Legal transitions

| From | Command or internal event | To |
|---|---|---|
| planning | planning completed | ready |
| planning | planning failed recoverably | recoverable_error |
| ready | start | asking |
| asking | begin_answer | listening |
| asking | request_hint | asking |
| asking | skip_question | advancing |
| asking | pause | paused |
| listening | keep_speaking | listening |
| listening | request_hint | listening |
| listening | finish_answer | processing_answer |
| listening | pause | paused |
| listening | cancel_attempt | asking |
| processing_answer | processing completed | awaiting_next_action |
| processing_answer | processing failed recoverably | recoverable_error |
| awaiting_next_action | request_coaching | coaching |
| awaiting_next_action | retry_answer | asking |
| awaiting_next_action | edit_transcript | processing_answer |
| awaiting_next_action | accept_attempt | asking_follow_up, advancing or reporting |
| awaiting_next_action | end_session | reporting |
| coaching | accept_attempt | asking_follow_up, advancing or reporting |
| coaching | retry_answer | asking |
| coaching | return_to_review | awaiting_next_action |
| asking_follow_up | follow-up persisted | asking |
| advancing | next planned question selected | asking |
| advancing | no remaining questions | reporting |
| paused | resume | stored resume state |
| recoverable_error | retry_processing | processing_answer |
| recoverable_error | retry_answer | asking |
| recoverable_error | end_session | reporting |
| reporting | report finalised | completed |
| reporting | report fallback finalised | completed |

Any transition not listed is invalid.

## 8.6 Transient-state transaction rule

`asking_follow_up` and `advancing` should normally begin and complete within one backend transaction. They remain persisted states so that a crash can be reconciled deterministically.

## 8.7 State version

Every successful state-changing command or internal finalisation increments:

```text
InterviewSession.state_version
```

Read-only operations do not increment it.

Background finalisation must include the expected state version or a narrower ownership predicate defined later in this specification.

---

## 9. Command contract

## 9.1 Endpoint

Add:

```http
POST /api/coach/sessions/{session_id}/commands
```

## 9.2 Request schema

```json
{
  "command_id": "01J...",
  "command_type": "begin_answer",
  "expected_state_version": 7,
  "payload": {},
  "contract_version": "coach_conversation_command_v1"
}
```

## 9.3 Supported commands

```text
start
begin_answer
finish_answer
keep_speaking
pause
resume
cancel_attempt
retry_answer
retry_processing
request_hint
request_coaching
return_to_review
edit_transcript
accept_attempt
skip_question
end_session
delete_audio
delete_transcript
```

## 9.4 Command result persistence

Add `interview_command_results`:

```text
id VARCHAR(36) primary key
session_id VARCHAR(36) not null FK interview_sessions.id cascade
command_id VARCHAR(64) not null
command_type VARCHAR(64) not null
request_hash VARCHAR(128) not null
expected_state_version INTEGER not null
result_state VARCHAR(32) not null
result_json JSON nullable
created_at DATETIME not null
completed_at DATETIME nullable
```

Constraints and indexes:

```text
UNIQUE(session_id, command_id)
INDEX(session_id, created_at)
```

Idempotency rules:

1. Same `command_id` and same canonical request hash -> return original result.
2. Same `command_id` and different hash -> `idempotency_conflict`.
3. Persisted result is written in the same transaction as the state mutation.
4. Result JSON must not contain raw audio, secrets or unbounded transcript content.

## 9.5 Optimistic concurrency

If `expected_state_version != session.state_version`, return HTTP 409:

```json
{
  "error": {
    "code": "conversation_state_version_conflict",
    "message": "The interview changed since this view was loaded.",
    "current_state_version": 8,
    "current_state": "awaiting_next_action",
    "retryable": false
  }
}
```

The client must refresh `/live` rather than blindly retrying the command.

## 9.6 Command response

```json
{
  "command_id": "01J...",
  "result": "completed",
  "session_id": "...",
  "state": "listening",
  "state_version": 8,
  "active_question_id": "...",
  "active_attempt_id": "...",
  "async_job_id": null,
  "allowed_commands": ["finish_answer", "keep_speaking", "pause", "request_hint"],
  "contract_version": "coach_conversation_command_result_v1"
}
```

## 9.7 Command result vocabulary

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
```

## 9.8 Exact command semantics

### `start`

Preconditions:

```text
state = ready
```

Effects:

- set `status = active`;
- set `started_at` if absent;
- select the first planned question;
- set `active_question_id` and `active_root_question_id`;
- set state to `asking`;
- append a session event.

### `begin_answer`

Preconditions:

```text
state = asking
active question exists
question is not skipped or accepted
```

Payload:

```json
{
  "recording_type": "audio",
  "client_attempt_id": "optional-client-uuid"
}
```

Allowed recording types for conversational sessions:

```text
audio
text
```

`video` is rejected for `conversational_v1`.

Effects:

- reserve a `SessionRecording` attempt;
- assign deterministic attempt number;
- set `active_recording_id`;
- set state to `listening`;
- return attempt identifier and media limits.

### `finish_answer`

Preconditions:

```text
state = listening
active attempt belongs to active question and session
```

For typed attempts, payload includes the transcript.

For audio attempts, final audio upload must already be persisted and hash-verified.

Effects:

- create transcript version for typed input, or begin transcription for audio;
- create attempt-processing job;
- set evaluation state pending;
- set state to `processing_answer`;
- return async job identifier.

### `keep_speaking`

Preconditions:

```text
state = listening
```

Effects:

- record a silence-warning acknowledgement event;
- clear the current browser silence prompt through the response projection;
- remain listening;
- increment state version because the command affects the current capture lease and UI projection.

### `pause`

Allowed from:

```text
asking
listening
awaiting_next_action
coaching
recoverable_error
```

Effects:

- store current state in `resume_state`;
- set state to `paused`;
- set `paused_at`;
- preserve the draft attempt.

If pausing during browser audio capture, the frontend must pause the `MediaRecorder`; it must not implicitly finish the answer.

### `resume`

Preconditions:

```text
state = paused
resume_state is valid
```

Effects:

- restore `resume_state`;
- clear `resume_state` and `paused_at`.

If the browser cannot restore a paused recorder after refresh, it must offer:

```text
Discard draft and retry
Upload the already captured draft, if available
```

It must not pretend recording resumed.

### `cancel_attempt`

Preconditions:

```text
state = listening
active attempt has not entered processing
```

Effects:

- remove temporary media;
- mark attempt `cancelled` through the extended attempt state;
- clear active attempt;
- return to `asking`.

### `retry_answer`

Allowed from:

```text
awaiting_next_action
coaching
recoverable_error
```

Effects:

- preserve prior attempts and evaluations;
- do not accept the current attempt;
- clear `active_recording_id`;
- return to `asking` for the same question.

### `retry_processing`

Preconditions:

```text
state = recoverable_error
active attempt exists
failure is classified retryable
retry budget remains
```

Effects:

- create a new processing job;
- update attempt ownership fields;
- return to `processing_answer`.

### `request_hint`

Allowed from:

```text
asking
listening
```

The hint must use one permitted type:

```text
star_structure
competency_reminder
experience_category
clarify_question
```

Forbidden hint output:

- a complete model answer;
- a fabricated personal example;
- an unsupported achievement;
- the hidden evaluation rubric;
- a Candidate Intelligence weakness.

The hint event is retained and included in attempt metadata, but does not automatically reduce the rubric level.

### `request_coaching`

Preconditions:

```text
state = awaiting_next_action
current evaluation is terminal and valid
```

Effects:

- move to `coaching`;
- return persisted coaching if already generated;
- otherwise create a bounded coaching-enrichment job;
- coaching failure must return deterministic evidence-backed review content.

### `return_to_review`

Preconditions:

```text
state = coaching
```

Effects:

- return to `awaiting_next_action`.

### `edit_transcript`

Preconditions:

```text
state in awaiting_next_action or coaching
current attempt recording_type in audio or text
```

Payload:

```json
{
  "transcript": "corrected transcript",
  "edit_reason": "transcription_error"
}
```

Effects:

- create a new immutable transcript version;
- preserve delivery metrics;
- create a new evaluation version and processing job;
- clear any current follow-up proposal derived from the previous transcript version;
- set state to `processing_answer`;
- do not overwrite prior transcript or evaluation versions.

### `accept_attempt`

Preconditions:

```text
state in awaiting_next_action or coaching
current evaluation is completed
attempt not deleted
```

Effects:

- set the question’s explicit accepted recording;
- mark the accepted timestamp on the attempt;
- run deterministic follow-up policy;
- transition to a validated follow-up, next planned question or reporting.

Acceptance is a candidate workflow choice. It is not a claim that the answer is high quality.

### `skip_question`

Preconditions:

```text
state = asking
```

Effects:

- persist a skipped attempt or explicit question state using the existing terminal vocabulary;
- never create a score;
- advance to the next planned question or reporting.

### `end_session`

Allowed from:

```text
asking
awaiting_next_action
coaching
recoverable_error
```

If a completed current attempt is unaccepted, payload must explicitly choose:

```text
accept_current_attempt
exclude_current_attempt
```

Effects:

- claim report generation using the existing activity-version pattern plus conversational state fencing;
- set state to `reporting`.

### `delete_audio`

Effects are defined in the privacy section. It never deletes transcript or evaluation by implication.

### `delete_transcript`

Effects are defined in the privacy section. It invalidates transcript-derived evaluation safely.

---

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
  "session_id": "...",
  "experience_version": "conversational_v1",
  "status": "active",
  "conversation_state": "awaiting_next_action",
  "state_version": 12,
  "active_question": {},
  "root_question": {},
  "active_attempt": {},
  "processing": {
    "job_id": null,
    "stage": null,
    "state": "completed",
    "retryable": false
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

Constraints:

```text
UNIQUE(session_id, sequence_number)
INDEX(session_id, created_at)
INDEX(session_id, event_type)
```

## 11.2 Event sequence allocation

Allocate sequence numbers transactionally per session.

Use either:

- an `event_version` integer on `InterviewSession`; or
- `state_version` when every event corresponds to a state mutation plus an additional deterministic suffix is not needed.

Recommended implementation:

```text
add event_version INTEGER NOT NULL DEFAULT 0
increment it transactionally for every event
```

Do not use `SELECT MAX(sequence_number) + 1` without an ownership or update lock because SQLite concurrent writers may race.

## 11.3 Required event types

```text
session_plan_started
session_plan_completed
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
attempt_processing_completed
attempt_processing_failed
transcript_edited
coaching_requested
coaching_presented
attempt_retried
attempt_accepted
question_skipped
follow_up_created
follow_up_presented
question_advanced
session_paused
session_resumed
report_claimed
report_completed
report_fallback_completed
audio_deleted
transcript_deleted
session_abandoned
```

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

## 12. Session planning contract

## 12.1 Planning objective

Every conversational session must persist a reproducible `session_plan_json` before becoming ready.

Add to `interview_sessions`:

```text
session_plan_json JSON NULL
session_plan_contract_version VARCHAR(64) NULL
evaluation_contract_version VARCHAR(64) NULL
report_contract_version VARCHAR(64) NULL
compatibility_key VARCHAR(256) NULL
retention_policy_json JSON NULL
```

## 12.2 Session plan schema

```json
{
  "plan_id": "...",
  "role": {
    "title": "Senior Solution Architect",
    "role_family": "solution_architecture",
    "role_level": "senior",
    "industry": "optional"
  },
  "interview": {
    "type": "behavioural",
    "difficulty": "senior",
    "duration_minutes": 30,
    "planned_question_count": 6,
    "focus_areas": ["stakeholder_management", "architecture_leadership"],
    "locale": "en-GB"
  },
  "evidence": {
    "application_id": "optional",
    "job_posting_id": "optional",
    "master_cv_version": "hash-or-version",
    "generated_cv_asset_id": "optional-approved-asset",
    "question_bank_record_ids": [],
    "company_research_id": "optional",
    "evidence_ledger_version": "writing_evidence_v1"
  },
  "contracts": {
    "question_generation": "coach_question_generation_v2",
    "evaluation": "coach_conversational_rubric_v1",
    "evidence_grounding": "coach_evidence_grounding_v1",
    "follow_up": "coach_follow_up_v1",
    "report": "coach_conversational_report_v1"
  },
  "retention": {
    "audio": "delete_after_processing",
    "transcript": "retain"
  },
  "compatibility": {
    "key": "...",
    "version": "coach_progress_compatibility_v1"
  },
  "created_at": "..."
}
```

## 12.3 Evidence-source selection

For an application-linked session, use sources in this priority order:

1. Approved application CV asset, if a `GeneratedDocument` or generated asset is explicitly approved.
2. Current application CV source, if no approved generated asset exists and it can be read deterministically.
3. Confirmed Master CV JSON.
4. Question Bank entries with confidence `reviewed` or `final`.
5. Job posting and application requirements.
6. Cached company research that is not expired.

Draft Question Bank entries may be used only if the candidate explicitly enables them for practice. They must be labelled draft evidence.

## 12.4 Evidence ledger

Reuse stable evidence-ID patterns from `writing_contracts.py`.

Create a session-scoped evidence package containing bounded records:

```text
evidence_id
source_type
source_record_id
source_record_version
source_path
normalized_text
approval_state
content_hash
```

The session plan stores identifiers and source hashes, not complete duplicated documents.

A bounded evidence snapshot may be persisted with the session when required for report reproducibility. It must contain only the approved evidence records selected for this session.

## 12.5 Compatibility key

Generate a deterministic compatibility key from:

```text
role_family
role_level
interview_type
difficulty
evaluation_contract_version
locale
```

Phase 1 uses exact compatibility for longitudinal comparisons.

Do not compare sessions if any component differs, except that missing industry does not affect the key.

## 12.6 Planning validation

A plan is valid only when:

- role title is non-empty;
- interview type is supported;
- duration is between 10 and 90 minutes;
- planned question count is between 3 and 12;
- question count fits configured duration rules;
- every focus area maps to a known Coach competency;
- evidence records have stable IDs and hashes;
- contract versions are supported;
- retention policy is valid;
- no prohibited inference dimension is present;
- all planned questions are persisted before state becomes `ready`.

## 12.7 Question-count defaults

Recommended deterministic defaults:

| Duration | Planned questions |
|---:|---:|
| 10–15 minutes | 3 |
| 16–25 minutes | 4 |
| 26–35 minutes | 6 |
| 36–50 minutes | 8 |
| 51–70 minutes | 10 |
| 71–90 minutes | 12 |

Candidate-selected count wins if valid.

Adaptive follow-ups do not count toward planned-question count.

## 12.8 Standard interviewer contract

Phase 1 uses one fixed behaviour contract:

```text
persona_id = standard_professional_v1
```

It controls only phrasing and transitions. It does not change rubric or follow-up limits.

Existing `interviewer_persona` config remains readable for legacy sessions but is not used to introduce Phase 2 persona behaviour.

---

## 13. Question model extensions

Add to `session_questions`:

```text
question_kind VARCHAR(32) NOT NULL DEFAULT 'planned'
root_question_id VARCHAR(36) NULL FK session_questions.id SET NULL
parent_question_id VARCHAR(36) NULL FK session_questions.id SET NULL
follow_up_depth INTEGER NOT NULL DEFAULT 0
follow_up_reason VARCHAR(64) NULL
question_state VARCHAR(32) NOT NULL DEFAULT 'pending'
accepted_recording_id VARCHAR(36) NULL FK session_recordings.id SET NULL
question_contract_version VARCHAR(64) NULL
asked_sequence INTEGER NULL
```

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
5. `accepted_recording_id`, when present, must belong to the same session and question. Enforce in repository service; add database constraints where feasible.
6. `asked_sequence` is unique within a session when non-null.

SQLite cannot express all cross-table ownership constraints. The repository must enforce them transactionally and tests must cover them.

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
current_transcript_version_id VARCHAR(36) NULL FK interview_transcript_versions.id SET NULL
current_evaluation_version_id VARCHAR(36) NULL FK interview_attempt_evaluations.id SET NULL
accepted_at DATETIME NULL
submitted_at DATETIME NULL
processing_started_at DATETIME NULL
processing_completed_at DATETIME NULL
audio_retention_state VARCHAR(32) NULL
audio_deleted_at DATETIME NULL
audio_content_hash VARCHAR(128) NULL
client_attempt_id VARCHAR(64) NULL
hint_count INTEGER NOT NULL DEFAULT 0
self_assessment_json JSON NULL
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

Legacy rows may retain null values for newly conversational fields.

## 14.2 Attempt numbering

Within each question:

```text
attempt_number = 1, 2, 3, ...
```

Allocate through an atomic repository operation.

Add unique index:

```text
UNIQUE(question_id, attempt_number)
```

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

1. Validate question/session ownership.
2. Validate completed current evaluation.
3. Clear `accepted_at` from any previously accepted recording for the same question.
4. Set `accepted_recording_id`.
5. Set current attempt `accepted_at`.
6. Increment session `activity_version` and `state_version`.
7. Append an event.

A retry never becomes accepted automatically.

## 14.4 Legacy canonical-attempt behaviour

`coach_aggregation.resolve_canonical_attempts()` remains unchanged for `legacy_v1`.

Create a separate conversational resolver:

```text
resolve_conversational_accepted_attempts()
```

It must use explicit accepted recordings only.

Do not modify legacy report results by changing the existing canonical resolver.

---

## 15. Transcript versioning

## 15.1 New table

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
created_at DATETIME not null
```

Constraints:

```text
UNIQUE(recording_id, version_number)
```

Allowed source:

```text
transcription
candidate_text
candidate_edit
recovered_transcription
```

Allowed creator:

```text
system
candidate
```

## 15.2 Current transcript compatibility field

Keep `SessionRecording.transcript` as a denormalized current transcript for compatibility.

Whenever a new transcript version becomes current, update in the same transaction:

```text
current_transcript_version_id
transcript
attempt_version += 1
```

## 15.3 Transcript edit rules

- Preserve all previous versions.
- Normalize line endings but do not silently rewrite wording.
- Compute a content hash over canonical UTF-8 text.
- Reject empty text unless the candidate chooses to delete the transcript.
- Enforce maximum configured character count.
- Do not recalculate speech metrics from edited text.
- Mark delivery metrics as based on original audio.
- Re-run content evaluation, evidence grounding and follow-up proposal.
- Store the evaluation against the new transcript-version ID.

---

## 16. Evaluation versioning

## 16.1 New table

Add `interview_attempt_evaluations`:

```text
id VARCHAR(36) primary key
recording_id VARCHAR(36) not null FK session_recordings.id cascade
transcript_version_id VARCHAR(36) not null FK interview_transcript_versions.id cascade
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

1. Verify job ownership and attempt version.
2. Complete the evaluation-version row.
3. Set prior current evaluation version to `superseded`, if applicable.
4. Set `current_evaluation_version_id`.
5. Mirror current JSON and state to `SessionRecording`.
6. Increment attempt and session versions.
7. Move conversation state to `awaiting_next_action`.
8. Append an event.

---

## 17. Attempt processing stages

## 17.1 New table

Add `interview_attempt_stages`:

```text
id VARCHAR(36) primary key
recording_id VARCHAR(36) not null FK session_recordings.id cascade
evaluation_version_id VARCHAR(36) nullable FK interview_attempt_evaluations.id cascade
stage_name VARCHAR(64) not null
stage_state VARCHAR(32) not null
attempt_count INTEGER not null default 0
repair_count INTEGER not null default 0
job_id VARCHAR(36) nullable
claim_token VARCHAR(64) nullable
expected_attempt_version INTEGER nullable
started_at DATETIME nullable
completed_at DATETIME nullable
last_error_code VARCHAR(128) nullable
diagnostics_json JSON nullable
```

Unique constraint:

```text
UNIQUE(recording_id, evaluation_version_id, stage_name)
```

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
not_applicable
unavailable
failed_retryable
failed_terminal
```

## 17.3 Why a stage table is required

The baseline has one async-job identity at the attempt level. Phase 1 adds transcript edits, separately retryable transcription, grounding and cleanup. A bounded stage table provides:

- visible processing state;
- targeted retries;
- stage diagnostics;
- exact ownership fencing;
- no need to overload a large unstructured JSON field.

It must remain a fixed Coach-specific table, not a generic workflow engine.

---

## 18. Database migration contract

## 18.1 Migration file

Create one additive migration descending from:

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
question_state = answered if a valid legacy completed recording exists
question_state = skipped if latest terminal recording is skipped
question_state = pending otherwise
```

Do not set `accepted_recording_id` for legacy sessions.

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

## 19.1 Endpoint

Add:

```http
PUT /api/coach/sessions/{session_id}/attempts/{attempt_id}/audio
```

A single final blob is sufficient for Phase 1. Chunked streaming and WebRTC are out of scope.

## 19.2 Preconditions

```text
experience_version = conversational_v1
conversation_state in listening or paused
attempt id = active_recording_id
attempt_state = draft
recording_type = audio
```

## 19.3 Request requirements

Use multipart form data with:

```text
file
upload_id
content_hash
client_duration_ms
mime_type
```

Allowed MIME types should extend the current upload allowlist only where the existing transcription provider supports them.

Recommended initial allowlist:

```text
audio/webm
audio/ogg
audio/wav
audio/mpeg
audio/mp4
```

The server must inspect both MIME type and file signature where practical. The filename alone is not authoritative.

Maximum size remains bounded by configuration. Reuse the current 50 MB boundary unless repo tests or provider constraints require a lower value.

## 19.4 Idempotency

Add unique upload identity at the attempt level:

```text
attempt_id + upload_id
```

Rules:

- same upload ID and same hash -> return original result;
- same upload ID and different hash -> conflict;
- an attempt cannot accept a second different final blob after processing starts;
- temporary partial files are cleaned after failure.

## 19.5 Persistence

Store media under the existing Coach data directory pattern, not in the database.

Recommended path:

```text
<data_dir>/recordings/<session_id>/<attempt_id>/<content_hash>.<ext>
```

Use an atomic temporary-file rename after validation.

After persistence:

```text
audio_uri = validated path
audio_content_hash = provided/verified hash
attempt_state = uploaded
```

Do not start evaluation until `finish_answer` succeeds.

## 19.6 Upload response

```json
{
  "attempt_id": "...",
  "upload_id": "...",
  "state": "uploaded",
  "content_hash": "sha256:...",
  "size_bytes": 123456,
  "contract_version": "coach_attempt_audio_upload_v1"
}
```

---

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
Transcript version created
    ↓
Speech metrics generated, audio only
    ↓
Content rubric proposed and validated
    ↓
Evidence claims extracted and grounded
    ↓
Follow-up proposal generated and validated
    ↓
Evaluation version finalised
    ↓
Conversation state becomes awaiting_next_action
    ↓
Audio cleanup, according to retention policy
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
expected_attempt_version
processing_contract_version
```

Do not pass ORM objects or live database sessions into the background task.

Every background task opens and closes its own `AsyncSessionLocal` scope, following the existing Coach queue and report pattern.

## 21.3 Stage dependency graph

For audio:

```text
audio_persist completed
    ↓
transcription
    ├── speech_analysis
    └── content_evaluation
           ↓
       evidence_grounding
           ↓
       follow_up_decision
```

Speech analysis may run after transcription or directly from audio, depending on current `SpeechAnalyser` requirements, but both branches must complete before evaluation finalisation if delivery is being assessed.

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

## 21.4 Stage timeouts

Add settings with current timeout conventions:

```text
HATCH_COACH_TIMEOUT_TRANSCRIPTION_SECONDS = 300
HATCH_COACH_TIMEOUT_SPEECH_ANALYSIS_SECONDS = 120
HATCH_COACH_TIMEOUT_CONVERSATIONAL_EVALUATION_SECONDS = 300
HATCH_COACH_TIMEOUT_EVIDENCE_GROUNDING_SECONDS = 180
HATCH_COACH_TIMEOUT_FOLLOWUP_DECISION_SECONDS = 120
HATCH_COACH_TIMEOUT_COACHING_ENRICHMENT_SECONDS = 180
HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_SECONDS = 60
HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS = 900
```

Use Pydantic bounds consistent with existing configuration fields.

Do not silently reuse a stage timeout for a semantically different stage.

## 21.5 Retry budgets

Recommended defaults:

| Stage | Retry budget | Repair budget |
|---|---:|---:|
| audio persistence | 1 | 0 |
| transcription | 2 | 0 |
| speech analysis | 1 | 0 |
| content evaluation | 2 | 1 |
| evidence grounding | 2 | 1 |
| follow-up decision | 1 | 1 |
| coaching enrichment | 1 | 1 |
| audio cleanup | 3 | 0 |

Retry counts are configurable but must remain bounded.

## 21.6 Model route

Use the existing provider and orchestration boundary.

Request capabilities rather than hard-coding a provider in the new services:

```text
structured_answer_evaluation
structured_evidence_grounding
structured_follow_up_proposal
coach_feedback_enrichment
speech_transcription
```

If the current router cannot express these names, implement a Coach-local capability mapping without changing provider contracts more broadly than required.

## 21.7 Deterministic fallback

If content evaluation cannot produce a valid contract after retries:

- preserve transcript and speech metrics;
- set evaluation state `unavailable`;
- return a neutral explanation;
- allow retry;
- do not produce an invented level;
- do not create a follow-up.

If evidence grounding fails but content evaluation succeeds:

- complete content dimensions;
- set evidence consistency `not_assessed`;
- set grounding state unavailable;
- disable evidence-based claims in coaching;
- allow the session to continue.

If follow-up generation fails:

- continue without an adaptive follow-up;
- never block advancing.

## 21.8 Pipeline finalisation fence

Final attempt finalisation must require all of:

```text
SessionRecording.id = recording_id
SessionRecording.async_job_id = job_id
SessionRecording.evaluation_state = pending
SessionRecording.attempt_version = expected_attempt_version
InterviewSession.id = session_id
InterviewSession.conversation_state = processing_answer
InterviewSession.active_recording_id = recording_id
InterviewSession.state_version = expected_session_state_version
InterviewAttemptEvaluation.id = evaluation_version_id
InterviewAttemptEvaluation.state = pending
```

If any predicate fails:

```text
result = stale_claim
no attempt/evaluation/session mutation
```

A late worker may still record content-free diagnostics against its generic async job, but it must not overwrite current user state.

## 21.9 Stage finalisation fence

Each stage update must require:

```text
stage job_id matches
claim_token matches
expected_attempt_version matches
stage_state in pending or running
```

## 21.10 Reconciliation

Extend `coach_reconciliation.py` to reconcile:

- stale `processing_answer` sessions;
- stale attempt jobs;
- stale stage claims;
- stale `asking_follow_up` transitions;
- stale `advancing` transitions;
- stale `reporting` state;
- pending audio cleanup.

Reconciliation rules must be idempotent.

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

## 22.3 Delivery assessment contract

Delivery is based only on observable metrics and receives one named level or `not_assessed`.

Create a versioned deterministic policy:

```text
coach_delivery_policy_v1
```

The exact thresholds must be configuration constants with tests. Recommended initial policy:

### Eligibility

Delivery is `not_assessed` when:

- input is typed;
- transcript has fewer than 40 words;
- audio duration is under 20 seconds;
- required timestamp data is unavailable;
- speech analysis failed.

### Material issue flags

```text
pace_fast: WPM > 190
pace_slow: WPM < 90
fillers_high: filler_rate_per_minute > 6
fillers_moderate: filler_rate_per_minute > 3
long_pauses_high: long_pause_count > max(3, duration_minutes * 2)
hedging_high: hedging_count > max(4, word_count / 40)
```

Thresholds must be reviewed with benchmark examples before stable release. They are coaching heuristics, not clinical or personality measures.

### Level derivation

```text
strong
- eligible
- no material issue
- at most one moderate issue

interview_ready
- eligible
- no more than one material issue

 developing
- eligible
- two material issues, or one severe repeated issue

needs_work
- eligible
- three or more material issues

not_assessed
- eligibility not met
```

The response must list the observed metrics that caused the level.

## 22.4 Candidate self-assessment

After an attempt, the candidate may optionally record:

```json
{
  "comfort_level": "low|medium|high",
  "felt_complete": true,
  "note": "optional bounded text"
}
```

Self-assessment:

- is displayed separately;
- does not set delivery level;
- does not prove confidence;
- does not affect evidence grounding;
- may be included in the final report as candidate reflection.

---

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
      "excerpt": "..."
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

- at least five assessed content dimensions are `strong`;
- every assessed content dimension is at least `interview_ready`;
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

Evidence grounding checks material factual claims in the answer against the session-scoped approved evidence package.

It is not a fact-check of the world and not a truth detector.

## 24.3 Claim schema

```json
{
  "claim_id": "claim_1",
  "claim_text": "I led the migration across three regional teams.",
  "transcript_start": 102,
  "transcript_end": 158,
  "claim_type": "experience_scope",
  "materiality": "material"
}
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

The material claim is directly supported by one or more approved evidence records without material contradiction.

### `partially_supported`

The core experience is supported, but a material detail such as metric, scope, ownership, date or technology is absent or only partially matched.

### `not_found`

No matching approved evidence was found.

This means only:

> Hatch could not find this claim in the selected evidence sources.

It must not be presented as false.

### `conflicting`

An authoritative selected source contains an objective contradiction.

Examples:

- answer says three regions; approved evidence says one region;
- answer says project completed in four weeks; approved evidence says four months;
- answer claims lead ownership; approved source explicitly identifies a supporting role.

Use sparingly. Ambiguity is not conflict.

### `not_verifiable`

The claim is subjective, hypothetical, future-oriented, too vague or outside selected evidence.

## 24.5 Evidence source trust

For Phase 1, use deterministic source priority:

```text
approved application CV asset
confirmed Master CV
Question Bank final
Question Bank reviewed
application/job requirements, for role expectations only
candidate-enabled Question Bank draft
```

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
      "evidence_ids": ["ev_..."],
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

Derive deterministically:

```text
strong
- all material verifiable claims supported

interview_ready
- no conflicts
- at most one partially supported material claim
- no not-found material claim

developing
- no conflicts
- multiple partial claims or one not-found material claim

needs_work
- at least one material conflicting claim
- or multiple not-found material claims central to the answer

not_assessed
- no material verifiable claim
- grounding unavailable
- evidence package absent by candidate choice
```

The UI label should still explain exact statuses. Do not reduce everything to the level.

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
  "target_competency": "impact",
  "duplicate_key": "root-question:impact:result"
}
```

## 25.5 Admission policy

The application admits a proposal only when:

1. `should_ask` is true.
2. Reason is allowed.
3. Transcript evidence matches current transcript.
4. Question is non-empty and bounded.
5. Root question follow-up count is below two.
6. No existing question has the same normalized duplicate key.
7. The proposal does not reveal hidden scoring or profiling.
8. The current attempt is accepted.
9. The root question has not been skipped.
10. The session has not been ended.

## 25.6 Follow-up creation

Create a new `SessionQuestion`:

```text
question_kind = adaptive_follow_up
root_question_id = planned root
parent_question_id = current question
follow_up_depth = parent depth + 1
follow_up_reason = admitted reason
question_state = pending
```

Assign the next `asked_sequence` only when presented.

## 25.7 Follow-up budget

Count all persisted adaptive follow-up questions under the root, regardless of whether answered or skipped.

This prevents retry or deletion from reopening the budget.

## 25.8 Sequence return

After the second follow-up, or when no valid proposal exists:

- advance to the next planned question;
- do not continue a model-created chain.

## 25.9 Deterministic fallback

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
hint event with type
```

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
- candidate self-assessment;
- retention state.

Unaccepted attempts remain available in session history but do not determine final rubric levels.

## 27.4 Root-bundle aggregation

A planned root question and its accepted follow-ups form one bundle.

Follow-up answers must not receive equal independent weight as planned root questions.

For each content dimension:

1. Start with the accepted root-attempt level.
2. A follow-up may raise that bundle dimension by at most one level when it directly addresses the same gap.
3. A follow-up may reveal a lower level only when the follow-up is itself the primary evidence for the targeted competency.
4. Cap at `strong`.
5. Store an explanation of the adjustment.

If the root question is skipped, follow-ups cannot exist.

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

The Phase 1 report may provide one named session outcome:

```text
needs_work
developing
interview_ready
strong
not_assessed
```

Derive using the session dimensions:

Critical report dimensions:

```text
relevance
structure
specificity
role_depth
```

Rules mirror answer-level gates but operate on session dimension levels.

Evidence consistency and delivery remain visible separate dimensions.

## 27.7 Report schema

```json
{
  "session_id": "...",
  "report_state": "completed",
  "session_level": "interview_ready",
  "dimensions": {},
  "strengths": [],
  "improvement_priorities": [],
  "evidence_review_items": [],
  "question_summaries": [],
  "practice_suggestions": [],
  "candidate_reflection": {},
  "retention_summary": {},
  "compatibility_key": "...",
  "diagnostics": {},
  "contract_version": "coach_conversational_report_v1"
}
```

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

Reuse existing:

```text
report_job_id
report_started_at
report_state
activity_version
report_json
```

Conversational report finalisation must require:

```text
matching report_job_id
report_state = building
claimed activity_version matches
conversation_state = reporting
state_version matches expected reporting claim version
```

A late report worker cannot overwrite a newer activity version or rebuilt report.

## 27.12 Report retrieval

`GET /sessions/{id}/report` remains a read.

It dispatches response schema by report contract.

It may reconcile stale report state but must not initiate a new report unless the existing contract already allows an explicit recovery operation. Prefer a separate retry command for failed conversational reports.

---

## 28. Longitudinal progress

## 28.1 Compatibility

Compare conversational sessions only when compatibility keys match exactly.

Legacy sessions are excluded from conversational progress unless shown in a separate legacy history section.

## 28.2 Endpoint

Add:

```http
GET /api/coach/conversational-progress
```

Query:

```text
application_id optional
compatibility_key optional
role_family optional
role_level optional
interview_type optional
```

At least one context selector is required.

## 28.3 Progress response

```json
{
  "context": {},
  "sessions": [],
  "current_levels": {},
  "previous_levels": {},
  "trends": {},
  "strongest_areas": [],
  "priority_areas": [],
  "evidence_review_items": [],
  "contract_version": "coach_conversational_progress_v1"
}
```

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

Require at least two completed compatible sessions.

For each dimension:

- compare the most recent two valid session levels;
- optionally show three-session context;
- one-level increase -> improving;
- same -> stable;
- one-level decrease -> declining;
- non-monotonic over three sessions -> mixed;
- missing assessment -> not enough evidence.

Do not say “confidence improved 23%” or equivalent.

## 28.6 Deleted sessions

Deleted sessions and sessions whose report was invalidated are excluded from progress.

Audio deletion alone does not remove a session from progress.

---

## 29. Privacy, retention and deletion

## 29.1 Session retention policy

Persist:

```json
{
  "audio": "delete_after_processing",
  "transcript": "retain"
}
```

Allowed audio values:

```text
delete_after_processing
retain_until_deleted
```

Phase 1 does not support arbitrary duration policies in the UI.

## 29.2 Audio retention state

Allowed `audio_retention_state`:

```text
not_applicable
temporary
retained
delete_pending
deleted
delete_failed
```

## 29.3 Delete-after-processing trigger

For successful audio processing, audio becomes eligible for deletion once:

- transcription version is committed;
- speech metrics are committed or terminal unavailable;
- file ownership/hash is verified;
- attempt still references the same audio path and hash.

Content evaluation and evidence grounding do not require the audio file and must not delay deletion.

## 29.4 Failed transcription grace period

If transcription fails and retry is possible:

```text
retain temporary audio for HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS
```

Recommended default:

```text
24 hours
```

The candidate may delete immediately.

A startup cleanup job deletes expired failed-processing audio and updates state.

## 29.5 Cleanup fencing

Audio cleanup must require:

```text
attempt audio_uri matches expected path
attempt audio_content_hash matches expected hash
audio_retention_state in temporary or delete_pending
policy remains delete_after_processing
```

A stale cleanup worker must not delete a replacement retained file.

## 29.6 Delete audio command

`delete_audio`:

- removes the file;
- clears `audio_uri`;
- sets state `deleted` and timestamp;
- keeps transcript, speech metrics, evaluation and report;
- appends content-free audit event;
- is idempotent.

If deletion fails:

- set `delete_failed`;
- expose retry;
- do not claim deletion succeeded.

## 29.7 Delete transcript command during active session

Deleting the current attempt transcript:

1. Deletes or redacts all transcript versions for the attempt.
2. Deletes transcript-derived evidence excerpts and evaluation versions.
3. Clears current evaluation and transcript compatibility fields.
4. Clears accepted recording if it points to this attempt.
5. Marks attempt `deleted`.
6. Deletes audio too unless the candidate explicitly retains it for re-transcription; default is delete both to avoid orphaned personal data.
7. Returns the session to `asking` for the same question when active.
8. Increments activity and state versions.

Store only a non-content event that deletion occurred.

## 29.8 Delete transcript after session completion

For completed conversational sessions:

1. Hide the report from normal reads immediately by setting `report_state = building` or a dedicated invalidated state. Because current report constraint lacks `invalidated`, recommended approach is add `invalidated` to allowed report states.
2. Delete transcript and transcript-derived evaluation content.
3. Clear affected accepted attempt.
4. Increment activity version.
5. Rebuild the report from remaining accepted attempts.
6. If no evaluable attempts remain, publish a completed report with `session_level = not_assessed` and deletion explanation.
7. Exclude the session from progress while rebuilding.

Add report state:

```text
invalidated
```

Update existing report-state constraint safely.

## 29.9 Delete session

For conversational sessions, provide an explicit hard-delete command or endpoint with confirmation.

Delete:

- media files;
- transcript versions;
- evaluation versions;
- stage records;
- events;
- command results;
- questions;
- recordings;
- report snapshot;
- session plan snapshot;
- session.

The current DELETE endpoint continues to mean **abandon**, preserving compatibility.

Add a separate command endpoint:

```http
POST /api/coach/sessions/{session_id}/deletion-commands
```

Request:

```json
{
  "command_id": "01J...",
  "scope": "session",
  "delete_mode": "hard_delete",
  "confirmation": "DELETE",
  "contract_version": "coach_session_deletion_v1"
}
```

The implementation must clearly distinguish abandonment from deletion. The hard-delete endpoint is available only for conversational sessions in Phase 1; legacy hard deletion remains outside this change.

## 29.10 Cloud disclosure

Before the session starts, disclose:

- configured transcription provider;
- configured evaluation provider;
- whether provider is local or cloud;
- categories sent: audio, transcript, job description, approved evidence excerpts;
- retention choice;
- local fallback availability.

Do not expose API keys or internal routing details.

## 29.11 Logs

Never log:

- transcript text;
- evidence excerpts;
- audio paths containing user-controlled names;
- CV text;
- prompt bodies;
- model response bodies.

## 29.12 Export

Add:

```http
POST /api/coach/sessions/{session_id}/exports
```

Required Phase 1 formats:

```text
json
markdown
```

A browser print view must also be provided so the candidate can use the browser's native **Print to PDF** capability without introducing a new server PDF converter:

```http
GET /coach/report/{session_id}/print
```

Request:

```json
{
  "command_id": "01J...",
  "format": "markdown",
  "include_transcript": false,
  "include_evidence_details": false,
  "include_attempt_history": false,
  "include_candidate_reflection": true,
  "contract_version": "coach_report_export_v1"
}
```

Export generation uses the persisted report and current permitted session content; it must not re-evaluate the interview.

Candidate-selectable options:

```text
include transcript
include evidence details
include attempt history
include candidate reflection
```

Raw audio is never embedded or linked in an export.

Exports must label evidence statuses as Hatch source matching, not independent verification.

If an included transcript or evidence item is deleted before download, regenerate the export or reject it as stale. Do not serve an old export containing deleted content.

Server-side binary PDF generation is explicitly deferred. The repository's existing LibreOffice-gated PDF service is designed for generated DOCX application documents and must not be repurposed for Coach reports in Phase 1.

---

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
hatch.coach.state_version
hatch.coach.command_type
hatch.coach.command_result
hatch.coach.recording_type
hatch.coach.attempt_kind
hatch.coach.attempt_number
hatch.coach.stage
hatch.coach.stage_state
hatch.coach.rubric_contract_version
hatch.coach.report_contract_version
hatch.coach.follow_up_reason
hatch.coach.follow_up_depth
hatch.coach.retention_policy
hatch.coach.retention_state
hatch.coach.evidence_status
hatch.coach.compatibility_version
```

Do not use session IDs, question IDs, transcripts or evidence strings as metric labels.

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

## 31.7 Diagnostics

Extend stable gate codes. Recommended namespace:

```text
coach_conversation_invalid_state
coach_conversation_version_conflict
coach_command_idempotency_conflict
coach_attempt_upload_missing
coach_attempt_upload_hash_mismatch
coach_attempt_stale_claim
coach_transcript_schema_invalid
coach_evaluation_evidence_span_invalid
coach_evaluation_prohibited_inference
coach_grounding_evidence_id_invalid
coach_grounding_source_unavailable
coach_followup_budget_exhausted
coach_followup_reason_invalid
coach_followup_transcript_ungrounded
coach_followup_duplicate
coach_audio_cleanup_failed
coach_report_conversational_snapshot_stale
coach_progress_incompatible_session
```

Every gate code must be added to the stable contract registry and tested.

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
  "...": "..."
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
Attempt 1 — Developing — not accepted
Attempt 2 — Interview-ready — accepted
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

For conversational sessions, it may create a new conversational session from the prior plan only after explicit contract implementation. If not implemented in Phase 1, return a clear unsupported response and offer session-plan recreation in frontend.

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
    "correlation_id": "...",
    "details": {}
  }
}
```

Canonical new error codes:

```text
coach_conversation_not_enabled
coach_conversational_command_required
coach_conversation_invalid_state
coach_conversation_version_conflict
coach_command_idempotency_conflict
coach_attempt_not_active
coach_attempt_upload_required
coach_attempt_upload_conflict
coach_attempt_retry_budget_exhausted
coach_transcript_deleted
coach_transcript_version_conflict
coach_evaluation_unavailable
coach_followup_budget_exhausted
coach_audio_already_deleted
coach_audio_deletion_failed
coach_report_not_ready
coach_report_invalidated
coach_session_incompatible_for_progress
coach_contract_unsupported
```

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
HATCH_COACH_MAX_FOLLOWUPS_PER_ROOT = 2
HATCH_COACH_MAX_TRANSCRIPT_CHARACTERS = 30000
HATCH_COACH_MAX_EVIDENCE_CLAIMS = 20
HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS = 24
```

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

## 37.3 Command idempotency tests

- duplicate identical command returns original result;
- duplicate command after application restart returns original result;
- same ID/different payload returns conflict;
- network retry does not create duplicate attempt;
- duplicate accept does not create duplicate follow-up;
- duplicate end does not create duplicate report job.

## 37.4 Attempt tests

- deterministic numbering;
- concurrent begin-answer claims create at most one active attempt;
- retry preserves prior attempt;
- accepted attempt explicit;
- prior accepted attempt is unaccepted transactionally;
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
- audio happy path;
- transcription unavailable;
- speech analysis unavailable but content evaluation succeeds;
- evidence grounding unavailable;
- follow-up generation unavailable;
- invalid structured output repaired;
- exhausted repair marks evaluation unavailable;
- job timeout reconciles to recoverable error;
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
- duplicate transient-state reconciliation.

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
- follow-up failure does not block progression.

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
- abandoned is not represented as deleted.

## 37.13 Router tests

- command schema;
- live view;
- audio upload;
- version conflicts;
- safe ID validation;
- legacy/cross-contract route rejection;
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

### Scenario A — Typed interview

1. Create conversational session.
2. Start.
3. Type answer.
4. Process.
5. Review.
6. Accept.
7. Complete remaining questions.
8. Generate named-level report.

### Scenario B — Voice and default deletion

1. Grant microphone.
2. Begin answer.
3. Silence prompt appears.
4. Keep speaking.
5. Finish.
6. Audio uploads and transcribes.
7. Audio deletes after processing prerequisites.
8. Transcript/evaluation remain.

### Scenario C — Retry

1. Submit attempt one.
2. Request coaching.
3. Retry.
4. Submit attempt two.
5. Accept attempt one or two explicitly.
6. Report uses selected attempt only.

### Scenario D — Adaptive follow-ups

1. Answer omits measurable result.
2. Valid grounded follow-up is proposed.
3. Candidate accepts root answer.
4. Follow-up asked.
5. Second follow-up allowed.
6. Third rejected and planned sequence resumes.

### Scenario E — Transcript edit race

1. Audio evaluation completes.
2. Candidate edits transcript.
3. New job starts.
4. Old late worker cannot restore previous evaluation.
5. Delivery remains original.

### Scenario F — Restart recovery

1. Submit audio.
2. Restart backend during processing.
3. Startup reconciliation resolves state.
4. Candidate returns to review or recoverable retry.
5. No duplicate attempt.

### Scenario G — Degraded AI

1. Transcription succeeds.
2. evaluator unavailable.
3. Transcript is preserved.
4. No level invented.
5. Candidate can retry or continue/skip.

### Scenario H — Legacy regression

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

## PR 1 — Conversational foundation and persistence

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

## PR 2 — Capture, processing and retention

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

## PR 3 — Evaluation, evidence, coaching and follow-ups

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

## PR 4 — Report, progress, privacy completion and production hardening

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
claim_conversation_command
append_session_event
reserve_conversational_attempt
persist_audio_upload
create_transcript_version
create_evaluation_version
claim_attempt_processing
finalise_attempt_processing
accept_attempt
create_follow_up_question
advance_question
claim_conversational_report
finalise_conversational_report
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

### AC-01 — Session planning

Given a valid conversational session request, the backend persists a versioned session plan, evidence references, contract versions, retention policy and compatibility key before returning state `ready`.

### AC-02 — State authority

After browser refresh at any non-terminal point, the UI restores from `/live` and does not infer progression from local question/recording arrays.

### AC-03 — Idempotent command

Re-sending an identical `begin_answer` command ID returns the same attempt and does not create another row.

### AC-04 — Stale client

A command with an old state version returns 409 and no mutation.

### AC-05 — Typed parity

A typed answer completes evaluation, grounding, coaching, follow-up and report flow with delivery `not_assessed`.

### AC-06 — Voice capture

A voice answer can be recorded, paused, resumed, uploaded and processed without browser Web Speech being required.

### AC-07 — Silence prompt

Prolonged silence prompts the candidate to Finish or Keep Speaking and does not auto-score or auto-submit at the warning threshold.

### AC-08 — Default audio deletion

With default policy, successful transcription and speech-analysis terminal state cause audio deletion while transcript and evaluation remain.

### AC-09 — Retained audio

With retained policy, cleanup does not delete audio.

### AC-10 — Transcript versioning

A candidate transcript correction creates a new transcript and evaluation version, preserving the original and keeping original delivery metrics.

### AC-11 — Late worker

A worker for a superseded transcript/evaluation fails its finalisation predicate and performs no authoritative mutation.

### AC-12 — Named rubric

Conversational evaluation returns only the specified named levels and no user-facing numeric score.

### AC-13 — Evidence spans

Every assessed content dimension contains at least one validated current-transcript evidence span.

### AC-14 — Evidence status

A claim absent from selected evidence returns `not_found`, with wording that does not assert falsehood.

### AC-15 — Evidence conflict

An objective contradiction returns `conflicting` and remains separate from answer communication quality.

### AC-16 — No confidence inference

No conversational evaluation, report or UI exposes vocal confidence, emotion, personality, deception or presence judgements.

### AC-17 — Follow-up grounding

Every adaptive follow-up has an allowed reason and a matching span in the current accepted transcript.

### AC-18 — Follow-up budget

No root planned question can create more than two adaptive follow-up rows, including after retry, deletion or recovery.

### AC-19 — Retry preservation

Retry creates a new attempt and does not overwrite or automatically accept either attempt.

### AC-20 — Explicit acceptance

Only the recording referenced by `accepted_recording_id` contributes as the root answer to the conversational report.

### AC-21 — Optional coaching

The interview can proceed without requesting coaching. Requesting coaching does not change rubric levels.

### AC-22 — Report determinism

The conversational report derives counts, named levels, accepted attempts and priorities deterministically before optional narrative enrichment.

### AC-23 — Report fallback

Narrative/model failure yields a usable fallback report and completed session, without changing deterministic values.

### AC-24 — Compatible progress

Only sessions with matching compatibility keys are compared.

### AC-25 — No false precision

Conversational UI, report and progress contain no readiness percentage or 0–10 score.

### AC-26 — Delete audio

Candidate can delete audio independently and receives truthful success/failure state.

### AC-27 — Delete transcript

Candidate can delete transcript; dependent evaluation/report data is invalidated and rebuilt or removed safely.

### AC-28 — Technical isolation

Transcription, evaluator, grounding or cleanup failure never reduces a candidate rubric level.

### AC-29 — Legacy preservation

A baseline legacy fixture produces the same numeric report before and after Phase 1.

### AC-30 — Observability privacy

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

# Appendix A — Allowed-command projection

| State | Allowed commands |
|---|---|
| planning | none; cancel/abandon through session action only |
| ready | start |
| asking | begin_answer, request_hint, skip_question, pause, end_session |
| listening | finish_answer, keep_speaking, request_hint, pause, cancel_attempt |
| processing_answer | no user mutation; end is blocked until processing terminal |
| awaiting_next_action | request_coaching, retry_answer, edit_transcript, accept_attempt, pause, end_session, delete_audio, delete_transcript |
| coaching | return_to_review, retry_answer, accept_attempt, pause, end_session, delete_audio, delete_transcript |
| asking_follow_up | none; transient |
| advancing | none; transient |
| paused | resume, end_session where safe, delete_audio where applicable |
| reporting | no mutable interview commands; report-status read only |
| completed | delete_audio, delete_transcript, hard-delete session, export/report reads |
| recoverable_error | retry_processing, retry_answer, pause, end_session, delete_audio, delete_transcript where safe |

The backend computes this list. The frontend does not maintain its own independent transition table.

---

# Appendix B — Fixed dimension priority

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

# Appendix C — Follow-up reason definitions

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

# Appendix D — Evidence wording guide

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

# Appendix E — Conversational report example

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

# Appendix F — Self-review checklist for the implementation PRs

Before claiming each PR complete, verify:

```text
[ ] No TODO/TBD remains in a required contract path.
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
