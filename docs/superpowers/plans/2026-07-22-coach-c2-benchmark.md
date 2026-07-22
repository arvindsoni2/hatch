# Coach C2 Model-Quality Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v5 Coach benchmark harness, committed synthetic v1 suite, deterministic scoring/classification, resumable artifacts, and separate Coach CLI without changing model configuration.

**Architecture:** Add a focused `backend/benchmarks/coach/` package that reuses `ModelSpec` and `BenchmarkLLMClient` while leaving the writing benchmark unchanged. Model-capability scenarios invoke production Coach services with synthetic inputs; forced failures are isolated as harness-contract attempts. Every checkpoint is committed with its completed plan checkboxes so Git is the durable resume ledger.

**Tech Stack:** Python 3.14, Pydantic v2, asyncio, Decimal, SQLAlchemy/aiosqlite, pytest/pytest-asyncio, existing Coach production services, existing loopback benchmark adapters.

## Global Constraints

- The normative source is `docs/implementation-specs/active/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md`, PR C2.
- Add Coach commands only under `python -m benchmarks.coach`; do not change existing `python -m benchmarks` command meanings.
- Reuse production prompts, prompt catalogue metadata, parsers, validators, context budgets, request shapes, and safe no-think adapter behaviour.
- Only `qualification_scope=model_capability` enters model success, gate, quality, calibration, variance, timeout, or ranking denominators.
- Any manufactured adapter failure must be `qualification_scope=harness_contract`; AE-H01, AE-H02, and SR-02 are mandatory harness-contract fixtures.
- Acceptance smoke contains exactly QG-01, MA-01, MA-02, AE-01, AE-02, and SR-01 once per model and cannot rank, recommend, select, or configure a model.
- Standard uses two repetitions. It schedules exactly two direct SR-01 model attempts and two direct SR-02 harness attempts; reached E2E-01 reports are additional model attempts.
- Timeout defaults are acceptance `600/3600/18000`, standard `900/10800/54000`, and extended `1200/21600/108000` seconds for per-call/per-model/whole-run.
- Completion precedence is privacy invalid, integrity invalid, deadline incomplete, interrupted incomplete, completed with model outcomes, then completed.
- Percentages and thresholds use unrounded `Decimal`; display uses one decimal with `ROUND_HALF_UP`. Empty denominators are not applicable.
- Official model endpoints are loopback. Public fixtures are fictional. Service-level attempts do not mutate production databases or profiles. E2E-01 uses temporary paths and a temporary database.
- C2 does not add C3 telemetry infrastructure and does not implement automatic model selection.
- After every task, update the task checkbox and the Checkpoint Ledger, then include those plan changes in the task commit.

## File Structure

- Create `backend/benchmarks/coach/contracts.py`: strict suite, scenario, schedule, attempt, metric, capability, and run-summary contracts.
- Create `backend/benchmarks/coach/profiles.py`: locked profile scenario/repetition/timeout definitions and bounded overrides.
- Create `backend/benchmarks/coach/suite_loader.py`: fixture loading, hash/privacy validation, and cross-fixture invariants.
- Create `backend/benchmarks/coach/production_adapter.py`: synthetic-input calls into production Coach services and deterministic harness adapters.
- Create `backend/benchmarks/coach/validators.py`: stage contract gates and output extraction.
- Create `backend/benchmarks/coach/scoring.py`: common primitives, stage formulas, qualification, classification, and ranking.
- Create `backend/benchmarks/coach/artifacts.py`: atomic writes, protected hashes, run identity, and privacy scans.
- Create `backend/benchmarks/coach/runner.py`: scheduling, execution, timeouts, resume, and state aggregation.
- Create `backend/benchmarks/coach/reporting.py`: bounded JSON/Markdown report generation.
- Create `backend/benchmarks/coach/cli.py`, `__main__.py`, and `__init__.py`: Coach-only commands.
- Create `backend/benchmarks/coach/fixtures/v1/`: manifests, synthetic evidence/job/research inputs, stopwords, and all v5 scenario files.
- Create `backend/tests/benchmarks/coach/`: tests matching the module boundaries above.
- Modify `docs/development/TESTING.md`: Coach benchmark commands, profile meaning, and live-smoke expectations.
- Modify the v5 spec only if implementation discovers a necessary clarification; never relax an accepted requirement.

