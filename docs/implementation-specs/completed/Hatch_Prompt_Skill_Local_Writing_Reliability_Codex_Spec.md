---
title: Hatch Prompt Skill And Local Writing Reliability Specification
document_type: implementation-spec
status: historical
implementation_status: partial
applies_to: main
last_verified: 2026-07-18
supersedes: []
superseded_by:
  - Hatch_Prompt_Skill_Local_Writing_Reliability_Codex_Spec_v2.md
---

# Hatch Prompt, Skill, and Local Writing Reliability Implementation Specification

**Status:** Implementation-ready  
**Repository:** `https://github.com/arvindsoni2/hatch`  
**Authoritative implementation baseline:** the clean local branch through commit `4726aa8`  
**Evidence source:** `data/benchmarks/results/20260715T183303Z-8d9f4a72/report.md`  
**Prepared:** 2026-07-16  

> **For Codex:** Implement this specification as separate pull requests in the prescribed order. Do not combine the PRs. Use test-driven development, preserve existing public contracts unless this specification explicitly changes them, and stop after each PR for review and benchmark evidence.

---

## 1. Executive decision

The five-model benchmark does **not** justify changing Hatch's default local writing model.

All 15 CV/cover-letter pairs completed successfully, but every pair failed the hard gates because every cover letter contained fewer than 250 body words. CV structure remained broadly reliable across all models. The common failure therefore belongs to the shared cover-letter prompt/generator/validation path, not to one model.

The required sequence is:

1. Fix the cover-letter generation and validation contract.
2. Rerun the existing benchmark harness unchanged apart from required result fields.
3. Establish shared evidence, factuality, numeric-fidelity, prompt-versioning, and repair contracts.
4. Audit and migrate the remaining prompts and skills.
5. Expand the benchmark corpus.
6. Consider a model change only after eligible outputs can be scored.

No model-selection change is permitted in PR 1 through PR 4.

---

## 2. Benchmark evidence

### 2.1 Results

| Model | Cover-letter words across seeds | Median pair latency | Hard-gate result |
|---|---:|---:|---|
| Qwen3.5 4B | 207, 216, 218 | 21.32 min | 0/3 |
| Qwen3.5 9B | 182, 209, 165 | 14.97 min | 0/3 |
| Qwen3 8B | 208, 213, 194 | 27.72 min | 0/3 |
| Gemma4 e2b | 165, 160, 167 | 3.80 min | 0/3 |
| Gemma4 e4b | 215, 185, 196 | 9.84 min | 0/3 |

### 2.2 Additional findings

- All generated CVs passed the structural hard gates covering roles, bullet counts, education, certifications, placeholders, and length preservation.
- Qwen3.5 4B introduced unsupported `20+` once.
- Gemma4 e4b changed source evidence `120+` to `120` once.
- Qwen3.5 9B paraphrased CV evidence more aggressively and produced additional advisory similarity warnings.
- No writing-quality score was assigned because hard-gate-failing pairs are deliberately excluded.
- The official run preserved database and profile hashes.
- Backend health passed and the frontend returned HTTP 200.
- The official local baseline reported 847 tests passed and 2 skipped.

### 2.3 Limitations

The existing benchmark covers one Delivery Manager case with three repetitions per model. It can identify a shared defect but cannot support a universal model ranking.

---

## 3. Goals

This programme must:

1. Make 250–350 body-word cover letters a deterministic product contract.
2. Repair both under-length and over-length output.
3. Count actual body words in application code.
4. prevent unsupported or mutated numeric evidence.
5. Separate evidence selection, prose generation, deterministic validation, targeted repair, and rendering.
6. Give every production prompt and skill an identifiable version.
7. Make model benchmarking reproducible and comparable.
8. Preserve Hatch's evidence-grounded and human-review boundaries.
9. Retain the current default model until a post-repair benchmark supports a change.
10. Avoid database, profile, and generated-document mutations during benchmark-only execution.

---

## 4. Non-goals

The following are explicitly out of scope unless required to preserve an existing contract:

- Changing the default local model in PR 1–PR 4.
- Rewriting the CV generator solely for stylistic improvement.
- Adding a new cloud provider.
- Changing the DOCX source-of-truth policy.
- Changing application-submission or human-review boundaries.
- Introducing an external prompt-management SaaS.
- Introducing a new database only for prompt telemetry.
- Allowing unrestricted autonomous retries.
- Using an LLM's self-reported word count or self-reported compliance as a hard gate.
- Treating similarity heuristics as proof of factual correctness.
- Broad frontend redesign.
- Benchmarking model quantisations not already supported by the harness.

