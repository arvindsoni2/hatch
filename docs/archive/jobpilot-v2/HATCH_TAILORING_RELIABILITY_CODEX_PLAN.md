---
title: Hatch Tailoring Reliability Fix
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# Hatch Tailoring Reliability Fix
## Codex Implementation Plan with Local OpenCode Workers

**Repository:** `https://github.com/arvindsoni2/hatch`  
**Feature area:** CV tailoring module  
**Problem:** Tailored CV output is sometimes truncated to a one-page CV and misses critical master-CV sections such as experience, education, certifications, and other evidence.  
**Primary orchestrator:** Codex  
**Local implementation workers:** OpenCode using local coding models  
**Execution model:** Sequential, bounded tasks on one feature branch  
**Status:** Ready for implementation  

---

## 1. Codex Directive

You are the lead engineer and integration owner for this change.

Read this document completely before changing code. Inspect the current repository at `HEAD` and reconcile any differences between this plan and the current implementation.

Your job is to fix the CV tailoring system so that Hatch never emits a tailored CV that loses mandatory master-CV content.

This is a correctness and reliability fix, not a fine-tuning project.

Codex owns:

1. repository reconnaissance;
2. design validation;
3. task breakdown;
4. local OpenCode delegation;
5. code review;
6. integration;
7. tests;
8. migration, if required;
9. final implementation summary.

Local OpenCode workers may implement bounded code changes, but Codex must review every diff before accepting it.

OpenCode workers must not:

- rewrite the whole tailoring module in one pass;
- change unrelated product behaviour;
- add cloud dependencies;
- add model fine-tuning;
- increase automation to submit applications;
- weaken fabrication safeguards;
- remove existing ATS or tailoring tests;
- change master CV semantics;
- commit or push code.

---

## 2. Executive Summary

The tailoring system currently asks a local LLM to produce a full structured CV. This is fragile.

Observed failure:

```text
Tailored CV is shortened to roughly one page.
Key experience roles are missing.
Education is missing.
Other master-CV evidence may be dropped.
```

This should be treated as a pipeline correctness bug.

Fine-tuning is not the first fix because a fine-tuned model cannot reliably solve missing sections if the code schema, parser, validator, or DOCX builder does not preserve and render those sections.

The correct architectural principle is:

> The master CV is the source of truth.  
> The LLM may suggest wording.  
> Hatch must own the final structure and guarantee that mandatory sections survive.

Implement a **Tailoring Reliability Fix**:

1. make the master CV and tailored CV section contract explicit;
2. add education and any other missing mandatory sections to schemas and rendering;
3. change tailoring from full-CV generation to bounded edit generation;
4. assemble the final CV deterministically from the master CV;
5. validate structural completeness before saving or rendering;
6. fail closed or repair from master data when the LLM omits sections;
7. add golden tests that catch missing roles, missing education, missing certifications, and truncated DOCX output.

---

## 3. Current Diagnosis to Verify

Codex must verify these observations against the current branch before implementation.

Likely relevant files:

```text
backend/app/agents/tailor_agent.py
backend/app/services/tailor_service.py
backend/app/services/cv_tailor.py
backend/app/services/docx_cv_builder.py
backend/app/services/llm_client.py
backend/app/prompts/cv_tailoring.j2
backend/app/schemas/tailor.py
backend/app/schemas/profile.py
backend/app/agents/tools/context_budgets.py
backend/tests/
frontend/src/
```

Expected current behaviour:

- `TailorService.generate_all()` orchestrates CV tailoring, cover-letter generation and ATS scoring.
- `CVTailor` or equivalent service sends a large prompt to the LLM and expects a full structured tailored CV.
- The prompt asks the LLM to preserve structure and avoid fabrication.
- The code includes some preservation logic, likely in a method similar to `_preserve_master_structure`.
- The tailored CV result schema contains fields such as summary, skills, experience, certifications, ATS keywords and notes.
- Education is missing from the tailored CV schema and/or parser and/or DOCX builder.
- The DOCX builder renders only fields present in the tailored result contract.
- Output token budget may be too small for reliable full-CV JSON generation.
- JSON parsing may accept structurally incomplete but syntactically valid model output.
- There may be no hard validation that compares final tailored output with the master CV before saving.

Codex must confirm or correct this list in:

```text
.codex/tailoring-reliability/00-reconnaissance.md
```

---

## 4. Primary Goal

Guarantee that the tailored CV preserves mandatory master-CV structure and evidence.

A generated CV must never silently lose:

- personal details;
- summary section, unless intentionally blank in the master;
- skills section;
- any experience role;
- role titles;
- company names;
- role dates or periods;
- mandatory bullets per role;
- education;
- certifications;
- other configured mandatory sections.

