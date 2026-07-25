# Coach Phase 1 PR3 Evaluation, Coaching, and Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver V6 PR3 named evaluation, immutable-evidence grounding, fact-safe coaching, bounded adaptive follow-ups, transcript re-evaluation, explicit acceptance, review UI, and conversational benchmark smoke evidence on top of merged PR1 and PR2.

**Architecture:** Keep `legacy_v1` numeric evaluation untouched and route `conversational_v1` through focused deterministic validators around bounded model proposals. PR3 consumes PR1 command/version/repository primitives and PR2 attempt-pipeline stage ownership, then persists evaluator, grounding, follow-up, and coaching results only through generation-fenced transactions. The browser renders the server `/live` review projection and sends versioned commands; it never derives acceptance, rubric state, or follow-up admission locally.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, SQLite/Alembic, pytest/pytest-asyncio; Next.js 15.5, React 18, TypeScript 5, Vitest/Testing Library, Playwright; existing `backend/benchmarks/coach` harness.

## Global Constraints

- V6 at `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md` is the sole Phase 1 technical authority; its SHA-256 when this plan was written is `626381be8963340972711bdfa5e47df0c82d521bb4e22ad75f3f873022c19ae8`.
- Approved integration design SHA-256 is `992f9693d82b5146770e5e002f6f8d7f2485d34716e89d0d6a775662c134ece6`; it adds delivery gates but cannot amend V6 contracts.
- Branch from `feature/coach-phase1-phase2` only after PR1 and PR2 are merged; use head `phase1/pr3-evaluation-coaching-followups` and target `feature/coach-phase1-phase2`. Never base PR3 on an unmerged sibling.
- Preserve `SessionRecording` as the physical attempt aggregate. Do not create an `InterviewAttempt` table or replace existing async-job, repository, reconciliation, provider-routing, or observability patterns.
- Keep `legacy_v1` schemas, numeric evaluation, `AnswerEvaluatorService`, `rubric_builder.py`, reports, routes, video/tone records, and canonical-attempt behavior unchanged.
- New conversational levels are exactly `needs_work`, `developing`, `interview_ready`, `strong`, `not_assessed`; expose no numeric score, readiness percentage, `vocal_confidence`, emotion, personality, deception, presence, or culture-fit judgement.
- Follow-up reasons are exactly `clarify_example`, `measurable_result`, `personal_action`, `reasoning`, `role_depth`, `resolve_ambiguity`, `evidence_consistency`; the application-enforced maximum is two persisted adaptive follow-ups per planned root question.
- Evidence statuses are exactly `supported`, `partially_supported`, `not_found`, `conflicting`, `not_verifiable`; `not_found` must never assert falsehood.
- Transcript/evidence spans use zero-based Unicode code-point half-open offsets over NFC/LF-normalized text; frontend code must convert code-point offsets rather than call JavaScript `slice()` directly.
- Treat transcript, CV, job, Question Bank, company research, evidence, model output, IDs, and metadata as untrusted. Prompts separate system contract, trusted metadata, and untrusted content; strict schemas plus application validation own all state changes.
- Model failures, schema exhaustion, grounding failures, and provider timeouts yield `unavailable`/`not_assessed` and no partial persistence; they never lower candidate levels.
- One structured-output repair is allowed by default and remains inside PR2's absolute processing deadline and retry budget.
- Benchmarks and active adversarial tests use bounded synthetic data only in an isolated local/ephemeral environment. Never run probes against production, shared services, or real-user data.
- No transcript, evidence, CV, prompt/model body, raw identifier, user path, raw media, token, or secret may appear in logs, metrics, traces, diagnostics, benchmark evidence, or PR evidence.
- Keep `HATCH_COACH_CONVERSATIONAL_ENABLED` disabled until acceptance evidence authorizes rollout; PR3 must not alter its default.
- Phase 2 is forbidden: do not add Candidate Intelligence entities/findings/confidence bands/governance gateways, mentor personas, weakness-driven multi-session plans, or candidate-source mutation.
- PR4 remains excluded: no report/progress builder or UI, deletion/export workflows, observability expansion, support diagnostics, standard/extended conversational benchmark, documentation rollout, or feature-flag enablement.
- PR3 permits candidate self-assessment only while the conversational session is active in `awaiting_next_action` or `coaching`. PR3 must reject it from `completed` and omit it from completed `/live.allowed_commands`; PR4 exclusively adds completed-session `record_self_assessment` in one atomic transaction with V6 §29.8 report invalidation and rebuild claim.
- Every behavior change follows RED → minimal GREEN → focused regression → commit. Do not combine specification-compliance and code-quality review; compliance must pass first.

---

## PR1/PR2 Prerequisites and Locked Interfaces

Execution stops before Task 1 unless PR1 and PR2 are merged into the integration branch and the inspected signatures are semantically equivalent to these contracts. Adapt import locations to the merged code only when names moved without changing behavior; material differences are a V6 stop condition and require the earlier PR to be corrected.

```python
# PR1: backend/app/services/coach_conversational_contracts.py
CONVERSATION_COMMAND_CONTRACT = "coach_conversation_command_v1"
LIVE_VIEW_CONTRACT = "coach_live_view_v1"
RUBRIC_CONTRACT = "coach_conversational_rubric_v1"
EVIDENCE_GROUNDING_CONTRACT = "coach_evidence_grounding_v1"
FOLLOW_UP_CONTRACT = "coach_follow_up_v1"
DELIVERY_POLICY = "coach_delivery_policy_v1"

# PR1: backend/app/repositories/conversational_session_repository.py
class ConversationalSessionRepository:
    async def get_attempt_processing_snapshot(
        self, *, recording_id: str, processing_generation: int
    ) -> AttemptProcessingSnapshot | None: ...

    async def finalise_attempt_processing(
        self, *, claim: AttemptProcessingClaim, result: AttemptProcessingResult
    ) -> bool: ...  # one transaction; False for every stale predicate

    async def create_transcript_version(
        self, *, recording_id: str, source: str, transcript: str,
        expected_attempt_version: int, processing_generation: int
    ) -> InterviewTranscriptVersion: ...

    async def create_evaluation_version(
        self, *, recording_id: str, transcript_version_id: str | None,
        evaluation_version: int, processing_generation: int,
        contract_version: str, state: str,
        async_job_id: str | None = None
    ) -> InterviewAttemptEvaluation: ...

    async def accept_attempt(
        self, *, session_id: str, question_id: str, attempt_id: str,
        expected_state_version: int
    ) -> AcceptanceResult: ...

    async def create_follow_up_question(
        self, *, claim: FollowUpAdmissionClaim
    ) -> FollowUpCreationResult: ...

# PR1: backend/app/services/coach_conversation_commands.py
class ConversationCommandService:
    async def execute(
        self, *, user_id: str, session_id: str,
        request: ConversationCommandRequest
    ) -> ConversationCommandResult: ...

# PR2: backend/app/services/coach_attempt_pipeline.py
class AttemptStage(Protocol):
    name: str
    async def run(self, context: AttemptProcessingContext) -> StageResult: ...

@dataclass(frozen=True)
class AttemptProcessingContext:
    session_id: str
    question_id: str
    recording_id: str
    transcript_version_id: str | None
    evaluation_version_id: str
    processing_generation: int
    deadline_at: datetime
    recording_type: Literal["text", "audio"]
    normalized_transcript: str | None
    speech_metrics: SpeechMetricsSnapshot | None
    evidence_records: tuple[SessionEvidenceSnapshot, ...]

# PR2 invariant: edit/retry claim transaction writes attempt_state="pending_processing",
# increments processing_generation, creates pending stage rows and async job, then dispatches.
```

Prerequisite verification:

```bash
git fetch origin
git checkout feature/coach-phase1-phase2
git pull --ff-only origin feature/coach-phase1-phase2
git log --merges --oneline --decorate -10
git status --short
git switch -c phase1/pr3-evaluation-coaching-followups
git merge-base --is-ancestor 3985da09 HEAD
git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
sha256sum docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md
python scripts/check_docs.py
```

Expected: PR1 and PR2 merge commits are visible in order, the worktree is clean, the ancestry and tracked-file checks exit 0, hashes are recorded, and docs checks pass. Record the integration-base SHA, new branch SHA, Python/Node/npm versions, and the four authority hashes in the PR evidence bundle.

## File Structure

Create or modify only the following PR3 implementation surfaces after prerequisites pass:

```text
backend/app/schemas/coach_conversation.py                    conversational read/write schemas
backend/app/services/coach_conversational_contracts.py      centralized PR3 versions/enums/mappings/errors
backend/app/services/coach_text_spans.py                     NFC/LF normalization and code-point span validation
backend/app/services/coach_delivery_policy.py                deterministic delivery buckets and named level
backend/app/services/coach_conversational_evaluator.py       strict content evaluation, derivation, repair
backend/app/services/coach_evidence_grounder.py              claim/source validation and consistency derivation
backend/app/services/coach_coaching.py                       deterministic skeleton and bounded enrichment
backend/app/services/coach_followup_policy.py                proposal validation and admission decision
backend/app/services/coach_attempt_pipeline.py               register PR3 stages after PR2 transcription/speech stages
backend/app/services/coach_conversation_commands.py          edit/coaching/accept command handlers
backend/app/services/coach_live_view.py                       server-authored reflection and allowed-command projection
backend/app/repositories/conversational_session_repository.py fenced PR3 persistence and atomic follow-up admission
backend/app/routers/coach_conversation.py                    existing command/live route wiring only
backend/app/prompts/coach_conversational_evaluation.j2       separated evaluator prompt contract
backend/app/prompts/coach_evidence_grounding.j2              separated grounding prompt contract
backend/app/prompts/coach_follow_up.j2                       separated follow-up prompt contract
backend/app/prompts/coach_coaching.j2                        separated coaching-enrichment prompt contract
backend/tests/test_services/test_coach_text_spans.py
backend/tests/test_services/test_coach_delivery_policy.py
backend/tests/test_services/test_coach_conversational_evaluator.py
backend/tests/test_services/test_coach_evidence_grounder.py
backend/tests/test_services/test_coach_coaching.py
backend/tests/test_services/test_coach_followup_policy.py
backend/tests/test_services/test_coach_attempt_pipeline.py
backend/tests/test_services/test_coach_conversation_commands.py
backend/tests/test_services/test_coach_live_view.py
backend/tests/test_repositories/test_conversational_session_repository.py
backend/tests/test_routers/test_coach_conversation_router.py
frontend/src/lib/api.ts                                     PR3 conversational review types/helper reuse
frontend/src/components/coach/conversation/AnswerReview.tsx
frontend/src/components/coach/conversation/TranscriptEditor.tsx
frontend/src/components/coach/conversation/AttemptHistory.tsx
frontend/src/components/coach/conversation/CodePointExcerpt.tsx
frontend/src/components/coach/conversation/__tests__/AnswerReview.test.tsx
frontend/src/components/coach/conversation/__tests__/TranscriptEditor.test.tsx
frontend/src/components/coach/conversation/__tests__/AttemptHistory.test.tsx
frontend/e2e/coach-conversational-review.spec.ts
backend/benchmarks/coach/contracts.py
backend/benchmarks/coach/profiles.py
backend/benchmarks/coach/suite_loader.py
backend/benchmarks/coach/production_adapter.py
backend/benchmarks/coach/scoring.py
backend/benchmarks/coach/validators.py
backend/benchmarks/coach/fixtures/conversational_v1/suite.json
backend/benchmarks/coach/fixtures/conversational_v1/models.json
backend/benchmarks/coach/fixtures/conversational_v1/evidence.json
backend/benchmarks/coach/fixtures/conversational_v1/scenarios/*.json
backend/tests/benchmarks/coach/test_conversational_fixture_contract.py
backend/tests/benchmarks/coach/test_conversational_contract_smoke.py
backend/tests/benchmarks/coach/test_conversational_acceptance_smoke.py
```

Do not edit legacy `backend/app/services/answer_evaluator.py`, `rubric_builder.py`, `rubric_synthesiser.py`, legacy prompts, `EvaluationCard`, `ScoreRadar`, or `FeedbackReport`; PR1 experience dispatch must keep those on `legacy_v1`.

### Task 1: Lock PR3 Contracts, Normalization, and Deterministic Delivery

**Files:**
- Modify: `backend/app/services/coach_conversational_contracts.py`
- Create: `backend/app/services/coach_text_spans.py`
- Create: `backend/app/services/coach_delivery_policy.py`
- Modify: `backend/app/schemas/coach_conversation.py`
- Test: `backend/tests/test_services/test_coach_text_spans.py`
- Test: `backend/tests/test_services/test_coach_delivery_policy.py`

**Interfaces:**
- Consumes: PR1 centralized contract module and PR2 `SpeechMetricsSnapshot`.
- Produces: `normalize_contract_text(text: str) -> str`, `validate_code_point_span(text: str, start: int, end: int, excerpt: str) -> ValidatedSpan`, `scan_prohibited_model_authorship(value: object) -> tuple[str, ...]`, `assess_delivery(recording_type: Literal["text", "audio"], transcript: str, metrics: SpeechMetricsSnapshot | None) -> ConversationalRubricDimension`.

- [ ] **Step 1: Write failing normalization and prohibited-authorship tests**

```python
def test_span_validation_uses_nfc_lf_and_unicode_code_points() -> None:
    text = "A\r\nCafe\u0301 😀 नमस्ते"
    normalized = normalize_contract_text(text)
    assert normalized == "A\nCafé 😀 नमस्ते"
    start = normalized.index("😀")
    assert validate_code_point_span(text, start, start + 1, "😀").excerpt == "😀"

def test_prohibited_scan_targets_model_authorship_not_candidate_quote() -> None:
    assert scan_prohibited_model_authorship(
        {"rationale": "The candidate seems anxious and deceptive."}
    ) == ("anxious", "deceptive")
    assert scan_prohibited_model_authorship(
        {"transcript_excerpt": "I felt anxious before the launch", "rationale": "This is a candidate quotation."}
    ) == ()
```

- [ ] **Step 2: Run the focused span tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_text_spans.py`

Expected: FAIL during import because `coach_text_spans` does not exist; record exit status and failure text.

- [ ] **Step 3: Implement normalization, strict half-open span validation, immutable enums, and safe contextual scanning**

```python
def normalize_contract_text(text: str) -> str:
    return unicodedata.normalize("NFC", str(text).replace("\r\n", "\n").replace("\r", "\n"))

def validate_code_point_span(text: str, start: int, end: int, excerpt: str) -> ValidatedSpan:
    normalized = normalize_contract_text(text)
    quoted = normalize_contract_text(excerpt)
    if isinstance(start, bool) or isinstance(end, bool) or not 0 <= start < end <= len(normalized):
        raise ContractValidationError("coach_evaluation_evidence_span_invalid")
    if normalized[start:end] != quoted:
        raise ContractValidationError("coach_evaluation_evidence_span_invalid")
    return ValidatedSpan(start=start, end=end, excerpt=quoted)
```

Centralize immutable tuples/maps for content dimensions, levels, evidence states, approval capabilities, claim types, follow-up reasons, reason-to-dimension/role mapping, and safe frontend errors. The contextual scanner traverses model-authored fields only and excludes schema-designated quoted transcript/evidence fields.

- [ ] **Step 4: Write failing delivery boundary vectors**

```python
@pytest.mark.parametrize(("wpm", "expected"), [(70, "material"), (90, "moderate"), (100, "none"), (170, "none"), (190, "moderate"), (220, "material")])
def test_pace_equality_boundaries(wpm: float, expected: str) -> None:
    result = assess_delivery("audio", WORDS_80, metrics(wpm=wpm, duration_ms=60_000))
    assert result.observations["pace"].severity == expected

def test_typed_and_short_audio_are_not_assessed() -> None:
    assert assess_delivery("text", WORDS_80, None).level == "not_assessed"
    assert assess_delivery("audio", "too short", metrics(duration_ms=19_999)).level == "not_assessed"
```

- [ ] **Step 5: Run delivery tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_delivery_policy.py`

Expected: FAIL because `assess_delivery` is missing.

- [ ] **Step 6: Implement the exact V6 §22.3 eligibility, threshold, and first-match algorithm**

Return metric family, raw value, thresholds, and severity without rounding comparisons. Cover 70/90/100/170/190/220 WPM, 3/6/9 fillers per minute, and equality around duration/word-derived pause and hedging thresholds. Never invoke legacy tone/video builders.

