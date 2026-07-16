# Local CV and Cover-Letter Model Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a reusable, fully automatic local benchmark that compares Hatch's current Qwen3.5 4B CV/cover-letter output with Qwen3.5 9B, Qwen3 8B, Gemma4 e2b, and Gemma4 e4b.

**Architecture:** A private benchmark case supplies a frozen JD analysis and master CV to the real `CVTailor` and `CoverLetterGenerator`. Runtime adapters call loopback llama.cpp or Ollama endpoints, while deterministic gates/scorers create auditable per-run artifacts and a lexicographically ranked Markdown/JSON report without touching application databases or profile configuration.

**Tech Stack:** Python 3.12, Pydantic v2, httpx, pytest, RapidFuzz, llama.cpp OpenAI-compatible API, Ollama native chat API.

## Global Constraints

- Local-only inference; every configured endpoint must resolve to loopback.
- Initial candidates are exactly `qwen35-4b`, `qwen35-9b`, `qwen3-8b`, `gemma4-e2b`, and `gemma4-e4b`; Llama 3.1 and Mistral are deferred.
- Three declared-seed repetitions per candidate; run candidates sequentially.
- Freeze JD analysis and master-CV input per case.
- Do not modify `data/profile.yaml`, application records, or Hatch databases.
- Do not use an LLM-as-judge.
- Hard-gate failures cannot win through ATS coverage, latency, or partial output.
- Personal inputs and benchmark outputs live only under ignored `data/benchmarks/`.
- Normal unit/integration tests must run without local model endpoints.

---

### Task 1: Benchmark contracts and private case loading

**Files:**
- Create: `backend/benchmarks/__init__.py`
- Create: `backend/benchmarks/contracts.py`
- Create: `backend/benchmarks/case_loader.py`
- Create: `backend/tests/benchmarks/test_case_loader.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `JDAnalysisResult`, JSON files under a case directory.
- Produces: `BenchmarkCase`, `ExpectedFacts`, `ModelSpec`, `load_case(path: Path) -> BenchmarkCase`, `hash_file(path: Path) -> str`.

- [x] **Step 1: Add failing case-loader and privacy tests**

Create synthetic case files in `tmp_path`, then assert schema loading, SHA-256 hashes, loopback endpoint rejection, missing-file errors, and explicit ignore coverage:

```python
def test_load_case_validates_files_and_hashes(synthetic_case: Path) -> None:
    case = load_case(synthetic_case)
    assert case.case_id == "synthetic-delivery"
    assert case.jd_analysis.role_title == "Delivery Manager"
    assert set(case.input_hashes) == {
        "case.json", "master_cv.json", "job_description.txt",
        "jd_analysis.json", "expected_facts.json",
    }

