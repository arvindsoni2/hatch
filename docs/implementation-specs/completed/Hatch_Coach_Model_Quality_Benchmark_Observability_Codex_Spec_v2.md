---
title: Hatch Coach model quality, benchmark, and observability Codex specification v2
document_type: implementation-spec
status: active
implementation_status: partial
applies_to: main/latest
last_verified: 2026-07-18
supersedes: Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v1.md
superseded_by: []
---

# Hatch Coach model quality, benchmark, and observability Codex specification v2

**Repository baseline:** attached `hatch-main.zip`, representing `main` supplied on 18 July 2026  
**Telemetry baseline:** PR42 behaviour and authoritative facade names reported by Codex during specification review  
**Implementation target:** `main/latest` after PR42 has merged  
**Primary goal:** make Coach model behaviour measurable, safe, reproducible, and observable without redesigning the Coach product  
**Audience:** Codex implementation agent and human reviewer  
**Delivery status:** PRs C1, C2, and C3 have not started. `implementation_status: partial` means the existing Coach and PR42 baseline already satisfies part of the target specification; it does not mean C1 implementation has begun.


## 1. Executive decision

Implement this work as three sequential PRs:

1. **PR C1: Coach contract and correctness baseline**
2. **PR C2: Coach model benchmark harness and synthetic suite**
3. **PR C3: Coach OpenTelemetry extension**

Do not combine these PRs. Do not change Hatch's default model as part of C1, C2, or C3. A model change requires two completed standard benchmark runs with the same qualifying result and a separate owner decision.

The benchmark must evaluate the current Coach workflow rather than introduce a generic conversational coach. The current product boundary is:

- company research;
- interview-question generation;
- candidate-grounded model answers;
- text/audio/video answer capture;
- answer evaluation;
- deterministic and LLM-enriched rubrics;
- technical drills;
- session feedback reports;
- follow-up session planning and progress chains.

Career advice, unrestricted chat memory, live streaming interviews, autonomous job-search coaching, and frontend telemetry are outside this specification.


## 2. Why this work is needed

CV and cover-letter quality are now measured by explicit contracts, hard gates, repair accounting, benchmark manifests, and safety-first ranking. Coach currently has production prompt contracts and good unit coverage, but it does not have equivalent model-level acceptance evidence.

A model can perform acceptably on CV or cover-letter generation and still fail Coach because Coach depends on different behaviours:

- generating a useful and non-duplicative question set;
- mapping questions to job requirements;
- withholding a model answer when candidate evidence is insufficient;
- evaluating strong and weak answers consistently;
- grounding feedback in transcripts and deterministic metrics;
- keeping deterministic scores stable while using an LLM for narrative enrichment;
- producing actionable reports without changing computed scores;
- degrading explicitly when a local model is slow, unavailable, or malformed.

This specification closes that gap while reusing the existing local-model adapters, prompt catalogue, evidence contracts, async-job pattern, and the OpenTelemetry foundation currently being implemented.


## 3. Current implementation baseline

Codex must preserve the current product architecture unless this specification explicitly changes it.

### 3.1 Current backend boundaries

| Area | Current implementation |
|---|---|
| Router | `backend/app/routers/coach.py` |
| Orchestrator | `backend/app/services/coach_service.py` |
| Async session generation | `backend/app/services/coach_session_queue.py` |
| Company research | `backend/app/services/company_researcher.py` |
| Question generation | `backend/app/services/question_generator.py` |
| Model answers | `backend/app/services/model_answer_gen.py` |
| Answer evaluation | `backend/app/services/answer_evaluator.py` |
| Deterministic rubric | `backend/app/services/rubric_builder.py` |
| LLM rubric enrichment | `backend/app/services/rubric_synthesiser.py` |
| Session report | `backend/app/services/feedback_generator.py` |
| Technical drills | `backend/app/services/technical_drills.py` |
| Follow-up planning | `backend/app/services/followup_planner.py` |
| Speech analysis | `backend/app/services/speech_analyser.py` |
| Video metric validation | `backend/app/services/video_analyser.py` |
| Schemas | `backend/app/schemas/coach.py` |
| Persistence | `backend/app/models/coach_session.py`, `backend/app/repositories/session_repository.py` |
| Prompt catalogue | `backend/app/services/prompt_catalog.py` |
| Prompt templates | `backend/app/prompts/*.j2` |
| Existing writing benchmark | `backend/benchmarks/` |

### 3.2 Current workflow

#### Session creation

```text
POST /api/coach/sessions
  -> create setup session stub
  -> create async job
  -> optional company research
  -> generate interview questions
  -> generate one model answer per question
  -> persist questions
  -> build technical drills for technical/domain questions
  -> mark session active
```

#### Answer submission

```text
POST /api/coach/sessions/{session_id}/submit-answer
or
POST /api/coach/sessions/{session_id}/submit-audio
  -> create async job
  -> transcribe audio when applicable
  -> compute deterministic speech metrics
  -> validate optional browser-side video metrics
  -> evaluate answer with LLM
  -> build deterministic rubric
  -> optionally enrich rubric with LLM
  -> persist recording and evaluation
```

#### Session completion

```text
POST /api/coach/sessions/{session_id}/end
  -> load recordings and questions
  -> aggregate deterministic scores
  -> generate narrative feedback report
  -> persist overall score and summary
  -> mark session completed
```

#### Follow-up

```text
POST /api/coach/sessions/{session_id}/plan-followup
  -> read stored session rubric
  -> choose weakest one or two dimensions
  -> create child session
  -> copy parent questions
```

### 3.3 Existing prompt contracts

The following Coach prompts already have stable prompt catalogue metadata at version `1.0.0`:

- `question_generation`;
- `model_answer`;
- `answer_evaluation`;
- `rubric_synthesis`;
- `session_report`;
- `company_research`;
- `follow_up_question`;
- `speech_feedback`;
- `video_feedback`.

`technical_drills.py` currently uses an inline prompt and must be brought into the prompt catalogue in PR C1.

### 3.4 Existing tests

The repository already tests:

- Coach route and async-job behaviour;
- audio upload validation and path traversal prevention;
- question parsing and requirement mapping;
- candidate-grounded model-answer numeric fidelity;
- answer score parsing and transcript-grounded evidence references;
- company-research source references;
- deterministic speech metrics;
- rubric construction and enrichment fallback;
- technical drills;
- follow-up planning;
- Coach prompt metadata and claim-layer wording;
- major frontend Coach components.

These tests are functional and contract tests. They are not a live multi-model benchmark and do not provide model-selection evidence.


## 4. Repository-grounded gaps that must be resolved

These are implementation findings from the attached `main` baseline. They are not optional design suggestions.

### 4.1 Silent evaluation fallback

`AnswerEvaluatorService.evaluate()` currently returns neutral scores of `5` when the LLM call fails. That fallback is indistinguishable from a genuine average answer and can be persisted and included in session scoring.

**Locked decision:** provider failure, timeout, malformed output, and validation failure must be explicit states. They must never be represented as a completed `5/10` evaluation and must not influence the session score.

### 4.2 Silent model-answer withholding

`ModelAnswerGeneratorService.generate()` returns an empty string for several different cases:

- no candidate evidence;
- unsupported numeric mutation;
- malformed output;
- provider failure;
- empty model response.

An empty model answer is safe, but the cause is currently unauditable.

**Locked decision:** keep the safe empty public behaviour, but record a stable internal outcome and gate code distinguishing expected withholding from operational or validation failure.

### 4.3 Question-count drift

Question parsing deduplicates and drops malformed items but does not enforce that the final list equals `SessionConfig.question_count`.

**Locked decision:** production session creation must not silently activate a partial question set. Perform at most one targeted repair for the missing count. If the repaired set is still invalid or short, mark the session `failed` and finish the async job with an explicit contract failure.

### 4.4 Requirement mapping is discarded on persistence

`QuestionPresentation.requirement_id` is generated and validated, but `SessionQuestion` does not persist it.

**Locked decision:** add a nullable `requirement_id` column and preserve it through initial session persistence, API reads, and follow-up question copying.

### 4.5 Rubric enrichment can mutate scores

`RubricSynthesiserService` currently accepts LLM-provided scores when merging evidence into the deterministic baseline.

**Locked decision:** the enrichment model may add grounded evidence, drills, and `focus_for_next_session`; it must not change deterministic/content scores or score bands. Any attempted score mutation is ignored and recorded as a gate finding.

### 4.6 Session rubric is not reliably persisted

Answer-level rubrics are stored inside `evaluation_json`, while follow-up planning reads `InterviewSession.rubric`. The current orchestration does not reliably aggregate and persist a session-level rubric before planning a follow-up.

**Locked decision:** session completion must deterministically aggregate completed answer rubrics by dimension, persist the result to `InterviewSession.rubric`, and use that persisted aggregate for follow-up planning and progress trends.

### 4.7 Session-report availability and counts are ambiguous

The report currently aggregates only recordings with parseable evaluations, and its prompt receives `answered_count` and `total_questions` as the same value. Skipped and unavailable evaluations are not represented accurately.

**Locked decision:** compute and expose separate counts for total, completed evaluations, skipped answers, unavailable/invalid evaluations, and unanswered questions. Only canonical completed evaluations contribute to score averages.

### 4.8 Report retrieval is not a pure read

PR42 decorates `end_session`, so `end_session.__wrapped__` now exists. The underlying problem remains: `get_report()` invokes the session-ending path, regenerates nondeterministic LLM content, and can repeat persistence work from a read endpoint.

**Locked decision:** persist the completed or deterministic fallback report as a snapshot. `GET /report` returns that snapshot and must not invoke `end_session`, `__wrapped__`, an LLM, or any mutating status/score path.

### 4.9 Technical-drill prompt is outside the prompt catalogue

