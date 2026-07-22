# Remaining Prompt and Skill Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit every production prompt and skill, then apply versioned factuality, provenance, schema-validation, evidence, numeric-fidelity, and safe-fallback contracts according to each prompt family's risk.

**Architecture:** Add one production prompt catalog that gives every template and inline prompt a stable ID, version, schema, family, and risk classification. Keep each service's existing public API, but assemble prompts from catalog metadata and shared contracts, validate structured output at the service boundary, and suppress unsupported candidate or employer claims before they reach downstream consumers. The checked-in audit is the human-readable source of migration evidence; contract tests keep it synchronized with prompt templates, inline prompt IDs, and skill directories.

**Tech Stack:** Python 3.12+, Pydantic v2, Jinja2, LangChain structured output, pytest/pytest-asyncio, existing `SkillRegistry`, `PromptMetadata`, evidence ledger, and numeric-fidelity validators.

## Global Constraints

- PR4 starts from merge commit `9363a51bff3210b994b433e469b486d8182e6e15`.
- Do not change the default local model, model catalog, `profile.yaml`, provider routing, or context budgets.
- Preserve all existing public API response fields; new provenance or verification fields must be optional.
- Do not add a destructive migration or a persisted failed-output review queue.
- Production prompts must not log full CVs, answers, emails, or failed generated content.
- Candidate-specific claims require approved evidence or a safe empty/review-required fallback.
- Employer/research facts require supplied source provenance or an explicit `not_verified` state.
- Numeric candidate facts must be preserved exactly; no rounding, inference, or mutation.
- Test-only strings and archived specifications are excluded from the production inventory.

---

### Task 1: Checked-in Production Prompt and Skill Inventory

**Files:**
- Create: `docs/implementation-notes/prompt-skill-audit-pr4-root-cause.md`
- Create: `docs/implementation-notes/PRODUCTION_PROMPT_AND_SKILL_AUDIT.md`
- Create: `backend/app/services/prompt_catalog.py`
- Create: `backend/tests/test_services/test_prompt_catalog.py`

**Interfaces:**
- Consumes: `backend/app/prompts/*.j2`, production inline prompt builders, `backend/app/skills/*/SKILL.md`, and `PromptMetadata`.
- Produces: `PromptContract`, `PROMPT_CONTRACTS`, `prompt_contract(prompt_id)`, `prompt_metadata(prompt_id)`, and a synchronized audit table.

- [ ] **Step 1: Write the root-cause note**

Record the discovery evidence: production prompts are split between 15 Jinja templates and inline prompts in scoring, email, cover-letter paragraph regeneration, and rubric synthesis; only CV tailoring and cover-letter generation currently expose version metadata; several high-risk services accept parseable JSON without provenance or post-generation claim validation; company research fabricates a generic fallback when retrieval fails; job classification contains a hard-coded candidate profile.

- [ ] **Step 2: Write failing catalog coverage tests**

Add tests that scan `backend/app/prompts/*.j2` and assert every stem is represented by a `PromptContract`, assert the inline IDs `cover_letter_paragraph_regeneration`, `job_scoring_triage`, `job_scoring_detailed`, `job_scoring_judge`, `rubric_synthesis`, `email_post_application`, `email_post_interview_thankyou`, and `email_warm_reengagement` exist, and assert every `backend/app/skills/*/SKILL.md` path appears in the audit document.

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_prompt_catalog.py --no-cov
```

Expected: import failure because `prompt_catalog.py` does not exist.

- [ ] **Step 4: Implement the catalog**

Define:

```python
@dataclass(frozen=True)
class PromptContract:
    metadata: PromptMetadata
    path: str
    family: str
    output_schema: str
    candidate_fact_risk: Literal["none", "low", "high"]
    employer_fact_risk: Literal["none", "low", "high"]
    numeric_fidelity_risk: Literal["none", "low", "high"]