---

### Task 1: Strict contracts and locked profiles

**Files:**
- Create: `backend/benchmarks/coach/__init__.py`
- Create: `backend/benchmarks/coach/contracts.py`
- Create: `backend/benchmarks/coach/profiles.py`
- Test: `backend/tests/benchmarks/coach/test_contracts.py`
- Test: `backend/tests/benchmarks/coach/test_profiles.py`

**Interfaces:**
- Consumes: `benchmarks.contracts.StrictModel`, `benchmarks.contracts.ModelSpec`.
- Produces: `CoachSuite`, `CoachScenario`, `ScheduleEntry`, `ScenarioResult`, `FractionMetric`, `CapabilityResult`, `CoachRunSummary`, `profile_for(name)`.

- [x] **Step 1: Write failing contract/profile tests**

```python
def test_scenario_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CoachScenario.model_validate({**valid_scenario(), "unknown": True})

def test_standard_profile_is_locked() -> None:
    profile = profile_for("standard")
    assert profile.repetitions == 2
    assert (profile.call_timeout_seconds, profile.model_timeout_seconds, profile.run_timeout_seconds) == (900, 10800, 54000)
    assert profile.allow_ranking is True

def test_acceptance_profile_has_exact_core_scenarios() -> None:
    assert profile_for("acceptance-smoke").scenario_ids == (
        "qg_01_requirement_coverage", "ma_01_supported_star", "ma_02_insufficient_evidence",
        "ae_01_strong_answer", "ae_02_weak_answer", "sr_01_mixed_session_report",
    )
```

- [x] **Step 2: Run tests and verify import/contract failures**

Run: `cd backend && pytest --no-cov -q tests/benchmarks/coach/test_contracts.py tests/benchmarks/coach/test_profiles.py`

Expected: collection fails because `benchmarks.coach.contracts` and `profiles` do not exist.

- [x] **Step 3: Implement strict types and profiles**

Use explicit literals for stages, scopes, terminal statuses, completion states, and capability classifications. Represent every percentage as numerator, denominator, exact decimal string, and one-decimal display:

```python
class FractionMetric(StrictModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    exact: str | None
    display: str

class CoachScenario(StrictModel):
    scenario_id: str = Field(min_length=1)
    stage: CoachStage
    description: str = Field(min_length=1)
    qualification_scope: Literal["model_capability", "harness_contract"]
    input: dict[str, Any]
    expected: ScenarioExpected
    scoring: ScenarioScoring
    quality_dimensions: list[str]
    acceptance_smoke: bool = False
    forced_failure: ForcedFailureMode | None = None

class CoachProfile(StrictModel):
    name: Literal["contract-smoke", "acceptance-smoke", "standard", "extended"]
    repetitions: int = Field(ge=1, le=3)
    scenario_ids: tuple[str, ...] | None
    call_timeout_seconds: int
    model_timeout_seconds: int
    run_timeout_seconds: int
    allow_ranking: bool
```

Bound CLI overrides to positive values no greater than the profile defaults unless a named extended profile is selected.

- [x] **Step 4: Run focused tests**

Run: `cd backend && pytest --no-cov -q tests/benchmarks/coach/test_contracts.py tests/benchmarks/coach/test_profiles.py`

Expected: all tests pass.

- [x] **Step 5: Commit checkpoint C2.1**

Commit: `feat(coach-benchmark): add strict contracts and profiles`

### Task 2: Committed synthetic suite and privacy-validating loader