- [ ] **Step 7: Run focused GREEN and commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_text_spans.py tests/test_services/test_coach_delivery_policy.py`

Expected: PASS with all normalization, contextual-scan, eligibility, and equality-boundary cases.

```bash
git add backend/app/services/coach_conversational_contracts.py backend/app/services/coach_text_spans.py backend/app/services/coach_delivery_policy.py backend/app/schemas/coach_conversation.py backend/tests/test_services/test_coach_text_spans.py backend/tests/test_services/test_coach_delivery_policy.py
git commit -m "feat(coach): lock conversational evaluation contracts"
```

### Task 2: Build the Strict Conversational Evaluator and Pipeline Stage

**Files:**
- Create: `backend/app/services/coach_conversational_evaluator.py`
- Create: `backend/app/prompts/coach_conversational_evaluation.j2`
- Modify: `backend/app/services/coach_attempt_pipeline.py`
- Test: `backend/tests/test_services/test_coach_conversational_evaluator.py`
- Test: `backend/tests/test_services/test_coach_attempt_pipeline.py`

**Interfaces:**
- Consumes: `AttemptProcessingContext`, Task 1 span/delivery functions, PR2 absolute deadline and stage-result contracts.
- Produces: `ConversationalEvaluator.evaluate(request: EvaluationRequest) -> EvaluationStageResult` and deterministic `derive_answer_level(dimensions: Mapping[str, ConversationalRubricDimension]) -> Level`.

- [ ] **Step 1: Write RED tests for exact level vectors, schema rejection, repair, and technical isolation**

```python
@pytest.mark.parametrize(("levels", "expected"), [
    (("strong", "strong", "strong", "strong", "strong", "interview_ready", "interview_ready"), "strong"),
    (("strong", "strong", "strong", "strong", "strong", "not_assessed", "not_assessed"), "developing"),
    (("strong", "strong", "strong", "strong", "interview_ready", "interview_ready", "not_assessed"), "interview_ready"),
    (("developing", "developing", "developing", "developing", "developing", "not_assessed", "not_assessed"), "developing"),
    (("strong", "strong", "strong", "not_assessed", "not_assessed", "not_assessed", "not_assessed"), "not_assessed"),
])
def test_answer_level_first_match(levels: tuple[str, ...], expected: str) -> None:
    assert derive_answer_level(dimension_map(levels)) == expected

@pytest.mark.asyncio
async def test_invalid_first_output_repairs_once_without_partial_persistence() -> None:
    model = StubJsonModel([{"dimensions": {"delivery": {"level": "strong"}}}, VALID_CONTENT_OUTPUT])
    result = await ConversationalEvaluator(model).evaluate(EVALUATION_REQUEST)
    assert result.state == "completed"
    assert result.repair_count == 1
    assert result.persistable.dimensions.keys() == set(CONTENT_DIMENSIONS)

@pytest.mark.asyncio
async def test_content_evaluation_guard_skips_nullable_pretranscription_attempt() -> None:
    context = dataclasses.replace(ATTEMPT_CONTEXT, transcript_version_id=None)
    model = StubJsonModel([VALID_CONTENT_OUTPUT])
    result = await ConversationalEvaluationStage(ConversationalEvaluator(model)).run(context)
    assert result.state == "unavailable"
    assert result.error_code == "coach_evaluation_unavailable"
    assert model.calls == []
```

- [ ] **Step 2: Run evaluator tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_evaluator.py`

Expected: FAIL because the conversational evaluator and prompt do not exist.

- [ ] **Step 3: Implement strict proposal parsing and deterministic ownership**

The pipeline-stage entry guard accepts PR1's nullable stored transcript FK but requires a non-null current transcript version before constructing `EvaluationRequest`; the pre-transcription unavailable branch returns without a model call. The prompt supplies immutable system rules, JSON trusted metadata, then delimited untrusted question/transcript. Accept only the seven content dimensions. Validate level enum, maximum two excerpts, exact current-transcript spans, bounded rationale/improvement, and absence of prohibited model-authored judgement. The application derives answer level and merges Task 1 delivery; the model cannot assign `delivery` or `evidence_consistency`.

```python
async def evaluate(self, request: EvaluationRequest) -> EvaluationStageResult:
    for repair_count in range(2):
        raw = await run_with_absolute_deadline(self._model.complete_json(...), request.deadline_at)
        validated = validate_content_proposal(raw, request.normalized_transcript)
        if validated.ok:
            return EvaluationStageResult.completed(
                content=validated.value,
                answer_level=derive_answer_level(validated.value.dimensions),
                delivery=assess_delivery(request.recording_type, request.normalized_transcript, request.speech_metrics),
                repair_count=repair_count,
            )
    return EvaluationStageResult.unavailable("coach_transcript_schema_invalid", repair_count=1)
```

- [ ] **Step 4: Register content evaluation after transcript and independent speech analysis**

Ensure typed input passes with delivery `not_assessed`; speech-analysis failure does not block content evaluation. Exhausted schema/repair returns unavailable and persists no dimension rows. Retain PR2 generation/job/deadline fences.

- [ ] **Step 5: Run evaluator and pipeline GREEN, then commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_evaluator.py tests/test_services/test_coach_attempt_pipeline.py`

Expected: PASS, including provider timeout, repair exhaustion, prompt-injection payload, invalid span, forbidden dimension, prohibited judgement, typed parity, and no-partial-persistence assertions.

```bash
git add backend/app/services/coach_conversational_evaluator.py backend/app/prompts/coach_conversational_evaluation.j2 backend/app/services/coach_attempt_pipeline.py backend/tests/test_services/test_coach_conversational_evaluator.py backend/tests/test_services/test_coach_attempt_pipeline.py
git commit -m "feat(coach): add evidence-backed named evaluator"
```

### Task 3: Implement Immutable Evidence Grounding

**Files:**
- Create: `backend/app/services/coach_evidence_grounder.py`
- Create: `backend/app/prompts/coach_evidence_grounding.j2`
- Modify: `backend/app/services/coach_attempt_pipeline.py`
- Test: `backend/tests/test_services/test_coach_evidence_grounder.py`

**Interfaces:**
- Consumes: PR1 `SessionEvidenceSnapshot`, current transcript version/hash, Task 1 span validation, Task 2 evaluation stage.
- Produces: `EvidenceGrounder.ground(request: GroundingRequest) -> GroundingStageResult` and `derive_evidence_consistency(claims: Sequence[ValidatedClaim], package_present: bool) -> Level`.

- [ ] **Step 1: Write RED trust, status, ID, injection, and derivation tests**

```python
@pytest.mark.parametrize(("counts", "expected"), [
    ((1, 0, 0, 0, 0), "strong"), ((2, 1, 0, 0, 0), "interview_ready"),
    ((1, 2, 0, 0, 0), "developing"), ((2, 0, 1, 0, 0), "developing"),
    ((2, 0, 1, 0, 1), "needs_work"), ((1, 0, 2, 0, 0), "needs_work"),
    ((3, 0, 0, 1, 0), "needs_work"), ((0, 0, 0, 0, 0), "not_assessed"),
])
def test_evidence_consistency_ordered_algorithm(counts: tuple[int, ...], expected: str) -> None:
    assert derive_evidence_consistency(claims_for_counts(counts), package_present=True) == expected

def test_non_authoritative_source_cannot_establish_conflict() -> None:
    finding = validate_grounding_proposal(CONTRADICTION_FROM_REVIEWED_SOURCE, PACKAGE)
    assert finding.status == "not_found"
    assert "false" not in finding.explanation.casefold()
```

- [ ] **Step 2: Run grounder tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_evidence_grounder.py`

Expected: FAIL because `coach_evidence_grounder` is missing.

- [ ] **Step 3: Implement deterministic trust capabilities and claim validation**

Validate claim type, materiality, centrality, deduplication, exact transcript span, evidence IDs against the immutable package, source record/hash, and approval capability. `approved`, `confirmed`, `reviewed_final` may conflict; `reviewed` and `candidate_selected_unapproved` may support/partially support only; consented `draft` may partially support only; `context_only` never grounds candidate experience. Authoritative conflict wins. Job/company context cannot become candidate history.

- [ ] **Step 4: Add grounding as a separately unavailable downstream stage**

Grounding receives only immutable session evidence records. A missing package or provider failure yields `not_assessed`, retains content evaluation, and does not invent a low level. Invalid evidence ID, stale source hash, injection instruction, or schema exhaustion persists no grounding claims.