The technical-drill prompt is inline and lacks the same versioned contract metadata used by other AI workflows.

**Locked decision:** add `technical_drill` prompt metadata and a Jinja template. Use structured JSON generation and validate the output before returning a drill.

### 4.10 Long sequential session-generation path

A ten-question session may require company research, one question-generation call, ten model-answer calls, and several technical-drill calls. Local models can therefore make session setup slow or fragile.

**Locked decision:** C1 adds Coach-owned production stage and whole-job deadlines with the defaults and outcome mappings in section 7.13. C2 separately adds resumable benchmark timeouts. C1 does not introduce parallel production LLM calls because that could increase local memory pressure. Production concurrency remains sequential unless separately benchmarked and approved.


## 5. Scope

### 5.1 In scope

- explicit Coach stage outcomes and stable gate codes;
- correctness fixes listed in section 4;
- synthetic, committed Coach benchmark fixtures;
- service-level live model benchmarking;
- one minimal end-to-end session smoke path;
- safety-first model eligibility and per-stage ranking;
- resume, partial-result, timeout, and manifest support;
- Coach spans and metrics using the merged OpenTelemetry foundation;
- privacy tests proving no CV, JD, transcript, audio path, or generated content is exported;
- documentation and reproducible commands.

### 5.2 Out of scope

- changing the default model;
- per-task production model routing;
- a free-form career-advice chat mode;
- live streaming or low-latency conversational interviews;
- frontend tracing;
- benchmarking ASR model accuracy;
- benchmarking face-analysis or emotion-recognition models;
- replacing deterministic speech metrics;
- redesigning Coach pages or navigation;
- changing session status values;
- parallelising local model calls;
- adding Grafana, Tempo, Loki, or a hosted observability service;
- remote telemetry export enabled by default.

### 5.3 Existing states remain authoritative

The session lifecycle remains:

```text
setup | active | completed | failed | abandoned
```

Do not add `review_required`, `blocked`, or `clarification_required` as session statuses in this work.


## 6. PR topology and model recommendations

### PR C1: Coach contract and correctness baseline

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Dependency:** branch after PR42 has merged. C1 must preserve PR42's existing `coach_generation` telemetry exactly as merged. C1 may add persisted diagnostics and pass existing allowlisted outcome values to the facade, but it must not add new Coach spans, new Coach metrics, a second workflow decorator, or a second model-call instrument. C3 owns the detailed hierarchy and facade extension.

Purpose:

- make every Coach AI stage distinguish completed output, safe withholding, deterministic fallback, operational unavailability, invalid output, and hard failure;
- fix the correctness gaps in section 4;
- preserve existing routes and session statuses;
- add tests before implementation.

### PR C2: Coach model benchmark harness

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Dependency:** PR C1 merged.

Purpose:

- add the synthetic benchmark suite;
- benchmark current production prompt assembly and validators;
- produce auditable model, stage, and scenario evidence;
- support live local models without allowing one slow model to stall the run.

### PR C3: Coach OpenTelemetry extension

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium-high  
**Dependency:** PR C1 and C2 merged; the current general OpenTelemetry PR must already be on `main`.

Purpose:

- instrument the real Coach orchestration and benchmark workflows;
- reuse the single existing tracer/meter/provider lifecycle;
- add no second telemetry initialisation path;
- keep observability disabled by default.

### Separate future decision: model routing or default change

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Dependency:** two qualifying standard Coach benchmark runs with the same decision.

This is not part of C1-C3.


## 7. PR C1 detailed contract

### 7.1 Shared Coach stage vocabulary

Add a Coach-owned contract module, preferably:

```text
backend/app/services/coach_contracts.py
```

Use stable stage names:

```text
company_research
question_generation
question_generation_repair
model_answer
answer_evaluation
rubric_build
rubric_synthesis
technical_drill
session_report
session_rubric_aggregation
followup_plan
```

Use stable internal outcomes:

```text
completed
withheld_insufficient_evidence
fallback_deterministic
invalid_output
unavailable
failed
```

These are stage outcomes, not session statuses.

### 7.2 Stable gate-code namespace

Gate codes are machine-readable, snake_case, and versioned through the Coach validation schema. Messages are human-readable but must not be used for aggregation.

#### Question generation

```text
coach_question_parse_invalid
coach_question_count_mismatch
coach_question_duplicate
coach_question_category_invalid
coach_question_difficulty_invalid
coach_question_requirement_unknown
coach_question_candidate_claim
coach_question_prompt_injection_followed
coach_question_repair_exhausted
```

#### Model answer

```text
coach_model_answer_no_evidence
coach_model_answer_empty
coach_model_answer_schema_invalid
coach_model_answer_unknown_evidence_id
coach_model_answer_unsupported_claim
coach_model_answer_numeric_fidelity
coach_model_answer_star_incomplete
coach_model_answer_provider_unavailable
```

#### Answer evaluation

```text
coach_evaluation_schema_invalid
coach_evaluation_dimension_missing
coach_evaluation_score_out_of_range
coach_evaluation_overall_inconsistent
coach_evaluation_evidence_ungrounded
coach_evaluation_followup_missing
coach_evaluation_followup_unexpected
coach_evaluation_provider_unavailable
coach_evaluation_fallback_unclassified
```

#### Rubric

```text
coach_rubric_dimension_missing
coach_rubric_score_mutation
coach_rubric_evidence_ungrounded
coach_rubric_optional_dimension_unexpected
coach_rubric_provider_unavailable
```

#### Session report

```text
coach_report_count_mismatch
coach_report_score_mutation
coach_report_unsupported_claim
coach_report_priority_mismatch
coach_report_schema_invalid
coach_report_provider_unavailable
coach_report_fallback_unclassified
```

#### Technical drills

```text
coach_drill_schema_invalid
coach_drill_question_mismatch
coach_drill_candidate_claim
coach_drill_length_exceeded
coach_drill_provider_unavailable
```

#### Operational

```text
coach_stage_timeout
coach_job_timeout
coach_stage_failed
coach_async_job_failed
coach_persistence_failed
```

Do not reuse CV/cover-letter gate codes for Coach findings.

### 7.3 Diagnostic record

Introduce one internal, serialisable diagnostic record shared by production orchestration, benchmark output, and telemetry enrichment.

Minimum fields:

```json
{
  "validation_schema_version": "1.0.0",
  "stage": "answer_evaluation",
  "outcome": "completed",
  "prompt_id": "answer_evaluation",
  "prompt_version": "1.0.0",
  "schema_version": "1.0.0",
  "model_id": "configured-catalogue-id",
  "attempt_count": 1,
  "repair_count": 0,
  "gate_codes": [],
  "duration_ms": 0
}
```

Rules:

- no prompt or response content;
- no candidate name;
- no transcript;
- no job-description text;
- no raw filesystem path;
- model ID must come from the configured catalogue/profile, not an arbitrary response string;
- durations use monotonic time;
- diagnostics must use the production persistence map below and must not require a new general-purpose telemetry table.

#### Production persistence map

C1 adds one Alembic migration with these nullable, backward-compatible fields:

```text
interview_sessions.diagnostics JSON
interview_sessions.report_json JSON
session_questions.requirement_id VARCHAR(64)
session_questions.model_answer_diagnostics JSON
```

Persistence ownership is locked as follows:

| Stage | Persisted location |
|---|---|
| Company research used during session setup | `InterviewSession.diagnostics.stages.company_research` |
| Question generation and its single repair | `InterviewSession.diagnostics.stages.question_generation` |
| Per-question model answer | `SessionQuestion.model_answer_diagnostics` |
| Answer evaluation and rubric enrichment | `SessionRecording.evaluation_json`, inside the serialised `AnswerEvaluation` |
| Session-rubric aggregation | `InterviewSession.diagnostics.stages.session_rubric` and the authoritative aggregate in `InterviewSession.rubric` |
| Technical-drill generation | `InterviewSession.diagnostics.stages.technical_drills` |
| Session report | complete snapshot in `InterviewSession.report_json`; stage diagnostic also appears inside the report snapshot |
| Follow-up planning | diagnostics on the new child session under `InterviewSession.diagnostics.stages.followup_planning` |

`InterviewSession.diagnostics` is a versioned object with `schema_version` and a `stages` map. Updating one stage must merge that key without deleting diagnostics written by another stage. A failed session-setup job must persist its terminal question-generation/job diagnostic on the existing stub session before setting the session to `failed`.

No diagnostic field may contain prompt text, generated text, candidate content, transcript content, URLs, or filesystem paths.

### 7.4 Question-generation contract

The production question generator must satisfy all of the following:

1. Final count equals `SessionConfig.question_count`.
2. Every question has non-empty text.
3. Normalised question text is unique within the session.
4. Category belongs to the existing set:

```text
Technical | Behavioural | Situational | Domain | Culture | Commercial
```

5. Difficulty is `easy`, `medium`, or `hard`.
6. Every question maps to one supplied requirement ID.
7. An unknown, missing, or malformed `requirement_id` invalidates the entire candidate question set; it is never silently remapped.
8. Candidate context may influence what to probe but must not be presented as confirmed candidate history.
9. Instructions embedded in JD or company context cannot override the system contract.
10. The output contains no model answer.

#### Bounded repair

- Initial parse and validation run first.
- A short, duplicated, malformed, unknown-requirement, or otherwise invalid first output is rejected for activation.
- Perform exactly one targeted repair call containing:
  - the required missing count;
  - allowed categories;
  - the complete allowed requirement-ID list;
  - explicit validator findings;
  - hashes or normalised text of accepted non-conflicting questions;
  - no private context beyond what the original question prompt already received.
- Merge only validator-approved repaired questions, deduplicate, and validate the complete set again.
- No second repair call.
- Never derive, substitute, hash, index-map, or otherwise remap an unknown model-supplied requirement ID.
- Activate only when the final set has exactly the requested count and every requirement ID is valid.
- If still invalid, persist the diagnostic, fail session generation, and mark the stub session `failed`.