The system may rewrite wording, reorder skills, and highlight relevant evidence, but it must not drop source-of-truth sections.

---

## 5. Non-Goals

Do not implement these in this change:

- model fine-tuning;
- LoRA training;
- RAG redesign for job search;
- cover-letter architecture rewrite unless necessary to keep tests passing;
- automatic job application submission;
- email integration;
- new cloud LLM dependency;
- multi-user analytics;
- design overhaul of the frontend;
- ATS scoring algorithm rewrite;
- import/export of CVs;
- PDF rendering overhaul unless current DOCX tests require small fixes.

---

## 6. Design Principle

Current fragile pattern:

```text
Master CV + JD -> LLM -> Full tailored CV JSON -> DOCX
```

Replace with safer pattern:

```text
Master CV + JD -> deterministic evidence map
Master CV + JD + evidence IDs -> LLM -> bounded edit plan
Master CV + bounded edit plan -> deterministic assembled CV
assembled CV -> structural validation
validated CV -> DOCX / preview / storage
```

The final document is not whatever the LLM returned.

The final document is the master CV skeleton plus safe edits.

---

## 7. Definitions

### Master CV

The source-of-truth CV profile stored in Hatch. It contains all user-provided experience, education, skills, certifications and other evidence.

### Tailored CV

A job-specific CV assembled from the master CV with safe edits. It must preserve mandatory structure.

### Tailoring edit plan

A bounded JSON object produced by the LLM. It contains only proposed edits, not a full replacement CV.

### Evidence ID

A deterministic stable ID assigned to master-CV sections, roles and bullets during tailoring.

Examples:

```text
summary
skills.technical
experience.exp_001
experience.exp_001.bullet_001
education.edu_001
certifications.cert_001
```

### Structural validation

A deterministic check that compares the assembled tailored CV against the master CV and rejects or repairs missing mandatory content.

---

## 8. Required Behaviour

The final tailored CV must satisfy these invariants:

```text
final experience role count >= master experience role count
final education count >= master education count
final certification count >= master certification count
every master role title appears unchanged unless explicitly configured otherwise
every master company name appears unchanged
every master role period/date appears unchanged
every master role has at least the same number of bullets as the master
no generated bullet may introduce unsupported facts
every mandatory section is rendered in DOCX
```

Recommended stricter MVP invariant:

```text
final experience role count == master experience role count
final education count == master education count
final certification count == master certification count
final bullet count per role == master bullet count per role
```

This stricter version is safer and easier to test.

---

## 9. Education Must Be First-Class

Education must be added to the tailoring contract if it is currently missing.

Update all relevant layers:

```text
master CV schema
tailored CV schema
LLM edit-plan schema
parser/validator
deterministic assembler
DOCX builder
frontend preview, if applicable
tests
documentation
```

Education should normally be copied verbatim from the master CV.

The LLM should not rewrite degree names, institution names, dates, or grades unless the master CV already contains alternative wording and the edit plan explicitly references the evidence.

Recommended education schema:

```python
class EducationEntry(BaseModel):
    institution: str
    qualification: str | None = None
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    details: list[str] = Field(default_factory=list)
```

If the existing profile schema already uses another shape, preserve it and map it through the tailoring pipeline.

---

## 10. Proposed Data Contracts

Codex must adapt names to existing repository conventions.

### 10.1 Tailored CV final result

The final assembled result should include all mandatory sections.

Suggested schema:

```python
class TailoredCVResult(BaseModel):
    personal: PersonalDetails | None = None
    summary: str
    skills: dict[str, list[str]] | list[str]
    experience: list[TailoredExperienceEntry]
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[CertificationEntry] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    tailoring_notes: list[str] = Field(default_factory=list)
    fabrication_warnings: list[str] = Field(default_factory=list)
    structural_warnings: list[str] = Field(default_factory=list)
    validation_status: Literal["passed", "repaired", "failed"] = "passed"
```

### 10.2 Tailoring edit plan

The LLM should return edits by ID.

Suggested schema:

```python
class CVTailoringEditPlan(BaseModel):
    summary_rewrite: str | None = None
    skill_order: list[str] = Field(default_factory=list)
    skill_highlights: list[str] = Field(default_factory=list)
    bullet_rewrites: dict[str, str] = Field(default_factory=dict)
    role_order: list[str] = Field(default_factory=list)
    ats_keywords: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

Important:

- `bullet_rewrites` keys must be evidence IDs only.
- Unknown evidence IDs must be ignored and logged.
- Missing bullet rewrites are not errors.
- Original bullets are used as fallback.
- `role_order` may be ignored in the MVP if preserving chronology is safer.
- The edit plan must not contain a replacement `experience` array.
- The edit plan must not contain a replacement `education` array.
- The edit plan must not contain a replacement `certifications` array.

### 10.3 Structural validation report

Suggested schema:

```python
class CVStructuralValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    section: str
    evidence_id: str | None = None