- [ ] **Step 5: Run GREEN and commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_evidence_grounder.py tests/test_services/test_coach_attempt_pipeline.py`

Expected: PASS for every V6 §24.7 vector and approved/confirmed/reviewed-final/reviewed/unapproved/draft/context-only case.

```bash
git add backend/app/services/coach_evidence_grounder.py backend/app/prompts/coach_evidence_grounding.j2 backend/app/services/coach_attempt_pipeline.py backend/tests/test_services/test_coach_evidence_grounder.py backend/tests/test_services/test_coach_attempt_pipeline.py
git commit -m "feat(coach): ground evaluations in immutable evidence"
```

### Task 4: Add Fact-safe Coaching Skeleton and Enrichment

**Files:**
- Create: `backend/app/services/coach_coaching.py`
- Create: `backend/app/prompts/coach_coaching.j2`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Test: `backend/tests/test_services/test_coach_coaching.py`
- Test: `backend/tests/test_services/test_coach_conversation_commands.py`

**Interfaces:**
- Consumes: current evaluation version, validated spans/findings, PR1 `request_coaching` command handler.
- Produces: `build_coaching_skeleton(evaluation: ConversationalAnswerEvaluation) -> CoachAnswerReview` and `CoachCoachingService.enrich(skeleton, transcript, evidence, deadline_at) -> CoachAnswerReview`.

- [ ] **Step 1: Write RED tests for deterministic fallback and factuality**

```python
@pytest.mark.asyncio
async def test_unavailable_model_returns_deterministic_skeleton() -> None:
    service = CoachCoachingService(FailingModel())
    review = await service.enrich(SKELETON, TRANSCRIPT, PACKAGE, DEADLINE)
    assert review == SKELETON

@pytest.mark.parametrize("invented", ["saved 37%", "led Project Orion", "managed 40 people"])
def test_enrichment_cannot_invent_candidate_facts(invented: str) -> None:
    with pytest.raises(ContractValidationError, match="coach_evaluation_prohibited_inference"):
        validate_coaching_enrichment(enrichment(example_revision=invented), TRANSCRIPT, PACKAGE)
```

- [ ] **Step 2: Run coaching tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_coaching.py`

Expected: FAIL because coaching service is missing.

- [ ] **Step 3: Implement skeleton and bounded enrichment**

Skeleton deterministically selects positive observation, priority improvement, exact transcript evidence, evidence review items, suggested structure, and practice instruction. Enrichment may reorder candidate statements, use supported evidence, or insert `[add verified metric]`; it cannot change levels, invent facts, promote `not_found`, mutate evidence records, or expose prompt/provider data.

- [ ] **Step 4: Wire `request_coaching` without changing evaluation**

Persist coaching under the current evaluation version. Network/provider failure returns the skeleton and leaves `state_version`, allowed commands, and rubric values correct. Read-only display does not increment `activity_version`.

- [ ] **Step 5: Run GREEN and commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_coaching.py tests/test_services/test_coach_conversation_commands.py`

Expected: PASS for provider failure, malicious transcript/evidence, invented metric/project/role, bracketed `[add verified metric]` token, evidence conflict disclosure, and unchanged rubric assertions.

```bash
git add backend/app/services/coach_coaching.py backend/app/prompts/coach_coaching.j2 backend/app/services/coach_conversation_commands.py backend/tests/test_services/test_coach_coaching.py backend/tests/test_services/test_coach_conversation_commands.py
git commit -m "feat(coach): add fact-safe optional coaching"
```

### Task 5: Complete Review Return and Candidate Self-assessment Commands

**Files:**
- Modify: `backend/app/schemas/coach_conversation.py`
- Modify: `backend/app/services/coach_conversational_contracts.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/services/coach_live_view.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Test: `backend/tests/test_services/test_coach_conversation_commands.py`
- Test: `backend/tests/test_repositories/test_conversational_session_repository.py`
- Test: `backend/tests/test_services/test_coach_live_view.py`

**Interfaces:**
- Consumes: PR1 atomic command result/event/state-version transaction, current attempt ownership, state registry, and `/live` projection; Task 4 persisted coaching.
- Produces: `SELF_ASSESSMENT_CONTRACT = "coach_candidate_self_assessment_v1"`; `return_to_review` (`coaching` → `awaiting_next_action`); active-only `record_self_assessment` from `awaiting_next_action` and `coaching`; `ConversationalSessionRepository.record_attempt_self_assessment(*, session_id: str, attempt_id: str, assessment: CandidateSelfAssessment, expected_state_version: int, recorded_at: datetime) -> SelfAssessmentMutationResult`; result fields `attempt_version: int`, `activity_version: int`, and `state_version: int`.
- Preserves: PR1's nullable `create_evaluation_version(..., transcript_version_id: str | None, ...)` storage interface for the pre-transcription unavailable branch. PR3 evaluator/grounder entry points reject a null transcript version before content evaluation; they do not narrow the repository signature.

- [ ] **Step 1: Write command-service RED tests for both command contracts**

```python
@pytest.mark.asyncio
async def test_return_to_review_is_atomic_and_does_not_change_evaluation(command_service, seeded_coaching_session) -> None:
    before = await seeded_coaching_session.snapshot()
    result = await command_service.execute(
        user_id=before.user_id,
        session_id=before.session_id,
        request=command("return_to_review", expected_state_version=before.state_version, payload={}),
    )
    after = await seeded_coaching_session.snapshot()
    assert result.conversation_state == after.conversation_state == "awaiting_next_action"
    assert after.state_version == before.state_version + 1
    assert after.activity_version == before.activity_version
    assert after.current_evaluation == before.current_evaluation

@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["awaiting_next_action", "coaching"])
async def test_record_self_assessment_preserves_quality_and_state(command_service, seeded_session, state: str) -> None:
    before = await seeded_session(state=state).snapshot()
    result = await command_service.execute(
        user_id=before.user_id,
        session_id=before.session_id,
        request=command("record_self_assessment", expected_state_version=before.state_version, payload={
            "attempt_id": before.attempt_id,
            "comfort_level": "medium",
            "felt_complete": True,
            "note": "  I want to make the outcome clearer.  ",
        }),
    )
    after = await seeded_session().snapshot()
    assert after.conversation_state == state
    assert after.current_evaluation == before.current_evaluation
    assert after.delivery_metrics == before.delivery_metrics
    assert after.evidence_findings == before.evidence_findings
    assert result.self_assessment.note == "I want to make the outcome clearer."

@pytest.mark.asyncio
async def test_completed_self_assessment_is_rejected_until_pr4(command_service, completed_session) -> None:
    before = await completed_session.snapshot()
    with pytest.raises(CoachContractError, match="coach_conversation_invalid_state"):
        await command_service.execute(
            user_id=before.user_id, session_id=before.session_id,
            request=command("record_self_assessment", expected_state_version=before.state_version, payload={
                "attempt_id": before.attempt_id, "comfort_level": "medium",
                "felt_complete": True, "note": "Must not persist before report invalidation exists",
            }),
        )
    assert await completed_session.snapshot() == before

def test_pr3_temporarily_removes_completed_reflection_from_transition_registry() -> None:
    rule = TRANSITIONS["record_self_assessment"]
    assert rule.states == frozenset({"awaiting_next_action", "coaching"})
    assert rule.statuses == frozenset({"active"})
```

- [ ] **Step 2: Run command tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py -k 'return_to_review or record_self_assessment'`

Expected: FAIL because the active-state handlers and completed-state rejection are absent.

- [ ] **Step 3: Write repository RED tests for active overwrite, ownership, versioning, and privacy**

```python
@pytest.mark.asyncio
async def test_self_assessment_overwrites_candidate_reflection_with_non_content_event(repository, active_review_attempt) -> None:
    result = await repository.record_attempt_self_assessment(
        session_id=active_review_attempt.session_id,
        attempt_id=active_review_attempt.id,
        assessment=CandidateSelfAssessment(comfort_level="high", felt_complete=False, note="Second reflection"),
        expected_state_version=active_review_attempt.state_version,
        recorded_at=FROZEN_NOW,
    )
    stored = await repository.get_attempt(active_review_attempt.id)
    event = await repository.get_latest_event(active_review_attempt.session_id)
    assert stored.self_assessment_json == {
        "comfort_level": "high", "felt_complete": False, "note": "Second reflection",
        "recorded_at": FROZEN_NOW.isoformat(), "contract_version": SELF_ASSESSMENT_CONTRACT,
    }
    assert stored.attempt_version == active_review_attempt.attempt_version + 1
    assert result.activity_version == active_review_attempt.activity_version + 1
    assert result.state_version == active_review_attempt.state_version + 1
    assert event.event_type == "self_assessment_recorded"
    assert "Second reflection" not in json.dumps(event.payload)

@pytest.mark.asyncio
async def test_cross_session_attempt_is_rejected_without_mutation(repository, session_a, attempt_b) -> None:
    with pytest.raises(CoachContractError, match="coach_attempt_not_active"):
        await repository.record_attempt_self_assessment(
            session_id=session_a.id, attempt_id=attempt_b.id,
            assessment=CandidateSelfAssessment(comfort_level="low", felt_complete=False, note=None),
            expected_state_version=session_a.state_version, recorded_at=FROZEN_NOW,
        )
    assert await repository.count_events(session_a.id, "self_assessment_recorded") == 0