```

Populate one entry per production Jinja template and inline prompt. Use prompt version `1.0.0` for newly cataloged prompts and retain the existing `2.0.0` versions for CV tailoring and cover-letter prompt IDs.

- [ ] **Step 5: Write the complete audit table**

For every catalog entry and all seven skills, record ID/path, owning feature, inputs, output schema, three risk columns, current validation, required migration, prompt/skill version, and focused test path. Mark migrations completed in this PR only after their implementation task is green.

- [ ] **Step 6: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_prompt_catalog.py backend/tests/test_skills --no-cov
python scripts/check_docs.py
```

Commit:

```bash
git add docs/implementation-notes/prompt-skill-audit-pr4-root-cause.md docs/implementation-notes/PRODUCTION_PROMPT_AND_SKILL_AUDIT.md backend/app/services/prompt_catalog.py backend/tests/test_services/test_prompt_catalog.py
git commit -m "docs: audit production prompts and skills"
```

---

### Task 2: Shared Prompt Assembly and Validation Contracts

**Files:**
- Modify: `backend/app/services/prompt_catalog.py`
- Modify: `backend/app/services/writing_contracts.py`
- Create: `backend/tests/test_services/test_prompt_safety_contracts.py`

**Interfaces:**
- Consumes: catalog metadata, `build_evidence_ledger`, `validate_numeric_fidelity`, and normalized source text.
- Produces: `prompt_contract_block(prompt_id)`, `candidate_claim_contract(prompt_id)`, `research_claim_contract(prompt_id)`, `validate_candidate_output(...)`, and `source_contains(...)`.

- [ ] **Step 1: Write failing shared-contract tests**

Assert catalog blocks include JSON metadata; candidate high-risk blocks require evidence IDs, exact numeric preservation, and safe missing-evidence behavior; research blocks require source IDs, retrieval timestamps, fact dates, confidence/verification state, and `not_verified`; candidate-output validation rejects unsupported numeric tokens while accepting employer-context numbers supplied separately.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_prompt_safety_contracts.py --no-cov
```

Expected: missing helper imports.

- [ ] **Step 3: Implement the helpers**

Build contract text from catalog metadata without embedding private content. Return `ValidationResult` from candidate validation and reuse the existing evidence/numeric tokenizer rather than adding another numeric regex.

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_prompt_safety_contracts.py backend/tests/test_services/test_writing_contracts.py --no-cov
```

Commit:

```bash
git add backend/app/services/prompt_catalog.py backend/app/services/writing_contracts.py backend/tests/test_services/test_prompt_safety_contracts.py
git commit -m "feat: share prompt safety contracts"
```

---

### Task 3: Job Extraction, Classification, and Scoring

**Files:**
- Modify: `backend/app/prompts/jd_analysis.j2`
- Modify: `backend/app/prompts/job_classification.j2`
- Modify: `backend/app/services/jd_analyser.py`
- Modify: `backend/app/services/job_classifier.py`
- Modify: `backend/app/agents/scorer_agent.py`
- Modify: `backend/tests/test_services/test_jd_analyser.py`
- Modify: `backend/tests/test_services/test_job_classifier.py`
- Modify: `backend/tests/test_agents/test_scorer_agent.py`

**Interfaces:**
- Consumes: raw job text, profile evidence, catalog metadata, Pydantic structured-output models, and deterministic score weights.
- Produces: source-grounded job extraction, validated classifications, and score results whose `overall_score` is recomputed from validated components.

- [ ] **Step 1: Add failing extraction tests**

Assert absent salary/rate, IR35, duration, location, sponsorship, and clearance signals remain `None`/absent; source-present values survive; the rendered prompt distinguishes explicit, inferred, and absent values and includes the `jd_analysis` metadata block.

- [ ] **Step 2: Add failing classification and scoring tests**