class CVStructuralValidationReport(BaseModel):
    status: Literal["passed", "repaired", "failed"]
    issues: list[CVStructuralValidationIssue] = Field(default_factory=list)
    master_counts: dict[str, int] = Field(default_factory=dict)
    tailored_counts: dict[str, int] = Field(default_factory=dict)
```

---

## 11. Evidence Map

Create a deterministic evidence-map service.

Suggested file:

```text
backend/app/services/cv_evidence_map.py
```

Responsibilities:

1. assign stable IDs to master-CV sections;
2. expose only allowed source content to the LLM;
3. provide lookup methods for assembly;
4. provide counts for validation;
5. avoid putting unnecessary personal data into prompts.

Suggested output shape:

```json
{
  "summary": {
    "id": "summary",
    "text": "..."
  },
  "skills": {
    "id": "skills",
    "groups": {
      "technical": ["Python", "AWS"],
      "delivery": ["Stakeholder management"]
    }
  },
  "experience": [
    {
      "id": "experience.exp_001",
      "role": "Senior Delivery Manager",
      "company": "Example Ltd",
      "period": "2022 - Present",
      "bullets": [
        {
          "id": "experience.exp_001.bullet_001",
          "text": "Led migration programme across..."
        }
      ]
    }
  ],
  "education": [
    {
      "id": "education.edu_001",
      "institution": "Example University",
      "qualification": "MSc ...",
      "period": "..."
    }
  ],
  "certifications": [
    {
      "id": "certifications.cert_001",
      "name": "AWS Certified Cloud Practitioner",
      "issuer": "AWS",
      "date": "..."
    }
  ]
}
```

The evidence map must preserve source order.

---

## 12. Prompt Changes

Replace or supplement the existing full-CV prompt with an edit-plan prompt.

Suggested file:

```text
backend/app/prompts/cv_tailoring_edit_plan.j2
```

The prompt should say:

```text
You are not writing a full CV.
You are creating a safe edit plan for an existing master CV.
Only rewrite bullets by evidence ID.
Do not remove roles.
Do not remove education.
Do not remove certifications.
Do not invent facts.
If no safe rewrite is possible, omit that bullet ID.
Return strict JSON matching the schema.
```

The output schema should be compact.

Example required JSON:

```json
{
  "summary_rewrite": "string or null",
  "skill_order": ["skill name"],
  "skill_highlights": ["skill name"],
  "bullet_rewrites": {
    "experience.exp_001.bullet_001": "rewritten bullet using only existing evidence"
  },
  "ats_keywords": ["keyword"],
  "notes": ["brief note"],
  "warnings": []
}
```

Hard prompt requirements:

- Do not output markdown.
- Do not output prose outside JSON.
- Do not output a full CV.
- Do not include education replacements.
- Do not include certification replacements.
- Do not include role replacements.
- Never create a new role.
- Never remove a role.
- Never alter company names, dates, job titles, institutions, or certifications.

---

## 13. Deterministic Assembler

Create:

```text
backend/app/services/cv_assembler.py
```

Responsibilities:

1. take master CV and edit plan;
2. create final tailored CV;
3. preserve mandatory sections;
4. apply safe summary rewrite;
5. reorder or highlight skills only if safe;
6. apply bullet rewrites by ID;
7. fallback to original bullets when rewrites are missing, empty, invalid or unsafe;
8. copy education verbatim;
9. copy certifications verbatim;
10. attach notes, warnings and ATS keywords.

Suggested pseudocode:

```python
def assemble_tailored_cv(master_cv, evidence_map, edit_plan) -> TailoredCVResult:
    result = copy_master_structure(master_cv)

    if safe_summary(edit_plan.summary_rewrite):
        result.summary = edit_plan.summary_rewrite

    result.skills = reorder_skills(master_cv.skills, edit_plan.skill_order)

    for role in result.experience:
        for bullet in role.bullets:
            rewrite = edit_plan.bullet_rewrites.get(bullet.evidence_id)
            if is_safe_rewrite(original=bullet.text, rewrite=rewrite):
                bullet.text = rewrite
            else:
                bullet.text = original

    result.education = copy(master_cv.education)
    result.certifications = copy(master_cv.certifications)
    result.ats_keywords = dedupe(edit_plan.ats_keywords)
    result.tailoring_notes = edit_plan.notes
    result.fabrication_warnings = edit_plan.warnings

    return result