@pytest.mark.asyncio
async def test_repository_rejects_completed_reflection_without_report_transaction(repository, completed_attempt) -> None:
    before = await repository.snapshot_session(completed_attempt.session_id)
    with pytest.raises(CoachContractError, match="coach_conversation_invalid_state"):
        await repository.record_attempt_self_assessment(
            session_id=completed_attempt.session_id, attempt_id=completed_attempt.id,
            assessment=CandidateSelfAssessment(comfort_level="medium", felt_complete=True, note=None),
            expected_state_version=before.state_version, recorded_at=FROZEN_NOW,
        )
    assert await repository.snapshot_session(completed_attempt.session_id) == before
```

- [ ] **Step 4: Run repository tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_repositories/test_conversational_session_repository.py -k 'self_assessment'`

Expected: FAIL because atomic active-session reflection persistence/versioning is missing.

- [ ] **Step 5: Implement minimal handlers and atomic repository mutation**

Narrow PR1's coarse `TRANSITIONS["record_self_assessment"]` in PR3 to states `awaiting_next_action|coaching` and status `active`, so the shared validator and `/live.allowed_commands` stop advertising the completed command before its report transaction exists. Validate `comfort_level` against `low|medium|high`; require a Boolean `felt_complete`; normalize/trim `note`, reject more than 1,000 Unicode code points, and validate attempt parent ownership. Persist only the latest candidate reflection with `recorded_at` and `SELF_ASSESSMENT_CONTRACT`; increment `attempt_version`, `activity_version`, and `state_version` once; append `self_assessment_recorded` with content-free version metadata; and persist the idempotent command result in the same transaction. Preserve conversation state, evaluation, delivery, evidence, coaching, acceptance, and follow-up data. Reject `completed` before calling the repository, with no mutation or command-result success row. `return_to_review` validates `coaching`, changes only conversation/state version plus the atomic command result, and makes duplicate replay return the original result.

- [ ] **Step 6: Write `/live` RED tests for state-derived commands and persisted reflection**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(("state", "required", "forbidden"), [
    ("awaiting_next_action", {"record_self_assessment"}, {"return_to_review"}),
    ("coaching", {"record_self_assessment", "return_to_review"}, set()),
    ("completed", set(), {"record_self_assessment", "return_to_review"}),
])
async def test_live_allowed_commands_include_exact_reflection_actions(live_service, state, required, forbidden) -> None:
    view = await live_service.get_view(await seeded_session_id(state))
    assert required <= set(view.allowed_commands)
    assert not (forbidden & set(view.allowed_commands))

@pytest.mark.asyncio
async def test_live_returns_persisted_reflection_without_report_side_effect(live_service, reflected_attempt) -> None:
    view = await live_service.get_view(reflected_attempt.session_id)
    assert view.active_attempt.self_assessment.model_dump(exclude={"recorded_at"}) == {
        "comfort_level": "medium", "felt_complete": True,
        "note": "I want to make the outcome clearer.", "contract_version": SELF_ASSESSMENT_CONTRACT,
    }
```

- [ ] **Step 7: Run live/command/repository GREEN and commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_repositories/test_conversational_session_repository.py tests/test_services/test_coach_live_view.py -k 'return_to_review or self_assessment or reflection'`

Expected: PASS for active review/coaching state parity, duplicate replay, invalid/completed-state rejection, stale version, ownership, note boundaries at 1,000/1,001 code points, overwrite, content-free event, and exact version increments. Tests assert a completed session has no reflection mutation and no `record_self_assessment` allowed command.

```bash
git add backend/app/schemas/coach_conversation.py backend/app/services/coach_conversational_contracts.py backend/app/services/coach_conversation_commands.py backend/app/services/coach_live_view.py backend/app/repositories/conversational_session_repository.py backend/tests/test_services/test_coach_conversation_commands.py backend/tests/test_repositories/test_conversational_session_repository.py backend/tests/test_services/test_coach_live_view.py
git commit -m "feat(coach): persist candidate self-assessment"
```

**PR4 handoff:** PR4 exclusively enables `record_self_assessment` from `completed`. Its command transaction must persist the new `SessionRecording.self_assessment_json`, increment attempt/activity/state versions, set `report_state = invalidated`, clear the stale report snapshot/job, and create the `reflection_update_rebuild` report claim atomically before returning success; PR4 also adds reconciliation and rebuild tests. Until that entire V6 §29.8 path exists, PR3 rejects the completed-state command and does not advertise it in `/live` or the UI. PR3 does not change `end_session`.

### Task 6: Enforce Follow-up Admission, Atomic Budget, and Explicit Acceptance

**Files:**
- Create: `backend/app/services/coach_followup_policy.py`
- Create: `backend/app/prompts/coach_follow_up.j2`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Test: `backend/tests/test_services/test_coach_followup_policy.py`
- Test: `backend/tests/test_repositories/test_conversational_session_repository.py`
- Test: `backend/tests/test_services/test_coach_conversation_commands.py`

**Interfaces:**
- Consumes: accepted attempt/current transcript/evaluation, PR1 command idempotency and acceptance transaction.
- Produces: `FollowUpPolicy.validate(proposal, context) -> FollowUpDecision` and atomic `create_follow_up_question(claim) -> FollowUpCreationResult`.

- [ ] **Step 1: Write RED policy and race tests**

```python
@pytest.mark.parametrize("proposal", [LOW_SCORE_ONLY, FILLER_ONLY, UNGROUNDED, WRONG_REASON_MAPPING, DUPLICATE])
def test_invalid_follow_up_proposals_are_rejected(proposal: dict[str, object]) -> None:
    assert FollowUpPolicy().validate(proposal, FOLLOW_UP_CONTEXT).admitted is False

@pytest.mark.asyncio
async def test_two_concurrent_admissions_never_exceed_root_budget(repository) -> None:
    results = await asyncio.gather(
        repository.create_follow_up_question(claim("root", "dup-a")),
        repository.create_follow_up_question(claim("root", "dup-b")),
    )
    assert await repository.count_all_root_followups("root") <= 2
    assert sum(result.created for result in results) == 1
```

- [ ] **Step 2: Run follow-up tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_followup_policy.py tests/test_repositories/test_conversational_session_repository.py -k 'follow_up or accept'`

Expected: FAIL because policy validation and atomic admission are absent.

- [ ] **Step 3: Implement exact reason mapping and deterministic admission**

Validate the V6 §25.5 mapping, current accepted attempt/transcript, exact span, bounded question, root not skipped/ended, depth, normalized duplicate key, total persisted root count below two, and `gap_repair` eligibility. Count answered, skipped, deleted-source, and retry-triggered follow-ups; deletion never refunds budget. No valid proposal means advance without a generic low-score fallback.

- [ ] **Step 4: Make acceptance and follow-up one idempotent transaction**

`accept_attempt` requires explicit attempt ID and one unused `acceptance_generation`, sets the pointer/accepted timestamp, then admits at most one validated follow-up. Duplicate command replay returns the original result. Concurrent admissions use conditional update/count predicates suitable for SQLite; at most two rows exist under the root. A second acceptance returns `coach_attempt_already_accepted` without changing the original pointer.

- [ ] **Step 5: Run GREEN and commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_followup_policy.py tests/test_repositories/test_conversational_session_repository.py tests/test_services/test_coach_conversation_commands.py -k 'follow_up or accept or idempot'`

Expected: PASS for allowed reasons, mapping mismatch, low-score/filler rejection, ungrounded/duplicate/third rejection, retry/deletion budget preservation, two-worker race, accepted attempt ownership, and duplicate acceptance.

```bash
git add backend/app/services/coach_followup_policy.py backend/app/prompts/coach_follow_up.j2 backend/app/repositories/conversational_session_repository.py backend/app/services/coach_conversation_commands.py backend/tests/test_services/test_coach_followup_policy.py backend/tests/test_repositories/test_conversational_session_repository.py backend/tests/test_services/test_coach_conversation_commands.py
git commit -m "feat(coach): enforce grounded follow-up admission"
```

### Task 7: Fence Transcript Editing and Re-evaluation