---

## 5. Repository and branch rules

1. The local branch through `4726aa8` is authoritative because it contains nine unpushed benchmark commits.
2. Before implementation, Codex must run:
   ```bash
   git status --short
   git rev-parse --short HEAD
   git log --oneline --decorate -12
   ```
3. Expected precondition:
   - working tree is clean;
   - `HEAD` is `4726aa8`, or a direct descendant containing the same benchmark implementation;
   - no benchmark-generated personal files are staged.
4. Codex must inspect the actual local files before locking paths:
   ```bash
   git ls-files backend | grep -Ei 'prompt|skill|cover|tailor|benchmark|quality|validator'
   git grep -n "CoverLetterGenerator"
   git grep -n "word_count"
   git grep -n "350"
   git grep -n "250"
   git grep -n "unsupported_numeric_token"
   ```
5. This specification uses logical component names where unpushed paths cannot be verified publicly. Codex must modify the existing owning files rather than introduce parallel duplicate implementations.
6. Do not rename public API fields or persisted schema fields without a migration and backward-compatibility test.
7. Benchmark fixtures and reports must remain free of personal secrets and ignored generated documents.

---

## 6. Architectural target

The document-writing flow must become:

```text
Confirmed profile/master CV
        +
Parsed job description
        ↓
Approved evidence ledger
        ↓
Task-specific content plan
        ↓
Versioned prompt assembly
        ↓
Initial structured draft
        ↓
Deterministic validators
        ↓
Targeted repair, when eligible
        ↓
Deterministic validators
        ↓
Render reviewable document
        ↓
Persist provenance and validation result
```

The LLM generates prose. Application code owns:

- body extraction;
- word counting;
- schema validation;
- immutable-token comparison;
- unsupported numeric-token detection;
- retry eligibility;
- retry limits;
- final pass/fail state;
- benchmark scoring eligibility.

---

## 7. Locked product contracts

## 7.1 Cover-letter word-count contract

### Accepted final range

- Minimum: **250 body words**
- Maximum: **350 body words**
- Internal generation target: **285–315 body words**

### Counted content

Count only the substantive cover-letter body paragraphs.

### Excluded content

Exclude:

- recipient address;
- sender address;
- date;
- subject line;
- salutation;
- complimentary close;
- candidate name/signature;
- JSON keys;
- markdown fences;
- metadata;
- model-reported counts;
- evidence IDs.

### Tokenisation rule

Implement one shared deterministic word-count helper.

Required behaviour:

- normalize Unicode whitespace;
- trim leading/trailing whitespace;
- collapse repeated whitespace;
- count human-readable word tokens;
- keep expressions such as `20+`, `120+`, `£2m`, `15%`, and hyphenated terms as one token when reasonably possible;
- use the same helper in generation validation, API output, tests, and benchmark gates.

Do not use different word-count implementations in the generator and benchmark.

## 7.2 Paragraph-budget contract

The generation prompt must request five body paragraphs with these guidance budgets:

| Paragraph | Purpose | Target |
|---|---|---:|
| 1 | Opening and role motivation | 45–55 words |
| 2 | Primary experience and evidence | 75–90 words |
| 3 | Secondary capability and evidence | 70–85 words |
| 4 | Employer/role alignment | 55–65 words |
| 5 | Closing | 30–40 words |

These are generation guidance, not separate hard gates. The hard gate remains the total 250–350 body-word range.

The prompt must not combine this requirement with contradictory language such as “very brief,” “short letter,” or “four concise paragraphs.”

## 7.3 Repair contract

Allowed automatic attempts:

1. Initial generation.
2. One targeted repair.
3. A second targeted repair only when:
   - the first repair fixed its targeted defect; and
   - a different deterministic defect remains.

Maximum model calls for one cover-letter draft: **3**.

After the allowed attempts, return a safe `review_required` or existing equivalent state with validator details. Do not loop.

### Under-length repair

When computed body count is below 250:

- include the computed count;
- request a target of 285–315;
- identify paragraphs below guidance budget;
- provide approved unused evidence that may be added;
- require preservation of all immutable tokens and already-valid claims;
- instruct the model not to add generic filler or unsupported claims.

### Over-length repair

When computed body count is above 350:

- include the computed count;
- request a target of 285–315;
- identify the longest paragraphs;
- require compression without deleting required evidence;
- preserve immutable tokens.