```

MVP safety rule for bullet rewrites:

- reject empty rewrite;
- reject rewrite above configured length limit;
- reject rewrite containing obvious unsupported metrics not present in original or evidence context;
- reject rewrite that removes all key nouns from original, if a simple heuristic exists;
- otherwise accept.

Do not over-engineer semantic verification in the MVP. The structural guarantee is more important.

---

## 14. Structural Validator

Create:

```text
backend/app/services/cv_structural_validator.py
```

Responsibilities:

1. compare master CV and assembled tailored CV;
2. produce a validation report;
3. repair missing content when possible;
4. fail closed when repair is impossible;
5. expose useful diagnostics.

Validation checks:

```text
experience count
role title preservation
company preservation
period/date preservation
bullet count per role
education count
education institution preservation
education qualification preservation
certification count
certification name preservation
mandatory section presence
```

Repair behaviour:

- missing role: copy role from master;
- missing bullet: copy bullet from master;
- missing education: copy education from master;
- missing certification: copy certification from master;
- changed role/company/period: restore from master;
- empty summary: restore master summary;
- empty skills: restore master skills.

Recommended default:

```text
repair_missing_sections = true
fail_on_unrepairable = true
```

The service should return:

```python
(validated_cv, validation_report)
```

The tailored document should be saved only when status is:

```text
passed
repaired
```

If status is `failed`, raise a domain-specific error and do not save the incomplete CV.

---

## 15. Truncation Detection and LLM Response Handling

Update the LLM call path for CV tailoring.

Requirements:

1. record prompt token estimate;
2. record output token estimate;
3. record model name;
4. record max output tokens used;
5. detect JSON parsing failures;
6. detect missing required edit-plan keys;
7. detect output that looks like a full CV instead of an edit plan;
8. detect incomplete JSON;
9. fail closed when output is truncated or invalid.

If the LLM client exposes a finish reason, log it and treat these as failure or retry signals:

```text
length
max_tokens
content_filter
error
```

If the current local llama.cpp wrapper does not expose finish reason, use defensive checks:

```text
raw output does not parse as JSON
raw output ends mid-string or mid-object
required top-level type is wrong
too many unknown top-level keys
edit plan includes replacement experience/education/certification arrays
```

Do not accept a malformed full-CV response as a valid tailored CV.

---

## 16. Output Budget

The new edit-plan architecture should need less output budget than full-CV JSON.

Recommended config:

```text
CV edit-plan output budget: 1500 to 2500 tokens
CV prompt budget: keep current safe budget unless evidence map is too large
```

If the current code has a hard-coded `3000` output-token budget for full CV generation, do not merely increase it as the primary fix. Increasing the budget can be a temporary safety improvement, but the architecture must not rely on full-CV generation.

---

## 17. Integration with Existing Tailor Flow

Update the existing CV tailoring flow in place.

Expected new flow:

```text
TailorService.generate_all
  -> CVTailor.tailor
      -> analyse job requirements
      -> build evidence map from master CV
      -> call LLM for edit plan
      -> parse edit plan
      -> assemble tailored CV from master + edit plan
      -> validate and repair structure
      -> build DOCX from validated CV
      -> save document and metadata
  -> cover letter generation
  -> ATS scoring
