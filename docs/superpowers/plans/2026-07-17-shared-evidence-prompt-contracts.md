# Shared Evidence and Prompt Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CV tailoring and cover-letter generation share deterministic evidence, numeric-fidelity, prompt-version, validation, and provenance contracts without changing their public document payloads.

**Architecture:** Add a focused `writing_contracts` service module containing immutable typed contracts, evidence-ledger construction, numeric-token extraction, prompt fragments, prompt metadata, and validation. Both generators assemble prompts from that module and run the same deterministic numeric validation after generation. Optional provenance remains internal to Pydantic results, benchmark artifacts record explicit metadata, and generated-document `tailoring_params` stores provenance through its existing extensible JSON.

**Tech Stack:** Python 3.14, Pydantic 2, Jinja2, pytest, existing Hatch benchmark harness.

## Global Constraints

- Branch directly from current `main`; do not merge or depend on `fix/cover-letter-contract-repair`.
- Preserve the existing public CV and cover-letter API payload shapes.
- Do not add a database migration.
- Keep the default model and model configuration unchanged.
- Evidence IDs use `sha256(schema_version + "\n" + canonical_source_path + "\n" + normalized_exact_evidence_text)[:24]`.
- Evidence normalization uses Unicode NFC, `\n` line endings, trimmed boundaries, and collapsed ASCII whitespace while preserving case, punctuation, symbols, and numeric formatting.
- Cover-letter generation prompt version is `2.0.0`.
- Cover-letter repair prompt version is `1.0.0`.
- CV-tailoring prompt version is `2.0.0`.
- Shared factuality and numeric-fidelity contract versions are `1.0.0`.
- Exact matching remains the only blocking semantic activation rule.

---

### Task 1: Shared typed writing contracts

**Files:**
- Create: `backend/app/services/writing_contracts.py`
- Create: `backend/tests/test_services/test_writing_contracts.py`

**Interfaces:**
- Produces: `PromptMetadata`, `EvidenceItem`, `NumericToken`, `ValidationIssue`, `ValidationResult`, and `GenerationProvenance`.
- Produces: `normalize_evidence_text(text: str) -> str`.
- Produces: `extract_numeric_tokens(text: str) -> tuple[NumericToken, ...]`.
- Produces: `build_evidence_ledger(master: dict[str, Any]) -> tuple[EvidenceItem, ...]`.
- Produces: `validate_numeric_fidelity(candidate_prose: Iterable[str], ledger: Iterable[EvidenceItem]) -> ValidationResult`.
- Produces: shared factuality and numeric-fidelity prompt fragment constants and prompt metadata constants.

- [ ] **Step 1: Write failing deterministic evidence tests**

```python
def test_evidence_ids_are_stable_and_duplicates_keep_first_source() -> None:
    master = {
        "summary_variants": {"a": "Delivered across 120+ locations", "b": " Delivered  across  120+ locations "},
    }
    ledger = build_evidence_ledger(master)
    assert len(ledger) == 1
    assert ledger[0].source_path == "summary_variants.a"
    assert ledger[0].id == stable_evidence_id(
        "summary_variants.a", "Delivered across 120+ locations"
    )
```

- [ ] **Step 2: Run the evidence test and verify it fails because the module does not exist**

Run: `pytest backend/tests/test_services/test_writing_contracts.py -q --no-cov`

Expected: collection failure for `app.services.writing_contracts`.

- [ ] **Step 3: Implement immutable dataclasses, normalization, ID derivation, and ordered deduplication**

```python
EVIDENCE_SCHEMA_VERSION = "1.0.0"

def stable_evidence_id(source_path: str, text: str) -> str:
    value = "\n".join(
        (EVIDENCE_SCHEMA_VERSION, source_path, normalize_evidence_text(text))
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
```

- [ ] **Step 4: Add failing numeric extraction and false-positive tests**

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Managed 120+ locations", ("120+ locations",)),
        ("Owned a £2.5m budget", ("£2.5m budget",)),
        ("Improved throughput by 15%", ("15%",)),
        ("Served from 2018–2022", ("2018–2022",)),
    ],
)
def test_extract_numeric_tokens_preserves_immutable_expression(text, expected):
    assert tuple(item.raw for item in extract_numeric_tokens(text)) == expected