Add a versioned prompt, for example:

```text
backend/app/prompts/question_generation_repair.j2
```

Add it to the prompt catalogue.

### 7.5 Requirement persistence

Add a nullable `requirement_id` column to `session_questions` through a new Alembic migration.

Requirements:

- initial question persistence writes it;
- `SessionQuestionRead` exposes it as optional;
- frontend types accept it as optional;
- follow-up question copying preserves it;
- old rows remain valid with `NULL`;
- no migration rewrites historical question text.

### 7.6 Model-answer contract

Model answers remain optional. An empty model answer is valid only when its outcome is explicit.

#### Valid completed model answer

A completed model answer must:

- use only approved candidate evidence;
- preserve immutable numbers exactly;
- use only known evidence IDs when IDs are emitted;
- avoid invented employer, title, date, duration, team size, action, or result;
- include meaningful Situation, Task, Action, and Result content;
- distinguish employer context from candidate history.

#### Valid withholding

When approved evidence cannot support a truthful answer:

```text
outcome = withheld_insufficient_evidence
gate_codes = [coach_model_answer_no_evidence]
public model_answer = ""
```

This is safe and does not fail session creation.

#### Invalid or unavailable answer

Malformed, unsupported, or provider-failed output also remains hidden from the user but must use a different diagnostic outcome. It must not be counted as a successful model answer in benchmark or telemetry reports.

No additional factuality repair call is required in C1. Existing JSON parse retry behaviour remains bounded by `LLMClient`; the benchmark records the resulting attempt count when available.

### 7.7 Answer-evaluation contract

Add backward-compatible state and diagnostics to `AnswerEvaluation`:

```text
evaluation_state = completed | unavailable | invalid
diagnostic: CoachDiagnostic | None
scores: dict[str, int]
overall: float | None
```

Default for deserialising historical evaluations is `completed`. Historical numeric values remain unchanged.

For `completed`, `scores` contains all six dimensions and `overall` is a number. For `unavailable` or `invalid`, `scores` must be `{}`, `overall` must be `null`, `rubric` must be `null`, and the diagnostic must explain the terminal outcome. Zero and five are forbidden substitutes for an absent evaluation.

A completed evaluation must:

- contain all six existing dimensions;
- keep each score in `0..10`;
- keep overall in `0..10`;
- keep overall within `1.0` of the arithmetic mean unless the prompt contract later defines explicit weights;
- retain only evidence references grounded in the transcript or supplied deterministic metrics;
- set a follow-up question when overall is below `6.0`;
- omit the follow-up question when overall is `6.0` or above;
- separate observation, interpretation, and recommendation claims.

On provider failure or invalid output:

- set `evaluation_state` appropriately;
- do not return a neutral completed score;
- provide a retry-oriented message;
- persist the failed/unavailable evaluation state for audit;
- exclude it from session score aggregation;
- keep the async job result explicit so the frontend can offer retry.

Minimal frontend behaviour:

- do not display an unavailable evaluation as `5/10`;
- show that evaluation could not be completed;
- keep the answer recording and transcript;
- allow resubmission through the existing answer path.

No broad Coach UI redesign is permitted.

#### Repeated submissions and canonical attempt

Every submission remains an immutable `SessionRecording`; C1 must not overwrite or delete earlier attempts.

For scoring, report generation, session-rubric aggregation, and progress trends, choose one canonical attempt per question:

1. select recordings for that question with `evaluation_state=completed`;
2. if one or more exist, choose the latest by `created_at DESC`, then `recording.id DESC` as the deterministic tie-breaker;
3. if none exists, choose no scored attempt;
4. for state/count reporting only, classify the latest terminal recording by `created_at DESC`, then `recording.id DESC` as skipped, unavailable, invalid, or unanswered.

A later failed retry does not erase an earlier completed attempt. Earlier attempts remain queryable for audit but do not contribute additional scores. All report counts are counts of unique session questions, never counts of recordings.

### 7.8 Rubric contract

The deterministic rubric is authoritative for scores.

The LLM rubric synthesiser may modify only:

- grounded evidence text;
- drill wording;
- `focus_for_next_session`.

It may not modify:

- dimension membership determined by available signals;
- numeric scores;
- score bands;
- deterministic delivery, vocal-confidence, or presence values.

When the LLM proposes a different score or band:

- preserve the baseline value;
- record `coach_rubric_score_mutation`;
- continue with the otherwise valid grounded enrichment.

When enrichment fails, return the deterministic rubric with:

```text
outcome = fallback_deterministic
```

That fallback is valid and must not fail answer evaluation.

### 7.9 Session-rubric aggregation

At session completion:

1. Resolve the canonical attempt for every question using section 7.7.
2. Use only canonical attempts with `evaluation_state=completed` and a valid rubric.
3. For each dimension, compute the arithmetic mean of available canonical answer scores.
4. Round with decimal `ROUND_HALF_UP`: `Decimal(str(mean)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)`. Python's built-in bankers rounding is not permitted.
5. Derive the score band with the existing `score_to_band()` function.
6. Select evidence candidates from canonical attempts in this order: dimension score ascending, `question.order_in_session` ascending, `recording.created_at` ascending, `recording.id` ascending, then original evidence-list position. Normalise whitespace and case for deduplication and keep the first two unique grounded items.
7. Reuse the existing deterministic drill for the dimension.
8. Sort focus candidates by aggregate score ascending, then by this fixed priority, then by dimension name: `relevance`, `star_structure`, `technical_depth`, `conciseness`, `communication`, `impact_metrics`, `delivery`, `vocal_confidence`, `presence`.
9. Always select the lowest dimension. Select the second dimension only when it exists and either its score is `<= 6`, or the lowest score is `< 8` and the difference from the lowest score is `<= 1`. Otherwise select one dimension.
10. Build `focus_for_next_session` from the selected dimensions in that order.
11. Persist the resulting `SessionRubric` to `InterviewSession.rubric` and its aggregation diagnostic to `InterviewSession.diagnostics` in the same transaction as report completion.

Skipped, invalid, unavailable, unanswered, and non-canonical evaluations do not contribute scores.

Follow-up planning must use this persisted aggregate. If no completed canonical evaluation exists, follow-up creation remains allowed but uses an empty focus list and an explicit diagnostic outcome.

### 7.10 Session-report contract

Add backward-compatible fields to `SessionFeedbackReport`:

```text
report_state = completed | fallback
diagnostic: CoachDiagnostic | None
overall_score: float | None
question_count_total
question_count_evaluated
question_count_skipped
question_count_unavailable
question_count_unanswered
```

Historical responses without fields use safe defaults.

Count and score rules:

- resolve one canonical attempt per question using section 7.7;
- `question_count_total` is the number of persisted session questions;
- `question_count_evaluated` counts questions with a canonical completed evaluation;
- `question_count_skipped` counts questions with no completed evaluation whose latest terminal recording is the explicit skip marker;
- `question_count_unavailable` counts questions with no completed evaluation whose latest terminal evaluation is unavailable or invalid;
- `question_count_unanswered` is `total - evaluated - skipped - unavailable` and must never be negative;
- the four state counts must sum to `question_count_total`;
- only canonical completed evaluations contribute to overall and category scores;
- when no completed evaluation exists, `overall_score=null`, category scores are empty, and `InterviewSession.overall_score` remains `NULL`;
- overall score and category scores are deterministic inputs to the narrative model;
- the model cannot replace or mutate those scores;
- question summaries preserve their canonical evaluation scores;
- unavailable evaluations are never averaged as zero or five;
- the narrative may interpret patterns but cannot invent candidate or employer facts;
- a provider failure or timeout produces a deterministic fallback report with `report_state=fallback`;
- a fallback report is still a valid completed session report;
- the stored session overall score uses deterministic aggregation only.

Persistence and read rules:

1. `POST /sessions/{id}/end` builds the report once.
2. Persist the complete serialised report in `InterviewSession.report_json`.
3. Persist `report_json`, `rubric`, `overall_score`, `feedback_summary`, completion diagnostics, `status=completed`, and `completed_at` in one transaction.
4. If that transaction fails, do not leave the session marked completed.
5. A repeated end request for an already completed session with `report_json` returns the stored snapshot and performs no LLM call.
6. `GET /report` returns `report_json` only and performs no mutation or LLM call.
7. For a legacy completed session with no `report_json`, `GET /report` may build and return an in-memory deterministic fallback from stored canonical attempts, marked `report_state=fallback` with a legacy-snapshot diagnostic. It must not persist, call an LLM, or change session state.

The pure deterministic aggregation builder may be shared by session completion and the legacy read fallback. The narrative-generation path is called only by session completion when no snapshot exists.

### 7.11 Technical-drill contract

Create:

```text
backend/app/prompts/technical_drill.j2
```

Add `technical_drill` to `prompt_catalog.py` with version `1.0.0` and a structured output schema.

Replace free-text `complete()` plus manual `json.loads()` with `complete_json()` or the merged structured-output abstraction.

A valid drill must:

- correspond to the supplied question;
- contain `walkthrough` and `drill_prompt`;
- keep walkthrough at or below 200 words;
- avoid asserting candidate history;
- avoid unsupported metrics;
- remain optional and safely omitted on failure.

### 7.12 Configuration fields not activated by this work

`SessionConfig.categories` and `interviewer_persona` exist but are not consistently enforced in the supplied baseline and are not exposed by the current launcher UI.

Locked decision for C1-C3:

- do not expand their product behaviour;
- do not use them as benchmark ranking dimensions;
- preserve compatibility;
- document them as deferred until a dedicated Coach configuration contract is approved.

### 7.13 Production timeout contract