### Numeric-fidelity repair

When an approved immutable token is mutated:

- supply expected and observed expressions;
- request exact restoration;
- forbid any other content changes where possible.

### Unsupported-number repair

When a numeric expression is not present in approved evidence or permitted job-description context:

- identify the unsupported expression;
- require removal or replacement with approved non-numeric wording;
- do not allow the model to justify or infer it.

## 7.4 Numeric-evidence contract

The following must be preserved exactly when used:

- digits;
- leading signs;
- `+`;
- `%`;
- currency symbols;
- decimal points;
- commas;
- ranges and dashes;
- units;
- the associated semantic phrase where needed to retain meaning.

Examples:

- `20+ years` must not become `20 years`.
- `120+ locations` must not become `120 locations`.
- `£2 million` must not become `£2` or `$2 million`.
- `15%` must not become `15`.
- `2018–2022` must not become an inferred duration unless that duration also exists in approved evidence.

The model must not calculate, combine, estimate, extrapolate, round, or infer numeric claims.

## 7.5 Evidence contract

Every candidate claim used by a writing task must derive from an approved evidence entry.

Minimum evidence representation:

```python
class EvidenceItem:
    id: str
    text: str
    source_path: str
    immutable_tokens: list[str]
    evidence_type: str
```

Equivalent existing domain types may be extended instead of creating this exact class.

Required evidence types include:

- profile summary;
- role responsibility;
- achievement;
- skill;
- education;
- certification;
- preference;
- eligibility.

The generator may paraphrase prose but may not alter immutable evidence.

## 7.6 Safe missing-evidence behaviour

When the requested content cannot be grounded:

- omit the claim;
- use neutral wording;
- or return a structured missing-evidence/review-required result.

Do not invent a STAR example, employer fact, technical skill, outcome, team size, budget, duration, or metric.

## 7.7 Prompt-version contract

Every production prompt invocation must expose:

- `prompt_id`;
- `prompt_version`;
- `schema_version`;
- `task_name`.

Prompt version must be persisted in benchmark results and, where the existing document-generation record supports metadata safely, generation provenance.

Use semantic versions for externally meaningful prompt behaviour. A change to hard constraints, schema, evidence rules, or repair logic requires a version increment.

## 7.8 Model-neutral quality contract

All supported models must share the same:

- factuality rules;
- body-word gate;
- numeric-fidelity gate;
- evidence-grounding gate;
- schema requirements;
- retry limits;
- final eligibility criteria.

Model-specific adapters may change only presentation details such as:

- whether a schema example is included;
- prompt compactness;
- stop sequences;
- grammar-constrained decoding configuration;
- maximum output tokens;
- sampling defaults.

They may not weaken product contracts.

---

## 8. Required shared components

Codex must use existing project conventions and names where suitable. Do not create duplicates if equivalents exist.

Logical components required:

### 8.1 Body text metrics

Responsibilities:

- extract normalized body paragraphs from structured output;
- calculate body word count;
- return paragraph-level counts;
- expose one canonical implementation.

Suggested interface:

```python
@dataclass(frozen=True)
class BodyMetrics:
    body_word_count: int
    paragraph_word_counts: tuple[int, ...]
    normalized_body: str

def calculate_cover_letter_body_metrics(draft: CoverLetterDraft) -> BodyMetrics:
    ...
```

### 8.2 Evidence ledger builder

Responsibilities:

- convert selected master-CV/profile evidence into stable entries;
- capture source paths;
- extract immutable numeric expressions;
- deduplicate evidence;
- preserve source ordering deterministically.

### 8.3 Numeric token extractor

Responsibilities:

- extract numeric expressions from evidence and generated prose;
- preserve signs, symbols, units, and ranges;
- avoid treating evidence IDs, dates in metadata, or JSON syntax as generated claims;
- support deterministic tests.

Suggested output:

```python
@dataclass(frozen=True)
class NumericToken:
    raw: str
    normalized: str
    context: str
```

### 8.4 Validation result

Use one common result shape:

```python
@dataclass(frozen=True)
class ValidationIssue:
    gate: str
    code: str
    severity: Literal["blocking", "advisory"]
    message: str
    expected: str | None = None
    observed: str | None = None
    evidence_id: str | None = None

@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: tuple[ValidationIssue, ...]
    metrics: dict[str, int | float | str]
```

Existing equivalent schemas may be extended.

### 8.5 Targeted repair request