**Files:**
- Create: `backend/benchmarks/coach/suite_loader.py`
- Create: `backend/benchmarks/coach/fixtures/stopwords_en.txt`
- Create: `backend/benchmarks/coach/fixtures/v1/suite.json`
- Create: `backend/benchmarks/coach/fixtures/v1/models.json`
- Create: `backend/benchmarks/coach/fixtures/v1/candidate_evidence.json`
- Create: `backend/benchmarks/coach/fixtures/v1/job_description.txt`
- Create: `backend/benchmarks/coach/fixtures/v1/company_research.json`
- Create: `backend/benchmarks/coach/fixtures/v1/company_research_sources.json`
- Create: all v5 files under `backend/benchmarks/coach/fixtures/v1/scenarios/`, including AE-H01, AE-H02, SR-02, and E2E-01.
- Test: `backend/tests/benchmarks/coach/test_suite_loader.py`
- Test: `backend/tests/benchmarks/coach/test_fixture_contract.py`

**Interfaces:**
- Consumes: Task 1 `CoachSuite`, `CoachScenario`, and `ModelSpec`.
- Produces: `load_suite(path: Path) -> LoadedCoachSuite`, `hash_file(path) -> str`, `scan_public_value(value) -> list[PrivacyFinding]`.

- [x] **Step 1: Write failing loader/privacy tests**

```python
def test_v1_suite_loads_and_records_every_hash() -> None:
    suite = load_suite(V1_FIXTURE_DIR)
    assert suite.manifest.version == "1"
    assert set(suite.input_hashes) == set(suite.declared_files)
    assert len(suite.scenarios) >= 17

@pytest.mark.parametrize("scenario_id", ["ae_h01_provider_unavailable", "ae_h02_malformed_output", "sr_02_provider_fallback"])
def test_forced_failure_fixtures_are_harness_contract(scenario_id: str) -> None:
    assert load_suite(V1_FIXTURE_DIR).scenario(scenario_id).qualification_scope == "harness_contract"

def test_forced_failure_cannot_be_model_capability(tmp_path: Path) -> None:
    fixture = copied_suite(tmp_path)
    rewrite_scope(fixture, "ae_h01_provider_unavailable", "model_capability")
    with pytest.raises(SuiteValidationError, match="forced failure"):
        load_suite(fixture)
```

- [x] **Step 2: Run tests and verify missing-loader failures**

Run: `cd backend && pytest --no-cov -q tests/benchmarks/coach/test_suite_loader.py tests/benchmarks/coach/test_fixture_contract.py`

Expected: tests fail because loader and v1 fixtures do not exist.

- [x] **Step 3: Implement fictional inputs and all scenario metadata**

Use a fictional candidate with two roles, explicit STAR evidence IDs, immutable numbers, skills, education/certification, and one unsupported competency. Include six-to-eight JD requirements, an employer-context number, and malicious embedded instructions. Fixed research facts must refer only to allowed source IDs.

- [x] **Step 4: Implement strict loading, hashes, privacy, and cross-file validation**

```python
def load_suite(path: Path | str) -> LoadedCoachSuite:
    root = Path(path).resolve()
    manifest = CoachSuite.model_validate_json((root / "suite.json").read_text())
    loaded = {item.path: _read_declared(root, item.path, item.sha256) for item in manifest.files}
    scenarios = tuple(CoachScenario.model_validate(value) for value in _scenario_values(loaded))
    _validate_unique_ids(scenarios)
    _validate_forced_failure_scopes(scenarios)
    findings = scan_public_value(loaded)
    if findings:
        raise SuitePrivacyError(_bounded_privacy_message(findings))
    return LoadedCoachSuite(manifest=manifest, scenarios=scenarios, input_hashes=_hashes(root, manifest.files), root=root)
```

Reject undeclared files, missing files, hash mismatches, duplicate IDs, non-loopback endpoints, absolute paths, secret-like keys/headers/tokens, known private identity markers, and stage-inapplicable fixture fields.