Assert the classifier prompt uses runtime profile data rather than a hard-coded person, unsupported eligibility assumptions normalize to `unknown`, classification IDs outside the input batch are dropped, score dimensions are clamped to `0.0..1.0`, and `overall_score` is recomputed from configured weights instead of trusting the model.

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_jd_analyser.py backend/tests/test_services/test_job_classifier.py backend/tests/test_agents/test_scorer_agent.py --no-cov
```

Expected: new grounding, runtime-profile, and deterministic-score assertions fail.

- [ ] **Step 4: Implement source grounding**

Pass prompt metadata and extraction rules to `jd_analysis.j2`. Before `_parse_jd_analysis`, clear sensitive extracted values whose normalized value or numeric token is absent from the JD. Preserve optional fields and existing API defaults.

- [ ] **Step 5: Implement classification validation**

Pass a serialized runtime candidate profile into `job_classification.j2`; remove the hard-coded profile. Validate enums, integer score bounds, input IDs, and unsupported assumptions before returning classifications.

- [ ] **Step 6: Implement deterministic score normalization**

Add one pure normalizer for `_ScoreResult` that clamps component values, filters keyword claims against candidate/job evidence, and calculates the weighted sum. Use it before persistence in both detailed LLM paths.

- [ ] **Step 7: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_jd_analyser.py backend/tests/test_services/test_jd_analysis_schema.py backend/tests/test_services/test_job_classifier.py backend/tests/test_agents/test_scorer_agent.py backend/tests/test_tools/test_local_scorer.py --no-cov
```

Commit:

```bash
git add backend/app/prompts/jd_analysis.j2 backend/app/prompts/job_classification.j2 backend/app/services/jd_analyser.py backend/app/services/job_classifier.py backend/app/agents/scorer_agent.py backend/tests/test_services/test_jd_analyser.py backend/tests/test_services/test_job_classifier.py backend/tests/test_agents/test_scorer_agent.py
git commit -m "fix: ground job extraction and scoring prompts"
```

---

### Task 4: Company Research Provenance

**Files:**
- Modify: `backend/app/prompts/company_research.j2`
- Modify: `backend/app/schemas/coach.py`
- Modify: `backend/app/services/company_researcher.py`
- Modify: `backend/app/skills/company-research/SKILL.md`
- Modify: `backend/tests/test_services/test_company_researcher.py`

**Interfaces:**
- Consumes: retrieved search snippets with source URL/title and an explicit retrieval timestamp.
- Produces: optional `sources`, `retrieved_at`, and `verification_state` fields on `CompanyResearchResponse`; unverified fallback never invents a company description.

- [ ] **Step 1: Write failing provenance tests**

Assert each verified research response records at least one source URL and retrieval timestamp, prompt facts reference source IDs, malformed/unsourced facts are dropped, and scrape/LLM failure returns `verification_state="not_verified"` with `description=None` and empty fact arrays.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_company_researcher.py --no-cov
```

Expected: missing provenance fields and invented fallback description.

- [ ] **Step 3: Implement retrieval provenance and schema**

Add:

```python
class ResearchSource(BaseModel):
    source_id: str
    title: str
    url: str
    retrieved_at: datetime
```

Add optional backward-compatible fields to `CompanyResearchResponse`. Preserve source URLs during scraping, require output facts to reference supplied IDs, and discard references to unknown source IDs.

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_company_researcher.py backend/tests/test_routers/test_coach_router.py --no-cov
```

Commit:

```bash
git add backend/app/prompts/company_research.j2 backend/app/schemas/coach.py backend/app/services/company_researcher.py backend/app/skills/company-research/SKILL.md backend/tests/test_services/test_company_researcher.py
git commit -m "feat: add company research provenance"
```

---

### Task 5: Interview Questions and Grounded Model Answers

**Files:**
- Modify: `backend/app/prompts/question_generation.j2`
- Modify: `backend/app/prompts/model_answer.j2`
- Modify: `backend/app/schemas/coach.py`
- Modify: `backend/app/services/question_generator.py`
- Modify: `backend/app/services/model_answer_gen.py`
- Modify: `backend/app/skills/interview-prep/SKILL.md`
- Modify: `backend/tests/test_services/test_question_generator.py`
- Create: `backend/tests/test_services/test_model_answer_gen.py`