def test_validation_excludes_metadata_and_evidence_ids() -> None:
    result = validate_numeric_fidelity(
        ["Delivered the migration safely."],
        build_evidence_ledger({"experience": [{"period": "2018–2022", "achievements": []}]}),
    )
    assert result.passed
```

- [ ] **Step 5: Implement numeric extraction and common validation**

The validator scans only prose strings supplied by each generator. It compares normalized tokens against the union of ledger immutable tokens and emits blocking `unsupported_numeric_token` issues for unmatched expressions. Metadata fields, JSON keys, evidence IDs, role periods, subject lines, greetings, and sign-offs are never supplied as candidate prose.

- [ ] **Step 6: Run shared contract tests**

Run: `pytest backend/tests/test_services/test_writing_contracts.py -q --no-cov`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/writing_contracts.py backend/tests/test_services/test_writing_contracts.py
git commit -m "feat: add shared writing evidence contracts"
```

### Task 2: Shared prompt assembly and compatible provenance

**Files:**
- Modify: `backend/app/schemas/tailor.py`
- Modify: `backend/app/prompts/cv_tailoring.j2`
- Modify: `backend/app/prompts/cl_generation.j2`
- Modify: `backend/app/services/cv_tailor.py`
- Modify: `backend/app/services/cl_generator.py`
- Modify: `backend/tests/test_services/test_cv_tailor.py`
- Modify: `backend/tests/test_services/test_cl_generator.py`
- Modify: `backend/tests/test_services/test_skill_injection.py`
- Modify: `backend/tests/test_services/test_writing_contracts.py`

**Interfaces:**
- Consumes: shared ledger, fragments, metadata, and validation from Task 1.
- Produces: `TailoredCVResult.generation_provenance` and `CoverLetterResult.generation_provenance` as optional excluded internal fields.
- Produces: generator prompts containing the same shared contract fragments.

- [ ] **Step 1: Write failing schema-compatibility tests**

```python
def test_old_generated_records_without_prompt_metadata_remain_readable() -> None:
    value = TailoredCVResult.model_validate({"summary": "Grounded"})
    assert value.generation_provenance is None
    assert "generation_provenance" not in value.model_dump()
```

- [ ] **Step 2: Run compatibility tests and verify the missing field failure**

Run: `pytest backend/tests/test_services/test_writing_contracts.py -q --no-cov`

Expected: assertion failure because `generation_provenance` is absent.

- [ ] **Step 3: Add internal optional provenance fields**

```python
generation_provenance: GenerationProvenance | None = Field(
    default=None,
    exclude=True,
)
```

- [ ] **Step 4: Write failing prompt-fragment tests for both generators**

Capture each fake client's system and user prompt and assert:

```python
assert SHARED_FACTUALITY_CONTRACT in complete_prompt
assert SHARED_NUMERIC_FIDELITY_CONTRACT in complete_prompt
assert "APPROVED_EVIDENCE" in complete_prompt
```

- [ ] **Step 5: Pass ledger JSON, shared fragments, and prompt metadata into both Jinja templates**

Prompt sections follow the specified order: role boundary, shared factuality, shared numeric fidelity, task instructions, approved evidence, JD context, output schema, and final reminder.

- [ ] **Step 6: Write failing validation and provenance tests**

CV test cases cover a mutated `120+ locations` claim, an unsupported `97%` claim, an unchanged role period, unchanged structural gates, and safe fallback to original source bullets when generated claims fail validation. Cover-letter cases cover unsupported numeric body prose and verify generation metadata.

- [ ] **Step 7: Run tests and confirm failures are caused by absent shared validation**

Run: `pytest backend/tests/test_services/test_cv_tailor.py backend/tests/test_services/test_cl_generator.py -q --no-cov`

Expected: new validation/provenance assertions fail.

- [ ] **Step 8: Apply shared validation on every generator return path**

CV validation scans summary, skill items, and achievement prose after structural preservation. Cover-letter validation scans body paragraphs. Existing placeholder and grounding checks remain in place; common blocking messages are projected into existing `blocking_issues` and `grounding_issues`.

- [ ] **Step 9: Run generator and skill-injection tests**