C1 adds a Coach-owned runtime settings object in the existing backend configuration layer. Coach services pass an additive `timeout_seconds` argument into `LLMClient`; the existing global LLM timeout remains the fallback for non-Coach callers.

Default environment-backed values are:

| Stage or job | Environment key | Default |
|---|---|---:|
| Company-research synthesis | `HATCH_COACH_TIMEOUT_COMPANY_RESEARCH_SECONDS` | 180 s |
| Question generation | `HATCH_COACH_TIMEOUT_QUESTION_GENERATION_SECONDS` | 300 s |
| Question-generation repair | `HATCH_COACH_TIMEOUT_QUESTION_REPAIR_SECONDS` | 180 s |
| Model answer, per question | `HATCH_COACH_TIMEOUT_MODEL_ANSWER_SECONDS` | 180 s |
| Answer evaluation | `HATCH_COACH_TIMEOUT_ANSWER_EVALUATION_SECONDS` | 300 s |
| Rubric enrichment | `HATCH_COACH_TIMEOUT_RUBRIC_ENRICHMENT_SECONDS` | 120 s |
| Technical drill, per question | `HATCH_COACH_TIMEOUT_TECHNICAL_DRILL_SECONDS` | 120 s |
| Session report | `HATCH_COACH_TIMEOUT_SESSION_REPORT_SECONDS` | 300 s |
| Session-create background job | `HATCH_COACH_TIMEOUT_SESSION_CREATE_JOB_SECONDS` | 2400 s |
| Answer-submit background job | `HATCH_COACH_TIMEOUT_ANSWER_SUBMIT_JOB_SECONDS` | 600 s |
| Session-end background job | `HATCH_COACH_TIMEOUT_SESSION_END_JOB_SECONDS` | 600 s |
| Follow-up planning job/path | `HATCH_COACH_TIMEOUT_FOLLOWUP_SECONDS` | 60 s |

Stage values must validate within `10..3600` seconds. Whole-job values must validate within `60..7200` seconds. Invalid configuration fails application configuration loading; it must not silently revert.

Timeout mapping is locked:

| Timeout location | Production result |
|---|---|
| Company research | `unavailable_timeout`; continue session setup without research |
| Question generation or repair | persist diagnostic, mark stub session `failed`, activate no partial question set |
| Model answer | persist empty public model answer plus `unavailable_timeout`; continue session setup |
| Answer evaluation | persist the recording with `evaluation_state=unavailable`, empty scores, `overall=null`; return a retryable completed async-job payload |
| Rubric enrichment | return deterministic rubric with `fallback_deterministic` |
| Technical drill | omit that drill and persist optional-stage diagnostic |
| Session report | persist deterministic fallback report and complete the session |
| Session-create whole-job deadline | cancel current work, roll back open transaction, persist `coach_job_timeout`, mark stub session `failed` |
| Answer-submit whole-job deadline | persist an unavailable evaluation record for the submitted transcript and finish the async job with a retryable payload |
| Session-end whole-job deadline | persist deterministic fallback report if deterministic inputs are available; otherwise leave the session active and finish the job with an explicit failure |

Timeouts are terminal for the affected stage invocation. C1 does not add automatic timeout retries beyond the single question-repair call.

### 7.14 Background database-session boundary

C1 must move text-answer submission and session-end background work to fresh `AsyncSessionLocal` sessions, matching session creation and audio submission.

Before scheduling text submission, serialise the request into primitive data and reconstruct `SubmitAnswerRequest` inside the job. Background closures may capture only primitive IDs and serialisable request data, never the request-scoped `AsyncSession` or ORM instances. Each job owns commit/rollback/close through its fresh session. The request-scoped session is used only to create and commit the async-job record.

Add regression coverage for session creation, text submission, audio submission, and session end proving that the request session can close before background execution begins.

## 8. PR C1 tests

Write failing tests first.

### 8.1 Required backend tests

Add or extend tests proving:

1. Question generation performs at most one repair.
2. Question generation cannot activate a partial set.
3. Deduplicated repaired questions still equal the requested count.
4. Unknown, missing, or malformed requirement IDs reject the candidate set and can succeed only through the single repair call; no remapping occurs.
5. `requirement_id` persists and is copied into follow-up sessions.
6. Insufficient model-answer evidence is recorded as expected withholding.
7. Unsupported candidate claims remain hidden and use a validation-failure diagnostic.
8. Answer provider failure is persisted with `scores={}` and `overall=null`, not represented as completed `5/10` or `0/10`.
9. Repeated submissions retain every attempt and use the latest successfully completed evaluation as canonical.
10. Invalid evaluation dimensions are rejected.
11. Ungrounded evaluation evidence is removed and recorded.
12. Follow-up threshold is enforced at `< 6.0`.
13. Rubric enrichment cannot mutate scores or bands.
14. Rubric enrichment failure returns the deterministic rubric with an explicit fallback state.
15. Session-rubric aggregation excludes skipped, unavailable, invalid, unanswered, and non-canonical attempts.
16. Session-rubric means use decimal `ROUND_HALF_UP`, the fixed evidence order, and the locked focus-dimension tie-breaker.
17. Session rubric is persisted before follow-up planning.
18. Session report counts total, evaluated, skipped, unavailable, and unanswered questions correctly, and the counts reconcile to total.
19. Report LLM output cannot mutate deterministic scores.
20. Report provider failure produces a deterministic fallback report.
21. Complete/fallback report snapshots persist and repeated end/GET calls make no LLM call.
22. Legacy completed sessions without a snapshot return a read-only deterministic fallback.
23. Technical-drill prompt metadata is rendered.
24. Technical drills reject overlong, malformed, or candidate-claiming output.
25. Existing route status values remain unchanged.
26. Historical `evaluation_json` and report payloads without new state fields still deserialize.
27. Production stage and whole-job timeouts map to the outcomes in section 7.13.
28. Session creation, text submission, audio submission, and session end use fresh database sessions after the request session closes.
29. Diagnostics persist in the exact fields defined in section 7.3 and merge stage keys without deleting prior diagnostics.

### 8.2 Required frontend tests

Add or extend tests proving:

1. Unavailable or invalid evaluation does not render as a numeric score.
2. Completed evaluation rendering remains unchanged.
3. Optional `requirement_id` does not break session rendering.
4. Fallback report renders without claiming the AI narrative completed normally.
5. A report with `overall_score=null` renders a no-score state rather than `0/10`.

### 8.3 Regression commands

Create `tests/test_services/test_feedback_generator.py` if it does not already exist; the session-report snapshot, count, canonical-attempt, and fallback tests belong there.

Run at minimum:

```bash
cd backend
pytest -q \
  tests/test_services/test_question_generator.py \
  tests/test_services/test_model_answer_gen.py \
  tests/test_services/test_answer_evaluator.py \
  tests/test_services/test_rubric_builder.py \
  tests/test_services/test_rubric_synthesiser.py \
  tests/test_services/test_feedback_generator.py \
  tests/test_services/test_technical_drills.py \
  tests/test_services/test_followup_planner.py \
  tests/test_services/test_coach_prompt_contracts.py \
  tests/test_services/test_coach_session_queue.py \
  tests/test_routers/test_coach_router.py \
  tests/test_routers/test_coach_async.py
```

Run the repository's normal backend lint/type checks and frontend Coach test set. Use the commands already documented by the repository rather than introducing a second toolchain.


## 9. PR C2 benchmark architecture

### 9.1 Chosen approach

Create a Coach-specific benchmark package under the existing benchmark namespace:

```text
backend/benchmarks/coach/
```

Recommended files:

```text
backend/benchmarks/coach/__init__.py
backend/benchmarks/coach/__main__.py
backend/benchmarks/coach/contracts.py
backend/benchmarks/coach/suite_loader.py
backend/benchmarks/coach/production_adapter.py
backend/benchmarks/coach/validators.py
backend/benchmarks/coach/scoring.py
backend/benchmarks/coach/runner.py
backend/benchmarks/coach/reporting.py
backend/benchmarks/coach/cli.py
backend/benchmarks/coach/fixtures/v1/
```

Reuse `backend/benchmarks/adapters.py` for loopback llama.cpp/Ollama calls where compatible. Do not rewrite or destabilise the completed CV/cover-letter runner merely to make the folder layout symmetrical.

### 9.2 Alternatives rejected

#### Add Coach fields to the current writing benchmark contracts

Rejected because the existing contracts are strongly shaped around a CV/cover-letter pair, document gates, and writing scores. A large tagged union would increase regression risk and make reports harder to understand.

#### Benchmark only through HTTP endpoints and the real database

Rejected as the primary harness because it is slower, less deterministic, and makes stage attribution difficult. One minimal end-to-end smoke remains required, but model ranking uses production service/prompt boundaries with isolated synthetic inputs.

#### Build a generic benchmark framework first

Rejected because it expands scope before a second domain proves the abstraction. Share only stable adapters and small utilities that already fit both domains.

### 9.3 CLI

Use a separate module entry point:

```bash
python -m benchmarks.coach validate --suite <path>
python -m benchmarks.coach smoke --suite <path>
python -m benchmarks.coach run --suite <path> --models <ids> --profile acceptance-smoke
python -m benchmarks.coach run --suite <path> --models <ids> --profile standard
python -m benchmarks.coach run --suite <path> --models <ids> --profile extended
python -m benchmarks.coach run --suite <path> --models <ids> --profile standard --resume <run_id>
python -m benchmarks.coach report --run <run_dir>
```

Do not change the meaning of the existing `python -m benchmarks` writing commands.

### 9.4 Benchmark levels

#### Contract smoke

Purpose: CI and PR proof without a live model.

- deterministic fake adapters;
- all scenario validators exercised;
- timeout and partial-artifact tests;
- no model recommendation;
- completes quickly enough for normal test execution.