**Interfaces:**
- Consumes: job-requirement IDs, approved candidate evidence records, and verified company-research facts.
- Produces: semantically deduplicated questions mapped to requirements and model answers that return an empty safe fallback when candidate evidence or numeric fidelity fails.

- [ ] **Step 1: Write failing question tests**

Assert every question has a valid `requirement_id`, categories are classified, semantically duplicate normalized questions are removed, candidate summary text does not cause the question to imply candidate experience, and metadata is present.

- [ ] **Step 2: Write failing model-answer tests**

Assert the prompt receives approved evidence IDs, exact metrics survive, invented/mutated numbers produce an empty result, and missing evidence produces an empty review-required fallback rather than a fabricated STAR story.

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_question_generator.py backend/tests/test_services/test_model_answer_gen.py --no-cov
```

- [ ] **Step 4: Implement questions**

Build stable requirement IDs from JD text/analysis, request `requirement_id` in structured output, validate it against supplied IDs, and deduplicate on normalized tokens while preserving order. Add `requirement_id: str | None = None` to `QuestionPresentation`.

- [ ] **Step 5: Implement model-answer grounding**

Build an evidence ledger from the supplied candidate summary/evidence input, render shared candidate contracts and metadata, validate the full answer plus STAR fields against approved numeric tokens, and return `""` on blocking validation or no evidence.

- [ ] **Step 6: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_question_generator.py backend/tests/test_services/test_model_answer_gen.py backend/tests/test_routers/test_coach_router.py --no-cov
```

Commit:

```bash
git add backend/app/prompts/question_generation.j2 backend/app/prompts/model_answer.j2 backend/app/schemas/coach.py backend/app/services/question_generator.py backend/app/services/model_answer_gen.py backend/app/skills/interview-prep/SKILL.md backend/tests/test_services/test_question_generator.py backend/tests/test_services/test_model_answer_gen.py
git commit -m "fix: ground interview questions and answers"
```

---

### Task 6: CV Import and Normalisation

**Files:**
- Modify: `backend/app/prompts/cv_parsing.j2`
- Modify: `backend/app/services/cv_parser.py`
- Modify: `backend/tests/test_services/test_cv_parser.py`

**Interfaces:**
- Consumes: raw extracted CV text.
- Produces: schema-normalized CV data, source-preserving warnings, and safe clearing of ambiguous/unverifiable fields.

- [ ] **Step 1: Write failing import tests**

Assert malformed top-level shapes fall back safely; inferred dates, seniority, credentials, employers, locations, education, metrics, and skill items are cleared/dropped; raw source text remains untouched; ambiguity creates warnings; prompt metadata and extract-vs-normalize rules are present.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_cv_parser.py --no-cov
```

- [ ] **Step 3: Implement normalization**

Validate the raw mapping shape before iterating it. Apply source-substring checks to every personal, experience, skill, certification, and education fact; preserve exact source values; use empty values for absent data. Keep the existing `CVParseResult` API and warning behavior.

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_cv_parser.py backend/tests/test_routers/test_resume_router.py --no-cov
```

Commit:

```bash
git add backend/app/prompts/cv_parsing.j2 backend/app/services/cv_parser.py backend/tests/test_services/test_cv_parser.py
git commit -m "fix: validate imported CV evidence"
```

---

### Task 7: Coach, Evaluation, and Recommendation Prompts

**Files:**
- Modify: `backend/app/prompts/answer_evaluation.j2`
- Modify: `backend/app/prompts/follow_up.j2`
- Modify: `backend/app/prompts/session_report.j2`
- Modify: `backend/app/prompts/speech_feedback.j2`
- Modify: `backend/app/prompts/video_feedback.j2`
- Modify: `backend/app/services/answer_evaluator.py`
- Modify: `backend/app/services/feedback_generator.py`
- Modify: `backend/app/services/rubric_synthesiser.py`
- Modify: `backend/tests/test_services/test_answer_evaluator.py`
- Modify: `backend/tests/test_services/test_rubric_synthesiser.py`
- Create: `backend/tests/test_services/test_coach_prompt_contracts.py`

