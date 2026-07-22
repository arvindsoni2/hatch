---
title: Hatch Prompt Skill And Local Writing Reliability Specification v4
document_type: implementation-spec
status: active
implementation_status: partial
applies_to: main
last_verified: 2026-07-16
accepted_baseline_merge_sha: a5a4d729a4dfddcabb2ec4ca54c91120f616f6de
accepted_baseline_pr: https://github.com/arvindsoni2/hatch/pull/36
accepted_baseline_date: 2026-07-16
supersedes:
  - Hatch_Prompt_Skill_Local_Writing_Reliability_Codex_Spec_v3.md
superseded_by: []
---

# Hatch Prompt, Skill, and Local Writing Reliability Implementation Specification v4

**Status:** Implementation-ready after baseline publication, decisions locked  
**Repository:** `https://github.com/arvindsoni2/hatch`  
**Historical benchmark source commit:** `4726aa8`  
**Accepted implementation baseline:** `a5a4d729a4dfddcabb2ec4ca54c91120f616f6de` (baseline PR #36, accepted 2026-07-16)
**Reviewable benchmark evidence:** `docs/benchmarks/LOCAL_WRITING_MODEL_BENCHMARK_2026-07-15.md`  
**Private raw benchmark source:** `data/benchmarks/results/20260715T183303Z-8d9f4a72/report.md` (ignored; not required in a fresh clone)  
**Prepared:** 2026-07-16  
**Supersedes:** v3  

> **For Codex:** Implement this specification as separate pull requests in the prescribed order. Do not combine the PRs. Use test-driven development, preserve existing public contracts unless this specification explicitly changes them, and stop after each PR for review and benchmark evidence.


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
- The original operator report stated that database and profile hashes remained unchanged, backend health passed, the frontend returned HTTP 200, and 847 tests passed with 2 skipped.
- Those safety and health statements were **previously reported but were not captured in the historical machine-readable benchmark report**.
- They must not be presented as independently auditable baseline evidence until a new run manifest records the exact values, commands, timestamps, and exit codes required by section 13.

### 2.3 Limitations

The existing benchmark covers one Delivery Manager case with three repetitions per model. It can identify a shared defect but cannot support a universal model ranking.


## 3. Goals

This programme must:

1. Make 250–350 body-word cover letters a deterministic product contract.
2. Repair both under-length and over-length output.
3. Count actual body words in application code.
4. Prevent unsupported or mutated numeric evidence.
5. Separate evidence selection, prose generation, deterministic validation, targeted repair, and rendering.
6. Give every production prompt and skill an identifiable version.
7. Make model benchmarking reproducible and comparable.
8. Preserve Hatch's evidence-grounded and human-review boundaries.
9. Retain the current default model until a post-repair benchmark supports a change.
10. Avoid database, profile, and generated-document mutations during benchmark-only execution.


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


## 5. Repository, baseline, and PR topology

### 5.1 Accepted baseline preparation

The benchmark implementation and this specification must become an accepted, reviewable baseline before PR 1 begins. The existing onboarding work must not be bundled into this baseline PR.

1. Start from the current remote `main` integration branch.
2. Create a purpose-named branch, for example `chore/local-writing-benchmark-baseline`.
3. Cherry-pick only the nine benchmark commits from the current local branch. Do not cherry-pick the six onboarding commits.
4. Add this v4 specification under the canonical active documentation hierarchy.
5. The baseline PR must contain only:
   - the nine benchmark commits;
   - this specification;
   - a sanitized benchmark evidence summary at `docs/benchmarks/LOCAL_WRITING_MODEL_BENCHMARK_2026-07-15.md`;
   - any minimal documentation-index update needed to expose the specification and evidence summary;
   - no raw model responses, private fixtures, generated CVs, generated cover letters, database copies, profile copies, or detailed ignored run artifacts;
   - no onboarding implementation;
   - no prompt-reliability implementation beyond the existing benchmark work.
6. Push the purpose-named branch, open the baseline PR against `main`, and merge it after existing tests and documentation checks pass.
7. PR 1 must branch from the merged baseline commit.

The existing branch `fix/first-run-onboarding-lock-routing` remains responsible for onboarding work and must be reviewed or merged independently. Its six onboarding commits must not enter this programme through the benchmark baseline PR.

### 5.1.1 Reviewable benchmark evidence publication

The baseline PR must publish a sanitized, reviewable summary at:

```text
docs/benchmarks/LOCAL_WRITING_MODEL_BENCHMARK_2026-07-15.md
```

That committed summary is the canonical evidence cited by this specification and must contain:

1. Benchmark run ID and historical source commit `4726aa8`.
2. Case name and repetition count.
3. The five-model safety/reliability table.
4. Cover-letter word counts by seed.
5. Median pair latency by model.
6. Numeric-fidelity findings.
7. The statement that no writing-quality ranking was possible because no pair passed all hard gates.
8. The limitation that the run covered one Delivery Manager case.
9. A clear provenance note that raw responses and private/detailed artifacts remain ignored.
10. A separate section labelled `Previously reported but not machine-recorded` for the historical test-count, hash, and service-health statements.

The committed summary must not contain:

- full prompts or responses;
- private CV or job-description content;
- generated documents;
- secrets;
- machine-specific absolute paths;
- database/profile contents;
- unsupported claims that are absent from the historical report or operator record.

Raw and detailed artifacts remain under ignored `data/benchmarks/` paths. A fresh clone must be able to inspect the committed sanitized summary without access to ignored files.

### 5.1.2 Baseline commit recording

The baseline PR cannot contain its own future merge SHA. Use this contract:

1. Preserve every historical benchmark manifest exactly as produced by the run.
2. Historical manifests retain the actual source commit SHA on which that run executed. They must never be rewritten to contain a later merge SHA.
3. After the baseline PR merges, record its exact merge commit SHA in PR 1's first bookkeeping commit and in every new PR 1 benchmark `run_manifest.json`.
4. Add a specification metadata field or adjacent baseline record in PR 1 containing:
   - `accepted_baseline_merge_sha`;
   - baseline PR number or URL when available;
   - date accepted.
5. A Git tag is optional. The accepted merge SHA in PR 1 provenance is mandatory.

### 5.2 PR topology

PRs 1 through 5 are **sequential**, not stacked:

```text
accepted benchmark/spec baseline
    -> PR 1 merged
    -> PR 2 branches from updated integration branch and merges
    -> PR 3 branches from updated integration branch and merges
    -> PR 4 branches from updated integration branch and merges
    -> PR 5 branches from updated integration branch and merges
```

PR 6, the optional OpenTelemetry work, is post-release and branches from the integration branch only after PR 5 or the release branch has settled.

Rules:

- Do not open PR 2 against PR 1's feature branch.
- Do not keep five long-lived stacked branches.
- Rebase or merge the current integration branch before starting each PR according to repository policy.
- Each merged PR must leave the repository deployable and independently testable.
- Stop for review after each PR.
- Emergency fixes may merge independently, but the next programme PR must incorporate them before implementation.

### 5.3 Initial repository checks

Before baseline publication and before every PR, run:

```bash
git status --short
git rev-parse --short HEAD
git branch --show-current
git log --oneline --decorate -12
```

Before PR 1, Codex must also inspect the actual owning files:

```bash
git ls-files backend | grep -Ei 'prompt|skill|cover|tailor|benchmark|quality|validator'
git grep -n "CoverLetterGenerator"
git grep -n "word_count"
git grep -n "350"
git grep -n "250"
git grep -n "unsupported_numeric_token"
```

### 5.4 Path and compatibility rules

1. This specification uses logical component names where unpushed paths could not previously be verified. Modify existing owning files instead of introducing parallel duplicate implementations.
2. Do not rename public API fields or persisted schema fields without a migration and backward-compatibility test.
3. Benchmark fixtures and reports must remain free of personal secrets and ignored generated documents.
4. The accepted baseline merge commit replaces `4726aa8` as the authoritative implementation anchor once published.

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


## 7. Locked product contracts

### 7.1 Cover-letter word-count contract

#### Accepted final range

- Minimum: **250 body words**
- Maximum: **350 body words**
- Internal generation target: **285–315 body words**

#### Counted content

Count only the substantive cover-letter body paragraphs.

#### Excluded content

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

#### Tokenisation rule

Use one canonical Unicode-aware tokenizer implemented with Python's standard `re` module. Do not add a tokenizer dependency solely for word counting.

The canonical pattern is:

```python
import re

COVER_LETTER_WORD_RE = re.compile(
    r"""
    (?:https?://|www\.)[^\s<>()]+                                      # URL
    |[\w.+-]+@[\w.-]+\.[^\W\d_]{2,}                                # email
    |(?:[^\W\d_]\.){2,}                                             # initials, e.g. U.K.
    |(?:[£$€¥])?\d+(?:[.,]\d+)*(?:[kmb])?(?:%|\+)?
       (?:[-–—]\d+(?:[.,]\d+)*(?:[kmb])?(?:%|\+)?)?
       (?:/[A-Za-z]+)?                                                  # numeric expression
    |[^\W\d_]+(?:['’][^\W\d_]+)*(?:-[^\W\d_]+)*                # words
    """,
    re.UNICODE | re.VERBOSE | re.IGNORECASE,
)


def count_words(text: str) -> int:
    normalized = " ".join(text.split())
    return len(COVER_LETTER_WORD_RE.findall(normalized))
```

Locked examples:

| Input | Tokens | Count |
|---|---|---:|
| `£2.5m budget` | `£2.5m`, `budget` | 2 |
| `£2 million budget` | `£2`, `million`, `budget` | 3 |
| `20+ years` | `20+`, `years` | 2 |
| `120+ locations` | `120+`, `locations` | 2 |
| `15% improvement` | `15%`, `improvement` | 2 |
| `U.K. delivery` | `U.K.`, `delivery` | 2 |
| `candidate@example.com` | one email token | 1 |
| `https://example.com/jobs/123` | one URL token | 1 |
| `end-to-end` | one hyphenated word token | 1 |
| `design/architecture` | `design`, `architecture` | 2 |
| `cloud—platform` | `cloud`, `platform` | 2 |

Magnitude suffix matching is case-insensitive and is limited to `k`, `m`, and `b`. The tokenizer does not determine whether a numeric claim is permitted; numeric authorization is handled by the evidence and employer-context validators.


Before matching, strip markdown fences and pass only the extracted substantive body paragraphs. The same implementation must be called by generation validation, API metadata, tests, and the benchmark harness.

Locked examples:

| Input | Count | Rule |
|---|---:|---|
| `candidate's experience` | 2 | Internal straight apostrophe stays within one word |
| `candidate’s experience` | 2 | Internal curly apostrophe stays within one word |
| `CI/CD delivery` | 3 | Slash-separated terms count separately |
| `and/or` | 2 | Slash-separated words count separately |
| `end-to-end delivery` | 2 | Hyphenated word counts as one token |
| `design—delivery` | 2 | Em/en-dash between words is a boundary |
| `U.K. programme` | 2 | Dotted initials count as one token |
| `name@example.com` | 1 | Email address counts as one token |
| `https://example.com/jobs/1` | 1 | URL counts as one token after trailing punctuation is trimmed |
| `(120+) locations` | 2 | Surrounding punctuation is ignored; `120+` stays intact |
| `£2.5m budget` | 2 | Currency-prefixed numeric expression stays intact |
| `2018–2022` | 1 | Numeric range stays intact |
| `15% improvement` | 2 | Percentage stays intact |

Additional rules:

- Trim terminal `.`, `,`, `;`, `:`, `!`, and `?` from URL matches before accepting the token.
- HTML tags, JSON keys, evidence IDs, and metadata are excluded before tokenisation.
- A tokenizer change is a product-contract change and requires updated golden tests and benchmark version metadata.

### 7.2 Paragraph-budget contract

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

### 7.3 Repair contract

Allowed automatic attempts:

1. Initial generation.
2. One targeted repair.
3. A second targeted repair only when:
   - the first repair fixed its targeted defect; and
   - a different deterministic defect remains.

Maximum model calls for one cover-letter draft: **3**.

After the allowed attempts, return a safe `review_required` or existing equivalent state with validator details. Do not loop.

#### Under-length repair

When computed body count is below 250:

- include the computed count;
- request a target of 285–315;
- identify paragraphs below guidance budget;
- provide approved unused evidence that may be added;
- require preservation of all immutable tokens and already-valid claims;
- instruct the model not to add generic filler or unsupported claims.

#### Over-length repair

When computed body count is above 350:

- include the computed count;
- request a target of 285–315;
- identify the longest paragraphs;
- require compression without deleting required evidence;
- preserve immutable tokens.

#### Numeric-fidelity repair

When an approved immutable token is mutated:

- supply expected and observed expressions;
- request exact restoration;
- forbid any other content changes where possible.

#### Unsupported-number repair

When a numeric expression is not present in approved evidence or permitted job-description context:

- identify the unsupported expression;
- require removal or replacement with approved non-numeric wording;
- do not allow the model to justify or infer it.

### 7.4 Numeric-evidence and semantic-usage contract

The validator must distinguish three numeric namespaces:

1. **Candidate evidence numbers:** numeric expressions originating in the approved candidate evidence ledger.
2. **Employer-context numbers:** numeric expressions explicitly present in the supplied job description or verified employer context.
3. **Unsupported numbers:** expressions present in generated prose but absent from the permitted namespace for that claim.

#### Candidate token usage

An immutable candidate token is required only when the generated draft uses the associated candidate claim. Unused evidence does not force every number from the CV into the cover letter.

PR 1 uses only deterministic activation based on explicit selection, explicit reporting, or exact configured anchor matching. Fuzzy similarity is advisory only in PR 1.

A candidate token is considered **missing or mutated** only when one of these conditions is met:

1. The content plan explicitly selected the evidence item, but the generated paragraph omits or changes its immutable token.
2. The output reports the evidence ID in `evidence_ids_used`, but omits or changes its immutable token.
3. The generated prose contains an exact configured semantic anchor for that evidence item within the same paragraph or sentence as the associated claim, and omits or changes the immutable token.

PR 1 exact-anchor rules:

- anchors are checked case-insensitively after Unicode normalization and whitespace collapse;
- anchors are whole words or exact normalized phrases, not substrings;
- every blocking anchor set is explicitly stored with the evidence item or cover-letter-scoped evidence mapping;
- at least one configured anchor must match exactly;
- fuzzy similarity, embeddings, edit distance, stemming, and LLM classification cannot create a blocking failure in PR 1;
- fuzzy similarity findings may be recorded as advisory diagnostics only.

PR 2 may introduce a versioned deterministic similarity rule only after calibration against checked-in fixtures. The version, algorithm, threshold, normalization, and fixture evidence must be recorded. Until then, exact matching remains the only semantic activation capable of blocking output.

Stable evidence IDs must use this algorithm:

```text
sha256(
  evidence_schema_version + "\n" +
  canonical_source_path + "\n" +
  normalized_exact_evidence_text
).hexdigest()[:24]
```

Normalization for evidence IDs:

- Unicode NFC normalization;
- normalize line endings to `\n`;
- trim leading and trailing whitespace;
- collapse internal runs of whitespace to one ASCII space;
- preserve case, punctuation, symbols, and numeric formatting;
- use the canonical source path used by the evidence ledger, not an absolute filesystem path.

Changing the evidence schema version intentionally changes derived IDs and therefore requires a migration or compatibility mapping.

Examples:

- Evidence `managed delivery across 120+ locations` is not required when the letter does not discuss that achievement.
- If the plan selects that evidence and the draft says `managed delivery across 120 locations`, `120+` is a blocking mutation.
- If the draft discusses an unrelated `multi-site environment` without selecting or citing that evidence, the validator must not automatically require `120+` unless deterministic anchor rules identify the same claim.

#### Employer-context numbers

Employer-context numbers may appear only in employer-facing or role-alignment statements and only when they occur verbatim in the normalized raw job description supplied to the task.

PR 1 must extend the internal `CoverLetterGenerator.generate(...)` boundary to receive both:

- normalized raw `jd_text`, which is the authoritative source for employer-context numeric validation;
- the existing `JDAnalysisResult`, which remains structured contextual guidance but is not authoritative evidence for numeric claims unless a field also maps to an exact span in normalized raw `jd_text`.

The calling service already possesses `jd_text`; pass it internally without changing the public API unless the current public boundary directly exposes the generator. Normalize `jd_text` once using the shared Unicode and whitespace normalization helper.

Required provenance:

```python
class PermittedNumericClaim:
    raw: str
    normalized: str
    namespace: Literal["candidate", "job_description", "verified_employer_context"]
    source_id: str
```

Rules:

- Candidate-achievement paragraphs may use only candidate evidence numbers.
- `role_alignment` may quote employer-context numbers, but must not grammatically attribute them to the candidate.
- A job-description number cannot satisfy a missing candidate number.
- A candidate number cannot be presented as an employer fact.
- If the same expression exists in both namespaces, claim position, selected evidence IDs, and source attribution determine its namespace.
- Generic calendar dates in headers or metadata are removed before claim validation.

Examples:

- Allowed: `I am drawn to your stated goal of supporting 50 sites.` when `50 sites` appears in the job description.
- Not allowed: `I supported 50 sites.` unless `50 sites` exists in approved candidate evidence.
- Not allowed: deriving `five years` from job dates or candidate dates when that exact duration is absent.

#### Exact preservation

The following must be preserved exactly when the associated claim is used:

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
- `2018–2022` must not become an inferred duration unless that duration also exists in permitted evidence.

The model must not calculate, combine, estimate, extrapolate, round, or infer numeric claims.

### 7.5 Evidence contract

Every candidate claim used by a writing task must derive from an approved evidence entry.

Minimum evidence representation:

```python
class EvidenceItem:
    id: str
    text: str
    source_path: str
    immutable_tokens: list[str]
    semantic_anchors: list[str]
    evidence_type: str
```

Equivalent existing domain types may be extended instead of creating this exact class.

`semantic_anchors` contains the versioned, explicitly configured exact phrases that activate the associated evidence for PR 1 blocking validation. It must be deterministic, normalized, fixture-tested, and may be empty. Fuzzy similarity scores must not populate or mutate this field at runtime.

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

### 7.6 Safe missing-evidence behaviour

When the requested content cannot be grounded:

- omit the claim;
- use neutral wording;
- or return a structured missing-evidence/review-required result.

Do not invent a STAR example, employer fact, technical skill, outcome, team size, budget, duration, or metric.

### 7.7 Prompt-version contract

Every production prompt invocation must expose:

- `prompt_id`;
- `prompt_version`;
- `schema_version`;
- `task_name`.

Prompt version must be persisted in benchmark results and, where the existing document-generation record supports metadata safely, generation provenance.

Use semantic versions for externally meaningful prompt behaviour. A change to hard constraints, schema, evidence rules, or repair logic requires a version increment.

### 7.8 Model-neutral quality contract

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


## 11. Pull-request plan

### PR 1: Cover-letter generation contract repair

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Purpose:** Fix the benchmark-blocking shared defect without broad prompt refactoring.

#### Scope

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

##### Minimum shared primitives permitted in PR 1

PR 1 may and must introduce the smallest cover-letter-scoped forms of the following primitives because the current generator receives only the tailored CV and personal details:

- cover-letter evidence extraction from the actual generator inputs;
- candidate and employer-context numeric namespaces;
- immutable-token and semantic-anchor records;
- prompt ID, prompt version, schema version, and task name;
- common validation issue/result shapes needed by the repair loop;
- unused approved evidence selection for under-length repair.

Locked boundary:

- These PR 1 contracts are production contracts, not throwaway prototypes.
- PR 2 generalizes and reuses them across CV tailoring and other tasks.
- PR 2 must not replace them with incompatible names or semantics.
- PR 1 must not build the full repository-wide evidence-ledger migration.
- Where the complete master-CV ledger is unavailable, PR 1 extracts approved evidence only from the tailored CV and personal details already accepted by the current flow, while retaining source paths back to those inputs.

#### Required implementation behaviour

##### Initial generation

- Build the prompt from current evidence.
- Request five structured paragraphs.
- Target 285–315 body words.
- Request exact preservation of immutable numeric tokens.
- Parse response through the existing safe structured-output path.

##### Validation

After every attempt, calculate:

- body word count;
- paragraph word counts;
- unsupported numeric tokens;
- missing/mutated immutable numeric tokens;
- required fields/schema;
- existing hard gates.

##### Repair selection order

Use deterministic priority:

1. malformed/unparseable schema;
2. unsupported numeric token;
3. mutated/missing immutable numeric token;
4. under-length;
5. over-length.

Only one repair type is targeted per call.

##### Final state

- Pass only if every blocking gate passes.
- Do not assign writing-quality eligibility otherwise.
- Return validator details when review is required.

#### Tests

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

#### Acceptance criteria

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

#### Commit guidance

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


### PR 2: Shared evidence and prompt contracts

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** High  
**Purpose:** Replace prompt-by-prompt factuality drift with shared typed contracts.

#### Scope

1. Introduce or consolidate the approved evidence ledger.
2. Introduce shared factuality and numeric-fidelity prompt fragments.
3. Add prompt metadata/versioning.
4. Add common validation result types.
5. Migrate cover-letter and CV-tailoring flows first.
6. Preserve public API and persisted-document compatibility.
7. Record prompt and schema versions in benchmark results.
8. Record generation provenance where an existing safe metadata field or extensible JSON structure exists.

#### Evidence ledger requirements

- stable evidence ID;
- exact source text;
- source path;
- immutable numeric tokens;
- evidence type;
- deterministic ordering;
- no hidden model inference.

#### CV-tailoring migration

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

#### Prompt versioning requirements

At minimum:

| Prompt | Initial new version |
|---|---|
| Cover-letter generation | `2.0.0` |
| Cover-letter repair | `1.0.0` |
| CV tailoring | next semantically valid version |
| Shared factuality contract | `1.0.0` |
| Shared numeric-fidelity contract | `1.0.0` |

#### Tests

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

#### Acceptance criteria

- Cover-letter and CV prompts use the same factuality and numeric contracts.
- No production path can bypass immutable-token validation.
- Existing tests pass.
- No destructive migration.
- Benchmark reports identify prompt versions.
- Default model remains unchanged.


### PR 3: Skill orchestration, targeted repair, and workflow diagnostics

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium–High  
**Purpose:** Turn skills into bounded workflows rather than opaque prompt wrappers.

#### Scope

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

#### Skill contract

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

#### Content planning

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

#### Observability

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

#### Tests

- each stage receives only declared inputs;
- unknown evidence IDs fail validation;
- repair selection is deterministic;
- attempt limits work across the skill boundary;
- telemetry excludes secrets and full private document content;
- rendering occurs only after every blocking gate passes;
- failure state returns structured validation issues and attempt metadata without rendering or persisting the failed draft in the production document workflow.

#### Acceptance criteria

- document-writing skill flow is stage-based and testable;
- targeted repair uses structured validator output;
- no unlimited retry path;
- no logging/privacy regression;
- existing API behaviour remains compatible;
- default model remains unchanged.


### PR 4: Remaining prompt and skill audit

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium  
**Purpose:** Apply the shared contracts to every production AI task according to its risk.

#### Mandatory discovery

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

#### Prompt families

##### A. Job extraction

Required behaviour:

- schema-constrained output;
- use `null` for absent values;
- retain evidence spans where the existing model permits;
- distinguish explicit, inferred, and absent;
- never infer salary, sponsorship, location eligibility, or clearance from generic wording;
- numeric tokens come from the job description, not candidate evidence.

##### B. Job scoring

Required behaviour:

- deterministic calculation where possible;
- separate score components from prose rationale;
- every rationale claim must map to profile/job evidence;
- no fabricated justification after choosing a score;
- no candidate metrics added by the model.

##### C. Company research

Required behaviour:

- source/provenance field;
- retrieval timestamp;
- fact date when known;
- confidence or verification state;
- “not verified” rather than invention;
- research facts must never be blended into candidate history.

##### D. Interview questions

Required behaviour:

- classify competency/category;
- map each question to a job requirement;
- deduplicate semantically similar questions;
- do not imply the candidate has experience not present in evidence.

##### E. Interview model answers and Question Bank

Required behaviour:

- use only approved candidate evidence;
- preserve metrics exactly;
- return missing-evidence/review-required when no grounded STAR example exists;
- distinguish an answer template from a claim that the candidate performed an action;
- do not invent dates, team sizes, budgets, tools, outcomes, or stakeholders.

##### F. Coach and recommendations

Required behaviour:

- clearly separate observation, interpretation, and recommendation;
- do not state inference as confirmed candidate or employer fact;
- evidence IDs for candidate-specific observations;
- recommendations may be general but must be labelled as recommendations.

##### G. CV import/normalisation

Required behaviour:

- distinguish extracted source text from normalized interpretation;
- preserve raw source evidence;
- no inferred credentials, dates, seniority, employers, or metrics;
- surface ambiguous fields for user review.

##### H. Job-search and ranking prompts

Required behaviour:

- prevent candidate evidence from leaking into external search queries unless current privacy rules allow it;
- no unsupported eligibility assumptions;
- distinguish discovery relevance from application suitability.

#### Migration priority

Use this order:

1. candidate-facing generated documents;
2. interview answers;
3. CV import/normalisation;
4. scoring/rationale;
5. company research;
6. question generation;
7. Coach recommendations;
8. low-risk summarisation/classification.

#### Acceptance criteria

- every production prompt/skill appears in the audit;
- every high-risk task uses shared factuality and numeric contracts;
- every structured task validates its schema;
- every candidate-specific claim has evidence or safe fallback;
- prompt versions are present;
- focused regression tests exist for each high-risk family;
- no model-default change.


### PR 5: Representative local-model benchmark and selection decision

**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium  
**Purpose:** Produce eligible evidence with staged elimination rather than running the full corpus against every model twice.

#### Benchmark corpus

Prepare at least these controlled fixture cases:

| Case | Main risk |
|---|---|
| Delivery/project manager | Leadership and metrics |
| AI/software engineer | Technical stack fidelity |
| Solution architect | Scope and seniority |
| Career transition | Transferable skills without invention |
| Sparse CV | Missing-evidence behaviour |
| Detailed multi-page CV | Evidence selection/context pressure |
| UK public-sector role | Essential/desirable criteria |
| Sponsorship/salary wording | Extraction and eligibility fidelity |

Fixtures must be synthetic or explicitly safe, deterministic, and checked for accidental personal data.

#### Staged execution

##### Stage A: Repair smoke test

- Models: all five existing models.
- Cases: the existing Delivery Manager case.
- Seeds: three shared seeds per model.
- Total: 15 pairs.

A model advances when:

- at least 2 of 3 pairs pass all post-repair hard gates;
- no final eligible pair contains an unsupported candidate numeric token;
- no infrastructure failure makes the result uninterpretable.

The current baseline model advances automatically as a comparator even if it misses this threshold, but the failure remains visible.

##### Stage B: Reduced-corpus qualification

- Models: up to the three best Stage A candidates, including the baseline comparator.
- Cases: four cases selected to cover management, technical, sparse-evidence, and eligibility risks.
- Seeds: three shared seeds per case.
- Maximum: 36 pairs.

A non-baseline candidate advances when, across its 12 pairs:

- at least 11 of 12 pass post-repair hard gates;
- at least 9 of 12 pass first-pass hard gates;
- zero eligible outputs contain unsupported candidate claims;
- immutable-token mutation rate after repair is 0%;
- schema success rate is at least 11 of 12.

Advance the strongest qualifying challenger plus the baseline. When no challenger qualifies, stop and retain the baseline without Stage C.

##### Stage C: Official full-corpus comparison

- Models: exactly the strongest qualifying challenger and the baseline.
- Cases: all eight cases.
- Seeds: five shared seeds per case.
- Total per official run: 80 pairs.
- Official runs: two independent runs using the same cases and seed set, executed only after a clean service restart.

This reduces the planned official workload from 200 pairs per run across five models to 80 pairs per run. Two official runs therefore contain 160 pairs, plus at most 51 qualification pairs.

The harness must print projected pair count and projected duration before each stage using observed median latency. The operator may stop before Stage C and record `benchmark_deferred`; such a run cannot authorize a model change.

#### Metrics

Report separately:

##### Reliability

- successful response rate;
- first-pass hard-gate rate;
- post-repair hard-gate rate;
- mean and median repair count;
- schema failure rate;
- timeout/failure rate.

##### Safety and fidelity

- unsupported candidate-claim rate;
- unsupported numeric-token rate;
- immutable-token mutation rate;
- missing-evidence safe-fallback rate;
- evidence coverage.

##### Quality

Only gate-passing pairs receive quality scores:

- CV score;
- cover-letter score;
- combined score;
- variance;
- role-specific rubric subscores.

Normalize the combined rubric to a 0–100 scale in the report while preserving raw component scores.

##### Operations

- first-pass latency;
- repair latency;
- total eligible-pair latency;
- output tokens;
- tokens per eligible pair where available;
- peak memory when already measurable safely.

#### Ranking

Ranking is lexicographic:

1. post-repair hard-gate pass rate;
2. first-pass hard-gate pass rate;
3. median eligible combined quality;
4. lower quality variance;
5. lower median eligible-pair latency.

A model with zero eligible outputs cannot outrank a model with eligible outputs solely because it is faster.

#### Locked model-change thresholds

A challenger may replace the baseline only when **each Stage C official run independently** satisfies all of these conditions:

1. At least 38 of 40 pairs pass all post-repair hard gates, equivalent to at least 95%.
2. Unsupported candidate-claim rate among eligible outputs is 0%.
3. Post-repair immutable-token mutation rate is 0%.
4. Median normalized combined quality is no more than 3.0 points below the baseline's median in the same run.
5. No role-specific median quality subscore is more than 5.0 normalized points below the baseline.
6. The challenger provides at least one meaningful operational improvement:
   - median total eligible-pair latency is at least 25% lower than the baseline; or
   - peak memory is at least 20% lower while median total eligible-pair latency is no more than 10% slower.
7. Successful response rate is at least 97.5%, meaning at least 39 of 40 pairs complete.
8. The decision is the same in both official runs.

When the baseline itself fails the 95% threshold, a challenger may still replace it only if the challenger meets all thresholds above. When neither model qualifies, retain the baseline and open a follow-up reliability issue rather than selecting the faster model.

#### Acceptance criteria

- Eight controlled fixture cases exist.
- Stages A and B complete and are reported.
- Stage C runs only when a challenger qualifies.
- Two Stage C runs independently satisfy the reporting contract before any model switch.
- Exact thresholds are evaluated automatically by the harness.
- Protected database/profile hashes remain unchanged.
- Test, documentation, and service-health checks pass.
- The final decision is recorded as `retain_baseline`, `change_default`, or `benchmark_deferred` with evidence.
- README, model catalogue, migration notes, and rollback instructions change only when the decision is `change_default`.

### PR 6: Optional local OpenTelemetry for AI workflow observability

**Classification:** Post-release engineering improvement; not a release blocker  
**Recommended Codex model:** GPT-5.6 Thinking  
**Reasoning level:** Medium–High  
**Dependency:** Begin only after PR 5 or after the release branch has stabilised.

#### Goal

Add narrowly scoped backend OpenTelemetry instrumentation for AI workflows so Hatch can diagnose model latency, retries, validation failures, and token usage without burdening basic users or exporting private content by default.

#### Capability boundary

Observability is an optional capability profile named `observability` or the repository's equivalent profile convention.

Default behaviour:

- disabled;
- no remote export;
- negligible instrumentation overhead when disabled;
- core installation remains unchanged;
- frontend tracing is out of scope;
- Grafana, Tempo, Loki, and a full monitoring stack are out of scope.

Optional local behaviour:

- backend OpenTelemetry SDK enabled;
- OTLP export to a locally configured OpenTelemetry Collector;
- collector disabled unless the observability profile is selected;
- console exporter permitted only in development/test mode;
- export endpoint and enablement configured through existing settings/environment conventions.

#### Initial trace scope

Create one root span for each supported workflow:

- CV tailoring;
- cover-letter generation;
- job scoring;
- job discovery/import when AI processing occurs;
- Coach generation;
- benchmark pair execution.

Create child spans for meaningful stages:

```text
prepare_input
select_evidence
assemble_prompt
generate_initial
parse_output
validate_output
repair_output
render_document
persist_document
```

Use only stages that actually exist in a workflow.

#### Required attributes

Use low-cardinality, non-secret attributes:

- workflow/task name;
- provider type;
- model ID from the configured catalogue;
- prompt ID and version;
- skill ID and version;
- attempt number;
- repair type;
- validation state;
- failed gate codes;
- input/output token counts when supplied by the provider/runtime;
- computed cover-letter body count;
- latency;
- benchmark case ID and seed for benchmark spans;
- generated document ID only after successful persistence.

Do not attach:

- prompt text;
- model response text;
- CV content;
- job-description content;
- candidate name, email, address, phone number, employer history, or other personal fields;
- API keys, tokens, cookies, or authorization headers;
- raw local filesystem paths.

#### Metrics

Provide local backend metrics derived from the same instrumentation:

- `hatch.ai.workflow.duration` histogram;
- `hatch.ai.model.call.duration` histogram;
- `hatch.ai.model.calls` counter;
- `hatch.ai.repair.calls` counter;
- `hatch.ai.validation.failures` counter by stable gate code;
- `hatch.ai.tokens.input` counter when available;
- `hatch.ai.tokens.output` counter when available;
- `hatch.ai.workflow.outcomes` counter by validation state.

Names may follow the repository's established naming convention, but they must remain stable and documented.

#### Logging correlation

- Include trace ID and span ID in structured backend logs when tracing is enabled.
- Preserve existing log redaction.
- Do not duplicate full span attributes into every log entry.
- Benchmark `run_id` must correlate logs, traces, and report artifacts.

#### Semantic conventions

Use stable OpenTelemetry HTTP/server conventions provided by official instrumentation. For AI-specific attributes, wrap names behind Hatch-owned constants so experimental upstream Generative AI semantic-convention changes do not become a database or public API contract.

Do not persist telemetry attribute names in business tables.

#### Failure behaviour

- Telemetry initialization or export failure must not fail an AI workflow.
- Export is best-effort and bounded.
- Hatch owns a strict **5-second wall-clock shutdown deadline** for telemetry flushing and shutdown.
- The 5-second deadline covers the complete application-owned flush/shutdown operation, not each exporter or processor independently.
- Invoke flushing/shutdown through an application-owned bounded execution wrapper rather than relying only on `BatchSpanProcessor` exporter timeout configuration.
- When the 5-second deadline expires, abandon pending telemetry, emit at most one redacted warning, and continue Hatch shutdown successfully.
- A timeout must not change an AI workflow result, process exit result, document state, or benchmark result.
- Do not block process termination waiting for exporter worker threads after the Hatch deadline.
- Use batch exporting during normal operation.
- Do not retry export indefinitely.
- Health reporting must show `disabled`, `active`, or `degraded` without exposing secrets.

#### Testing

Add tests proving:

1. No spans are exported when observability is disabled.
2. AI workflow spans contain required low-cardinality attributes.
3. Prompts, responses, CV content, and secrets are absent from span attributes and events.
4. Trace IDs correlate with structured logs.
5. Model failure and validation failure set appropriate span status/events without raising telemetry exceptions.
6. Exporter failure does not change workflow result.
7. Benchmark spans include run ID, case ID, seed, prompt version, model ID, and repair count.
8. Optional collector/profile configuration validates successfully.
9. Core installation does not start the collector.
10. Shutdown flushing completes within the application-owned 5-second deadline when a fake exporter blocks indefinitely.
11. Deadline expiry abandons pending telemetry and does not alter Hatch's shutdown exit result.

#### Acceptance criteria

- Observability remains opt-in.
- Backend AI workflows are traceable end-to-end.
- Quality-gate and retry metrics are queryable through local OTLP collection.
- No private prompt/document content is exported.
- Telemetry cannot delay Hatch shutdown by more than 5 seconds.
- Core users install and run Hatch without the collector.
- Frontend tracing and full Grafana stack remain deferred.
- Documentation explains enablement, local data flow, privacy, disabling, and cleanup.
- The PR can be reverted without changing document or AI workflow contracts.


## 12. Cross-PR testing strategy

### 12.1 Unit tests

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

### 12.2 Contract tests

Use fake model responses to cover:

- valid first-pass draft;
- under-length draft then valid repair;
- over-length draft then valid repair;
- numeric mutation then exact repair;
- unsupported number then removal;
- malformed JSON then schema repair;
- repeated failure and safe stop;
- model-supplied false word count.

### 12.3 Integration tests

Cover:

- CV-pack generation through the existing service/API boundary;
- document rendering compatibility;
- generation history/provenance;
- benchmark runner integration;
- unchanged app-lock/auth behaviour;
- no persistent profile/database mutation.

### 12.4 Golden fixtures

Golden fixtures may validate structure and immutable evidence, but avoid brittle full-prose equality.

Assert:

- required sections;
- exact numeric tokens;
- evidence IDs;
- body count;
- absence of unsupported claims;
- output schema.

### 12.5 Test commands

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


## 13. Baseline and run evidence record

The original `report.md` is authoritative only for the model results it actually contains. It does not independently evidence the reported test count, protected hashes, or service-health checks.

Treat the earlier statements about `847 passed, 2 skipped`, unchanged hashes, backend health, and frontend HTTP 200 as implementation-status claims pending capture in a machine-readable evidence record.

PR 1 must extend the harness to write both:

1. `run_manifest.json`, containing exact commands, timestamps, commit SHA, branch, model/runtime configuration, environment summary, and exit codes.
2. An expanded `report.md`, summarising the manifest and linking relative artifact paths.

Minimum manifest fields:

```json
{
  "run_id": "...",
  "repository_commit": "...",
  "working_tree_clean_before": true,
  "working_tree_clean_after": true,
  "commands": [
    {"command": "...", "exit_code": 0, "started_at": "...", "ended_at": "..."}
  ],
  "tests": {"passed": 0, "failed": 0, "skipped": 0},
  "protected_hashes": {
    "before": {"profile": "...", "database": "..."},
    "after": {"profile": "...", "database": "..."},
    "unchanged": true
  },
  "health": {
    "backend": {"url": "...", "status_code": 200},
    "frontend": {"url": "...", "status_code": 200}
  },
  "prompt_versions": {},
  "skill_versions": {},
  "models": []
}
```

Rules:

- Do not fabricate retroactive hash values for the prior run.
- Mark unavailable historical evidence as `not_recorded`.
- New official runs are valid only when their manifest contains the required fields.
- Public documentation must not expose absolute local paths, secrets, or private fixture content.

## 14. Benchmark immutability and safety

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


## 15. Backward compatibility

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


## 16. Document lifecycle and generation-validation state

The existing persisted document workflow statuses remain unchanged:

```text
generated | reviewed | approved | sent
```

Do not redefine `generated`, add `valid` or `repaired` to the existing document status column, or migrate historical documents for this programme.

Introduce a separate, non-conflicting generation-validation state in service results, benchmark records, and optional generation-attempt provenance:

```text
valid_first_pass | valid_after_repair | review_required | failed | unavailable
```

Operational behaviour:

1. A parseable draft that still fails a blocking gate is **not** persisted as a normal `Document` and is **not** rendered to DOCX/PDF.
2. Preserve the current safety behaviour that withholds a document on grounding or hard-gate failure.
3. The application returns structured validation issues, computed metrics, attempt metadata, and a safe status message. It must not return a full failed-draft preview and PR 1 must not add a persisted review queue.
4. Standard logs must not contain the full failed draft.
5. The benchmark harness may retain failed drafts under its existing ignored private result directory for diagnosis.
6. A valid first-pass or repaired draft enters the existing document workflow with persisted status `generated`.
7. Store `generation_validation_state=valid_first_pass` or `valid_after_repair` in generation provenance when an existing extensible metadata field is available. Otherwise return it in the service result and defer persistence to a backward-compatible migration.
8. `review_required` means the generation attempt needs engineering or user intervention; it does not mean a persisted document is ready for the normal review workflow.
9. There is no production rendering fallback for a blocking failure in PR 1 through PR 6.
10. “Reviewable” means the caller receives structured validation issues, computed metrics, attempt count, repair history, and a safe error/status message. It does not mean a DOCX/PDF, persisted `Document`, full failed-draft preview, or review-queue item is created.
11. A future persisted failed-draft review feature requires a separate product specification, privacy review, lifecycle design, and migration. It is not implicitly authorised by this specification.

## 17. Documentation requirements

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


## 18. Definition of done per PR

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


## 19. Codex implementation protocol

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


## 20. Questions are already resolved

Codex should not pause for these decisions:

| Question | Locked decision |
|---|---|
| Change the default model now? | No |
| PR topology? | Sequential merged PRs; no stacked five-branch chain |
| May PR 1 add shared primitives? | Yes, the minimum cover-letter-scoped evidence, numeric namespace, validation, and prompt-version contracts; PR 2 generalizes them compatibly |
| Does unused evidence force its number into a letter? | No; a token is required only when its evidence item is selected, cited, or deterministically activated by the associated claim |
| May job-description numbers appear? | Yes, only as employer context with provenance and never as candidate achievement |
| Exact word tokenizer? | Locked standard-library Unicode regex and examples in section 7.1 |
| Persist `review_required` drafts? | No normal document persistence or rendering; use separate generation-validation state and benchmark-only ignored artifacts |
| How are baseline safety claims evidenced? | New `run_manifest.json` plus expanded report; do not fabricate historical values |
| Is 95% combined across two runs? | No, at least 38/40 in each official Stage C run independently |
| Full five-model, two-run benchmark? | No; use staged elimination, then challenger versus baseline only |
| OpenTelemetry release blocker? | No; optional post-release PR 6 and disabled by default |
| Which branch is authoritative? | Publish and merge the benchmark/spec baseline first; thereafter use its integration-branch merge SHA |
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
| Include onboarding commits in the benchmark baseline PR? | No; cherry-pick only the nine benchmark commits onto current `main` |
| Rewrite historical benchmark manifests with the baseline merge SHA? | No; preserve historical source SHAs and record the accepted merge SHA in PR 1 provenance |
| Authoritative employer-number source in PR 1? | Normalized raw `jd_text`; `JDAnalysisResult` is contextual only unless mapped to an exact raw span |
| Can fuzzy semantic similarity block PR 1 output? | No; selected IDs, reported IDs, and exact configured anchors only |
| Stable evidence-ID algorithm? | First 24 hex characters of SHA-256 over schema version, canonical source path, and normalized exact evidence text |
| Render or persist blocking-failure drafts? | No; return structured validation issues only |


## 21. OpenTelemetry release classification

PR 6 is optional and post-release. PRs 1 through 5 define writing reliability and model-selection readiness. A release may proceed without PR 6 when existing release criteria pass. OpenTelemetry becomes recommended before wider multi-user or remotely supported deployment, but it must remain disabled by default and privacy-preserving.

## 22. Expected final outcome

After all five PRs:

- cover letters reliably satisfy the 250–350 body-word hard gate or fail safely;
- numeric evidence such as `20+` and `120+` remains exact;
- the model cannot self-certify compliance;
- every high-risk prompt and skill uses shared evidence and validation contracts;
- retries are bounded and targeted;
- prompt and skill versions make benchmarks reproducible;
- benchmark reports separate first-pass reliability, repaired reliability, safety, quality, and speed;
- Hatch can make an evidence-based local-model decision rather than choosing by latency alone.
- Optional local OpenTelemetry can trace AI workflows and quality gates without exporting private content or burdening the core profile.