Suggested logical shape:

```python
@dataclass(frozen=True)
class RepairRequest:
    repair_type: Literal[
        "under_length",
        "over_length",
        "restore_numeric_fidelity",
        "remove_unsupported_numeric_token",
        "restore_schema",
    ]
    current_draft: CoverLetterDraft
    validation_issues: tuple[ValidationIssue, ...]
    approved_evidence: tuple[EvidenceItem, ...]
    target_min_words: int = 285
    target_max_words: int = 315
```

### 8.6 Prompt metadata

Suggested logical shape:

```python
@dataclass(frozen=True)
class PromptMetadata:
    prompt_id: str
    prompt_version: str
    schema_version: str
    task_name: str
```

---

## 9. Prompt assembly rules

Production prompts must be assembled in this order:

1. Role and task boundary.
2. Shared factuality contract.
3. Shared numeric-fidelity contract.
4. Task-specific instructions.
5. Approved evidence.
6. Job-description context.
7. Output schema.
8. Final short compliance reminder.

The final reminder must contain only the highest-risk requirements:

```text
FINAL CHECK BEFORE RETURNING:
1. The body must contain 285–315 words.
2. Use only APPROVED_EVIDENCE for candidate claims.
3. Preserve every IMMUTABLE_TOKEN exactly.
4. Return only the required structured schema.
```

Do not ask the model to provide a trustworthy `word_count`. If an existing schema requires the field for compatibility, retain it temporarily as optional advisory metadata and never use it for validation.

---

## 10. Structured cover-letter output

Prefer structured paragraphs over one opaque body string.

Required logical fields:

```json
{
  "opening": "...",
  "primary_evidence": "...",
  "secondary_evidence": "...",
  "role_alignment": "...",
  "closing": "...",
  "evidence_ids_used": ["..."]
}
```

Compatibility rule:

- Existing API consumers must continue to receive the assembled cover-letter body/document.
- Structured fields may remain internal if exposing them would break or unnecessarily expand the API.
- The backend owns final assembly and rendering.
- The backend calculates all metrics.

---

# 11. Pull-request plan

## PR 1 — Cover-letter generation contract repair

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Purpose:** Fix the benchmark-blocking shared defect without broad prompt refactoring.

### Scope

1. Locate the current `CoverLetterGenerator` and owning prompt.
2. Add canonical body metrics.
3. Stop trusting model-supplied `word_count`.
4. Add the under-length repair path.
5. Preserve or improve the existing over-length repair path.
6. Add paragraph budgets and 285–315 internal target.
7. Add exact numeric-token preservation for cover-letter generation.
8. Enforce maximum call/repair limits.
9. Extend benchmark output with first-pass and post-repair data.
10. Rerun focused tests and the five-model harness.

### Required implementation behaviour

#### Initial generation

- Build the prompt from current evidence.
- Request five structured paragraphs.
- Target 285–315 body words.
- Request exact preservation of immutable numeric tokens.
- Parse response through the existing safe structured-output path.

#### Validation

After every attempt, calculate:

- body word count;
- paragraph word counts;
- unsupported numeric tokens;
- missing/mutated immutable numeric tokens;
- required fields/schema;
- existing hard gates.

#### Repair selection order

Use deterministic priority:

1. malformed/unparseable schema;
2. unsupported numeric token;
3. mutated/missing immutable numeric token;
4. under-length;
5. over-length.

Only one repair type is targeted per call.

#### Final state

- Pass only if every blocking gate passes.
- Do not assign writing-quality eligibility otherwise.
- Return validator details when review is required.

### Tests

Codex must add focused unit tests for at least:

1. body count excludes salutation and sign-off;
2. body count collapses whitespace;
3. `20+` counts as one word;
4. `120+ locations` is preserved;
5. model-reported count cannot override computed count;
6. 249 words triggers under-length repair;
7. 250 words passes the length gate;
8. 350 words passes the length gate;
9. 351 words triggers over-length repair;
10. under-length repair targets 285–315 words;
11. retry limit is enforced;
12. a second repair is allowed only for a different remaining defect;
13. `120+` changed to `120` is blocking;
14. unsupported `20+` is blocking;
15. no unsupported numeric tokens yields pass;
16. failed final validation returns review-required, not success;
17. existing rendering/API output remains compatible;
18. benchmark run leaves profile/database hashes unchanged.

### Acceptance criteria