**Interfaces:**
- Consumes: transcripts, deterministic metrics, existing scores, and catalog metadata.
- Produces: prompts and outputs that label observation, interpretation, and recommendation separately and cite transcript/metric evidence for candidate-specific observations.

- [ ] **Step 1: Write failing coach contract tests**

Assert all five templates and inline rubric prompt contain metadata and observation/interpretation/recommendation rules; evaluation evidence is quoted from transcript or deterministic metrics; unsupported candidate/employer facts are removed; generic advice is explicitly labelled recommendation.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_answer_evaluator.py backend/tests/test_services/test_rubric_synthesiser.py backend/tests/test_services/test_coach_prompt_contracts.py --no-cov
```

- [ ] **Step 3: Implement prompt and output validation**

Pass catalog blocks to every coach template. Add optional evidence-reference fields where schemas permit without removing existing fields. Filter evidence excerpts against the transcript and retain deterministic fallback behavior when validation fails.

- [ ] **Step 4: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_answer_evaluator.py backend/tests/test_services/test_rubric_synthesiser.py backend/tests/test_services/test_coach_prompt_contracts.py backend/tests/test_routers/test_coach_router.py --no-cov
```

Commit:

```bash
git add backend/app/prompts/answer_evaluation.j2 backend/app/prompts/follow_up.j2 backend/app/prompts/session_report.j2 backend/app/prompts/speech_feedback.j2 backend/app/prompts/video_feedback.j2 backend/app/services/answer_evaluator.py backend/app/services/feedback_generator.py backend/app/services/rubric_synthesiser.py backend/tests/test_services/test_answer_evaluator.py backend/tests/test_services/test_rubric_synthesiser.py backend/tests/test_services/test_coach_prompt_contracts.py
git commit -m "fix: separate coach evidence and recommendations"
```

---

### Task 8: Remaining Candidate-facing and Low-risk Prompt Coverage

**Files:**
- Modify: `backend/app/prompts/ats_keywords.j2`
- Modify: `backend/app/prompts/summary_rewrite.j2`
- Modify: `backend/app/services/ats_optimiser.py`
- Modify: `backend/app/services/email_generator.py`
- Modify: `backend/app/skills/ats-optimization/SKILL.md`
- Modify: `backend/app/skills/screening-answers/SKILL.md`
- Modify: `backend/app/skills/form-mapping/SKILL.md`
- Create: `backend/tests/test_services/test_email_prompt_contracts.py`
- Modify: `backend/tests/test_services/test_ats_optimiser.py`
- Modify: `backend/tests/test_services/test_prompt_catalog.py`

**Interfaces:**
- Consumes: approved profile/CV evidence, prompt catalog blocks, and existing email/ATS schemas.
- Produces: grounded email/summary/ATS prompts, safe numeric validation, and complete runtime metadata coverage for remaining low-risk templates.

- [ ] **Step 1: Write failing candidate-facing tests**

Assert all three email prompts use runtime approved evidence rather than hard-coded candidate claims; prompt metadata is present; unsupported/mutated candidate numbers withhold the generated email body; ATS and summary prompts use shared factuality/numeric contracts.

- [ ] **Step 2: Write failing remaining-coverage tests**

Assert every cataloged production prompt renders its metadata ID/version and every high-risk audit row names a focused regression test and completed migration.

- [ ] **Step 3: Verify RED**

Run:

```bash
pytest -q backend/tests/test_services/test_email_prompt_contracts.py backend/tests/test_services/test_ats_optimiser.py backend/tests/test_services/test_prompt_catalog.py --no-cov
```

- [ ] **Step 4: Implement email and ATS grounding**