**Files:**
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/coach_attempt_pipeline.py`
- Modify: `backend/app/routers/coach_conversation.py`
- Test: `backend/tests/test_services/test_coach_conversation_commands.py`
- Test: `backend/tests/test_services/test_coach_attempt_pipeline.py`
- Test: `backend/tests/test_repositories/test_conversational_session_repository.py`
- Test: `backend/tests/test_routers/test_coach_conversation_router.py`

**Interfaces:**
- Consumes: PR1 `edit_transcript` envelope, PR2 generation/stage claim, Task 2/3 stages.
- Produces: candidate-edit transcript version and a new generation-fenced evaluation, while original transcript and delivery metrics remain immutable.

- [ ] **Step 1: Write the stale-worker RED test**

```python
@pytest.mark.asyncio
async def test_late_generation_one_cannot_replace_edited_generation_two(repository, pipeline) -> None:
    old_claim = await fixture_completed_audio_attempt(repository, transcript="old text", generation=1)
    edit = await repository.claim_transcript_edit(
        recording_id=old_claim.recording_id,
        expected_attempt_version=old_claim.attempt_version,
        transcript="corrected text",
    )
    assert edit.transcript_version.version_number == 2
    assert edit.processing_generation == 2
    assert await pipeline.finalise(old_claim, OLD_RESULT) is False
    current = await repository.get_current_attempt(old_claim.recording_id)
    assert current.transcript == "corrected text"
    assert current.delivery_metrics == ORIGINAL_DELIVERY
```

- [ ] **Step 2: Run edit/race tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_services/test_coach_attempt_pipeline.py tests/test_repositories/test_conversational_session_repository.py -k 'edit_transcript or stale_generation'`

Expected: FAIL because PR3 edit/re-evaluation behavior is not wired.

- [ ] **Step 3: Implement the atomic edit claim**

Permit from `awaiting_next_action` and `coaching`; validate ownership, state, expected attempt version, 1–30,000 normalized code points, and non-deleted transcript. In one transaction create `candidate_edit` transcript version, increment `attempt_version` and `processing_generation`, create pending evaluation/stages/job, set attempt `pending_processing`, set session `processing_answer`, increment activity/state versions, and persist command result before dispatch.

- [ ] **Step 4: Prove stale finalization and safe router errors**

Finalization must match recording, job/claim token, processing generation, transcript version/hash, evaluation version, deadline, and pending state. A stale worker writes no authoritative data. Router returns canonical safe errors and no transcript/path/provider detail.

- [ ] **Step 5: Run GREEN and commit**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_services/test_coach_attempt_pipeline.py tests/test_repositories/test_conversational_session_repository.py tests/test_routers/test_coach_conversation_router.py -k 'edit_transcript or stale or prohibited or redaction'`

Expected: PASS for edit from review/coaching, stale `attempt_version`, generation race, original transcript preservation, original delivery preservation, and safe failure body.

```bash
git add backend/app/services/coach_conversation_commands.py backend/app/repositories/conversational_session_repository.py backend/app/services/coach_attempt_pipeline.py backend/app/routers/coach_conversation.py backend/tests/test_services/test_coach_conversation_commands.py backend/tests/test_services/test_coach_attempt_pipeline.py backend/tests/test_repositories/test_conversational_session_repository.py backend/tests/test_routers/test_coach_conversation_router.py
git commit -m "feat(coach): fence transcript re-evaluation"
```

### Task 8: Deliver the Server-authored Answer Review UI

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/coach/conversation/CodePointExcerpt.tsx`
- Create: `frontend/src/components/coach/conversation/AnswerReview.tsx`
- Create: `frontend/src/components/coach/conversation/TranscriptEditor.tsx`
- Create: `frontend/src/components/coach/conversation/AttemptHistory.tsx`
- Test: `frontend/src/components/coach/conversation/__tests__/AnswerReview.test.tsx`
- Test: `frontend/src/components/coach/conversation/__tests__/TranscriptEditor.test.tsx`
- Test: `frontend/src/components/coach/conversation/__tests__/AttemptHistory.test.tsx`

**Interfaces:**
- Consumes: PR1 `ConversationLiveView`, `sendCoachConversationCommand(sessionId, command)` and allowed commands; Task 1–7 review schemas.
- Produces: accessible review panels, code-point-safe excerpts, edit disclosure, explicit attempt selection, optional coaching, and named-level comparison.

- [ ] **Step 1: Write RED rendering and interaction tests**

```tsx
it("renders named review without numeric precision or inferred confidence", async () => {
  render(<AnswerReview live={reviewFixture} onCommand={onCommand} />);
  expect(screen.getByRole("heading", { name: /answer quality/i })).toBeVisible();
  expect(screen.getByText("Interview-ready")).toBeVisible();
  expect(screen.queryByText(/\/10|%|confidence|personality/i)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /accept attempt 1/i }));
  expect(onCommand).toHaveBeenCalledWith("accept_attempt", { attempt_id: "attempt-1" });
});

it("explains transcript correction before sending the edit", () => {
  render(<TranscriptEditor attempt={attemptFixture} onCommand={onCommand} />);
  expect(screen.getByText(/re-runs answer and evidence review/i)).toBeVisible();
  expect(screen.getByText(/delivery observations remain based on the original audio/i)).toBeVisible();
});

it("submits candidate reflection and returns from coaching only when allowed", async () => {
  render(<AnswerReview live={coachingFixture} onCommand={onCommand} />);
  await userEvent.selectOptions(screen.getByLabelText(/comfort level/i), "medium");
  await userEvent.click(screen.getByRole("checkbox", { name: /felt complete/i }));
  await userEvent.type(screen.getByLabelText(/reflection note/i), "I want to make the outcome clearer.");
  await userEvent.click(screen.getByRole("button", { name: /save reflection/i }));
  expect(onCommand).toHaveBeenCalledWith("record_self_assessment", {
    attempt_id: "attempt-1", comfort_level: "medium", felt_complete: true,
    note: "I want to make the outcome clearer.",
  });
  await userEvent.click(screen.getByRole("button", { name: /return to review/i }));
  expect(onCommand).toHaveBeenCalledWith("return_to_review", {});
});
```

- [ ] **Step 2: Run frontend tests and capture RED**

Run: `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/AnswerReview.test.tsx src/components/coach/conversation/__tests__/TranscriptEditor.test.tsx src/components/coach/conversation/__tests__/AttemptHistory.test.tsx`

Expected: FAIL because PR3 components do not exist.

- [ ] **Step 3: Add discriminated review API types and code-point helper**

```typescript
export function sliceCodePoints(value: string, start: number, end: number): string {
  return Array.from(value.normalize("NFC").replace(/\r\n?/g, "\n")).slice(start, end).join("");
}
```

Render four panels: Answer quality, Delivery observations, Evidence check, Your reflection. Render untrusted text as React text nodes, never HTML. Show evidence status wording, explicit unapproved/draft labels, technical unavailable state distinct from performance, and an ARIA-live status that does not steal focus.

- [ ] **Step 4: Implement allowed-command-driven actions and history**

Show accept/edit/retry/coaching, `return_to_review`, and reflection-save actions only when included in server `allowed_commands`. The Your reflection panel initializes from persisted server assessment and sends the exact Task 5 payload in active review/coaching states; completed state shows neither reflection-save nor Return to review in PR3. Use explicit attempt IDs and current state version. Preserve stable command ID for network retry; on 409 refresh `/live` without replaying a new command. Never infer accepted state from the highest level. Provide text equivalents and no color-only distinctions.

- [ ] **Step 5: Run GREEN, type-check, and commit**

Run: `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/AnswerReview.test.tsx src/components/coach/conversation/__tests__/TranscriptEditor.test.tsx src/components/coach/conversation/__tests__/AttemptHistory.test.tsx && npm run type-check`

Expected: PASS; TypeScript exits 0; malicious markup remains inert; emoji/combining/Hindi excerpts match backend code-point offsets; keyboard and accessible-name assertions pass.

```bash
git add frontend/src/lib/api.ts frontend/src/components/coach/conversation/CodePointExcerpt.tsx frontend/src/components/coach/conversation/AnswerReview.tsx frontend/src/components/coach/conversation/TranscriptEditor.tsx frontend/src/components/coach/conversation/AttemptHistory.tsx frontend/src/components/coach/conversation/__tests__/AnswerReview.test.tsx frontend/src/components/coach/conversation/__tests__/TranscriptEditor.test.tsx frontend/src/components/coach/conversation/__tests__/AttemptHistory.test.tsx
git commit -m "feat(coach): add conversational answer review"
```

### Task 9: Add Typed Review, Follow-up, and Edit-race E2E Coverage

**Files:**
- Create: `frontend/e2e/coach-conversational-review.spec.ts`
- Modify: existing PR2 synthetic Coach API fixtures only if required for deterministic states

**Interfaces:**
- Consumes: merged conversational UI/API and synthetic isolated test server.
- Produces: browser evidence for AC-05, AC-10–AC-21, and AC-28 without invoking production/shared providers.

- [ ] **Step 1: Write failing E2E scenarios**