```

The public API shape should remain compatible where possible.

If frontend currently expects `TailoredCVResult`, keep the final response type stable but add missing fields such as `education`, `structural_warnings` and `validation_status`.

---

## 18. DOCX Builder Requirements

Update the DOCX builder to render all mandatory sections.

At minimum render:

```text
personal details
summary
skills
experience
education
certifications
```

Do not rely only on the Python object being correct. Add a DOCX content test that extracts text from the generated DOCX and asserts that mandatory headings and specific source values exist.

DOCX text must include:

```text
at least one known role title
all role titles
all company names
all role periods
education institution
education qualification
certification name
```

If the builder delegates to a Node script, update both Python and Node-side contracts.

---

## 19. Frontend Requirements

If the frontend previews tailored CV content, update it to display education and structural status.

Requirements:

- show education when present;
- show certifications when present;
- show validation status if useful;
- show warnings only when non-empty;
- do not display scary technical messages to normal users;
- do not allow download of a structurally failed CV;
- preserve existing layout.

Suggested user-facing warning for repaired output:

```text
Hatch restored some master-CV sections that the model omitted.
```

Suggested user-facing error for failed output:

```text
Hatch could not safely create a complete tailored CV. Your master CV has not been modified.
```

---

## 20. Tests

Testing is the core of this fix.

### 20.1 Golden master CV fixture

Create a representative fixture with:

```text
personal details
professional summary
skills grouped into categories
at least 5 experience roles
at least 3 bullets per role
education
certifications
optional achievements or projects if supported by current schema
```

Suggested file:

```text
backend/tests/fixtures/master_cv_complete.yaml
```

The fixture should be realistic enough to catch truncation.

### 20.2 Unit tests

Add tests for:

```text
evidence-map ID stability
education mapping
certification mapping
bullet ID mapping
edit-plan parsing
unknown bullet IDs ignored
full-CV-shaped LLM output rejected
assembler preserves all roles
assembler preserves all bullets
assembler copies education
assembler copies certifications
validator detects missing role
validator repairs missing role
validator detects missing education
validator repairs missing education
validator detects changed company
validator restores changed company
validator fails when repair is impossible
```

### 20.3 Integration tests

Create an integration test that simulates a bad local-model response:

```json
{
  "summary_rewrite": "A short summary",
  "bullet_rewrites": {
    "experience.exp_001.bullet_001": "Relevant rewrite"
  },
  "ats_keywords": ["delivery", "cloud"]
}
```

Then assert:

```text
final CV still includes all roles
final CV still includes all bullets
final CV still includes education
final CV still includes certifications
validation_status is passed or repaired
DOCX contains all mandatory values
```

Create another test where the model returns a full CV with only one role. Assert this is rejected as an invalid edit plan or repaired via deterministic assembly without losing master content.

### 20.4 DOCX tests

Extract text from the generated DOCX. Use the repository's existing helper if present. Otherwise add a small test helper using the standard DOCX zip XML structure or an existing test dependency.

Assert text contains:

```text
all role titles
all company names
all role periods
education institution
education qualification
certification names
```

### 20.5 Regression tests

Add a regression test specifically named for the failure:

```text
test_tailored_cv_does_not_collapse_to_one_page_or_drop_sections
```

It should fail if any master section disappears.

### 20.6 Frontend tests

If frontend preview is affected, add tests for:

```text
education renders
certifications render
repaired warning renders
failed CV blocks download
existing preview still renders without education for old data
```

---

## 21. Logging

Add structured logs around CV tailoring.

Log:

```text
job id
application id if available
model name
prompt token estimate
output token estimate
edit-plan parse status
number of master roles
number of final roles
number of master education entries
number of final education entries
number of master certifications
number of final certifications
validation status
number of repairs
DOCX build success/failure
```

Do not log:

```text
full CV contents
full job description
personal contact details
private notes
API keys
raw generated document content
```

Include enough counters to debug truncation without exposing personal data.

---

## 22. Performance Requirements

Target local CPU-first usage.

Requirements:

- do not increase local model calls dramatically for normal use;
- no fine-tuning;
- no training step;
- no embeddings required for this fix;
- deterministic assembly and validation should be fast;
- avoid loading large files repeatedly;
- keep prompt smaller by passing evidence map rather than full unstructured CV where possible.

Acceptable MVP local-model calls:

```text
1 call for job requirement analysis, if already present
1 call for CV edit plan
1 call for cover letter, if already present
1 call for ATS scoring, if already present
```

Do not add one LLM call per bullet in the MVP. That is safer semantically but too slow for CPU-only local use.

---

## 23. Suggested Implementation Sequence

Codex must implement in this order.

### Phase 0: Reconnaissance

Deliverable:

```text
.codex/tailoring-reliability/00-reconnaissance.md
```

Include:

- current CV tailoring call graph;
- current schemas;
- whether education exists anywhere in profile schema;
- where education is lost;
- current DOCX rendering path;
- current tests;
- current LLM output budget;
- current JSON parsing behaviour;
- risks and deviations from this plan.

### Phase 1: Golden tests before code changes

Add failing or expected-failure tests that reproduce the issue.

Deliverables:

```text
backend/tests/fixtures/master_cv_complete.yaml
backend/tests/test_services/test_tailoring_reliability_regression.py
```

Gate:

```text
test fails for the current bug or is marked xfail with a precise reason
```

Codex should prefer writing a failing test first, then making it pass.

### Phase 2: Education contract

Add education to all relevant backend contracts.

Update:

```text
schemas
parser
tailored result
DOCX builder inputs
frontend API types if needed
```

Gate:

```text
education survives from master CV to final structured result
```

### Phase 3: Evidence map and edit-plan schema

Add evidence-map service and edit-plan schema.

Gate:

```text
stable evidence IDs
unknown IDs ignored
full-CV-shaped output rejected
```

### Phase 4: Deterministic assembler

Add assembler that creates final CV from master plus edit plan.

Gate:

```text
all master roles, bullets, education and certifications survive even with sparse edit plan
```

### Phase 5: Structural validator and repair

Add validator and integrate repair/fail-closed behaviour.

Gate:

```text
missing sections are repaired
unrepairable outputs are not saved
```

### Phase 6: CVTailor integration

Refactor existing CV tailoring flow to use:

```text
evidence map
edit-plan prompt
edit-plan parser
assembler
validator
DOCX builder
```

Gate:

```text
existing tailoring API still works
no incomplete CV is emitted
```

### Phase 7: DOCX rendering and extraction tests

Update DOCX builder and tests.

Gate:

```text
generated DOCX contains all mandatory source values
```

### Phase 8: Frontend preview, if applicable

Add education and structural warning display.

Gate:

```text
frontend tests pass
no failed CV can be downloaded from UI
```

### Phase 9: Documentation and final validation

Update docs and run full validation.

Gate:

```text
backend tests pass
frontend tests pass
lint/typecheck pass
Docker build or compose validation passes
```

---

## 24. Local OpenCode Worker Strategy

Run only one edit-capable OpenCode worker at a time.

Use local OpenCode workers for bounded tasks only. Codex remains the architect and reviewer.

Recommended workers:

| Worker | Scope | Edit permission |
|---|---|---|
| `hatch-backend` | backend models, schemas, services, tests | allowed files only |
| `hatch-frontend` | frontend preview and API types | allowed files only |
| `hatch-tests` | fixtures and tests | tests only |
| `hatch-review` | review only | no edits |

Do not delegate the whole refactor to one worker.

---

## 25. Suggested OpenCode Agent Files

Codex may create these if the repository does not already have suitable agents.

Directory:

```text
.opencode/agents/
```

### `.opencode/agents/hatch-backend.md`

```markdown
---
description: Implements bounded Hatch backend tasks using existing FastAPI, SQLAlchemy, Pydantic and pytest conventions.
mode: primary
model: ollama/qwen3-coder
temperature: 0.1
steps: 35
permission:
  edit: allow
  external_directory: deny
  webfetch: deny
  websearch: deny
  bash:
    "*": ask
    "git status*": allow
    "git diff*": allow
    "rg *": allow
    "find *": allow
    "pytest *": allow
    "python -m pytest *": allow
    "git commit*": deny
    "git push*": deny
    "git reset --hard*": deny
    "rm -rf *": deny
