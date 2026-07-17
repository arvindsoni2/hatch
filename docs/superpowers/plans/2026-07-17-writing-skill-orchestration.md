# Writing Skill Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing cover-letter skill into a bounded, stage-based workflow with validated evidence planning, deterministic targeted repair, privacy-safe diagnostics, and render/persistence gates.

**Architecture:** Keep `SkillRegistry` and `SkillLoader` as the only skill-discovery framework, extending them with a typed JSON contract. Add a cover-letter-specific workflow module whose public stage methods accept explicit immutable inputs and return structured outputs. `CoverLetterGenerator` remains the API-compatible facade, while `TailorService` owns the final render and persistence gate.

**Tech Stack:** Python 3.12+, dataclasses, Pydantic v2 schemas already used by the service, pytest/pytest-asyncio, existing Jinja prompt renderer, existing SQLAlchemy repositories.

## Global Constraints

- Preserve the current public `CoverLetterGenerator.generate(...) -> CoverLetterResult` API.
- Preserve the configured default model and provider selection.
- Reuse `SkillRegistry`, `SkillLoader`, `EvidenceItem`, `ValidationIssue`, `ValidationResult`, `GenerationProvenance`, and the versioned prompt contracts.
- Workflow stages are exactly `select_evidence`, `create_content_plan`, `generate_draft`, `validate_draft`, `repair_specific_failure`, and `render_document`.
- Cover-letter content plans contain evidence and job-requirement IDs only; they never persist private source text.
- Unknown evidence or requirement IDs are blocking.
- Only contract-declared repair actions may run, in deterministic priority order.
- Maximum generation attempts are enforced across the skill boundary.
- Standard logs and persisted diagnostics exclude provider secrets, full CV content, full cover-letter content, email, phone, and other personal values.
- Failed drafts are not rendered or persisted as generated documents.
- Benchmark fixture content remains confined to existing ignored benchmark paths.

---

### Task 1: Expose Typed Contracts Through the Existing Skill Loader

**Files:**
- Create: `backend/app/skills/cover-letter/contract.json`
- Modify: `backend/app/skills/skill_loader.py`
- Modify: `backend/tests/test_skills/test_skill_loader.py`

**Interfaces:**
- Consumes: existing `SkillRegistry.skill_dir(name)`.
- Produces: immutable `SkillContract` and `SkillLoader.contract(name) -> SkillContract | None`.

- [ ] **Step 1: Write failing contract-loader tests**

Add tests that load `cover-letter/contract.json` and assert:

```python
contract.skill_id == "cover-letter"
contract.skill_version == "1.0.0"
contract.input_schema == "CoverLetterWorkflowInput"
contract.output_schema == "CoverLetterResult"
contract.preconditions == ("approved_evidence_available", "job_analysis_available")
contract.validators == (
    "content_plan_ids",
    "required_fields",
    "placeholder",
    "numeric_fidelity",
    "body_length",
)
contract.allowed_repair_actions == (
    "unsupported_numeric_token",
    "mutated_numeric_token",
    "missing_required_fields",
    "under_length",
    "over_length",
)
contract.maximum_attempts == 3
contract.safe_failure_state == "review_required"
```

Also assert an unknown skill returns `None`, malformed JSON raises `ValueError`, and a contract whose `skill_id` differs from its folder name raises `ValueError`.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/test_skills/test_skill_loader.py -k contract --no-cov
```

Expected: failure because `SkillContract`, `contract.json`, and `SkillLoader.contract` do not exist.

- [ ] **Step 3: Implement the typed loader extension**

Add a frozen dataclass:

```python
@dataclass(frozen=True)
class SkillContract:
    skill_id: str
    skill_version: str
    input_schema: str
    output_schema: str
    preconditions: tuple[str, ...]
    validators: tuple[str, ...]
    allowed_repair_actions: tuple[str, ...]
    maximum_attempts: int
    safe_failure_state: str