Load candidate facts from existing runtime profile/master-CV sources, build approved evidence records, inject catalog/shared contracts, validate numeric output, and retain the current `GeneratedEmail` API with an empty body on blocking failure.

- [ ] **Step 5: Finish low-risk metadata and skill contracts**

Pass catalog metadata into remaining summarisation/classification templates. Update skill constraints to reference explicit missing-data behavior and factuality rules without creating another skill framework.

- [ ] **Step 6: Update the audit completion column**

Mark every high-risk family migrated, record exact validators and focused test paths, and leave only explicitly low-risk/no-migration entries as `metadata_only`.

- [ ] **Step 7: Verify and commit**

Run:

```bash
pytest -q backend/tests/test_services/test_email_prompt_contracts.py backend/tests/test_services/test_ats_optimiser.py backend/tests/test_services/test_prompt_catalog.py backend/tests/test_services/test_skill_injection.py backend/tests/test_skills --no-cov
python scripts/check_docs.py
```

Commit:

```bash
git add backend/app/prompts/ats_keywords.j2 backend/app/prompts/summary_rewrite.j2 backend/app/services/ats_optimiser.py backend/app/services/email_generator.py backend/app/skills/ats-optimization/SKILL.md backend/app/skills/screening-answers/SKILL.md backend/app/skills/form-mapping/SKILL.md backend/tests/test_services/test_email_prompt_contracts.py backend/tests/test_services/test_ats_optimiser.py backend/tests/test_services/test_prompt_catalog.py docs/implementation-notes/PRODUCTION_PROMPT_AND_SKILL_AUDIT.md
git commit -m "fix: complete production prompt safety audit"
```

---

### Task 9: Full Compatibility and Privacy Verification

**Files:**
- Modify only if verification exposes a PR4 regression.

**Interfaces:**
- Consumes: all PR4 commits.
- Produces: a review-ready branch with prompt/skill inventory, high-risk regression evidence, and unchanged model/API contracts.

- [ ] **Step 1: Run the complete PR4-focused suite**

```bash
pytest -q \
  backend/tests/test_services/test_prompt_catalog.py \
  backend/tests/test_services/test_prompt_safety_contracts.py \
  backend/tests/test_services/test_jd_analyser.py \
  backend/tests/test_services/test_job_classifier.py \
  backend/tests/test_agents/test_scorer_agent.py \
  backend/tests/test_services/test_company_researcher.py \
  backend/tests/test_services/test_question_generator.py \
  backend/tests/test_services/test_model_answer_gen.py \
  backend/tests/test_services/test_cv_parser.py \
  backend/tests/test_services/test_answer_evaluator.py \
  backend/tests/test_services/test_rubric_synthesiser.py \
  backend/tests/test_services/test_coach_prompt_contracts.py \
  backend/tests/test_services/test_email_prompt_contracts.py \
  backend/tests/test_skills \
  --no-cov
```

- [ ] **Step 2: Run the complete backend suite**

```bash
pytest -q backend/tests --no-cov
```

- [ ] **Step 3: Run repository contracts**

```bash
python scripts/check_docs.py
python scripts/check_readme_contract.py
git diff origin/main...HEAD --check
```

- [ ] **Step 4: Confirm protected configuration**

```bash
git diff --name-only origin/main...HEAD | rg 'model_catalog|profile\\.yaml|config/model' && exit 1 || true
```

- [ ] **Step 5: Review the acceptance matrix**

Confirm the audit covers every production template, inline prompt, and skill; high-risk tasks use shared contracts and focused tests; structured output is validated; candidate claims have evidence or safe fallback; research facts have provenance or `not_verified`; all prompt versions are present; API fields remain available; and model defaults are unchanged.

- [ ] **Step 6: Publish for review**

Use `superpowers:verification-before-completion`, perform the local code-review checklist because workspace instructions prohibit subagents, then use `superpowers:finishing-a-development-branch` to push and open the PR while preserving the worktree.