Add tests that: submit a typed answer and see delivery `Not assessed`; review named levels and evidence; save and overwrite a candidate reflection without changing quality; enter coaching and use Return to review; accept attempt one explicitly; request optional coaching without changing rubric; admit two grounded follow-ups and return to planned sequence; reject a third; edit an audio transcript while a synthetic old worker finalizes; retain original delivery observations; and render `<script>`/unsafe-link payloads inert.

- [ ] **Step 2: Run the isolated file and capture RED**

Run: `cd frontend && npm run test:e2e -- coach-conversational-review.spec.ts`

Expected: FAIL at the first unimplemented PR3 review assertion, with the synthetic server confirmed local and no external model route configured.

- [ ] **Step 3: Make only fixture/wait corrections needed for deterministic server state**

Use server-observable state transitions, accessible locators, and stable synthetic IDs. Do not use fixed sleeps or browser-derived progression. Assert no numeric score, prohibited judgement, invented coaching fact, duplicate acceptance, or more than two follow-ups.

- [ ] **Step 4: Run GREEN and commit**

Run: `cd frontend && npm run test:e2e -- coach-conversational-review.spec.ts`

Expected: PASS for typed parity, persisted reflection, coaching return, explicit acceptance, optional coaching, two-follow-up cap, stale edit race, safe rendering, and keyboard interactions.

```bash
git add frontend/e2e/coach-conversational-review.spec.ts
git add -u frontend/e2e
git commit -m "test(coach): cover conversational review flows"
```

If PR2 stores fixtures elsewhere, stage only the exact existing fixture files changed; do not create `frontend/e2e/fixtures` solely to satisfy the example command.

### Task 10: Extend the Existing Coach Benchmark for Conversational Smoke Profiles

**Files:**
- Modify: `backend/benchmarks/coach/contracts.py`
- Modify: `backend/benchmarks/coach/profiles.py`
- Modify: `backend/benchmarks/coach/suite_loader.py`
- Modify: `backend/benchmarks/coach/production_adapter.py`
- Modify: `backend/benchmarks/coach/scoring.py`
- Modify: `backend/benchmarks/coach/validators.py`
- Create: `backend/benchmarks/coach/fixtures/conversational_v1/suite.json`
- Create: `backend/benchmarks/coach/fixtures/conversational_v1/models.json`
- Create: `backend/benchmarks/coach/fixtures/conversational_v1/evidence.json`
- Create: `backend/benchmarks/coach/fixtures/conversational_v1/scenarios/*.json`
- Test: `backend/tests/benchmarks/coach/test_conversational_fixture_contract.py`
- Test: `backend/tests/benchmarks/coach/test_conversational_contract_smoke.py`
- Test: `backend/tests/benchmarks/coach/test_conversational_acceptance_smoke.py`

**Interfaces:**
- Consumes: existing `CoachProfile`, `RunRequest`, artifacts/manifest/reporting/privacy validation, and PR3 services.
- Produces: suite `coach_conversational_v1`, existing profile names `contract-smoke` and `acceptance-smoke`, hard-gate findings, manifest and gate summary.

- [ ] **Step 1: Write RED fixture/profile tests**

```python
def test_conversational_suite_declares_required_groups_and_only_synthetic_data() -> None:
    suite = load_suite(CONVERSATIONAL_SUITE)
    assert suite.suite_id == "coach_conversational_v1"
    assert required_groups(suite) == {"rubric", "evidence_grounding", "follow_up", "coaching", "prohibited_inference", "end_to_end"}

@pytest.mark.asyncio
async def test_conversational_contract_smoke_exercises_every_scenario(tmp_path: Path) -> None:
    summary = await run_benchmark(RunRequest(
        suite_path=CONVERSATIONAL_SUITE, output_root=tmp_path,
        profile_name="contract-smoke", model_ids=("deterministic-contract",),
        command="pytest conversational contract smoke",
    ))
    assert summary.terminal == summary.scheduled
    assert not blocking_findings(summary)
```

- [ ] **Step 2: Run benchmark tests and capture RED**

Run: `cd backend && python -m pytest -q --no-cov tests/benchmarks/coach/test_conversational_fixture_contract.py tests/benchmarks/coach/test_conversational_contract_smoke.py tests/benchmarks/coach/test_conversational_acceptance_smoke.py`

Expected: FAIL because conversational suite and contract support do not exist.

- [ ] **Step 3: Extend contracts without breaking v1 fixtures**

Add conversational stages/groups and expected named levels/statuses while retaining legacy `CoachStage`, profiles, fixtures, loaders, and scoring. `contract-smoke` exercises every fixture with deterministic doubles inside the existing 90-second hard bound; `acceptance-smoke` selects one required case from each PR3 group and remains non-ranking.

- [ ] **Step 4: Commit a complete synthetic scenario suite and hard gates**

Include V6 §38.5 cases: strong/vague/no-impact/typed/technical-failure/span fidelity; supported/partial/not-found/conflict/opinion/injected evidence; clarify/result/role-depth/low-score-no-gap/filler-complete/duplicate/third; no invented metric/bracketed missing-metric token/fact preservation/conflict disclosure; anxiety/confidence/personality/culture-fit/deception/ignore-contract attacks; end-to-end evaluation→grounding→follow-up. Hard fail invalid schema after repair, mismatched span/ID, numeric score, prohibited inference, invalid/ungrounded/excess follow-up, `not_found` as false, technical downgrade, model-answer evidence, or stale-worker mutation.

- [ ] **Step 5: Run GREEN and CLI smoke, then commit**

Run: `cd backend && python -m pytest -q --no-cov tests/benchmarks/coach/test_conversational_fixture_contract.py tests/benchmarks/coach/test_conversational_contract_smoke.py tests/benchmarks/coach/test_conversational_acceptance_smoke.py tests/benchmarks/coach`

Expected: PASS; legacy benchmark regression remains green.

Run: `cd backend && python -m benchmarks.coach smoke --suite benchmarks/coach/fixtures/conversational_v1 --profile contract-smoke --models deterministic-contract --output-root /tmp/hatch-coach-pr3-contract-smoke`

Expected: exit 0; manifest records suite/profile/model route/model ID/provider/contracts/prompts/timeouts/repair budget/fixture hashes/repository SHA/timestamp; gate summary has no blocking finding and contains no sensitive canary.

```bash
git add backend/benchmarks/coach backend/tests/benchmarks/coach
git commit -m "feat(coach): add conversational benchmark smoke"
```

### Task 11: Run Adversarial Gates, Regressions, Traceability, and Ordered Reviews

**Files:**
- Modify only PR3 test files when a genuine PR3 defect is found
- Create outside Git: `/tmp/hatch-coach-pr3-evidence/` for redacted command output, manifests, gate summaries, and review records

**Interfaces:**
- Consumes: all PR3 commits and isolated synthetic fixtures.
- Produces: reproducible merge evidence and the completed traceability table below.

- [ ] **Step 1: Run focused backend PR3 gate**

```bash
cd backend
python -m pytest -q --no-cov \
  tests/test_services/test_coach_text_spans.py \
  tests/test_services/test_coach_delivery_policy.py \
  tests/test_services/test_coach_conversational_evaluator.py \
  tests/test_services/test_coach_evidence_grounder.py \
  tests/test_services/test_coach_coaching.py \
  tests/test_services/test_coach_followup_policy.py \
  tests/test_services/test_coach_attempt_pipeline.py \
  tests/test_services/test_coach_conversation_commands.py \
  tests/test_services/test_coach_live_view.py \
  tests/test_repositories/test_conversational_session_repository.py \
  tests/test_routers/test_coach_conversation_router.py \
  tests/benchmarks/coach/test_conversational_fixture_contract.py \
  tests/benchmarks/coach/test_conversational_contract_smoke.py \
  tests/benchmarks/coach/test_conversational_acceptance_smoke.py
```

Expected: exit 0 with exact pass count recorded.

- [ ] **Step 2: Run isolated adversarial boundary matrix**

Run focused cases for negative ownership/safe ID, injection in transcript/CV/job/Question Bank/evidence, invented/wrong-source IDs, invalid spans/enums, authoritative-vs-lower-trust conflict, schema repair exhaustion, prohibited model-authored judgement versus legitimate quotation, duplicate/third follow-up, concurrent admission, edit stale worker, safe error bodies, and browser stored/reflected markup. Seed unique synthetic canaries in all sensitive fields and scan captured logs, spans, metric attributes, diagnostics, error bodies, and benchmark artifacts.

Expected: no partial persistence, state mutation, unsafe rendering, source mutation, canary leakage, critical/high finding, or undispositioned medium finding. Record non-applicable PR4 classes as excluded: media path, cleanup/deletion, export, report/progress, and production diagnostics.