def test_model_spec_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        ModelSpec(id="remote", runtime="ollama", model="x", endpoint="https://example.com")
```

- [x] **Step 2: Run the focused tests and verify RED**

Run: `cd backend && python -m pytest tests/benchmarks/test_case_loader.py -q --no-cov`

Expected: collection fails because `benchmarks.case_loader` does not exist.

- [x] **Step 3: Implement typed contracts and strict loading**

Define Pydantic models with explicit fields and forbidden extras:

```python
class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    runtime: Literal["llamacpp", "ollama"]
    model: str
    endpoint: AnyHttpUrl
    context_size: int
    temperature: float = 0.3
    max_tokens_cv: int = CV_GENERATE.max_output
    max_tokens_cl: int = CL_BODY.max_output

    @field_validator("endpoint")
    @classmethod
    def loopback_only(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("benchmark endpoints must be loopback")
        return value

class BenchmarkCase(BaseModel):
    case_id: str
    source_dir: Path
    master_cv: dict[str, Any]
    job_description: str
    jd_analysis: JDAnalysisResult
    expected_facts: ExpectedFacts
    models: list[ModelSpec]
    input_hashes: dict[str, str]
```

`load_case` must validate every required file before parsing any model configuration. Add `data/benchmarks/` to `.gitignore` without unignoring descendants.

- [x] **Step 4: Run tests and privacy checks**

Run:

```bash
cd backend && python -m pytest tests/benchmarks/test_case_loader.py -q --no-cov
cd .. && git check-ignore data/benchmarks/private/master_cv.json
```

Expected: focused tests pass and `git check-ignore` prints the private path.

- [x] **Step 5: Commit Task 1**

```bash
git add .gitignore backend/benchmarks backend/tests/benchmarks/test_case_loader.py
git commit -m "feat(benchmarks): add private case contracts"
```

---

### Task 2: Inject benchmark master-CV data into the production tailor

**Files:**
- Modify: `backend/app/services/cv_tailor.py`
- Modify: `backend/tests/test_services/test_cv_tailor.py`

**Interfaces:**
- Consumes: optional `Callable[[], dict[str, Any]]` supplied by the benchmark runner.
- Produces: `CVTailor(..., master_cv_loader=...)` while preserving the production default central store.

- [x] **Step 1: Add a failing dependency-injection test**

```python
@pytest.mark.asyncio
async def test_tailor_accepts_isolated_master_cv_loader() -> None:
    loader = MagicMock(return_value=MOCK_MASTER_CV)
    tailor = CVTailor(make_mock_client(MOCK_TAILOR_RESPONSE), master_cv_loader=loader)
    result = await tailor.tailor(JD_ANALYSIS)
    assert result.experience[0].company == "Company A"
    assert loader.call_count >= 1
```

- [x] **Step 2: Run the test and verify RED**

Run: `cd backend && python -m pytest tests/test_services/test_cv_tailor.py::test_tailor_accepts_isolated_master_cv_loader -q --no-cov`

Expected: `TypeError` for unexpected `master_cv_loader`.

- [x] **Step 3: Add the minimal loader seam**

```python
MasterCVLoader = Callable[[], dict[str, Any]]

def __init__(
    self,
    claude_client: LLMClient,
    skill_loader: SkillLoader | None = None,
    master_cv_loader: MasterCVLoader | None = None,
) -> None:
    self._client = claude_client
    self._skill_loader = skill_loader or _default_skill_loader()
    self._master_cv_loader = master_cv_loader or load_master_cv

def _load_master_cv(self) -> dict[str, Any]:
    return self._master_cv_loader()
```

- [x] **Step 4: Run the complete CV-tailor test file**

Run: `cd backend && python -m pytest tests/test_services/test_cv_tailor.py -q --no-cov`

Expected: all tests pass, including existing patched-loader tests.

- [x] **Step 5: Commit Task 2**

```bash
git add backend/app/services/cv_tailor.py backend/tests/test_services/test_cv_tailor.py
git commit -m "refactor(tailor): allow isolated master CV input"
```

---

### Task 3: Deterministic hard gates and quality scores

**Files:**
- Create: `backend/benchmarks/scoring.py`
- Create: `backend/tests/benchmarks/test_scoring.py`

**Interfaces:**
- Consumes: `BenchmarkCase`, `TailoredCVResult`, `CoverLetterResult`.
- Produces: `score_pair(case, cv, cover_letter) -> PairScore`, with auditable `GateFinding` and `DimensionScore` records.

- [x] **Step 1: Add failing hard-gate tests**

Cover valid and invalid structured content, roles, employers, periods, education, certifications, bullet counts, numeric tokens, placeholders, LaTeX, CV length tolerance, cover-letter word count, and empty output:

```python
def test_unsupported_metric_is_a_blocking_gate(case, valid_cv, valid_cl) -> None:
    valid_cl.body_paragraphs[1] += " I improved throughput by 97%."
    score = score_pair(case, valid_cv, valid_cl)
    assert not score.eligible
    assert any(f.code == "unsupported_numeric_token" for f in score.gates)

def test_missing_role_is_a_blocking_gate(case, valid_cv, valid_cl) -> None:
    valid_cv.experience.pop()
    score = score_pair(case, valid_cv, valid_cl)
    assert any(f.code == "role_structure_mismatch" for f in score.gates)
```

- [x] **Step 2: Run hard-gate tests and verify RED**

Run: `cd backend && python -m pytest tests/benchmarks/test_scoring.py -q --no-cov`

Expected: collection fails because `benchmarks.scoring` does not exist.

- [x] **Step 3: Implement hard gates with source-derived allowlists**

Implement normalised matching helpers, protected identity comparisons, numeric-token allowlists from source CV/JD company context, duplicate n-gram detection, and exact structural checks. Return all findings in one pass:

```python
def score_pair(case: BenchmarkCase, cv: TailoredCVResult, letter: CoverLetterResult) -> PairScore:
    gates = [
        *_cv_structure_gates(case, cv),
        *_protected_fact_gates(case, cv, letter),
        *_format_gates(case, cv, letter),
    ]
    if any(item.blocking for item in gates):
        return PairScore(eligible=False, gates=gates)
    cv_score = _score_cv(case, cv)
    cl_score = _score_cover_letter(case, cv, letter)
    return PairScore(
        eligible=True,
        gates=gates,
        cv=cv_score,
        cover_letter=cl_score,
        combined=round(cv_score.total * 0.6 + cl_score.total * 0.4, 2),
    )
```

- [x] **Step 4: Add and pass weighted-score boundary tests**

Assert every weight from the approved design, unsupported-gap exclusion, component totals, readable findings, and the `60/40` combined calculation.

Run: `cd backend && python -m pytest tests/benchmarks/test_scoring.py -q --no-cov`

Expected: all scoring tests pass.

- [x] **Step 5: Commit Task 3**

```bash
git add backend/benchmarks/scoring.py backend/tests/benchmarks/test_scoring.py
git commit -m "feat(benchmarks): add deterministic writing scores"
```

---

### Task 4: Loopback model adapters and metrics

**Files:**
- Create: `backend/benchmarks/adapters.py`
- Create: `backend/tests/benchmarks/test_adapters.py`

**Interfaces:**
- Consumes: `ModelSpec`, seed, prompt strings, max-token budget.
- Produces: `BenchmarkLLMClient.complete_json(...)`, `GenerationObservation`, and typed `BenchmarkInferenceError` subclasses compatible with `CVTailor` and `CoverLetterGenerator`.

- [x] **Step 1: Add failing mocked HTTP tests**

Use `httpx.MockTransport` to verify llama.cpp `/v1/chat/completions` and Ollama `/api/chat` payloads include system/user messages, JSON output request, temperature, seed, and token budget. Cover health failure, timeout, malformed JSON, Python-literal repair, and usage/timing extraction.

```python
@pytest.mark.asyncio
async def test_ollama_adapter_sends_seed_and_json_format() -> None:
    client = BenchmarkLLMClient(OLLAMA_SPEC, seed=41, transport=transport)
    result = await client.complete_json("system", "user", max_tokens=512)
    assert result == {"summary": "ok"}
    assert captured["format"] == "json"
    assert captured["options"]["seed"] == 41
```

- [x] **Step 2: Run adapter tests and verify RED**

Run: `cd backend && python -m pytest tests/benchmarks/test_adapters.py -q --no-cov`

Expected: collection fails because `benchmarks.adapters` does not exist.

- [x] **Step 3: Implement runtime-specific request builders and shared parsing**

Implement one `httpx.AsyncClient` per benchmark client, enforce loopback again at request time, use native Ollama metrics (`prompt_eval_count`, `eval_count`, durations), retain llama.cpp response metadata, retry JSON parsing up to the application policy, and append every request attempt to `observations`.

- [x] **Step 4: Run adapter tests**

Run: `cd backend && python -m pytest tests/benchmarks/test_adapters.py -q --no-cov`

Expected: all adapter tests pass without live models.

- [x] **Step 5: Commit Task 4**

```bash
git add backend/benchmarks/adapters.py backend/tests/benchmarks/test_adapters.py
git commit -m "feat(benchmarks): add local model adapters"
```

---

### Task 5: Sequential runner, atomic artifacts, and aggregation

**Files:**
- Create: `backend/benchmarks/runner.py`
- Create: `backend/tests/benchmarks/test_runner.py`

**Interfaces:**
- Consumes: `BenchmarkCase`, selected model IDs, repetition count, output root.
- Produces: `run_benchmark(...) -> BenchmarkSummary`, atomic per-repetition artifacts, resumable partial runs, and lexicographic ranking.

- [x] **Step 1: Add failing mocked end-to-end runner tests**

Use two fake adapters and synthetic CV/letter responses to prove sequential ordering, three declared seeds, real prompt rendering through both production generators, partial failure preservation, unavailable-model continuation, no profile/database writes, medians, variance, and ranking:

```python
@pytest.mark.asyncio
async def test_runner_ranks_gate_pass_rate_before_quality(tmp_path, synthetic_case) -> None:
    summary = await run_benchmark(
        synthetic_case,
        model_ids=["safe", "unsafe"],
        repetitions=3,
        output_root=tmp_path,
        adapter_factory=fake_factory,
    )
    assert summary.ranking[0].model_id == "safe"
    assert (tmp_path / summary.run_id / "summary.json").exists()
```

- [x] **Step 2: Run runner tests and verify RED**

Run: `cd backend && python -m pytest tests/benchmarks/test_runner.py -q --no-cov`

Expected: collection fails because `benchmarks.runner` does not exist.

- [x] **Step 3: Implement sequential execution and atomic JSON writes**

For every repetition, construct `CVTailor(client, master_cv_loader=lambda: case.master_cv)`, generate the CV, generate the letter from that CV, score the pair, and write to a temporary file followed by `Path.replace`. Store failures as typed repetition artifacts instead of aborting the model loop.

- [x] **Step 4: Implement aggregation and recommendation classification**

Sort by negative pass rate, negative median score, variance, latency, then memory. Implement `keep_current_model`, `prompt_or_skill_change`, `model_change`, and `inconclusive` classifications with evidence strings; a single case must retain the single-case limitation.

- [x] **Step 5: Run runner and existing service tests**

Run:

```bash
cd backend && python -m pytest tests/benchmarks/test_runner.py tests/test_services/test_cv_tailor.py tests/test_services/test_cl_generator.py -q --no-cov
```

Expected: all selected tests pass.

- [x] **Step 6: Commit Task 5**

```bash
git add backend/benchmarks/runner.py backend/tests/benchmarks/test_runner.py
git commit -m "feat(benchmarks): run and rank writing models"
```

---

### Task 6: Reports, CLI, and private-case initialisation

**Files:**
- Create: `backend/benchmarks/reporting.py`
- Create: `backend/benchmarks/cli.py`
- Create: `backend/benchmarks/__main__.py`
- Create: `backend/tests/benchmarks/test_reporting.py`
- Create: `backend/tests/benchmarks/test_cli.py`
- Modify: `docs/superpowers/specs/2026-07-15-local-cv-cover-letter-model-benchmark-design.md`

**Interfaces:**
- Consumes: benchmark cases and result directories.
- Produces: `validate`, `init-case`, `smoke`, `run`, and `report` CLI commands; stable `report.md` and `summary.json`.

- [x] **Step 1: Add failing CLI/report tests**

Assert exact exit codes for valid/invalid cases, unavailable smoke targets, partial runs, external output-path warnings, and stable Markdown sections for CV, cover letter, hard gates, operational metrics, rankings, recommendation, and limitations.

- [x] **Step 2: Run CLI/report tests and verify RED**

Run: `cd backend && python -m pytest tests/benchmarks/test_reporting.py tests/benchmarks/test_cli.py -q --no-cov`

Expected: collection fails because reporting and CLI modules do not exist.

- [x] **Step 3: Implement stable reporting and CLI dispatch**

Use `argparse`; make `validate` inference-free, `smoke` perform one minimal completion, `run` create a timestamp/UUID run directory, and `report` regenerate Markdown from `summary.json`. `init-case` copies a supplied master JSON, JD, frozen analysis, and expected-facts file through validated Python APIs into ignored storage.

- [x] **Step 4: Update the design with final command names only if implementation differs**

Keep the approved contract unchanged unless an exact CLI spelling needed correction; record any correction explicitly in the design rather than silently diverging.

- [x] **Step 5: Run all benchmark tests and CLI help**

Run:

```bash
cd backend && python -m pytest tests/benchmarks -q --no-cov
python -m benchmarks.cli --help
python -m benchmarks.cli run --help
```

Expected: tests pass and help lists all five subcommands.

- [x] **Step 6: Commit Task 6**

```bash
git add backend/benchmarks backend/tests/benchmarks docs/superpowers/specs/2026-07-15-local-cv-cover-letter-model-benchmark-design.md
git commit -m "feat(benchmarks): add writing benchmark CLI and reports"
```

---

### Task 7: Build the private Delivery Manager case and run the live benchmark

**Files:**
- Create locally/ignored: `data/benchmarks/tds-delivery-manager/*`
- Create locally/ignored: `data/benchmarks/results/<run-id>/*`
- Modify: `docs/superpowers/plans/2026-07-15-local-cv-cover-letter-model-benchmark.md`

**Interfaces:**
- Consumes: supplied PDF, current reviewed master-CV data, Test Driven Solutions JD, five installed/local candidates.
- Produces: validated private case, 15 attempted repetitions, local report, and evidence-backed recommendation.

- [x] **Step 1: Prepare and review private inputs**

Extract the supplied PDF only to cross-check the existing normalised master CV. Create frozen JD analysis and expected facts from the source data. Validate that every protected metric/entity comes from the source and that unsupported JD skills remain marked as gaps.

- [x] **Step 2: Run the private case validator**

Run: `cd backend && python -m benchmarks.cli validate --case ../data/benchmarks/tds-delivery-manager`

Expected: checksums and all five model IDs print; no inference occurs.

- [x] **Step 3: Run mocked/full repository verification before live inference**

Run:

```bash
cd backend && python -m pytest tests/benchmarks tests/test_services/test_cv_tailor.py tests/test_services/test_cl_generator.py -q --no-cov
cd .. && python3 scripts/check_docs.py
git diff --check
```

Expected: every command exits zero.

- [x] **Step 4: Smoke-test the five local endpoints**

Run: `cd backend && python -m benchmarks.cli smoke --case ../data/benchmarks/tds-delivery-manager`

Expected: all five candidates report available and return a minimal valid completion. If a model is unavailable, record it and continue; do not download an unapproved replacement.

- [x] **Step 5: Run the five-model, three-repetition benchmark**

Run:

```bash
cd backend && python -m benchmarks.cli run \
  --case ../data/benchmarks/tds-delivery-manager \
  --models qwen35-4b,qwen35-9b,qwen3-8b,gemma4-e2b,gemma4-e4b \
  --repetitions 3
```

Expected: the command completes with per-model artifacts even if individual repetitions fail.

- [x] **Step 6: Verify report evidence and data isolation**

Confirm report totals, raw artifacts, prompt/skill hashes, gate findings, rankings, recommendation logic, and limitation text. Compare pre/post SHA-256 hashes for `data/profile.yaml`, `data/jobpilot.db`, and other present Hatch DB files.

- [x] **Step 7: Run full backend verification**

Run:

```bash
cd backend && python -m pytest tests/ -q
cd .. && python3 scripts/check_docs.py
git diff --check
git status --short --untracked-files=all
```

Expected: repository tests and documentation validation pass; private case/results do not appear in Git status.

- [x] **Step 8: Commit plan bookkeeping**

```bash
git add -f docs/superpowers/plans/2026-07-15-local-cv-cover-letter-model-benchmark.md
git commit -m "docs: record local writing benchmark results"
```