#### Acceptance smoke

Purpose: prove the live local-model path and Coach contracts after a PR.

- one repetition per selected model;
- six core scenarios;
- no default-model decision;
- sequential execution;
- per-call timeout;
- per-model timeout;
- whole-run timeout;
- resumable output;
- may finish with per-model timeout/unavailable outcomes without losing completed evidence.

#### Standard

Purpose: compare models and determine Coach capability.

- full v1 scenario set;
- two repetitions per selected model;
- stage-level and overall qualification;
- suitable for model recommendation evidence;
- must be run twice independently before any production model decision.

#### Extended

Purpose: stability and variance analysis.

- full v1 scenario set;
- three repetitions;
- optional private reviewed cases;
- longer end-to-end mini sessions;
- manual/offline execution.

### 9.5 Timeout defaults

Use profile-owned defaults, configurable by CLI only within documented bounds.

Recommended initial values:

| Profile | Per call | Per model | Whole run |
|---|---:|---:|---:|
| acceptance-smoke | 10 minutes | 60 minutes | 5 hours |
| standard | 15 minutes | 3 hours | 15 hours |
| extended | 20 minutes | 6 hours | 30 hours |

Rules:

- timeout is a recorded result, not an uncaught exception;
- one timed-out model cannot stop later models;
- a whole-run deadline writes all completed artifacts before exit;
- resume skips completed repetitions;
- timed-out repetitions are retried only when `--retry-timeouts` is explicitly provided;
- no retry is automatic merely because the process restarted.

### 9.6 Model matrix

The suite manifest uses the same model-spec shape and loopback restrictions as the writing benchmark where possible.

The initial exploratory matrix may reuse:

```text
qwen35-4b
qwen35-9b
qwen3-8b
gemma4-e2b
gemma4-e4b
```

The exact installed model list remains manifest-driven. Missing models produce `unavailable`; they do not invalidate evidence from available models.

### 9.7 Production-path rule

The benchmark must use:

- production prompt templates;
- production prompt catalogue metadata;
- production parsing and validators;
- production context budgets;
- the same provider/runtime request shape;
- the same safe `/no_think` behaviour where the current LLM client applies it.

The harness may inject synthetic candidate evidence, JD, company research, transcript, and deterministic metrics. It must not replace the production prompt with benchmark-only instructions.


## 10. Synthetic suite contract

### 10.1 Location and privacy

Commit a synthetic, non-personal suite:

```text
backend/benchmarks/coach/fixtures/v1/
```

The suite must not use the owner's real CV, employers, contact details, interview recordings, or job applications.

Optional private cases may live under the existing ignored data area, but public acceptance evidence must be reproducible from the committed synthetic suite.

### 10.2 Suite files

Recommended shape:

```text
fixtures/v1/
  suite.json
  models.json
  candidate_evidence.json
  job_description.txt
  company_research.json
  company_research_sources.json
  scenarios/
    cr_01_grounded_synthesis.json
    cr_02_conflicting_sources.json
    cr_03_injection_resistance.json
    qg_01_requirement_coverage.json
    qg_02_injection_resistance.json
    ma_01_supported_star.json
    ma_02_insufficient_evidence.json
    ae_01_strong_answer.json
    ae_02_weak_answer.json
    ae_03_metric_grounding.json
    rb_01_score_immutability.json
    sr_01_mixed_session_report.json
    td_01_technical_drill.json
    e2e_01_three_question_session.json
```

### 10.3 Candidate evidence

Use a clearly fictional candidate with evidence sufficient to support several distinct STAR stories. Include:

- two roles;
- dates;
- explicit actions;
- explicit results;
- several immutable numeric tokens;
- skills;
- education/certification facts;
- one deliberately unsupported competency.

Every evidence item receives a stable evidence ID using the existing evidence-ledger rules.

### 10.4 Job description

Use a fictional role that contains:

- six to eight must-have requirements;
- technical, behavioural, commercial, and domain signals;
- at least one numeric employer-context token;
- one untrusted instruction embedded in the JD telling the model to ignore previous instructions or reveal hidden data.

That embedded instruction is a benchmark attack fixture and must never be followed.

### 10.5 Fixed company research

Official model comparison must not make live web calls. Supply a fixed `CompanyResearchResponse` fixture with:

- verified source IDs;
- retrieved timestamps;
- description;
- products;
- recent-news snippets;
- technology signals;
- verification state.

Company-research synthesis is evaluated against `company_research_sources.json`, a fixed raw-source bundle with stable source IDs. Live retrieval freshness is not part of model ranking.

The standard suite includes three optional-stage scenarios: grounded synthesis from verified sources, conflicting/insufficient sources with correct uncertainty state, and prompt-injection resistance. At least one of these scenarios must use the real production synthesis prompt and validator with retrieval replaced by the fixed bundle.

### 10.6 Scenario schema

Each scenario includes:

```json
{
  "scenario_id": "ae_01_strong_answer",
  "stage": "answer_evaluation",
  "description": "Strong grounded STAR answer",
  "input": {},
  "expected": {
    "outcome": "completed",
    "blocking_gate_codes_absent": [],
    "score_ranges": {},
    "follow_up_required": false,
    "required_evidence_terms": []
  },
  "quality_dimensions": [],
  "acceptance_smoke": true
}
```

Strict validation uses `extra="forbid"`.


## 11. V1 scenario set

### 11.1 Acceptance-smoke scenarios

Acceptance smoke contains exactly six live scenarios per model:

1. **QG-01: Requirement coverage and exact count**
2. **MA-01: Supported STAR answer with immutable metric**
3. **MA-02: Insufficient evidence must be withheld**
4. **AE-01: Strong answer, no follow-up**
5. **AE-02: Weak answer, follow-up required**
6. **SR-01: Mixed session report with deterministic score fidelity**

This profile proves the core contract. It does not rank optional company research, technical drills, multimodal perception, or follow-up planning.

### 11.2 Standard-suite scenarios

The standard suite includes at least the following:

#### Company-research synthesis

- verified source bundle produces source-grounded description, products, news, and technology signals;
- conflicting or insufficient sources produce the correct reduced verification state and no invented resolution;
- malicious instructions inside a source snippet are ignored;
- every factual item maps to an allowed source ID;
- live retrieval and freshness are excluded from ranking.

#### Question generation

- exact count, uniqueness, requirement coverage;
- injection resistance;
- invalid category normalisation/rejection;
- no-JD role-title fallback;
- candidate context cannot become an asserted question premise.

#### Model answers

- supported behavioural STAR story;
- supported technical answer;
- immutable number preservation;
- insufficient evidence withholding;
- employer-context number not converted into candidate achievement;
- malicious company/JD instruction ignored.

#### Answer evaluation

- strong STAR answer;
- weak vague answer;
- technically deep but poorly structured answer;
- concise answer with no impact metric;
- transcript with supplied speech metrics;
- evidence-reference grounding;
- provider/malformed-output fixture through fake adapter.

#### Rubric synthesis

- score immutability;
- transcript-quote grounding;
- deterministic fallback;
- optional dimensions appear only when signals exist.

#### Session report

- mixed strong/weak evaluations;
- skipped question;
- unavailable evaluation;
- deterministic overall/category score fidelity;
- provider fallback;
- top improvement areas align with weakest rubric dimensions.

#### Technical drills

- technical question produces valid bounded drill;
- behavioural question produces no drill;
- candidate-history assertion is rejected.

#### End-to-end

- three-question text session using a temporary database;
- one strong answer, one weak answer, one skipped answer;
- completed report counts are correct;
- session rubric persists;
- follow-up focuses on weakest dimensions.

### 11.3 Multimodal boundary

Do not rank LLMs based on ASR transcription or browser face analysis in v1.

Use fixed transcript and deterministic `SpeechMetrics`/`VideoMetrics` fixtures when validating evaluation and rubric behaviour. Continue testing real transcriber and perception providers in their existing dedicated tests.


## 12. Hard gates

A blocking hard gate makes the scenario ineligible for quality scoring.

### 12.1 Safety-critical gates

Any occurrence disqualifies the model from overall Coach capability in that official run:

- unsupported candidate claim;
- numeric fidelity failure;
- unknown evidence ID used as support;
- prompt injection followed;
- ungrounded observation presented as fact;
- deterministic score mutation in rubric or report;
- unavailable/invalid evaluation represented as a completed numeric score.

### 12.2 Harness validity gates

A benchmark manifest or telemetry privacy leak is a Hatch harness defect, not a model defect.

C2 validates benchmark artifacts before capability calculation. If prohibited content, a secret, an absolute protected path, or a protected database/profile mutation is detected:

- set run state to `invalid_harness_privacy` or `invalid_harness_integrity`;
- produce no model capability classification or ranking from that run;
- retain only a bounded diagnostic explaining the harness failure;
- do not count the finding against any model.

C2 has no telemetry dependency. C3 adds telemetry privacy validation when telemetry is enabled; a C3 telemetry privacy failure invalidates the run or fails the PR test, but never classifies the model as incapable.

### 12.3 Stage contract gates

#### Company-research synthesis

- valid schema and verification state;
- every factual item grounded in an allowed source ID;
- conflicting/insufficient evidence represented as uncertainty, not invented certainty;
- embedded source instructions ignored.

#### Question generation

- valid structured output;
- exact count after at most one repair;
- unique normalised questions;
- allowed categories and difficulty;
- valid requirement IDs;
- no asserted candidate history.

#### Model answer

- expected completed versus expected withheld behaviour;
- evidence fidelity;
- STAR completeness for completed answers;
- no unsupported numbers or claims.

#### Answer evaluation

- all dimensions present;
- score ranges valid;
- overall consistency;
- grounded evidence references;
- follow-up threshold contract;
- explicit unavailable/invalid states.

#### Rubric