- All existing tests pass.
- New focused tests pass.
- No model-default configuration changes.
- No database/profile hash mutation during benchmark.
- The benchmark report distinguishes:
  - first-pass gate rate;
  - post-repair gate rate;
  - repair count;
  - final body count;
  - numeric-fidelity failures;
  - total latency.
- At least one full official benchmark run completes.
- If all models still fail the length gate, PR 1 must not be declared successful merely because tests pass; include diagnostic attempt traces in the report.
- Documentation and README contract checks pass.

### Commit guidance

Use small commits, for example:

```text
test: define cover letter body metric contract
feat: calculate deterministic cover letter body metrics
test: define under-length repair behaviour
fix: repair under-length cover letter drafts
test: enforce numeric evidence fidelity
fix: preserve immutable numeric tokens in cover letters
feat: report first-pass and repaired benchmark results
docs: document cover letter generation contract
```

---

## PR 2 — Shared evidence and prompt contracts

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Purpose:** Replace prompt-by-prompt factuality drift with shared typed contracts.

### Scope

1. Introduce or consolidate the approved evidence ledger.
2. Introduce shared factuality and numeric-fidelity prompt fragments.
3. Add prompt metadata/versioning.
4. Add common validation result types.
5. Migrate cover-letter and CV-tailoring flows first.
6. Preserve public API and persisted-document compatibility.
7. Record prompt and schema versions in benchmark results.
8. Record generation provenance where an existing safe metadata field or extensible JSON structure exists.

### Evidence ledger requirements

- stable evidence ID;
- exact source text;
- source path;
- immutable numeric tokens;
- evidence type;
- deterministic ordering;
- no hidden model inference.

### CV-tailoring migration

Do not broadly rewrite the successful CV flow. Add:

- immutable-token validation;
- source evidence IDs for generated/rephrased claims;
- unsupported-numeric-token gate;
- safe missing-evidence behaviour;
- prompt metadata.

Where the current response schema can safely support it, each generated bullet should internally retain:

```json
{
  "text": "...",
  "source_evidence_ids": ["..."],
  "change_type": "preserved|rephrased|removed",
  "new_claims": []
}
```

Do not expose internal provenance publicly unless already consistent with API design.

### Prompt versioning requirements

At minimum:

| Prompt | Initial new version |
|---|---|
| Cover-letter generation | `2.0.0` |
| Cover-letter repair | `1.0.0` |
| CV tailoring | next semantically valid version |
| Shared factuality contract | `1.0.0` |
| Shared numeric-fidelity contract | `1.0.0` |

### Tests

Include:

- evidence IDs are deterministic;
- duplicate evidence is deduplicated;
- immutable tokens are extracted correctly;
- numeric dates/metadata outside candidate prose are not false positives;
- shared fragments are present in assembled CV and cover-letter prompts;
- prompt metadata is present in benchmark records;
- CV structural gates remain unchanged;
- existing API fixtures remain valid;
- old generated records without prompt metadata remain readable.

### Acceptance criteria

- Cover-letter and CV prompts use the same factuality and numeric contracts.
- No production path can bypass immutable-token validation.
- Existing tests pass.
- No destructive migration.
- Benchmark reports identify prompt versions.
- Default model remains unchanged.

---

## PR 3 — Skill orchestration, targeted repair, and observability

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium–High  
**Purpose:** Turn skills into bounded workflows rather than opaque prompt wrappers.

### Scope

Refactor the document-generation skill orchestration into explicit stages:

```text
select_evidence
→ create_content_plan
→ generate_draft
→ validate_draft
→ repair_specific_failure
→ render_document
```

Use current skill abstractions and naming. Do not create a competing second skill framework.

### Skill contract

Every migrated writing skill must declare or expose:

- skill ID;
- skill version;
- input schema;
- output schema;
- preconditions;
- validators;
- allowed repair actions;
- maximum attempts;
- safe failure state.

### Content planning

For cover letters, create a deterministic or structured content plan before prose generation:

```json
{
  "opening_evidence_ids": ["..."],
  "primary_evidence_ids": ["..."],
  "secondary_evidence_ids": ["..."],
  "alignment_job_requirement_ids": ["..."]
}
```

Rules:

- evidence selection may be model-assisted only if output is validated against the ledger;
- no unknown evidence IDs;
- no generated numeric claims;
- unused evidence may be offered to under-length repair;
- content plans must be persisted only if consistent with existing privacy/storage rules.

### Observability

Record non-secret diagnostic fields:

- generation/benchmark run ID;
- task;
- skill ID/version;
- prompt ID/version;
- model ID;
- attempt number;
- repair type;
- input/output token counts when available;
- latency;
- validator results;
- computed body count;
- final state.

Never log:

- provider secrets;
- full private CV by default;
- full cover-letter content in standard application logs;
- personal data beyond current established policy.

Benchmark artifacts may contain controlled fixture content under existing ignored benchmark paths.

### Tests

- each stage receives only declared inputs;
- unknown evidence IDs fail validation;
- repair selection is deterministic;
- attempt limits work across the skill boundary;
- telemetry excludes secrets and full private document content;
- rendering occurs only after blocking gates pass or explicit human-review fallback;
- failure state remains reviewable and does not silently discard the draft.

### Acceptance criteria

- document-writing skill flow is stage-based and testable;
- targeted repair uses structured validator output;
- no unlimited retry path;
- no logging/privacy regression;
- existing API behaviour remains compatible;
- default model remains unchanged.

---

## PR 4 — Remaining prompt and skill audit

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium  
**Purpose:** Apply the shared contracts to every production AI task according to its risk.

### Mandatory discovery

Before changing code, produce a checked-in audit table under the existing current documentation hierarchy, not an archive folder.

For every production prompt and skill, record:

- ID/path;
- owning feature;
- input data;
- output schema;
- candidate-fact risk;
- employer/research-fact risk;
- numeric-fidelity risk;
- current validation;
- required migration;
- prompt version;
- test coverage.

Exclude test-only strings and historical archived specifications from production migration.

### Prompt families

#### A. Job extraction

Required behaviour:

- schema-constrained output;
- use `null` for absent values;
- retain evidence spans where the existing model permits;
- distinguish explicit, inferred, and absent;
- never infer salary, sponsorship, location eligibility, or clearance from generic wording;
- numeric tokens come from the job description, not candidate evidence.

#### B. Job scoring

Required behaviour:

- deterministic calculation where possible;
- separate score components from prose rationale;
- every rationale claim must map to profile/job evidence;
- no fabricated justification after choosing a score;
- no candidate metrics added by the model.

#### C. Company research

Required behaviour:

- source/provenance field;
- retrieval timestamp;
- fact date when known;
- confidence or verification state;
- “not verified” rather than invention;
- research facts must never be blended into candidate history.

#### D. Interview questions

Required behaviour:

- classify competency/category;
- map each question to a job requirement;
- deduplicate semantically similar questions;
- do not imply the candidate has experience not present in evidence.

#### E. Interview model answers and Question Bank

Required behaviour:

- use only approved candidate evidence;
- preserve metrics exactly;
- return missing-evidence/review-required when no grounded STAR example exists;
- distinguish an answer template from a claim that the candidate performed an action;
- do not invent dates, team sizes, budgets, tools, outcomes, or stakeholders.

#### F. Coach and recommendations

Required behaviour:

- clearly separate observation, interpretation, and recommendation;
- do not state inference as confirmed candidate or employer fact;
- evidence IDs for candidate-specific observations;
- recommendations may be general but must be labelled as recommendations.

#### G. CV import/normalisation

Required behaviour:

- distinguish extracted source text from normalized interpretation;
- preserve raw source evidence;
- no inferred credentials, dates, seniority, employers, or metrics;
- surface ambiguous fields for user review.

#### H. Job-search and ranking prompts

Required behaviour:

- prevent candidate evidence from leaking into external search queries unless current privacy rules allow it;
- no unsupported eligibility assumptions;
- distinguish discovery relevance from application suitability.

### Migration priority

Use this order:

1. candidate-facing generated documents;
2. interview answers;
3. CV import/normalisation;
4. scoring/rationale;
5. company research;
6. question generation;
7. Coach recommendations;
8. low-risk summarisation/classification.

### Acceptance criteria

- every production prompt/skill appears in the audit;
- every high-risk task uses shared factuality and numeric contracts;
- every structured task validates its schema;
- every candidate-specific claim has evidence or safe fallback;
- prompt versions are present;
- focused regression tests exist for each high-risk family;
- no model-default change.

---

## PR 5 — Representative local-model benchmark and selection decision

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium  
**Purpose:** Produce enough eligible evidence to make a model decision.

### Benchmark corpus

Add at least these controlled fixture cases:

| Case | Main risk |
|---|---|
| Delivery/project manager | leadership and metrics |
| AI/software engineer | technical stack fidelity |
| Solution architect | scope and seniority |
| Career transition | transferable skills without invention |
| Sparse CV | missing-evidence behaviour |
| Detailed multi-page CV | evidence selection/context pressure |
| UK public-sector role | essential/desirable criteria |
| Sponsorship/salary wording | extraction and eligibility fidelity |

Fixtures must be synthetic or explicitly safe, deterministic, and checked for accidental personal data.

### Repetitions

- Minimum five seeds per model per case.
- Use the same seeds for every model.
- Preserve generation settings in the report.
- Record model file/hash, quantisation, context size, and runtime configuration where available.

### Metrics

Report separately:

#### Reliability

- successful response rate;
- first-pass hard-gate rate;
- post-repair hard-gate rate;
- mean/median repair count;
- schema failure rate;
- timeout/failure rate.

#### Safety and fidelity

- unsupported candidate-claim rate;
- unsupported numeric-token rate;
- immutable-token mutation rate;
- missing-evidence safe-fallback rate;
- evidence coverage.

#### Quality

Only gate-passing pairs receive quality scores:

- CV score;
- cover-letter score;
- combined score;
- variance;
- role-specific rubric subscores.

#### Operations

- first-pass latency;
- repair latency;
- total pair latency;
- output tokens;
- tokens per eligible pair where available;
- peak memory if the harness already measures it safely.

### Ranking

Ranking remains lexicographic:

1. post-repair hard-gate pass rate;
2. first-pass hard-gate pass rate;
3. median eligible writing-quality score;
4. lower variance;
5. lower eligible-pair latency.

Do not rank a model with zero eligible outputs above a model with eligible outputs solely because it is faster.

### Model-change decision rule

A default-model change is allowed only when:

1. candidate model has at least 95% post-repair hard-gate pass rate across the full corpus;
2. candidate model does not regress numeric fidelity against the baseline;
3. median combined eligible quality is not materially worse than the baseline;
4. operational improvement is meaningful on the benchmark machine;
5. results are reproducible in a second official run;
6. README/model catalogue/runtime configuration are updated together;
7. upgrade and rollback implications are documented.

Gemma4 e2b is a speed candidate, not the preselected winner. Qwen3.5 9B is also a candidate. The benchmark must decide.

### Acceptance criteria

- at least eight fixture cases;
- five seeds per model per case;
- all required metrics reported;
- two reproducible official runs;
- no database/profile mutations;
- all test, documentation, and health checks pass;
- model decision documented as `retain` or `change` with evidence;
- if evidence is inconclusive, retain the current default.

---

## 12. Cross-PR testing strategy

## 12.1 Unit tests

Prefer pure deterministic tests for:

- body extraction;
- word counting;
- numeric token extraction;
- immutable-token comparison;
- evidence-ledger construction;
- repair selection;
- retry limits;
- prompt assembly;
- prompt metadata;
- validator serialization.

## 12.2 Contract tests

Use fake model responses to cover:

- valid first-pass draft;
- under-length draft then valid repair;
- over-length draft then valid repair;
- numeric mutation then exact repair;
- unsupported number then removal;
- malformed JSON then schema repair;
- repeated failure and safe stop;
- model-supplied false word count.

## 12.3 Integration tests

Cover:

- CV-pack generation through the existing service/API boundary;
- document rendering compatibility;
- generation history/provenance;
- benchmark runner integration;
- unchanged app-lock/auth behaviour;
- no persistent profile/database mutation.

## 12.4 Golden fixtures

Golden fixtures may validate structure and immutable evidence, but avoid brittle full-prose equality.

Assert:

- required sections;
- exact numeric tokens;
- evidence IDs;
- body count;
- absence of unsupported claims;
- output schema.

## 12.5 Test commands

Codex must discover and use the repository's current canonical commands. At minimum, run the relevant equivalents of:

```bash
cd backend
python -m pytest

cd ../frontend
npm run type-check
npm test

cd ..
docker compose config --quiet
```

Also run current documentation/README contract checks and the targeted benchmark command introduced by the local benchmark commits.

At each PR boundary, record exact commands and results.

---

## 13. Benchmark immutability and safety

Every official benchmark must:

1. record pre-run profile/database hashes;
2. use benchmark fixtures, not the user's active profile, unless an explicit isolated copy is used;
3. record post-run hashes;
4. fail the official run if protected hashes change;
5. avoid changing selected AI provider/model configuration permanently;
6. restore temporary runtime configuration in `finally`/equivalent cleanup;
7. keep generated benchmark documents under ignored benchmark paths;
8. never stage benchmark outputs automatically;
9. report backend and frontend health after completion.