---

You are a bounded backend implementation worker for Hatch.

Read AGENTS.md and the task file first. Inspect neighbouring files and follow repository conventions.

Rules:

- Change only files explicitly allowed by the task.
- Preserve manual application submission.
- Preserve anti-fabrication safeguards.
- Do not add dependencies unless the task explicitly allows it.
- Add focused tests.
- Do not commit or push.
- End with changed files, implementation summary, tests run, failures, and concerns.
```

### `.opencode/agents/hatch-frontend.md`

```markdown
---
description: Implements bounded Hatch frontend tasks using existing Next.js, TypeScript, component and test conventions.
mode: primary
model: ollama/qwen3-coder
temperature: 0.1
steps: 35
permission:
  edit: allow
  external_directory: deny
  webfetch: deny
  websearch: deny
  bash:
    "*": ask
    "git status*": allow
    "git diff*": allow
    "rg *": allow
    "find *": allow
    "npm test*": allow
    "npm run test*": allow
    "npm run lint*": allow
    "npm run typecheck*": allow
    "npx tsc *": allow
    "git commit*": deny
    "git push*": deny
    "git reset --hard*": deny
    "rm -rf *": deny
---

You are a bounded frontend worker for Hatch.

Rules:

- Change only files explicitly allowed by the task.
- Preserve existing layout and accessibility.
- Show education and structural warnings only where appropriate.
- Do not allow download of structurally failed CVs.
- Do not add dependencies unless explicitly allowed.
- Do not commit or push.
- End with changed files, tests run, failures, and concerns.
```

### `.opencode/agents/hatch-tests.md`

```markdown
---
description: Adds focused tests for Hatch without changing production behaviour.
mode: primary
model: ollama/qwen3-coder
temperature: 0.0
steps: 25
permission:
  edit: allow
  external_directory: deny
  webfetch: deny
  websearch: deny
  bash:
    "*": ask
    "git status*": allow
    "git diff*": allow
    "rg *": allow
    "find *": allow
    "pytest *": allow
    "python -m pytest *": allow
    "npm test*": allow
    "npm run test*": allow
    "git commit*": deny
    "git push*": deny
    "git reset --hard*": deny
    "rm -rf *": deny