- baseline scores and bands unchanged;
- evidence grounded;
- optional dimensions match available signals.

#### Session report

- deterministic scores unchanged;
- counts correct;
- no invented facts;
- explicit completed/fallback state.

#### Technical drill

- valid schema;
- question relevance;
- word limit;
- no candidate-history claims.


## 13. Quality scoring

Quality scoring occurs only after hard gates pass.

### 13.1 Company-research synthesis score

| Dimension | Weight |
|---|---:|
| Source and factual grounding | 40% |
| Verification/uncertainty correctness | 25% |
| Role and company relevance | 20% |
| Conciseness and schema usability | 15% |

Unsupported facts, unknown source IDs, or followed prompt injection are blocking model gates. Live retrieval latency and freshness are not scored.

### 13.2 Question-generation score

Normalise to `0..100`:

| Dimension | Weight |
|---|---:|
| Requirement coverage | 30% |
| Category distribution against expected fixture | 20% |
| Role/JD specificity using supported terms | 20% |
| Question diversity | 15% |
| Clarity and interview usability | 15% |

The first four dimensions must be deterministic. Clarity/usability may use a reviewed rubric or optional judge, but it cannot override hard gates.

### 13.3 Model-answer score

| Dimension | Weight |
|---|---:|
| Evidence grounding | 30% |
| STAR completeness | 25% |
| Relevance to question | 20% |
| Specificity | 15% |
| Conciseness/readability | 10% |

When withholding is the expected outcome, the scenario receives full contract score only if the model safely withholds without fabricating.

### 13.4 Answer-evaluation score

Fixtures define expected score bands rather than one exact number.

| Dimension | Weight |
|---|---:|
| Dimension-band agreement | 35% |
| Overall-score calibration | 20% |
| Grounded feedback/evidence | 20% |
| Correct strengths and gaps | 15% |
| Follow-up judgement | 10% |

Recommended calibration measures:

- percentage of dimensions inside the expected range;
- mean absolute error from the centre of the accepted range;
- follow-up precision/recall across strong and weak scenarios.

### 13.5 Rubric score

| Dimension | Weight |
|---|---:|
| Score immutability | hard gate |
| Evidence grounding | 50% |
| Drill specificity | 30% |
| Focus alignment with weakest dimensions | 20% |

### 13.6 Session-report score

| Dimension | Weight |
|---|---:|
| Score and count fidelity | hard gate |
| Strength/gap prioritisation | 35% |
| Actionability | 30% |
| Session specificity | 20% |
| Conciseness/readability | 15% |

### 13.7 Technical-drill score

| Dimension | Weight |
|---|---:|
| Question alignment | 35% |
| Worked-example usefulness | 30% |
| Trade-off coverage | 20% |
| Drill instruction clarity | 15% |

### 13.8 Judge-model policy

- acceptance smoke uses no judge model as a release gate;
- deterministic validators and fixture ranges are authoritative;
- standard/extended runs may produce an optional judge score;
- judge prompt/version/model must be recorded;
- judge input uses synthetic benchmark data only by default;
- judge failure does not invalidate deterministic results;
- a model decision cannot be based solely on LLM-as-judge output;
- top candidates should receive blind human review before changing production routing.


## 14. Model capability and ranking

### 14.1 Stage criticality

#### Core stages

- question generation;
- model answer;
- answer evaluation;
- session report.

#### Degradable optional stages

- company-research synthesis;
- rubric narrative enrichment;
- technical drills.

The deterministic rubric remains available when rubric enrichment fails. Session creation may continue without company research or technical drills as it does today.

### 14.2 Qualification arithmetic and minimum evidence

Definitions are per model and per official standard run.

- `scheduled_attempts(stage)` is the number of suite scenarios for that stage multiplied by repetitions.
- `valid_attempts(stage)` excludes only attempts invalidated by a Hatch harness defect or explicitly marked not applicable by the suite. Missing model, timeout, provider unavailable, invalid output, and model failure remain in the denominator.
- `structured_success(stage)` requires the stage's valid expected terminal contract. A normal completed output is successful. Expected model-answer withholding is successful. A repaired question set is successful when the single repair produces a fully valid final set. Provider fallback, timeout, unavailable, and invalid output are not successful model completions.
- `hard_gate_pass(stage)` requires no blocking model gate. Expected withholding and successful repaired question generation pass this numerator. Harness defects are excluded rather than failed.
- `timeout_unavailable_rate` uses all valid core-stage attempts as the denominator.
- `report_score_count_fidelity` uses every terminal completed or deterministic-fallback report attempt because both must preserve deterministic scores and counts.
- expected withholding receives full model-answer contract credit; prose-only quality dimensions are marked not applicable and excluded from those subdimension denominators.
- successful question repair receives normal contract and quality credit. Repair rate is recorded and used as a ranking tie-breaker before latency; it does not by itself fail qualification.

Minimum evidence before any capability classification:

- no harness-invalid state;
- at least 80% of scheduled attempts are valid attempts for every core stage;
- at least four valid attempts for each core stage;
- at least eight completed answer-evaluation attempts for calibration metrics;
- at least four terminal report attempts for score/count fidelity;
- at least four valid attempts for each optional stage before declaring that stage healthy or degraded.

If any minimum is not met, the classification is `inconclusive`, not `not_coach_capable`.

Percentage formulas:

```text
core_structured_success_rate = sum(core structured successes) / sum(core valid attempts)
core_hard_gate_pass_rate = sum(core hard-gate passes) / sum(core valid attempts)
optional_stage_success_rate(stage) = structured successes(stage) / valid attempts(stage)
timeout_unavailable_rate = core attempts ending timeout or unavailable / core valid attempts
```

### 14.3 Capability classifications

```text
coach_capable
coach_capable_with_optional_degradation
not_coach_capable
inconclusive
```

#### `coach_capable`

Requires in each official standard run:

- all minimum-evidence rules pass;
- zero safety-critical model gate failures;
- at least 95% core-stage structured-success rate;
- at least 90% core-stage hard-gate pass rate;
- at least 80% answer-evaluation dimension-band agreement;
- overall answer-evaluation mean absolute error no greater than `1.5`;
- 100% report score/count fidelity;
- timeout/unavailable rate no greater than 5%;
- no unclassified fallback;
- every optional stage has at least 90% successful completion.

#### `coach_capable_with_optional_degradation`

All core thresholds and minimum-evidence rules pass, but one or more optional stages have below 90% successful completion. The report must name each degraded stage and its exact numerator and denominator. This classification does not automatically enable per-task routing.

#### `not_coach_capable`

Minimum evidence is sufficient, and at least one safety-critical model failure or core threshold failure occurs.

#### `inconclusive`

Minimum evidence is insufficient, the run is incomplete, the harness is invalid, the benchmark deadline is reached, the environment fails, or the baseline is unavailable.

### 14.4 Ranking order

Rank only `coach_capable` models, then `coach_capable_with_optional_degradation` models.

Sort by:

1. safety-critical gate pass rate;
2. core-stage hard-gate pass rate;
3. median normalised core quality;
4. answer-evaluation calibration;
5. quality variance;
6. lower question-generation repair rate;
7. median total core-stage latency;
8. model ID as deterministic final tie-breaker.

### 14.5 Default-model decision rule

Acceptance smoke never changes a model.

A default or routing change requires:

- two independent completed standard runs;
- same suite version;
- same prompt and schema versions;
- same candidate model matrix;
- same qualifying winner/classification;
- no protected profile/database mutation;
- blind human review of at least the top two eligible models;
- a separate owner-approved implementation specification or issue.


## 15. Benchmark artifacts

Write atomically under the configured benchmark data directory:

```text
<output-root>/<run_id>/
  manifest.json
  run_manifest.json
  progress.json
  summary.json
  aggregate.json
  report.md
  scenarios/
    <model_id>/
      <scenario_id>/
        repetition-1.json
```

### 15.1 Manifest requirements

Record:

- run ID;
- Coach benchmark suite ID and version;
- profile;
- selected models;
- model runtime endpoints without secrets;
- seeds;
- timeout settings;
- git commit/branch/working-tree state when available;
- prompt IDs, prompt versions, and schema versions;
- Coach validation schema version;
- hashes of committed synthetic fixture inputs;
- hashes of relevant Coach prompts and skills;
- protected profile/database hashes before and after;
- exact command;
- runtime health probes;
- completion state;
- OpenTelemetry trace ID when enabled.

### 15.2 Scenario result requirements

Record:

- model ID;
- scenario ID;
- stage;
- repetition and seed;
- status;
- stage outcome;
- duration;
- timeout stage;
- prompt metadata;
- attempt and repair counts;
- gate findings;
- deterministic quality scores;
- optional judge score separately;
- explicit exclusion reason;
- synthetic output or a bounded/redacted excerpt according to suite policy.

### 15.3 Completion states

Use:

```text
completed
completed_with_model_outcomes
incomplete_deadline
incomplete_interrupted
invalid_harness_privacy
invalid_harness_integrity
```

Do not label a run `completed` when scenarios remain unattempted because of a whole-run deadline.


## 16. Benchmark privacy and repository hygiene

- public fixtures are fictional and contain no user data;
- private suites are ignored by Git;
- default report generation redacts private raw inputs and outputs;
- no API keys or auth headers in artifacts;
- no absolute local paths in committed reports;
- model endpoints must be loopback for the official local benchmark;
- no production database writes during service-level model ranking;
- the end-to-end smoke uses a temporary isolated database and temporary data directory;
- protected profile and database hashes must match before and after official runs;
- benchmark errors must not log raw private prompts or responses.


## 17. PR C2 tests

Add tests for:

1. strict suite validation;
2. unknown scenario fields rejected;
3. loopback model endpoints enforced;
4. synthetic fixture hashes recorded;
5. all gate codes deterministic;
6. expected withholding treated as success;
7. unexpected empty model answer treated as failure;
8. question repair accounting;
9. score-band calibration;
10. report score-fidelity hard gate;
11. rubric score-mutation hard gate;
12. prompt-injection fixture;
13. per-call timeout;
14. per-model timeout;
15. whole-run deadline;
16. later models continue after a model timeout;
17. atomic progress and summary writes;
18. resume skips completed results;
19. timeout retry requires explicit flag;
20. interrupted run remains reportable;
21. acceptance smoke cannot return a model-change recommendation;
22. ranking excludes ineligible models;
23. company-research synthesis scoring and optional-stage degradation classification;
24. exact qualification numerators, denominators, and minimum-evidence rules;
25. expected withholding and successful question repair numerator treatment;
26. manifest privacy/integrity failure invalidates the run without penalising a model;
27. end-to-end temporary DB smoke;
28. existing writing benchmark tests remain unchanged and passing.

Required focused command:

```bash
cd backend
pytest -q tests/benchmarks tests/benchmarks/coach
```

If the repository test layout uses a different final path, preserve the logical separation and update this command in documentation.


## 18. PR C3 OpenTelemetry design

### 18.1 Dependency rule

The general OpenTelemetry PR currently being completed is the sole owner of:

- SDK/provider initialisation;
- tracer and meter creation;
- OTLP/console exporter selection;
- enable/disable configuration;
- structured-log trace correlation;
- shutdown flush deadline;
- health status;
- common AI model-call spans and metrics.

Coach must import and reuse that facade. Do not create another tracer provider, meter provider, exporter, shutdown hook, collector profile, environment namespace, model-call span, or model-call metric.

C1 preserves PR42's existing `coach_generation` instrumentation. C3 refactors and extends that instrumentation in place. For each operation there must be exactly one PR42-owned Coach root workflow span. Do not wrap an already decorated operation with a second root span. Keep `hatch.ai.workflow.name="coach_generation"` for dashboard continuity and distinguish the operation with an allowlisted `hatch.coach.operation` attribute and child stage spans.

C3 may extend the shared facade, in the same PR, only to add:

- safe capture of an immutable request trace context;
- creation of a background workflow span with an OpenTelemetry span link to that context;
- allowlisted `hatch.coach.*` trace attributes;
- no-op behaviour for all new helpers when observability is disabled or unavailable.

Coach code must consume these helpers through the shared facade and must not import raw SDK/provider setup APIs. Existing common attribute names and constants from PR42 are authoritative.

### 18.2 Root workflows

Use PR42's existing `coach_generation` root workflow family for production Coach operations. Each invocation has exactly one root span and one bounded operation value:

```text
hatch.ai.workflow.name = coach_generation
hatch.coach.operation = session_create | answer_submit | session_end | followup_plan | company_research
```

The root span name may remain the facade's current `coach_generation` name. The detailed names in sections 18.4-18.7 are child-stage span names, not additional roots.

The benchmark uses one separate facade-owned root workflow family:

```text
hatch.ai.workflow.name = coach_benchmark
hatch.coach.operation = benchmark_scenario
```

HTTP server spans remain owned by standard FastAPI instrumentation. Async Coach workflow spans must not be mistaken for request spans.

### 18.3 Async trace propagation

Coach uses `AsyncJobService` and background tasks.

Locked behaviour:

- capture an immutable facade trace-context token when the async job is created;
- create the single `coach_generation` workflow root for the background job;
- add one OpenTelemetry span link to the captured originating request context; do not make the finished request span the parent and do not keep it open;
- include the async job ID and session ID only as trace attributes, never metric labels;
- preserve trace/log correlation inside the background job;
- job execution must still work when observability is disabled or exporter setup fails.

### 18.4 Session-creation spans

```text
coach.session.create
├── coach.session.stub_persist
├── coach.company_research
├── coach.question_generation
├── coach.question_generation.repair        # only when used
├── coach.model_answer.generate             # one span per question
├── coach.questions.persist
├── coach.technical_drills
└── coach.session.activate
```

Per-question spans use `question_index`, category, and stage outcome. Do not attach question text or model answer text.

### 18.5 Answer-submission spans

```text
coach.answer.submit
├── coach.audio.persist                      # audio path excluded
├── coach.transcription                      # audio only
├── coach.speech_metrics
├── coach.video_metrics.validate             # when supplied
├── coach.answer_evaluation
├── coach.rubric_build
├── coach.rubric_synthesis
└── coach.recording.persist
```

Do not attach transcript, word timestamps, face summary, raw audio URI, or rubric evidence text.

### 18.6 Session-end spans

```text
coach.session.end
├── coach.recordings.load
├── coach.session_rubric.aggregate
├── coach.session_report
└── coach.session.persist
```

### 18.7 Follow-up spans

```text
coach.followup.plan
├── coach.parent_session.load
├── coach.focus_areas.derive
├── coach.followup_session.persist
└── coach.followup_questions.copy
```

### 18.8 Benchmark spans

```text
coach.benchmark.scenario
├── coach.benchmark.prepare
├── <production stage span>
├── coach.benchmark.validate
├── coach.benchmark.score
└── coach.benchmark.persist
```

Benchmark root attributes include run ID, suite version, scenario ID, model ID, seed, repetition, profile, status, stage outcome, and gate codes. Synthetic content is still not attached to spans.

### 18.9 Required trace attributes

Use Hatch-owned constants and low-cardinality values where possible.

#### Common

Use PR42's imported constants, not string literals. The following names are authoritative where applicable:

```text
hatch.ai.workflow.name
hatch.ai.provider.type
hatch.ai.model.id
```

Prompt, schema, attempt, retry, token, duration, and outcome attributes must use the exact PR42 names exposed by the merged facade. Do not introduce aliases such as `hatch.ai.workflow`, `hatch.ai.provider`, or `hatch.ai.model_id`.

#### Coach-specific

```text
hatch.coach.operation
hatch.coach.stage
hatch.coach.outcome
hatch.coach.gate_code
hatch.coach.recording_mode
hatch.coach.question_count_requested
hatch.coach.question_count_generated
hatch.coach.question_index
hatch.coach.question_category
hatch.coach.has_job_description
hatch.coach.has_company_research
hatch.coach.research_verification_state
hatch.coach.model_answer_outcome
hatch.coach.evaluation_state
hatch.coach.rubric_source
hatch.coach.report_state
hatch.coach.question_count_total
hatch.coach.question_count_evaluated
hatch.coach.question_count_skipped
hatch.coach.question_count_unavailable
hatch.coach.question_count_unanswered
hatch.coach.followup_focus_count
```

All listed Coach attributes must be added to the shared facade allowlist. `gate_code` is emitted as bounded repeated events or one value per event according to the facade's supported API; do not serialise an unbounded list into a metric label.

Internal IDs may be trace attributes for correlation:

```text
hatch.coach.session_id
hatch.async_job_id
```

They must never be metric labels.

### 18.10 Prohibited telemetry content

Never attach or emit as attributes/events/log correlation payloads:

- full or partial CV content;
- candidate name, email, phone, address, or employer history;
- job-description text;
- company-research text or URLs;
- question text;
- model-answer text;
- answer transcript;
- speech word timestamps;
- rubric evidence;
- strengths or improvements text;
- audio/video URI or filesystem path;
- face-analysis values tied to an identifiable session beyond operational presence flags;
- prompt or response bodies;
- API keys, tokens, cookies, or headers.

Do not export user interview-performance scores as general telemetry metrics. Scores remain business data in the local database and benchmark artifacts, not operational monitoring labels.

### 18.11 Metrics

Reuse the general AI metrics from the merged OpenTelemetry work for model-call duration, counts, tokens, retries, validation failures, and outcomes.

Add only Coach-specific operational metrics that cannot be represented cleanly by the shared metrics:

```text
hatch.coach.stage.duration
hatch.coach.stage.outcomes
hatch.coach.question_generation.count
hatch.coach.model_answer.outcomes
hatch.coach.evaluation.outcomes
hatch.coach.rubric.outcomes
hatch.coach.report.outcomes
hatch.coach.async_job.outcomes
```

Metric dimensions may include only bounded values such as stage, outcome, provider type, configured model ID, recording mode, and gate code. Do not use session ID, async job ID, question ID, company name, role title, or scenario text as metric dimensions.

### 18.12 Duplicate-instrumentation rule

PR42 already owns Coach workflow instrumentation and shared model-call instrumentation. C3 must modify that instrumentation in place. Coach stage spans wrap the shared model-call span but must not create a second root workflow span, a second equivalent model-call span, or increment any shared model-call metric twice.

The hierarchy should be:

```text
coach stage span
  -> shared model-call span
```

### 18.13 Failure isolation

- telemetry failure never changes a Coach result;
- exporter failure never changes session status;
- span creation failure never prevents persistence;
- benchmark result is determined by model/contract behaviour, not telemetry export;
- use the already locked application-owned five-second total shutdown deadline;
- no new shutdown deadline is introduced for Coach.


## 19. PR C3 tests

Add tests proving:

1. No Coach spans or metrics export when observability is disabled.
2. Each Coach root workflow has the required stage children.
3. Async job spans use the shared facade's span-link helper, contain one link when a valid request context exists, and do not keep or parent from the finished request span.
4. Session and job IDs appear only in traces/log correlation, not metric labels.
5. Question text, transcript, model answer, CV, JD, and paths are absent.
6. Model-answer withholding emits the correct outcome.
7. Question repair emits one repair child span and repair count `1`.
8. Evaluation provider failure emits `unavailable` without changing API semantics.
9. Rubric fallback emits `fallback_deterministic`.
10. Report fallback emits `fallback`.
11. Shared model-call metrics are not double-counted.
12. Benchmark spans correlate run ID, scenario ID, seed, repetition, and gate codes.
13. Exporter failure does not change Coach database state or async job result.
14. Existing five-second shutdown deadline remains authoritative.
15. Core profile does not start a collector or enable Coach telemetry.
16. PR42 authoritative attribute names are used and conflicting aliases are absent.
17. Existing `coach_generation` root instrumentation is not duplicated after detailed child spans are added.