```

`SkillLoader.contract(name)` reads only `<skill>/contract.json`, validates every required field, requires `maximum_attempts >= 1`, converts arrays to tuples, and verifies `skill_id == name`. It returns `None` when the skill or contract file is absent.

- [ ] **Step 4: Add the cover-letter contract**

Create JSON with the exact values asserted in Step 1. Do not add a new registry, manifest index, or executable skill abstraction.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest -q backend/tests/test_skills/test_skill_loader.py --no-cov
```

Expected: all skill-loader tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/skills/skill_loader.py backend/app/skills/cover-letter/contract.json backend/tests/test_skills/test_skill_loader.py
git commit -m "feat: expose writing skill contracts"
```

---

### Task 2: Add Structured Planning, Validation, and Diagnostic Types

**Files:**
- Create: `backend/app/services/writing_workflow.py`
- Modify: `backend/app/services/writing_contracts.py`
- Create: `backend/tests/test_services/test_writing_workflow.py`
- Modify: `backend/tests/test_services/test_writing_contracts.py`

**Interfaces:**
- Consumes: `EvidenceItem`, `PromptMetadata`, `ValidationIssue`, `ValidationResult`.
- Produces: `JobRequirement`, `EvidenceSelection`, `CoverLetterContentPlan`, `AttemptDiagnostic`, `WorkflowDiagnostics`, `CoverLetterWorkflowResult`, and optional JSON-safe `GenerationProvenance.content_plan/workflow`.

- [ ] **Step 1: Write failing content-plan validation tests**

Test a valid plan and plans containing unknown evidence and requirement IDs:

```python
result = validate_content_plan(
    CoverLetterContentPlan(
        opening_evidence_ids=("e1",),
        primary_evidence_ids=("e2",),
        secondary_evidence_ids=("e3",),
        alignment_job_requirement_ids=("r1",),
    ),
    allowed_evidence_ids=("e1", "e2", "e3"),
    allowed_requirement_ids=("r1",),
)
assert result.passed is True
```

Unknown IDs must produce blocking issues with codes `unknown_evidence_id` or `unknown_job_requirement_id`. The result must contain no source text.

- [ ] **Step 2: Write failing deterministic-selection tests**

Create a ledger containing summary, achievements, skills, and certifications. Assert `select_evidence(...)` and `create_content_plan(...)` return the same ordered IDs on repeated calls, prefer achievement evidence for primary slots, and expose unused evidence IDs separately for under-length repair.

- [ ] **Step 3: Write failing privacy-safe diagnostic tests**

Construct diagnostics with model ID, counts, validation results, and a secret/full-document-shaped input. Assert `to_dict()` exposes only:

```python
{
    "run_id",
    "task",
    "skill_id",
    "skill_version",
    "prompt_id",
    "prompt_version",
    "model_id",
    "attempts",
    "final_state",
}
```

Assert serialized output excludes the supplied API key, email, phone number, CV text, and cover-letter text.

- [ ] **Step 4: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_writing_workflow.py backend/tests/test_services/test_writing_contracts.py --no-cov
```

Expected: import failures for the new workflow types/functions and missing provenance fields.

- [ ] **Step 5: Implement immutable workflow types and pure functions**

In `writing_workflow.py`, add frozen dataclasses and pure functions:

```python
def build_job_requirements(jd_analysis: JDAnalysisResult) -> tuple[JobRequirement, ...]: ...
def select_evidence(ledger: tuple[EvidenceItem, ...]) -> EvidenceSelection: ...
def create_content_plan(
    selection: EvidenceSelection,
    requirements: tuple[JobRequirement, ...],
) -> CoverLetterContentPlan: ...
def validate_content_plan(
    plan: CoverLetterContentPlan,
    allowed_evidence_ids: tuple[str, ...],
    allowed_requirement_ids: tuple[str, ...],
) -> ValidationResult: ...
def select_repair_action(
    validation: ValidationResult,
    allowed_actions: tuple[str, ...],
    prior_repairs: tuple[str, ...],
) -> str | None: ...
```

Repair priority is:

```python
(
    "unsupported_numeric_token",
    "mutated_numeric_token",
    "missing_required_fields",
    "under_length",
    "over_length",
)
```

The same repair action is not selected twice. Unsupported actions return `None`.

- [ ] **Step 6: Extend internal provenance compatibly**

Add optional `content_plan: dict[str, list[str]] | None = None` and `workflow: dict[str, Any] | None = None` to `GenerationProvenance`. Keeping JSON-ready dictionaries here avoids a dependency cycle between shared provenance and workflow orchestration. Keep defaults so old persisted records and existing constructors remain valid. `to_dict()` serializes IDs and diagnostic metadata only.

- [ ] **Step 7: Verify GREEN**

Run:

```bash
pytest -q backend/tests/test_services/test_writing_workflow.py backend/tests/test_services/test_writing_contracts.py --no-cov
```

Expected: all workflow and compatibility tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/writing_workflow.py backend/app/services/writing_contracts.py backend/tests/test_services/test_writing_workflow.py backend/tests/test_services/test_writing_contracts.py
git commit -m "feat: add writing workflow contracts"
```

---

### Task 3: Refactor Cover-Letter Generation Into Explicit Stages

**Files:**
- Modify: `backend/app/services/cl_generator.py`
- Modify: `backend/app/prompts/cl_generation.j2`
- Modify: `backend/tests/test_services/test_cl_generator.py`
- Modify: `backend/tests/test_services/test_writing_workflow.py`

**Interfaces:**
- Consumes: `SkillLoader.contract("cover-letter")`, content-plan functions, shared numeric validator, current prompt metadata.
- Produces: stage methods `select_evidence`, `create_content_plan`, `generate_draft`, `validate_draft`, `repair_specific_failure`, plus the unchanged `generate(...) -> CoverLetterResult` facade.

- [ ] **Step 1: Write failing stage-boundary tests**

Instantiate `CoverLetterGenerator` with the existing mock client and assert each public stage receives a dedicated frozen input type. Verify:

- `select_evidence` only consumes the ledger;
- `create_content_plan` only consumes selection and requirements;
- `generate_draft` receives the plan, approved evidence, JD analysis, personal details, variant, and skill instructions;
- `validate_draft` receives the draft, ledger, plan validation, and allowed employer context;
- `repair_specific_failure` receives one structured repair action, current draft, unused approved evidence, and generation inputs.

Use dataclass-field assertions to prove no stage input includes a database session, repository, builder, provider secret, or unrelated prior-stage object.

- [ ] **Step 2: Write failing prompt-plan tests**

Run a valid mock generation and assert both initial and repair prompts include `CONTENT_PLAN` with the four required ID arrays. For an under-length repair, assert `UNUSED_APPROVED_EVIDENCE` contains only ledger records not used by the plan. Assert no unknown ID can reach `complete_json`.

- [ ] **Step 3: Write failing structured-repair and attempt-limit tests**

Return drafts that fail multiple gates and assert one repair per call in deterministic order. Assert the contract’s `maximum_attempts` controls the total calls and the final result is `review_required` with structured issues and attempt diagnostics.

- [ ] **Step 4: Write failing telemetry tests**

Use a benchmark-style mock client exposing `spec` and `observations`. Assert diagnostics record run ID, skill/prompt versions, model ID, attempt number, repair type, token counts when available, latency, validator output, computed body count, and final state. Assert neither prompts nor generated body text are serialized into diagnostics.

- [ ] **Step 5: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_cl_generator.py backend/tests/test_services/test_writing_workflow.py --no-cov
```

Expected: failures because the stage input types, methods, plan prompt data, and workflow diagnostics are absent.

- [ ] **Step 6: Implement stage methods and bounded orchestration**

Refactor `generate` to execute:

```text
select_evidence
create_content_plan
generate_draft
validate_draft
repair_specific_failure (zero or more, contract-bounded)
```

Record each attempt after validation. Preserve `_parse_cover_letter`, canonical body counting, tone selection, shared prompt fragments, and public result fields. Replace string-driven `_blocking_defect` selection with structured `ValidationIssue.code` selection.