---

You are a test worker.

Add tests only for the behaviour described in the task. Do not weaken assertions. Do not change production code unless explicitly permitted.

End with tests added, commands run, failures, and uncovered risks.
```

### `.opencode/agents/hatch-review.md`

```markdown
---
description: Reviews Hatch tailoring changes for correctness, missing sections, fabrication risk, regressions and tests without editing files.
mode: primary
model: ollama/qwen3-coder
temperature: 0.0
steps: 25
permission:
  edit: deny
  external_directory: deny
  webfetch: deny
  websearch: deny
  bash:
    "*": ask
    "git status*": allow
    "git diff*": allow
    "git log*": allow
    "rg *": allow
    "find *": allow
    "pytest *": allow
    "python -m pytest *": allow
    "npm test*": allow
    "npm run test*": allow
---

Review only. Do not edit.

Focus on:

- master-CV sections being dropped;
- education not mapped or rendered;
- full-CV output still accepted;
- structural validator not integrated;
- repair silently hiding serious errors;
- DOCX output missing source values;
- fabricated facts;
- excessive LLM calls;
- missing regression tests;
- frontend allowing failed downloads.

Return findings ordered by severity with exact file references.
```

Update the `model` field to match the installed local model from:

```bash
ollama list
```

---

## 26. Task File Template

Codex should create one task file per OpenCode invocation under:

```text
.codex/tailoring-reliability/tasks/
```

Template:

```markdown
# Task: <bounded task name>

## Objective

<one clear outcome>

## Allowed files

- `exact/path.py`
- `exact/test_path.py`

## Read-only context

- `related/path.py`
- `related/schema.py`

## Required behaviour

1. ...
2. ...
3. ...

## Constraints

- Change only allowed files.
- Do not add dependencies.
- Do not commit or push.
- Preserve anti-fabrication safeguards.
- Preserve manual application submission.
- Use repository conventions.

## Tests to run

```bash
<focused command>
```

## Completion response

Return:

1. files changed;
2. implementation summary;
3. tests run and result;
4. unresolved concerns.
```

---

## 27. Suggested Task Breakdown

Use small tasks.

```text
00 reconnaissance
01 golden master CV fixture
02 regression tests for missing sections
03 education schema propagation
04 DOCX builder education rendering
05 evidence-map service
06 edit-plan schema and parser
07 edit-plan prompt
08 reject full-CV-shaped model output
09 deterministic assembler
10 structural validator
11 repair missing sections from master
12 CVTailor integration
13 truncation diagnostics
14 DOCX extraction tests
15 frontend API type updates
16 frontend preview education rendering
17 frontend structural warning handling
18 backend integration regression
19 end-to-end tailoring flow
20 documentation
90 backend review
91 frontend review
92 final regression review
```

A task should normally touch one service and one test file.

---

## 28. OpenCode Invocation Pattern

Run from the repository root.

Backend task example:

```bash
opencode run \
  --agent hatch-backend \
  --model ollama/qwen3-coder \
  "$(cat .codex/tailoring-reliability/tasks/05-evidence-map-service.md)"
```

Test task example:

```bash
opencode run \
  --agent hatch-tests \
  --model ollama/qwen3-coder \
  "$(cat .codex/tailoring-reliability/tasks/02-regression-tests-missing-sections.md)"
```

Review task example:

```bash
opencode run \
  --agent hatch-review \
  --model ollama/qwen3-coder \
  "$(cat .codex/tailoring-reliability/tasks/90-backend-review.md)"