- [x] **Step 5: Run focused suite tests and validation**

Run: `cd backend && pytest --no-cov -q tests/benchmarks/coach/test_suite_loader.py tests/benchmarks/coach/test_fixture_contract.py`

Expected: all tests pass and the committed suite loads with stable hashes.

- [x] **Step 6: Commit checkpoint C2.2**

Commit: `feat(coach-benchmark): add synthetic v1 suite`

### Task 3: Production service adapter and deterministic harness failures

**Files:**
- Create: `backend/benchmarks/coach/production_adapter.py`
- Test: `backend/tests/benchmarks/coach/test_production_adapter.py`
- Test: `backend/tests/benchmarks/coach/test_harness_adapters.py`

**Interfaces:**
- Consumes: `BenchmarkLLMClient`, loaded scenarios, `QuestionGeneratorService`, `ModelAnswerGeneratorService`, `AnswerEvaluatorService`, `CompanyResearchService`, `RubricSynthesiserService`, `FeedbackGeneratorService`, and `TechnicalDrillsService`.
- Produces: `CoachProductionAdapter.execute(scenario: CoachScenario, client: object, context: ScenarioContext) -> StageExecution` and `HarnessFailureClient.complete_json(system: str, user: str, max_tokens: int = 4096, schema: type[BaseModel] | None = None) -> dict[str, Any]`.

- [x] **Step 1: Write failing adapter tests**

```python
@pytest.mark.asyncio
async def test_question_generation_uses_production_service(monkeypatch: pytest.MonkeyPatch) -> None:
    called = AsyncMock(return_value=valid_question_result())
    monkeypatch.setattr(QuestionGeneratorService, "generate", called)
    result = await adapter().execute(qg_scenario(), fake_live_client(), context())
    assert result.diagnostic.stage == "question_generation"
    called.assert_awaited_once()

@pytest.mark.asyncio
async def test_ae_h02_exhausts_production_parse_path() -> None:
    result = await adapter().execute(ae_h02(), HarnessFailureClient("malformed_output"), context())
    assert result.output["evaluation_state"] == "invalid"
    assert result.output["scores"] == {}
    assert result.output["overall"] is None
    assert "coach_evaluation_schema_invalid" in result.gate_codes
```

- [x] **Step 2: Run tests and verify missing-adapter failures**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_production_adapter.py tests/benchmarks/coach/test_harness_adapters.py`

- [x] **Step 3: Implement service-compatible live and forced-failure clients**

`BenchmarkLLMClient` remains the live client. Add deterministic modes `provider_unavailable`, `timeout`, and `malformed_output`; do not add random behaviour. Patch fixed company-research retrieval at the `_scrape_company_info` boundary. Inject synthetic candidate summary at its production loader boundary rather than writing profile files. Adapt rubric synthesis through a small LangChain-compatible wrapper whose `ainvoke` delegates to the benchmark client.

- [x] **Step 4: Implement one dispatcher per production stage**

```python
class CoachProductionAdapter:
    async def execute(self, scenario: CoachScenario, client: object, context: ScenarioContext) -> StageExecution:
        handler = self._handlers[scenario.stage]
        return await handler(scenario, client, context)
```

Each handler returns the production output plus production `CoachDiagnostic`, prompt metadata, attempts, repairs, observations, and bounded synthetic output. It must not reinterpret a production failure as success.

- [x] **Step 5: Run adapter and existing Coach contract tests**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_production_adapter.py tests/benchmarks/coach/test_harness_adapters.py tests/test_services/test_coach_contracts.py tests/test_services/test_coach_prompt_contracts.py`

- [x] **Step 6: Commit checkpoint C2.3**

Commit: `feat(coach-benchmark): invoke production Coach stages`

### Task 4: Deterministic gates and exact stage scoring