- [ ] **Step 7: Add plan and unused-evidence prompt sections**

Pass JSON-ready `content_plan` and `unused_approved_evidence` to `cl_generation.j2`. The initial generation has an empty unused-evidence section. Under-length repair may use unused approved evidence; other repairs receive none.

- [ ] **Step 8: Attach safe provenance**

Set `GenerationProvenance.content_plan` and `.workflow` on both successful and review-required results. Preserve the existing prompt metadata, evidence schema version, source evidence IDs, and numeric validation result.

- [ ] **Step 9: Verify GREEN**

Run:

```bash
pytest -q backend/tests/test_services/test_cl_generator.py backend/tests/test_services/test_writing_workflow.py backend/tests/test_services/test_writing_contracts.py --no-cov
```

Expected: all generation, planning, repair, and diagnostic tests pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/cl_generator.py backend/app/prompts/cl_generation.j2 backend/tests/test_services/test_cl_generator.py backend/tests/test_services/test_writing_workflow.py
git commit -m "feat: orchestrate cover letter skill stages"
```

---

### Task 4: Gate Rendering and Persistence on the Workflow Final State

**Files:**
- Modify: `backend/app/services/tailor_service.py`
- Modify: `backend/tests/test_services/test_blocking_gate.py`

**Interfaces:**
- Consumes: `CoverLetterResult.validation_status`, structured provenance validation, and attempt diagnostics.
- Produces: explicit `render_document` stage and one shared cover-letter gate used before every `DocxCLBuilder.build` and `DocumentRepository.create` call.

- [ ] **Step 1: Write failing failure-state tests**

Create a `CoverLetterResult` with:

```python
validation_status="review_required"
validation_issues=["Cover letter body has 248 words; expected 250-350."]
attempt_count=2
```

Assert `generate_cover_letter` raises HTTP 422 whose detail contains structured issues, `attempt_count`, and `final_state`. Assert `render_document`, `_cl_builder.build`, `doc_repo.create`, and `db.commit` are not called.

- [ ] **Step 2: Write failing package and stream gate tests**

For the combined package path and SSE path, return the same review-required result. Assert no cover-letter builder or cover-letter repository create call occurs. The SSE error contains validation metadata but not body paragraphs or personal details.

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_blocking_gate.py -k cover_letter --no-cov
```

Expected: the current service gates only `grounding_issues`, so length/schema review failures still reach rendering.

- [ ] **Step 4: Implement one shared render gate**

Add a facade stage to `CoverLetterGenerator`:

```python
def render_document(
    self,
    result: CoverLetterResult,
    renderer: Callable[[], tuple[str, int]],
) -> tuple[str, int]: ...
```

It refuses non-passing final states and otherwise invokes the supplied backend renderer. `TailorService` remains responsible for constructing the renderer callback and for repository persistence.

Also add:

```python
def _cover_letter_failure_detail(result: CoverLetterResult) -> dict[str, Any] | None: ...
```

It returns `None` only for final states `passed` or `repaired` with no blocking grounding issues. Otherwise it returns:

```python
{
    "error": "Cover letter failed validation — document withheld.",
    "final_state": result.validation_status,
    "attempt_count": result.attempt_count,
    "issues": result.validation_issues or result.grounding_issues,
}
```

Call this helper before every cover-letter render/persistence path, then invoke `CoverLetterGenerator.render_document(...)` instead of calling `DocxCLBuilder.build` directly. This makes the sixth workflow stage explicit without moving database or document-builder concerns into the skill framework.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
pytest -q backend/tests/test_services/test_blocking_gate.py backend/tests/test_services/test_cl_generator.py --no-cov
```

Expected: all blocking-gate and generator tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/cl_generator.py backend/app/services/tailor_service.py backend/tests/test_services/test_blocking_gate.py
git commit -m "fix: gate cover letter rendering on workflow validation"
```

---

### Task 5: Carry Workflow Diagnostics Into Benchmark Artifacts