```

After every worker run, Codex must inspect:

```bash
git status --short
git diff --stat
git diff
```

Codex must reject changes outside the task boundary.

---

## 29. Codex Review Checklist

After every backend change:

- [ ] master CV remains source of truth;
- [ ] no mandatory section is dropped;
- [ ] education is preserved;
- [ ] certifications are preserved;
- [ ] all roles are preserved;
- [ ] all role titles, companies and periods are preserved;
- [ ] bullet count per role is preserved;
- [ ] unknown edit-plan IDs are ignored safely;
- [ ] invalid full-CV-shaped output is rejected;
- [ ] no unsupported facts are introduced;
- [ ] structural validator is actually called before DOCX generation;
- [ ] failed validation prevents document save;
- [ ] logs do not expose full CV contents;
- [ ] tests cover the edge case.

After every frontend change:

- [ ] education renders when present;
- [ ] certifications still render;
- [ ] warning copy is user-friendly;
- [ ] failed CV cannot be downloaded;
- [ ] existing happy path is unchanged;
- [ ] old data without education does not crash;
- [ ] tests cover loading, empty, warning and failure states.

Before final completion:

- [ ] golden regression test passes;
- [ ] DOCX extraction test passes;
- [ ] backend suite passes;
- [ ] frontend suite passes if touched;
- [ ] lint/typecheck pass;
- [ ] Docker or compose validation passes;
- [ ] README or docs explain the reliability guardrail;
- [ ] final report lists remaining limitations.

---

## 30. Acceptance Criteria

### Structural preservation

- [ ] Tailored CV preserves every master experience role.
- [ ] Tailored CV preserves every master company name.
- [ ] Tailored CV preserves every master role title.
- [ ] Tailored CV preserves every master role period/date.
- [ ] Tailored CV preserves bullet count per role.
- [ ] Tailored CV preserves education.
- [ ] Tailored CV preserves certifications.
- [ ] Tailored CV preserves mandatory skills section.
- [ ] Tailored CV does not collapse to a one-page subset.

### Architecture

- [ ] LLM returns an edit plan, not a full replacement CV.
- [ ] Final CV is assembled deterministically from the master CV.
- [ ] Structural validator runs before save/render.
- [ ] Missing sections are repaired from master where possible.
- [ ] Unrepairable structural failures are not saved.
- [ ] Full-CV-shaped output is rejected or ignored safely.
- [ ] Truncation and malformed JSON are detected.

### Safety

- [ ] No fabricated roles.
- [ ] No fabricated companies.
- [ ] No fabricated education.
- [ ] No fabricated certifications.
- [ ] Unsupported metrics are rejected where detectable.
- [ ] Anti-fabrication warnings remain intact.
- [ ] Logs avoid sensitive full-content dumps.

### DOCX

- [ ] DOCX renders education.
- [ ] DOCX renders certifications.
- [ ] DOCX contains all role titles.
- [ ] DOCX contains all company names.
- [ ] DOCX contains all role periods.
- [ ] DOCX content test verifies mandatory values.

### UI

- [ ] Preview displays education if relevant.
- [ ] Repaired structural warning is shown when relevant.
- [ ] Failed CV cannot be downloaded.
- [ ] Old tailored CV records do not break UI.

### Quality

- [ ] Regression test exists for the one-page/truncated CV bug.
- [ ] Unit tests cover evidence map, assembler and validator.
- [ ] Integration test covers sparse LLM output.
- [ ] Integration test covers bad full-CV output.
- [ ] Backend tests pass.
- [ ] Frontend tests pass if frontend touched.
- [ ] Documentation updated.

---

## 31. Definition of Done

Codex final report must include:

```text
1. Root cause confirmed
2. Architecture implemented
3. Files added and changed
4. Schema changes
5. Prompt changes
6. Validation and repair behaviour
7. DOCX rendering changes
8. Tests executed
9. Remaining limitations
10. Deferred follow-up issues
```

The final report must explicitly confirm:

```text
- no fine-tuning was added;
- master CV is the source of truth;
- final CV is assembled deterministically;
- education is preserved and rendered;
- every experience role is preserved;
- incomplete LLM output cannot silently produce an incomplete CV;
- manual application submission remains unchanged.
```

---

## 32. Recommended Future Fine-Tuning Scope

Do not implement this now.

After the reliability fix is complete, fine-tuning can be considered for one narrow task:

```text
Given:
- one original CV bullet,
- a job requirement,
- allowed supporting evidence,

return:
- one rewritten bullet that improves relevance without adding facts.
```

This is a much better fine-tuning target than generating a whole CV.

Fine-tuning should not own:

- CV structure;
- section selection;
- education rendering;
- role inclusion;
- certification inclusion;
- final document assembly.

The system should still validate every fine-tuned output.

---

## 33. First Prompt for Codex

Use this as the first message to Codex:

```text
Read HATCH_TAILORING_RELIABILITY_CODEX_PLAN.md completely.

Act as the lead engineer for the Hatch tailoring reliability fix.

Do not implement immediately.

First:

1. inspect the current repository;
2. map the CV tailoring call graph;
3. confirm where education is present or lost;
4. inspect the current tailored CV schema, parser, prompt, DOCX builder and tests;
5. inspect current LLM output budget and JSON parsing behaviour;
6. create .codex/tailoring-reliability/00-reconnaissance.md;
7. create the task ledger under .codex/tailoring-reliability/tasks/;
8. prepare the first bounded OpenCode task for a golden master CV regression test.

Use local OpenCode workers sequentially. Review every diff yourself. Do not commit or push. Do not add fine-tuning. The master CV must remain the source of truth.
```