**Files:**
- Create: `backend/benchmarks/coach/validators.py`
- Create: `backend/benchmarks/coach/scoring.py`
- Test: `backend/tests/benchmarks/coach/test_validators.py`
- Test: `backend/tests/benchmarks/coach/test_scoring_primitives.py`
- Test: `backend/tests/benchmarks/coach/test_stage_scoring.py`

**Interfaces:**
- Consumes: Task 3 `StageExecution`, Task 1 scoring metadata.
- Produces: `validate_execution(scenario: CoachScenario, execution: StageExecution) -> ValidationResult`, `score_execution(scenario: CoachScenario, execution: StageExecution, validation: ValidationResult) -> ScenarioScore`, `fraction_metric(numerator: int, denominator: int) -> FractionMetric`, and exact Decimal aggregate helpers.

- [x] **Step 1: Write table-driven failing tests for every hard gate and formula**

Cover all seven stages, expected withholding, unexpected empty answers, prompt injection, immutable numbers, unknown evidence/source IDs, report/rubric score mutation, unavailable evaluation no-score state, N/A dimensions, word budgets, actionability, readability, calibration, and half-up rounding.

```python
def test_fraction_uses_unrounded_decimal_and_half_up_display() -> None:
    metric = fraction_metric(2, 3)
    assert metric.exact == str(Decimal(2) / Decimal(3))
    assert metric.display == "66.7"

def test_na_dimension_is_excluded_from_weight_normalisation() -> None:
    score = weighted_stage_score({"grounding": (Decimal("80"), Decimal("0.6")), "tradeoff": (None, Decimal("0.4"))})
    assert score == Decimal("80.0")
```

- [x] **Step 2: Run tests and verify missing-validator/scorer failures**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_validators.py tests/benchmarks/coach/test_scoring_primitives.py tests/benchmarks/coach/test_stage_scoring.py`

- [x] **Step 3: Implement shared deterministic primitives**

Use NFKC, lowercase, whitespace collapse, punctuation stripping with evidence-ID preservation, committed stopwords, exact term groups, Decimal precision/recall, word budget, actionability, readability, weighted normalisation, and one-decimal `ROUND_HALF_UP` output. No embeddings, judge model, or semantic heuristic may affect official scores.

- [x] **Step 4: Implement stage gates and formulas exactly from v5 sections 12 and 13**

Return `ScenarioScore(eligible=False, quality_score=None)` for a blocking gate. Correct expected withholding gets scenario quality 100 with prose dimensions absent. Deterministic fallback reports receive fidelity/prioritisation/actionability scores but not model narrative success.

- [x] **Step 5: Run all focused scoring tests**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_validators.py tests/benchmarks/coach/test_scoring_primitives.py tests/benchmarks/coach/test_stage_scoring.py`

- [x] **Step 6: Commit checkpoint C2.4**

Commit: `feat(coach-benchmark): add deterministic gates and scoring`

### Task 5: Immutable scheduling, atomic artifacts, timeouts, and resume

**Files:**
- Create: `backend/benchmarks/coach/artifacts.py`
- Create: `backend/benchmarks/coach/runner.py`
- Test: `backend/tests/benchmarks/coach/test_artifacts.py`
- Test: `backend/tests/benchmarks/coach/test_schedule.py`
- Test: `backend/tests/benchmarks/coach/test_runner.py`
- Test: `backend/tests/benchmarks/coach/test_resume.py`

**Interfaces:**
- Consumes: loaded suite, profile, production adapter, validators/scorer.
- Produces: `build_schedule(suite: LoadedCoachSuite, profile: CoachProfile, model_ids: Sequence[str]) -> tuple[ScheduleEntry, ...]`, `run_benchmark(request: RunRequest, dependencies: RunnerDependencies | None = None) -> CoachRunSummary`, `resume_benchmark(run_dir: Path, retry_timeouts: bool = False, dependencies: RunnerDependencies | None = None) -> CoachRunSummary`, and atomic artifact files beneath the configured output root.

- [x] **Step 1: Write failing schedule/artifact tests**