- [ ] **Step 3: Run touched-layer and legacy regressions**

```bash
cd backend
python -m pytest -q --no-cov tests/test_services tests/test_repositories tests/test_routers tests/benchmarks/coach
python -m pytest tests/ -v --tb=short
cd ../frontend
npm run type-check
npm test
npm run build
npm run test:e2e -- coach-conversational-review.spec.ts
cd ..
python scripts/check_docs.py
make ci
```

Expected: every command exits 0; record pass counts and durations. Any baseline failure is diagnosed and attributed with pre-existing evidence; PR3-caused failure is fixed through a new RED/GREEN cycle.

- [ ] **Step 4: Recheck migration/flag/compatibility despite no PR3 migration**

```bash
cd backend
alembic heads
alembic upgrade head
alembic current
python -m pytest -q --no-cov tests/test_migrations/test_conversational_coach_migration.py tests/test_services/test_feedback_generator.py tests/test_routers/test_coach_router.py
rg -n "HATCH_COACH_CONVERSATIONAL_ENABLED" app tests
```

Expected: exactly one Alembic head/current revision; migration/legacy aggregation/router tests pass; feature flag default remains false and existing conversational reads/cleanup behavior remains available when creation is disabled.

- [ ] **Step 5: Run contract and acceptance smoke with artifacts**

```bash
cd backend
python -m benchmarks.coach smoke --suite benchmarks/coach/fixtures/conversational_v1 --profile contract-smoke --models deterministic-contract --output-root /tmp/hatch-coach-pr3-evidence/contract-smoke
python -m benchmarks.coach run --suite benchmarks/coach/fixtures/conversational_v1 --profile acceptance-smoke --models configured-local --output-root /tmp/hatch-coach-pr3-evidence/acceptance-smoke
```

Expected: both exit 0; manifest and gate summary paths recorded; hard gates pass. If no supported local model route is available, acceptance smoke is explicitly unexecuted and PR3 is not merge-ready; never weaken fixtures or gates.

- [ ] **Step 6: Perform leakage review and artifact cleanup**

```bash
rg -n -i "(bearer |api[_-]?key|access[_-]?token|password|secret|/home/|transcript_canary|evidence_canary|prompt_canary|cv_canary)" /tmp/hatch-coach-pr3-evidence
git status --short
git diff --check
```

Expected: scan finds no secret/path/content canary in distributable evidence; generated runtime caches remain untracked; worktree contains only reviewed PR3 files; diff check is clean. Remove isolated synthetic runtime data through the test harness cleanup command and record cleanup success; retain only redacted manifests/gate summaries required for review.

- [ ] **Step 7: Complete traceability and request specification-compliance review**

Populate each row with the actual RED command/failure, implementation paths, GREEN command, exit status/pass count, and artifact path. Reviewer verifies V6 authority, PR3 scope/exclusions, PR1/PR2 ancestry, AC mapping, deterministic ownership, Phase 2 absence, and PR4 absence. Any finding is fixed and affected verification rerun before proceeding.

- [ ] **Step 8: Request code-quality/security review only after compliance passes**

Reviewer checks correctness, SQLite atomicity, stale-worker fencing, prompt/schema boundaries, factuality, safe rendering, test isolation, benchmark integrity, maintainability, and legacy separation. Critical/high blocks merge; every medium records owner and `fix`, `accepted risk`, `deferred optional hardening`, or `false positive`, with binding versus optional classification.

- [ ] **Step 9: Record final branch evidence without committing generated artifacts**

```bash
git rev-parse HEAD
git merge-base HEAD feature/coach-phase1-phase2
git log --oneline feature/coach-phase1-phase2..HEAD
git diff --stat feature/coach-phase1-phase2...HEAD
git status --short
```

Expected: base is the post-PR2 integration head; only PR3 commits/files appear; worktree is clean; review verdicts and all command evidence are attached externally to the PR.

## Traceability Matrix

During Task 11, replace each evidence description with captured command output, exit status, pass count, and artifact path; do not mark a row complete from assertion alone.

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| `§12.4–12.5, §23.4, AC-13 — immutable snapshots and Unicode span fidelity` | `test_span_validation_uses_nfc_lf_and_unicode_code_points`: import failure before Task 1 | `coach_text_spans.py`, schemas | focused span/evaluator tests | Exact spans for emoji, combining marks, Hindi, CRLF; pass count/artifact captured |
| `§22.2–22.3, AC-05/AC-16 — deterministic delivery and prohibited dimensions` | delivery equality/typed RED cases | `coach_delivery_policy.py`, contracts | delivery tests + typed E2E | Boundary vectors pass; typed is `not_assessed`; no tone/video inference |
| `§23, AC-12/AC-13/AC-28 — named evidence-backed rubric` | answer-level/schema/repair RED cases | evaluator, prompt, pipeline | evaluator/pipeline + contract smoke | Named levels only; invalid output never partially persists |
| `§24, AC-14/AC-15 — attributable non-accusatory grounding` | trust/status/ID RED cases | grounder, prompt, pipeline | grounder tests + acceptance smoke | Trust matrix and §24.7 vectors pass; `not_found` is not false |
| `§26.3–26.5, AC-21 — optional fact-safe coaching` | fallback/invented-fact RED cases | coaching service/prompt/command | coaching tests + coaching benchmark group | Skeleton fallback passes; no invented metric/project/role |
| `§8.5, §9.9 return_to_review/record_self_assessment, §22.4 — review return and candidate reflection` | command/repository/live RED cases for active review, coaching, and completed rejection | command service, repository, live view, review UI | focused command/repository/live tests + E2E | Return changes only review state; active reflection persists/version-increments without changing quality; completed command/advertisement remains disabled until PR4's atomic §29.8 implementation |
| `§25, AC-17/AC-18 — grounded capped adaptive follow-ups` | invalid proposal/concurrent admission RED cases | follow-up policy/repository/command | policy/repository tests + follow-up benchmark | Exact mappings, grounding, idempotency, cap and sequence pass |
| `§14.3, AC-20 — explicit one-time acceptance` | explicit/second/duplicate acceptance RED cases | repository/command | command/repository tests + E2E | Selected pointer authoritative; replay stable; second rejected |
| `§15–§16, §21, AC-10/AC-11 — versioned edit and stale-worker fencing` | late-generation race RED case | command/repository/pipeline/router | edit race tests + E2E | Version 2 current; version 1 cannot mutate; delivery unchanged |
| `§30.1–30.3/30.7, §38.6 — adversarial AI boundary` | injection/schema/prohibited-authorship RED cases | validators/prompts/benchmark | adversarial focused suite + smoke profiles | No prompt override, schema escape, prohibited persistence, or leakage |
| `§33.6–33.10, AC-12/AC-16/AC-25 — accessible review UI` | review/editor/history import RED | API types and review components | Vitest/type-check/E2E | Four panels, inert untrusted text, keyboard access, named labels only |
| `§34, AC-29 — legacy preservation` | existing legacy baseline is GREEN before PR3 | no legacy evaluator/component edits | full backend/frontend and legacy fixtures | Legacy numeric schemas/results unchanged |
| `§37.8–37.10/37.15, §38 — PR3 automated evidence` | conversational suite/profile RED | existing benchmark harness + new fixtures | benchmark tests and two CLI profiles | Manifests/gate summaries recorded; no hard-gate failure |
| `§39 PR3/§39.1–39.2 — topology and exclusions` | preflight fails if PR2 merge absent or branch wrong | no application file | Git ancestry/diff commands | Post-PR2 base; Phase 2 and PR4 file scans clean |
| `§42.2–42.4, AC-05/10–21/28 — PR3 release gates` | component RED evidence above | all PR3 files | focused/full/E2E/benchmark commands | Exact command outputs and two ordered review verdicts attached |

## PR3 Completion Record

The pull request is merge-ready only when its evidence bundle contains:

- scope and explicit PR4/Phase 2 exclusions;
- integration-base/head/target SHAs and PR1/PR2 merge ancestry;
- repository revision plus V6/design/contract-map/threat-matrix hashes;
- isolated-environment and synthetic-fixture statement;
- completed traceability rows with RED and GREEN evidence;
- commands, runtime/tool versions, cases, exit statuses, pass counts, benchmark manifest and gate-summary paths;
- leakage scan and synthetic-artifact cleanup result;
- findings with severity, binding/optional class, reproduction, owner, disposition, verification, and residual limitation;
- separate specification-compliance verdict followed by code-quality/security verdict;
- known limitations and unexecuted gates;
- merge-readiness statement. Missing evidence means PR3 is not ready.
