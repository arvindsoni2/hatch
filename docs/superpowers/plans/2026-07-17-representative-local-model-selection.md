# Representative Local-Model Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing local writing benchmark into an eight-case, staged qualification harness that automatically enforces the PR5 safety and model-change thresholds and records an auditable selection decision.

**Architecture:** Keep `run_benchmark()` as the single-case execution engine and add a checked-in synthetic suite plus a staged coordinator above it. Derive pair-level safety, quality, and operations metrics from typed repetition artifacts, aggregate them with pure selection functions, and keep all raw prompts, generated documents, and detailed run artifacts under ignored `data/benchmarks/`; only a privacy-reviewed decision summary is checked in.

**Tech Stack:** Python 3.12+, Pydantic v2, asyncio, existing CV/cover-letter production services, pytest/pytest-asyncio, Markdown reports, Docker Compose health checks.

## Global Constraints

- Branch from merged PR4 commit `c0a5fd52ee02bbda13bcf0a5696f0b010ed8ec74`.
- Do not change the default model, model catalogue, README, migration notes, or rollback instructions unless two independent Stage C runs return `change_default`.
- Stage A uses all five existing models, the Delivery Manager case, and seeds `11`, `23`, and `41`: exactly 15 pairs.
- Stage B uses no more than three models including the baseline, four risk-diverse cases, and three shared seeds: at most 36 pairs.
- Stage C uses exactly the strongest qualifying challenger plus baseline, all eight cases, and five shared seeds: 80 pairs per official run and two independent runs.
- Quality is scored only for hard-gate-passing pairs and normalized to 0–100 while preserving raw CV and cover-letter scores.
- Ranking is lexicographic: post-repair gate rate, first-pass gate rate, median eligible combined quality, lower quality variance, then lower eligible-pair latency.
- Protected database/profile hashes must remain unchanged.
- Fixtures and checked-in reports must contain no real personal data, raw model responses, full generated documents, secrets, or machine-specific absolute paths.
- A deferred or incomplete run cannot authorize a model change.

---

### Task 1: Checked-in Representative Suite and Privacy Validation

**Files:**
- Create: `backend/benchmarks/fixtures/representative_suite.json`
- Modify: `backend/benchmarks/contracts.py`
- Modify: `backend/benchmarks/case_loader.py`
- Create: `backend/tests/benchmarks/test_representative_suite.py`

**Interfaces:**
- Consumes: the existing `BenchmarkCase`, `ModelSpec`, `JDAnalysisResult`, and expected-fact contracts.
- Produces: `BenchmarkSuite`, `SuiteCase`, `load_suite(path) -> BenchmarkSuite`, and `suite_case(suite, case_id) -> BenchmarkCase`.

- [ ] **Step 1: Write failing suite tests**

Add tests asserting that the suite contains exactly the eight required case IDs, each case has five shared seeds, all personal names/domains are synthetic, the Stage B set covers management/technical/sparse/eligibility risks, and all five existing model IDs are present.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/benchmarks/test_representative_suite.py --no-cov
```

Expected: import failure because `load_suite` and `BenchmarkSuite` do not exist.

- [ ] **Step 3: Add typed suite contracts and loader**

Define suite-level models with `extra="forbid"`:

```python
class SuiteCase(StrictModel):
    case_id: str
    risk_tags: set[Literal[
        "management", "technical", "seniority", "career_transition",
        "sparse_evidence", "context_pressure", "public_sector", "eligibility"
    ]]
    master_cv: dict[str, Any]
    job_description: str
    jd_analysis: JDAnalysisResult
    expected_facts: ExpectedFacts
    cv_length_tolerance: float = Field(default=0.1, ge=0.0, le=1.0)

class BenchmarkSuite(StrictModel):
    suite_id: str
    baseline_model_id: str
    seeds: list[int] = Field(min_length=5)
    models: list[ModelSpec] = Field(min_length=5)
    stage_b_case_ids: list[str] = Field(min_length=4, max_length=4)
    historical_median_pair_seconds: dict[str, float]
    cases: list[SuiteCase] = Field(min_length=8, max_length=8)