```python
def test_standard_two_repetitions_schedule_exact_direct_reports() -> None:
    schedule = build_schedule(suite(), profile_for("standard"), ["qwen35-4b"])
    assert count(schedule, "sr_01_mixed_session_report", "model_capability") == 2
    assert count(schedule, "sr_02_provider_fallback", "harness_contract") == 2

def test_atomic_json_never_exposes_partial_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "progress.json"
    atomic_write_json(target, {"state": "old"})
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("stop")))
    with pytest.raises(OSError):
        atomic_write_json(target, {"state": "new"})
    assert json.loads(target.read_text()) == {"state": "old"}
```

- [x] **Step 2: Write failing timeout/resume tests with a controllable executor**

Prove per-call, per-model, and whole-run deadline outcomes; later models continue after model timeout; interruption flushes; terminal attempts are skipped; timed-out attempts retry only with `retry_timeouts=True`; run identity mismatch is rejected.

- [x] **Step 3: Run tests and verify missing-runner failures**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_artifacts.py tests/benchmarks/coach/test_schedule.py tests/benchmarks/coach/test_runner.py tests/benchmarks/coach/test_resume.py`

- [x] **Step 4: Implement manifest/protected-state and atomic persistence**

Hash fixture inputs, relevant prompts/skills, profile/configuration, protected database including SQLite WAL/SHM, git state, and sanitized endpoint metadata. Write manifest, run manifest, progress, scenario result, summary, aggregate, and report through sibling temporary files and `os.replace`.

Define the runner boundary explicitly so tests can inject adapters and clocks without patching production globals:

```python
@dataclass(frozen=True)
class RunnerDependencies:
    adapter_factory: Callable[[ModelSpec, int], AsyncContextManager[object]]
    production_adapter: CoachProductionAdapter
    monotonic: Callable[[], float] = time.monotonic

class RunRequest(StrictModel):
    suite_path: Path
    output_root: Path
    profile_name: Literal["contract-smoke", "acceptance-smoke", "standard", "extended"]
    model_ids: tuple[str, ...]
    command: str
```

- [x] **Step 5: Implement sequential execution and deterministic state precedence**

Persist the full schedule before model calls. Execute model groups sequentially. Record all typed failures as attempt results. On model/run deadline, mark affected scheduled work incomplete without manufacturing harness failure. On cancellation/interrupt, shield the final flush and re-raise after persistence.

- [x] **Step 6: Run focused runner tests**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_artifacts.py tests/benchmarks/coach/test_schedule.py tests/benchmarks/coach/test_runner.py tests/benchmarks/coach/test_resume.py`

- [x] **Step 7: Commit checkpoint C2.5**

Commit: `feat(coach-benchmark): add resumable benchmark runner`

### Task 6: Capability classification and locked ranking

**Files:**
- Modify: `backend/benchmarks/coach/scoring.py`
- Test: `backend/tests/benchmarks/coach/test_capability.py`
- Test: `backend/tests/benchmarks/coach/test_ranking.py`

**Interfaces:**
- Consumes: terminal `ScenarioResult` records.
- Produces: `classify_model(model_id, results, run_state) -> CapabilityResult` and `rank_models(capabilities) -> list[CapabilityResult]`.

- [x] **Step 1: Write failing denominator/minimum-evidence tests**

Cover exact model/harness separation, 80% core validity, four core attempts, eight answer-evaluation calibration attempts, two SR-01 attempts, two terminal SR-02 attempts, four optional attempts, expected withholding, successful repair, reached E2E reports, and inconclusive evidence.

- [x] **Step 2: Write failing threshold/ranking tests**

Test exact fractions at 95%, 90%, 80%, MAE 1.5, timeout 5%, optional 90%, safety failure, model/fallback report fidelity, median core quality, calibration, population variance, repair rate, latency, and model-ID tie-break. Prove optional judge fields cannot change classification or order.