Run: `pytest backend/tests/test_services/test_cv_tailor.py backend/tests/test_services/test_cl_generator.py backend/tests/test_services/test_skill_injection.py -q --no-cov`

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add backend/app/schemas/tailor.py backend/app/prompts/cv_tailoring.j2 backend/app/prompts/cl_generation.j2 backend/app/services/cv_tailor.py backend/app/services/cl_generator.py backend/tests/test_services
git commit -m "feat: share writing prompt and validation contracts"
```

### Task 3: Benchmark and document provenance metadata

**Files:**
- Modify: `backend/benchmarks/contracts.py`
- Modify: `backend/benchmarks/runner.py`
- Modify: `backend/tests/benchmarks/test_runner.py`
- Modify: `backend/app/services/tailor_service.py`
- Modify: `backend/tests/test_services/test_blocking_gate.py`

**Interfaces:**
- Consumes: prompt metadata constants and generator provenance from Tasks 1–2.
- Produces: benchmark manifest `prompt_versions` and `schema_versions`.
- Produces: repetition-result `prompt_metadata`.
- Persists generation provenance in existing `tailoring_params` JSON.

- [ ] **Step 1: Write failing benchmark metadata test**

```python
manifest = json.loads((tmp_path / "test-run" / "manifest.json").read_text())
assert manifest["prompt_versions"]["cv_tailoring"] == "2.0.0"
assert manifest["prompt_versions"]["cover_letter_generation"] == "2.0.0"
result = json.loads(
    (tmp_path / "test-run" / "runs/qwen35-4b/01/result.json").read_text()
)
assert result["prompt_metadata"]["cv_tailoring"]["schema_version"] == "1.0.0"
```

- [ ] **Step 2: Run the benchmark test and verify the metadata assertion fails**

Run: `pytest backend/tests/benchmarks/test_runner.py::test_runner_ranks_gate_pass_rate_before_quality -q --no-cov`

Expected: `KeyError` for `prompt_versions` or `prompt_metadata`.

- [ ] **Step 3: Add strict benchmark metadata fields and write them in manifest/result artifacts**

`RepetitionResult.prompt_metadata` is a dictionary of serialized `PromptMetadata` values. Failed and unavailable runs retain an empty dictionary; successful runs include CV tailoring and cover-letter generation metadata.

- [ ] **Step 4: Write failing persistence test for existing extensible JSON**

Assert generated CV and cover-letter `tailoring_params` contain `generation_provenance` with prompt and evidence schema versions, while repository method signatures and database columns remain unchanged.

- [ ] **Step 5: Persist provenance through `tailoring_params`**

Use an internal helper to serialize excluded provenance and merge it into each existing tailoring-parameter object. Do not add a column or expose the internal field through response serialization.

- [ ] **Step 6: Run benchmark, service, and compatibility tests**

Run: `pytest backend/tests/benchmarks backend/tests/test_services/test_blocking_gate.py backend/tests/test_services/test_cv_tailor.py backend/tests/test_services/test_cl_generator.py -q --no-cov`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/benchmarks backend/tests/benchmarks backend/app/services/tailor_service.py backend/tests/test_services/test_blocking_gate.py
git commit -m "feat: record writing contract provenance"
```

### Task 4: Full contract verification

**Files:**
- Modify only if verification reveals a PR2-scoped defect.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: evidence that PR2 meets its acceptance criteria.

- [ ] **Step 1: Run focused PR2 tests**

Run: `pytest backend/tests/test_services/test_writing_contracts.py backend/tests/test_services/test_cv_tailor.py backend/tests/test_services/test_cl_generator.py backend/tests/test_services/test_skill_injection.py backend/tests/benchmarks --no-cov`

Expected: all pass.

- [ ] **Step 2: Run the complete backend suite**

Run: `pytest backend --no-cov`

Expected: all pass, with only pre-existing skips/warnings.

- [ ] **Step 3: Run repository documentation contract checks**

Run: `python scripts/check_docs.py`

Expected: pass.

Run: `python scripts/check_readme_contract.py`

Expected: pass.

- [ ] **Step 4: Review compatibility and scope**

Confirm no database migration, model-default edit, public response-field addition, or dependency on `fix/cover-letter-contract-repair` exists. Confirm every production CV and cover-letter generation path reaches shared numeric validation.

- [ ] **Step 5: Commit any verification-only documentation if required**

```bash
git status --short
```

Expected: clean branch after all intentional changes are committed.