**Files:**
- Modify: `backend/benchmarks/contracts.py`
- Modify: `backend/benchmarks/runner.py`
- Modify: `backend/tests/benchmarks/test_runner.py`

**Interfaces:**
- Consumes: internal `GenerationProvenance.workflow` and content-plan IDs.
- Produces: optional privacy-safe `workflow_diagnostics` in each `RepetitionResult`.

- [ ] **Step 1: Write failing benchmark diagnostic tests**

Run a fixture repetition and assert `result.json` includes:

```python
payload["workflow_diagnostics"]["skill_id"] == "cover-letter"
payload["workflow_diagnostics"]["skill_version"] == "1.0.0"
payload["workflow_diagnostics"]["final_state"] in {"passed", "repaired", "review_required"}
payload["workflow_diagnostics"]["attempts"][0]["attempt_number"] == 1
```

Serialize the artifact and assert it excludes fixture CV text, cover-letter paragraphs, personal email/phone, and any test secret outside the existing controlled `cv`/`cover_letter` artifact fields.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/benchmarks/test_runner.py -k workflow --no-cov
```

Expected: failure because `RepetitionResult` does not expose workflow diagnostics.

- [ ] **Step 3: Add optional benchmark workflow diagnostics**

Add `workflow_diagnostics: dict[str, Any] | None = None` to `RepetitionResult`. Populate it from internal provenance before public schema serialization removes provenance. Do not add prompt bodies or private documents to this field.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
pytest -q backend/tests/benchmarks/test_runner.py backend/tests/benchmarks/test_reporting.py --no-cov
```

Expected: all runner/reporting tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/benchmarks/contracts.py backend/benchmarks/runner.py backend/tests/benchmarks/test_runner.py
git commit -m "feat: record writing workflow diagnostics"
```

---

### Task 6: Full Compatibility and Privacy Verification

**Files:**
- Modify only if verification exposes a PR3 regression.

**Interfaces:**
- Consumes: all PR3 commits.
- Produces: review-ready branch with evidence for skill, service, benchmark, API, privacy, and docs contracts.

- [ ] **Step 1: Run the focused PR3 suite**

```bash
pytest -q \
  backend/tests/test_skills/test_skill_loader.py \
  backend/tests/test_services/test_writing_contracts.py \
  backend/tests/test_services/test_writing_workflow.py \
  backend/tests/test_services/test_cl_generator.py \
  backend/tests/test_services/test_blocking_gate.py \
  backend/tests/benchmarks \
  --no-cov
```

Expected: zero failures.

- [ ] **Step 2: Run the complete backend suite**

```bash
pytest -q backend/tests --no-cov
```

Expected: zero failures; existing skips/warnings may remain.

- [ ] **Step 3: Run documentation and repository contract checks**

```bash
python scripts/check_docs.py
python scripts/check_readme_contract.py
git diff origin/main...HEAD --check
```

Expected: both scripts pass and Git reports no whitespace errors.

- [ ] **Step 4: Confirm protected configuration and API compatibility**

```bash
git diff --name-only origin/main...HEAD | rg 'model_catalog|profile\\.yaml|config/model' && exit 1 || true
pytest -q backend/tests/test_routers/test_tailor_router.py backend/tests/test_services/test_writing_contracts.py --no-cov
```

Expected: no model-default files changed and compatibility tests pass.

- [ ] **Step 5: Review the requirement matrix**

Confirm:

- every declared stage is directly testable;
- only declared stage inputs are present;
- unknown IDs block before generation;
- repairs are deterministic and bounded;
- diagnostics are secret/document-free;
- rendering and persistence require a passing final state;
- failed results retain structured issues and attempts;
- public API fields and default model are unchanged.

- [ ] **Step 6: Prepare the branch for review**

Use `superpowers:verification-before-completion`, self-review the complete diff, and use `superpowers:finishing-a-development-branch`. Because workspace instructions prohibit subagents unless explicitly requested, perform the code-review checklist locally unless the user asks for delegated review.