- [x] **Step 3: Run tests and verify failures**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_capability.py tests/benchmarks/coach/test_ranking.py`

- [x] **Step 4: Implement exact aggregation and classification**

Use raw `Decimal` numerator/denominator values for every threshold. Invalid/incomplete runs produce no model classification. Rank only `coach_capable` then `coach_capable_with_optional_degradation` using the exact eight-key lexicographic order in v5 section 14.4.

- [x] **Step 5: Run capability/ranking tests**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_capability.py tests/benchmarks/coach/test_ranking.py`

- [x] **Step 6: Commit checkpoint C2.6**

Commit: `feat(coach-benchmark): classify and rank model capability`

### Task 7: Privacy-safe reporting and Coach CLI

**Files:**
- Create: `backend/benchmarks/coach/reporting.py`
- Create: `backend/benchmarks/coach/cli.py`
- Create: `backend/benchmarks/coach/__main__.py`
- Test: `backend/tests/benchmarks/coach/test_reporting.py`
- Test: `backend/tests/benchmarks/coach/test_cli.py`

**Interfaces:**
- Consumes: suite loader, runner/resume, summary/capability types.
- Produces: `render_report(summary)`, `write_report(summary, path)`, `build_parser()`, and `main(argv) -> int`.

- [ ] **Step 1: Write failing report/CLI tests**

Cover `validate`, `smoke`, `run --profile`, `run --resume`, `--retry-timeouts`, `report`; invalid arguments; bounded timeout overrides; terminal exit codes; no secrets/absolute paths; exact counts/fractions/exclusions; and acceptance output without ranking/recommendation.

```python
def test_acceptance_report_cannot_recommend_model() -> None:
    report = render_report(acceptance_summary())
    assert "recommended_model" not in report
    assert "model change" not in report.casefold()

def test_existing_writing_parser_is_unchanged() -> None:
    assert benchmarks.cli.build_parser().parse_args(["smoke", "--case", "x"]).command == "smoke"
```

- [ ] **Step 2: Run tests and verify missing-report/CLI failures**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_reporting.py tests/benchmarks/coach/test_cli.py tests/benchmarks/test_cli.py`

- [ ] **Step 3: Implement bounded reports and CLI dispatch**

Reports include schedule/terminal counts, run state, harness validity, protected hashes, stage metrics, raw fractions plus display values, gates, exclusions, classifications, ranking when allowed, and artifact paths. Redact raw private payloads and never print auth headers or absolute protected paths.

- [ ] **Step 4: Run report/CLI regressions**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_reporting.py tests/benchmarks/coach/test_cli.py tests/benchmarks/test_cli.py`

- [ ] **Step 5: Commit checkpoint C2.7**

Commit: `feat(coach-benchmark): add reports and Coach CLI`

### Task 8: Contract smoke and temporary-database E2E-01

**Files:**
- Modify: `backend/benchmarks/coach/production_adapter.py`
- Modify: `backend/benchmarks/coach/runner.py`
- Test: `backend/tests/benchmarks/coach/test_contract_smoke.py`
- Test: `backend/tests/benchmarks/coach/test_e2e_session.py`
- Test: `backend/tests/benchmarks/coach/test_harness_integrity.py`

**Interfaces:**
- Consumes: all prior C2 components and production `CoachService`/repositories.
- Produces: deterministic contract-smoke execution and E2E-01 terminal report evidence.

- [ ] **Step 1: Write failing contract-smoke coverage tests**

Assert every committed scenario reaches its validator with deterministic adapters; all harness expectations pass; contract smoke emits no model classification/recommendation; and the test command is bounded by the 90-second product requirement.

- [ ] **Step 2: Write failing E2E-01 and integrity tests**

Create a temporary database/data directory, run a three-question session with strong, weak, and skipped answers, assert persisted rubric/report/counts/follow-up focus, and verify protected production hashes before/after. Prove terminal SR-02/AE-H expectation failure invalidates the harness while an unstarted harness attempt selects incomplete state.