```

`load_suite()` must hash the checked-in suite file and reject duplicate case/model IDs, non-loopback endpoints, missing Stage B cases, non-synthetic email domains, and any fixture text containing the repository user's real name or known private email domains.

- [ ] **Step 4: Add eight deterministic synthetic cases**

Add these IDs and risk coverage:

1. `delivery-project-manager` — management, leadership, exact team/programme metrics.
2. `ai-software-engineer` — technical stack fidelity.
3. `solution-architect` — seniority and scope.
4. `career-transition` — transferable skills without target-sector invention.
5. `sparse-cv` — missing-evidence safe fallback.
6. `detailed-multipage-cv` — evidence selection and context pressure.
7. `uk-public-sector` — essential/desirable criteria.
8. `sponsorship-salary` — explicit sponsorship, salary, and eligibility wording.

Use only `*.example.test` contact data, fictional employers, and synthetic metrics mirrored exactly in `expected_facts`.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest -q backend/tests/benchmarks/test_representative_suite.py backend/tests/benchmarks/test_case_loader.py --no-cov
```

Commit:

```bash
git add backend/benchmarks/fixtures/representative_suite.json backend/benchmarks/contracts.py backend/benchmarks/case_loader.py backend/tests/benchmarks/test_representative_suite.py
git commit -m "test: add representative writing benchmark suite"
```

---

### Task 2: Pair-Level Reliability, Safety, Quality, and Operations Metrics

**Files:**
- Modify: `backend/benchmarks/contracts.py`
- Modify: `backend/benchmarks/runner.py`
- Modify: `backend/benchmarks/scoring.py`
- Modify: `backend/tests/benchmarks/test_runner.py`
- Modify: `backend/tests/benchmarks/test_scoring.py`

**Interfaces:**
- Consumes: `RepetitionResult`, production generation provenance, hard-gate findings, and adapter observations.
- Produces: `PairMetrics`, `first_pass_hard_gate_passed`, `post_repair_hard_gate_passed`, safety counters, token totals, evidence coverage, and role/case quality values.

- [ ] **Step 1: Write failing metric tests**

Add tests for:

- first-pass failure followed by post-repair success;
- schema failure and timeout classification;
- unsupported candidate/numeric claim counters;
- immutable-token mutation count;
- sparse-case `review_required` fallback;
- evidence coverage from source evidence IDs;
- prompt/completion/output-token totals;
- quality exclusion for failed gates;
- normalized combined quality preserving raw component scores.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/benchmarks/test_runner.py backend/tests/benchmarks/test_scoring.py --no-cov
```

Expected: missing `PairMetrics` fields and first-pass classification failures.

- [ ] **Step 3: Implement typed metrics**

Add:

```python
class PairMetrics(StrictModel):
    first_pass_hard_gate_passed: bool
    post_repair_hard_gate_passed: bool
    schema_succeeded: bool
    unsupported_candidate_claims: int = Field(ge=0)
    unsupported_numeric_tokens: int = Field(ge=0)
    immutable_token_mutations: int = Field(ge=0)
    missing_evidence_safe_fallback: bool = False
    evidence_items_available: int = Field(ge=0)
    evidence_items_used: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    first_pass_latency_ms: float | None = Field(default=None, ge=0.0)
    repair_latency_ms: float | None = Field(default=None, ge=0.0)
    eligible_pair_latency_ms: float | None = Field(default=None, ge=0.0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    tokens_per_eligible_pair: int | None = Field(default=None, ge=0)
    peak_memory_mb: float | None = Field(default=None, ge=0.0)
    normalized_combined_quality: float | None = Field(default=None, ge=0.0, le=100.0)
```

Derive first-pass status from the first cover-letter workflow attempt plus the final CV structural gates. Treat production grounding/numeric blocking findings as unsupported candidate claims, but do not infer unsupported prose from lexical difference alone. Preserve `peak_memory_mb=None` unless an adapter/runtime already supplies it safely.

- [ ] **Step 4: Correct ranking input metrics**

Update aggregation so latency uses only eligible pair latency, first-pass rate uses the explicit first-attempt gate, response rate uses all requested pairs, repair mean and median are both available, and schema failures remain separate from transport failures.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest -q backend/tests/benchmarks/test_runner.py backend/tests/benchmarks/test_scoring.py backend/tests/benchmarks/test_adapters.py --no-cov
```

Commit:

```bash
git add backend/benchmarks/contracts.py backend/benchmarks/runner.py backend/benchmarks/scoring.py backend/tests/benchmarks/test_runner.py backend/tests/benchmarks/test_scoring.py
git commit -m "feat: record benchmark safety and operations metrics"
```

---

### Task 3: Pure Staged Qualification and Locked Selection Thresholds

**Files:**
- Create: `backend/benchmarks/selection.py`
- Create: `backend/tests/benchmarks/test_selection.py`

**Interfaces:**
- Consumes: pair results grouped by stage, model, case, seed, and official run.
- Produces: `StageQualification`, `OfficialRunDecision`, `SelectionDecision`, `rank_models(...)`, `qualify_stage_a(...)`, `qualify_stage_b(...)`, and `decide_stage_c(...)`.

- [ ] **Step 1: Write failing threshold tests**

Cover every boundary exactly:

- Stage A passes at 2/3 and fails at 1/3; baseline advances regardless but retains failure evidence.
- Stage B challenger passes at 11/12 post-repair, 9/12 first-pass, 0 unsupported claims/mutations, and 11/12 schema success.
- Stage C passes at 38/40 post-repair, 39/40 responses, quality delta exactly `-3.0`, role delta exactly `-5.0`, and latency improvement exactly `25%`.
- Memory improvement passes at exactly `20%` only when latency is no more than `10%` slower.
- Either official run failing yields `retain_baseline`.
- Missing/deferred Stage C yields `benchmark_deferred`.
- Zero eligible outputs cannot outrank an eligible model.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/benchmarks/test_selection.py --no-cov
```

Expected: import failure because `selection.py` does not exist.

- [ ] **Step 3: Implement lexicographic ranking**

Sort on:

```python
(
    -post_repair_hard_gate_rate,
    -first_pass_hard_gate_rate,
    -median_normalized_combined_quality,
    quality_variance,
    median_eligible_pair_latency_ms,
    model_id,
)
```

Use worst-value sentinels for missing eligible metrics and force models with zero eligible outputs behind any model with eligible output.

- [ ] **Step 4: Implement exact advancement and decision functions**

Return explicit per-threshold booleans and observed/required values so reports can show why a model advanced or failed. `SelectionDecision.decision` must be exactly one of `retain_baseline`, `change_default`, or `benchmark_deferred`.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest -q backend/tests/benchmarks/test_selection.py --no-cov
```

Commit:

```bash
git add backend/benchmarks/selection.py backend/tests/benchmarks/test_selection.py
git commit -m "feat: enforce staged model selection thresholds"
```

---

### Task 4: Staged Coordinator, Projection, Resume, and Deferral

**Files:**
- Create: `backend/benchmarks/staged_runner.py`
- Modify: `backend/benchmarks/cli.py`
- Modify: `backend/tests/benchmarks/test_cli.py`
- Create: `backend/tests/benchmarks/test_staged_runner.py`

**Interfaces:**
- Consumes: `BenchmarkSuite`, `run_benchmark()`, selection functions, historical/observed latency, and protected hashes.
- Produces: ignored staged artifacts under `data/benchmarks/results/<run-id>/`, `run_stage_suite(...)`, resumable stage manifests, projected pair counts/durations, and CLI command `staged-run`.

- [ ] **Step 1: Write failing coordinator tests**

Assert:

- Stage A schedules exactly 15 pairs.
- Stage B schedules at most 36 pairs and only the top three Stage A candidates including baseline.
- no qualifying challenger stops before Stage C with `retain_baseline`;
- qualifying Stage B schedules two 80-pair official runs;
- `--defer-stage-c` records `benchmark_deferred`;
- Stage C refuses to start without a fresh service-restart evidence record;
- interrupted runs preserve completed pair artifacts and resume without replay;
- projected pair count and duration are printed before each stage;
- database/profile hashes are unchanged across the staged run.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/benchmarks/test_staged_runner.py backend/tests/benchmarks/test_cli.py --no-cov
```

Expected: missing `staged-run` command and coordinator import.

- [ ] **Step 3: Implement stage orchestration**

Use `run_benchmark()` once per `(stage, official_run, case)` with stage-owned run IDs. Read typed `result.json` artifacts for aggregation. Persist `staged_manifest.json`, `staged_progress.json`, and `selection.json` atomically after every case.

- [ ] **Step 4: Implement projections and clean-restart evidence**

Before Stage A, estimate duration from checked-in historical model medians. Before later stages, use observed eligible median latency, falling back to successful response latency. Require a JSON restart record containing timestamp, model endpoint health, and the staged source commit before each official Stage C run.

- [ ] **Step 5: Add CLI**

Add:

```text
python -m benchmarks staged-run \
  --suite backend/benchmarks/fixtures/representative_suite.json \
  --output-root data/benchmarks/results \
  [--resume RUN_ID] [--defer-stage-c] [--restart-evidence PATH]
```

Print projection lines before inference and return nonzero only for infrastructure/protected-hash failures, not for an evidence-backed `retain_baseline`.

- [ ] **Step 6: Verify and commit**

Run:

```bash
pytest -q backend/tests/benchmarks/test_staged_runner.py backend/tests/benchmarks/test_cli.py backend/tests/benchmarks/test_runner.py --no-cov
```

Commit:

```bash
git add backend/benchmarks/staged_runner.py backend/benchmarks/cli.py backend/tests/benchmarks/test_staged_runner.py backend/tests/benchmarks/test_cli.py
git commit -m "feat: orchestrate staged local model benchmark"
```

---

### Task 5: Representative Reporting and Operator Runbook

**Files:**
- Modify: `backend/benchmarks/reporting.py`
- Modify: `backend/tests/benchmarks/test_reporting.py`
- Create: `docs/operations/REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md`

**Interfaces:**
- Consumes: staged manifest, per-stage aggregates, threshold evidence, and `SelectionDecision`.
- Produces: `render_staged_report(...)`, privacy-safe Markdown, and an operator runbook covering restart, resume, defer, hashes, and conditional model change.

- [ ] **Step 1: Write failing report tests**

Require separate Reliability, Safety and fidelity, Quality, Operations, Stage qualification, Locked threshold evaluation, Decision, Privacy, and Limitations sections. Assert raw candidate text, prompts, generated documents, absolute paths, and secrets never appear.

- [ ] **Step 2: Verify RED**

Run:

```bash
pytest -q backend/tests/benchmarks/test_reporting.py --no-cov
```

- [ ] **Step 3: Implement staged report**

Report rates and counts together, preserve raw CV/cover-letter component scores, show normalized combined quality, include per-role medians, and render every Stage C threshold as pass/fail with observed and required values.

- [ ] **Step 4: Write operator runbook**

Document:

- suite validation and privacy scan;
- Stage A/B invocation;
- clean service restart and restart evidence;
- Stage C execution/resume;
- `benchmark_deferred`;
- protected hash and service-health checks;
- why no model file changes are permitted for `retain_baseline` or `benchmark_deferred`;
- conditional README/catalog/migration/rollback update checklist for `change_default`.

- [ ] **Step 5: Verify and commit**

Run:

```bash
pytest -q backend/tests/benchmarks/test_reporting.py --no-cov
python scripts/check_docs.py
```

Commit:

```bash
git add backend/benchmarks/reporting.py backend/tests/benchmarks/test_reporting.py docs/operations/REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md
git commit -m "docs: add representative benchmark reporting"
```

---

### Task 6: Execute Stages A and B, Then Conditionally Stage C

**Files:**
- Create: `docs/benchmarks/LOCAL_WRITING_MODEL_SELECTION_2026-07-17.md`
- Conditionally modify only for `change_default`: `README.md`, the canonical model catalogue, migration notes, and rollback instructions identified by the runbook.

**Interfaces:**
- Consumes: committed PR5 harness, live five-model endpoints, clean restart evidence if needed, and ignored detailed artifacts.
- Produces: actual Stage A/B evidence, conditional Stage C evidence, and one checked-in privacy-safe decision record.

- [ ] **Step 1: Commit and validate the harness before inference**

Run:

```bash
git status --short
pytest -q backend/tests/benchmarks --no-cov
python -m benchmarks validate-suite --suite backend/benchmarks/fixtures/representative_suite.json
```

Expected: clean committed harness, all benchmark tests pass, eight valid synthetic cases.

- [ ] **Step 2: Record protected hashes and service health**

Record database/profile hashes, backend/frontend health, llama.cpp health, Ollama tags, repository commit, branch, and exact command timestamps in ignored run artifacts.

- [ ] **Step 3: Run Stage A and Stage B**

Run:

```bash
python -m benchmarks staged-run \
  --suite backend/benchmarks/fixtures/representative_suite.json \
  --output-root data/benchmarks/results
```

Allow the harness to stop after Stage B when no challenger qualifies.

- [ ] **Step 4: Conditionally run Stage C**

If a challenger qualifies, cleanly restart the relevant local model services, create restart evidence, and resume the same staged run. Repeat the restart/evidence boundary for official run 2. If the operator intentionally stops, resume with `--defer-stage-c` and record `benchmark_deferred`.

- [ ] **Step 5: Review privacy-safe evidence**

Verify the checked-in report contains no fixture prose beyond case names, no generated content, no raw response, no absolute path, no secret, and no database/profile content or hash value that the repository treats as sensitive.

- [ ] **Step 6: Apply the decision boundary**

- `retain_baseline`: do not modify model defaults or model documentation.
- `benchmark_deferred`: do not modify model defaults or model documentation.
- `change_default`: update README, canonical model catalogue, migration notes, and rollback instructions in one separate commit, then rerun their contract tests.

- [ ] **Step 7: Commit the decision evidence**

```bash
git add docs/benchmarks/LOCAL_WRITING_MODEL_SELECTION_2026-07-17.md
git commit -m "docs: record representative local model decision"
```

If and only if selected:

```bash
git add README.md docs/operations/LOCAL_MODELS.md <canonical-model-catalogue> <migration-and-rollback-docs>
git commit -m "feat: select benchmark-qualified local writing model"
```

---

### Task 7: Full Verification and PR Publication

**Files:**
- Modify only if verification exposes a PR5 regression.

**Interfaces:**
- Consumes: all PR5 commits and benchmark evidence.
- Produces: a review-ready PR with unchanged protected data and an auditable decision.

- [ ] **Step 1: Run benchmark and backend tests**

```bash
pytest -q backend/tests/benchmarks --no-cov
pytest -q backend/tests --no-cov
```

- [ ] **Step 2: Run repository contracts**

```bash
python scripts/check_docs.py
python scripts/check_readme_contract.py
git diff origin/main...HEAD --check
```

- [ ] **Step 3: Confirm protected configuration boundary**

For `retain_baseline` or `benchmark_deferred`, assert no README/model-catalogue/profile/model-default file changed. For `change_default`, assert both official decisions are `change_default` and every threshold evidence row passes before accepting those changes.

- [ ] **Step 4: Confirm operational evidence**

Verify service health passed, protected hashes are unchanged, pair projections were recorded, Stage A/B completed, Stage C followed the qualification/defer rule, and the final decision is one of the three locked values.

- [ ] **Step 5: Review and publish**

Use `superpowers:verification-before-completion`, perform the local review checklist because workspace instructions prohibit subagents, then use `superpowers:finishing-a-development-branch` to push `chore/local-model-benchmark-selection` and open PR5 while preserving `/tmp/hatch-writing-pr5`.