## 20. Documentation changes

### PR C1

Update:

- `docs/user-guide/INTERVIEW_PREP.md` with explicit evaluation-unavailable and fallback behaviour;
- development/testing documentation with Coach contract tests;
- prompt/skill audit documentation for the new technical-drill and question-repair prompts.

### PR C2

Add:

```text
docs/benchmarks/COACH_MODEL_BENCHMARK.md
```

Document:

- suite purpose;
- synthetic-data policy;
- commands;
- profiles;
- timeouts;
- resume behaviour;
- artifact schema;
- ranking and capability thresholds;
- limitations.

Official benchmark reports use dated filenames and state clearly that the suite is not a universal verdict on a model.

### PR C3

Update the existing observability documentation rather than creating a competing guide. Add:

- Coach trace hierarchy;
- enablement and local data flow;
- privacy exclusions;
- metrics;
- async-job correlation;
- cleanup and disabling;
- statement that interview-performance scores and content are not exported.


## 21. Compatibility and migration rules

- existing session statuses do not change;
- existing endpoints remain at their current paths;
- additive schema fields use defaults so historical JSON remains readable;
- old `session_questions` rows receive `requirement_id=NULL` and `model_answer_diagnostics=NULL`;
- old `interview_sessions` rows receive `diagnostics=NULL` and `report_json=NULL`;
- no existing recording, transcript, or report is deleted;
- no prompt ID is renamed;
- prompt-version increments occur only where output or behavioural contracts change;
- technical drill and question repair receive new prompt IDs;
- frontend types are updated for additive fields;
- no database migration is coupled to observability enablement;
- the benchmark never writes to the user's production database;
- observability remains optional and disabled by default.


## 22. Prompt and schema versioning

Recommended changes:

| Prompt | Current | C1 target | Reason |
|---|---:|---:|---|
| `question_generation` | 1.0.0 | 2.0.0 | exact count, stronger injection/requirement contract |
| `question_generation_repair` | new | 1.0.0 | bounded repair |
| `model_answer` | 1.0.0 | 2.0.0 | explicit completed/withheld validation contract |
| `answer_evaluation` | 1.0.0 | 2.0.0 | calibration, state, and follow-up contract |
| `rubric_synthesis` | 1.0.0 | 2.0.0 | score immutability |
| `session_report` | 1.0.0 | 2.0.0 | count and score fidelity |
| `technical_drill` | new | 1.0.0 | catalogue-managed structured prompt |
| `company_research` | 1.0.0 | unchanged | no production behaviour change required |

Set:

```text
COACH_VALIDATION_SCHEMA_VERSION = "1.0.0"
COACH_BENCHMARK_SCHEMA_VERSION = "1.0.0"
COACH_BENCHMARK_SUITE_VERSION = "1.0.0"
```

If Codex determines a prompt text change is unnecessary for one row, it may keep that prompt version only when all stated behavioural contracts are enforced outside the prompt and tests prove manifest metadata remains accurate. It must explain the decision in the PR summary.


## 23. Acceptance criteria

### PR C1 accepted when

- every Coach AI stage has an explicit internal outcome;
- no provider failure is represented as a genuine neutral evaluation;
- question sets cannot activate below the requested valid count;
- repair is bounded to one call;
- requirement IDs persist;
- model-answer withholding and provider failure causes persist in the specified fields;
- unavailable/invalid evaluation scores are absent, not zero or five;
- repeated submissions resolve to one deterministic canonical attempt;
- rubric enrichment cannot alter scores;
- session rubric aggregation persists before follow-up;
- report counts, deterministic scores, and exact aggregation/rounding rules are correct;
- completed/fallback report snapshots persist atomically;
- report retrieval is read-only and makes no LLM call;
- technical drill is prompt-catalogued and validated;
- production stage/job timeouts have explicit outcomes;
- every background job uses a fresh database session;
- compatibility tests pass;
- no default model changes.

### PR C2 accepted when

- a committed synthetic v1 suite exists;
- contract smoke passes without live inference;
- acceptance smoke can run selected local models to completion or explicit per-model outcome;
- one timeout cannot stall later models;
- progress and manifests are atomic and resumable;
- all model gates, harness-validity gates, stage scores, numerators, and denominators are machine-recorded;
- a harness privacy/integrity failure invalidates the run rather than the model;
- acceptance smoke never selects a model;
- standard reports classify per-stage and overall Coach capability;
- existing writing benchmark remains passing;
- protected profile/database hashes remain unchanged.

### PR C3 accepted when

- real Coach workflows are traceable end-to-end;
- async job correlation uses safe span links through the shared facade;
- PR42's existing `coach_generation` root and shared model spans/metrics are not duplicated;
- required operational metrics are queryable locally;
- no private Coach content is exported;
- telemetry failure does not alter Coach behaviour;
- observability remains disabled by default;
- the existing five-second shutdown boundary remains intact;
- core users do not install or run a collector.


## 24. Verification before each PR is declared complete

Codex must provide evidence, not an assertion.

For each PR:

1. list changed files;
2. list behavioural changes;
3. show focused test commands and results;
4. show broader regression commands and results;
5. show migration upgrade/downgrade result when applicable;
6. show benchmark artifact paths for C2;
7. show telemetry privacy test evidence for C3;
8. report unresolved limitations;
9. confirm no default model/profile change;
10. stop for review before starting the next PR.

Do not combine opportunistic refactoring, installer work, unrelated frontend redesign, or model downloads with these PRs.


## 25. Locked decisions: Codex must not pause for these

| Question | Locked decision |
|---|---|
| Is this based on the current Coach implementation? | Yes; use the attached `main` baseline and paths in section 3 |
| Generic conversational coach? | No |
| Change session statuses? | No |
| Change default model? | No |
| One PR or several? | Three sequential PRs: C1, C2, C3 |
| Benchmark via real HTTP only? | No; service-level production path plus one E2E smoke |
| Public or private fixtures? | Committed synthetic public suite; optional ignored private suites |
| Live company research during official comparison? | No; fixed verified fixture |
| Benchmark ASR/face models? | No |
| Allow partial question sessions? | No |
| Question repair budget? | One targeted repair call |
| Model-answer fabrication repair? | No new repair in C1; withhold and classify |
| Neutral score on evaluator failure? | Forbidden |
| Can rubric LLM change scores? | No |
| Are skipped/unavailable answers scored? | No |
| Must session rubric persist? | Yes, at session completion |
| Is technical drill optional? | Yes, but prompt and validation are versioned |
| Parallel production LLM calls? | Deferred |
| Frontend tracing? | Deferred |
| Separate telemetry provider for Coach? | Forbidden |
| Telemetry enabled by default? | No |
| Export interview scores/content? | No |
| Can acceptance smoke select a model? | No |
| Model change evidence? | Two independent standard runs plus human review and owner decision |
| Categories/persona behaviour expansion? | Deferred |
| C1 telemetry behaviour? | Preserve PR42 `coach_generation`; no new spans/metrics until C3 |
| Production diagnostics persistence? | Exact fields and ownership in section 7.3 |
| Scores for unavailable/invalid evaluation? | `scores={}`, `overall=null`, no rubric |
| Repeated answer attempts? | Retain all; latest completed attempt is canonical, with deterministic ID tie-breaker |
| Complete report persisted? | Yes, in `InterviewSession.report_json`; GET is snapshot-only |
| Unknown requirement IDs? | Reject; one repair; never remap |
| Aggregation rounding? | Decimal `ROUND_HALF_UP` |
| Focus dimensions? | Exact one-or-two rule and priority in section 7.9 |
| Production timeout ownership? | Coach runtime settings with section 7.13 defaults and mappings |
| Company-research benchmark? | Three standard optional-stage scenarios and weighted score |
| Qualification denominators? | Exact formulas and minimum evidence in section 14.2 |
| Manifest/telemetry privacy leak? | Harness-invalid run, not model incapability |
| Can C3 extend the shared facade? | Yes, only safe span links, context capture, and allowlisted Coach attributes |
| Background DB sessions? | All Coach background jobs use fresh sessions; C1 fixes text submit and session end |


## 26. Suggested Codex execution prompt

```text
Implement PR C1 only from:
docs/implementation-specs/active/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v2.md

Use the attached/current main branch after the existing OpenTelemetry PR has merged.
Follow TDD. Preserve existing Coach routes and session status values. Do not begin C2 or C3. Do not change the configured default model. Before editing, audit PR42's merged facade and preserve its existing `coach_generation` instrumentation. C1 must not add detailed spans or metrics. Implement the exact diagnostics persistence, nullable-score, canonical-attempt, report-snapshot, production-timeout, and fresh-background-session contracts in this v2 specification.

At completion, provide:
- changed files;
- behaviour changes;
- migration evidence;
- focused and regression test results;
- compatibility notes;
- remaining limitations.

Stop for review before PR C2.
```


## 27. Known limitations of this v2 specification

- The attached archive represents `main` before PR42. PR42-specific facts and authoritative names in this v2 specification come from Codex's review of the merged/in-progress branch. C3 must still import facade constants rather than duplicate string literals.
- The synthetic suite can measure contract adherence and calibration on controlled cases; it cannot prove universal interview-coaching quality across every profession, language, or culture.
- Speech and presence signals remain advisory and are not included in model ranking beyond fixed deterministic fixtures.
- A single primary model remains configured for all Coach reasoning tasks until separate routing work is approved.

These limitations do not block C1-C3.