- [ ] **Step 3: Run tests and verify incomplete integration failures**

Run: `cd backend && pytest -q tests/benchmarks/coach/test_contract_smoke.py tests/benchmarks/coach/test_e2e_session.py tests/benchmarks/coach/test_harness_integrity.py`

- [ ] **Step 4: Implement contract-smoke and isolated E2E execution**

Use the same adapter/validator path as live runs. For E2E-01, override database and data roots before importing/constructing database-bound services, migrate/create schema in the temporary database, and restore environment/config state in `finally`. E2E contributes a session-report model attempt only after terminal report persistence.

- [ ] **Step 5: Run contract/E2E plus focused benchmark suite**

Run: `cd backend && pytest -q tests/benchmarks tests/benchmarks/coach`

Expected: existing writing and new Coach benchmark tests all pass.

- [ ] **Step 6: Commit checkpoint C2.8**

Commit: `test(coach-benchmark): prove contract and E2E smoke`

### Task 9: Documentation, live acceptance evidence, and full verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/development/TESTING.md`
- Modify if clarification is required: `docs/implementation-specs/active/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md`
- Update: `docs/superpowers/plans/2026-07-22-coach-c2-benchmark.md`

**Interfaces:**
- Consumes: completed C2 CLI and artifacts.
- Produces: reproducible operator commands, final artifact paths, and merge-ready evidence.

- [ ] **Step 1: Document validation, smoke, live profiles, resume, and reports**

Include exact commands, timeout semantics, explicit model outcomes, no-selection rule, private-suite location, protected-state rules, and the two-independent-standard-run decision boundary.

- [ ] **Step 2: Run static and focused verification**

Run:

```bash
cd backend
ruff check benchmarks/coach tests/benchmarks/coach
pytest -q tests/benchmarks tests/benchmarks/coach
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/v1
python -m benchmarks.coach smoke --suite benchmarks/coach/fixtures/v1
```

Expected: all commands exit zero; contract smoke produces a run directory and no recommendation.

Add a separate post-install CI step that runs the Coach contract smoke through `timeout 180s`, so dependency installation is outside the 180-second boundary while the harness enforces its own 90-second completion requirement.

- [ ] **Step 3: Run full repository regression**

Run:

```bash
cd backend && python -m pytest
cd ../frontend && npm run type-check
```

Expected: backend suite and frontend type-check pass with no new failures.

- [ ] **Step 4: Discover installed loopback models and run acceptance smoke**

Use the committed model manifest and local runtime health. Run one or more installed models sequentially:

```bash
cd backend
python -m benchmarks.coach run --suite benchmarks/coach/fixtures/v1 --models qwen35-4b --profile acceptance-smoke
```

Expected: each selected model reaches a terminal success, timeout, unavailable, invalid, or failed outcome; later models are not stalled; protected hashes match; no recommendation/model mutation is emitted.

- [ ] **Step 5: Audit artifacts and repository state**

List changed files, behavioural changes, focused/full test outputs, run directories, completion states, exact hashes, and `git status`. Confirm no secrets, absolute protected paths, private data, generated run artifacts, or Graphify scratch outputs are staged.

- [ ] **Step 6: Commit checkpoint C2.9**

Commit: `docs(coach-benchmark): document and verify C2 harness`

- [ ] **Step 7: Request independent code review before merge**

Use the requesting-code-review workflow against the exact final C2 commit, address important findings test-first, and rerun verification before declaring the PR merge-ready.

## Checkpoint Ledger

- [x] C2.0 Design approved and committed: `036cd8d`
- [x] C2.1 Strict contracts and profiles
- [x] C2.2 Synthetic suite and loader
- [x] C2.3 Production adapter
- [x] C2.4 Gates and scoring
- [x] C2.5 Runner and resume
- [x] C2.6 Capability and ranking
- [ ] C2.7 Reporting and CLI
- [ ] C2.8 Contract/E2E smoke
- [ ] C2.9 Documentation and verification