---

## 14. Backward compatibility

1. Existing saved CVs and cover letters remain readable.
2. Existing API response fields remain available.
3. New provenance fields must be optional for old records.
4. No destructive database migration.
5. If `word_count` is already public:
   - retain it for compatibility;
   - populate it from the computed body count going forward;
   - document its changed source of truth;
   - never accept the model's value.
6. Existing cloud and local provider paths must use the same validators.
7. Existing no-AI/deferred-AI functionality must remain unaffected.
8. DOCX remains the source of truth.

---

## 15. Error and status contract

Use existing status conventions where possible. The workflow must distinguish:

- `generated`: model returned parseable output;
- `valid`: all blocking gates passed;
- `repaired`: final valid output required one or more repairs;
- `review_required`: output exists but blocking gates remain;
- `failed`: no usable draft was produced;
- `unavailable`: model/provider could not run.

Do not report `generated` as equivalent to `valid`.

The UI/API must not imply that a hard-gate-failing document is ready without human review.

---

## 16. Documentation requirements

Update current, canonical documentation only.

Required documentation:

1. cover-letter generation contract;
2. word-count definition;
3. evidence and numeric-fidelity rules;
4. repair limit and safe failure;
5. prompt/skill versioning;
6. benchmark methodology;
7. model-selection decision policy;
8. privacy/logging rules;
9. developer instructions for adding a new prompt or skill.

README changes are required only when user-facing behaviour or the default model changes.

Do not expose private benchmark content or local absolute paths in public documentation.

---

## 17. Definition of done per PR

A PR is complete only when:

- scoped code is implemented;
- focused tests were written first or alongside the contract;
- all relevant existing tests pass;
- lint/type checks pass;
- documentation checks pass;
- compose/config checks pass;
- protected hashes remain unchanged for benchmark PRs;
- no secret or personal fixture is committed;
- working tree is clean;
- implementation summary includes exact evidence;
- no out-of-scope model switch occurred;
- limitations are documented honestly.

---

## 18. Codex implementation protocol

For each PR:

1. Inspect current implementation and tests.
2. Write a short root-cause note before editing.
3. Identify exact files and owning interfaces.
4. Add failing tests for the smallest contract slice.
5. Implement the smallest change.
6. Run focused tests.
7. Commit a coherent unit.
8. Repeat.
9. Run full relevant verification.
10. Produce a PR summary with:
    - files changed;
    - behaviour changed;
    - tests and commands;
    - benchmark evidence where applicable;
    - compatibility notes;
    - remaining limitations.
11. Stop for review before starting the next PR.

Do not combine opportunistic cleanup, installer work, UI redesign, model downloads, or unrelated refactors.

---

## 19. Questions are already resolved

Codex should not pause for these decisions:

| Question | Locked decision |
|---|---|
| Change the default model now? | No |
| Which branch is authoritative? | Clean local branch through `4726aa8` or direct descendant |
| Fix all prompts in one PR? | No, use five ordered PRs |
| Trust model `word_count`? | No |
| Body range? | 250–350 |
| Internal target? | 285–315 |
| Under-length repair? | Required |
| Over-length repair? | Required |
| Unlimited retries? | No, maximum three model calls |
| Preserve `20+`/`120+` exactly? | Yes |
| Allow inferred numeric claims? | No |
| Score hard-gate failures for writing quality? | No |
| Select Gemma4 e2b because it is fastest? | No, benchmark after repair |
| Rewrite the working CV generator broadly in PR 1? | No |
| Add external prompt SaaS? | No |
| Preserve existing API/document compatibility? | Yes |
| Persist secrets or full private prompts in logs? | No |
| Use one benchmark case for final model choice? | No |
| Require a second reproducible run before model change? | Yes |

---

## 20. Expected final outcome

After all five PRs:

- cover letters reliably satisfy the 250–350 body-word hard gate or fail safely;
- numeric evidence such as `20+` and `120+` remains exact;
- the model cannot self-certify compliance;
- every high-risk prompt and skill uses shared evidence and validation contracts;
- retries are bounded and targeted;
- prompt and skill versions make benchmarks reproducible;
- benchmark reports separate first-pass reliability, repaired reliability, safety, quality, and speed;
- Hatch can make an evidence-based local-model decision rather than choosing by latency alone.
