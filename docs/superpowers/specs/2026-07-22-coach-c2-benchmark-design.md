# Coach C2 Model-Quality Benchmark Design

Date: 2026-07-22
Status: Approved for implementation planning
Normative requirements: `docs/implementation-specs/active/Hatch_Coach_Model_Quality_Benchmark_Observability_Codex_Spec_v5.md`, PR C2

## Purpose

PR C2 adds a reproducible Coach model-quality benchmark harness and a committed synthetic v1 suite. The harness must exercise production Coach prompts, parsers, validators, context limits, and provider request shapes while keeping model inputs isolated from personal data and mutable production state.

C2 is one cohesive PR. It supplies contract smoke, live acceptance-smoke, standard, and extended profiles without changing the production model automatically. It does not add the C3 telemetry stack.

## Chosen approach

Add a thin Coach-specific package under `backend/benchmarks/coach/`. Reuse the existing loopback Ollama and llama.cpp adapters where their contracts fit, but keep the completed writing benchmark and its CLI semantics unchanged.

The Coach package owns only Coach-specific suite contracts, production invocation mapping, deterministic validation and scoring, scheduling, reporting, and CLI commands. Model-capability scenarios pass through production Coach boundaries. Deterministic fake adapters are available only to fixtures explicitly classified as `harness_contract`.

### Alternatives not chosen

1. Extending the writing benchmark contracts with Coach variants would create a large tagged-union framework shaped by unrelated document gates and would increase regression risk.
2. Driving every scenario through HTTP and the real database would make stage attribution, deterministic failures, timeouts, and repeatability harder. HTTP/database integration is limited to E2E-01 with a temporary database.
3. Building a generic benchmark framework first would introduce an abstraction before a second stable domain proves it. C2 shares only existing adapters and small utilities that already fit both domains.

## Package boundaries

The implementation will use focused modules with stable interfaces:

- `contracts.py`: strict manifests, fixtures, schedules, attempts, run states, scoring results, and report contracts.
- `suite_loader.py`: fixture loading, hash verification, privacy scanning, cross-file validation, and forced-failure scope enforcement.
- `production_adapter.py`: translation between synthetic benchmark inputs and production Coach service, prompt, parser, validator, and provider boundaries.
- `validators.py`: deterministic stage gates and expected-output checks.
- `scoring.py`: applicable quality dimensions, qualification calculations, calibration, and ranking inputs.
- `runner.py`: immutable schedule construction, execution, timeouts, incremental persistence, protected-state checks, and resume.
- `reporting.py`: machine-readable and human-readable evidence without sensitive payloads or unsupported conclusions.
- `cli.py`, `__main__.py`: separate Coach validate, smoke, run, resume, and report entry points.
- `fixtures/v1/`: the committed fictional candidate, job, research bundle, model manifest, and scenario fixtures required by v5.

The existing `python -m benchmarks` writing commands retain their current meaning. Coach commands use `python -m benchmarks.coach`.

## Suite and contract rules

All suite models use strict validation with unknown fields rejected. The committed suite is synthetic and must not contain the owner's identity, CV, employers, contact details, recordings, applications, secrets, or absolute protected paths. Stable input hashes are part of run identity.

Every scenario declares `qualification_scope` as either `model_capability` or `harness_contract`. Any fixture that selects a forced timeout, unavailable provider, malformed output, parser exhaustion, or other fake-adapter failure must be `harness_contract`. The mandatory AE-H01, AE-H02, and SR-02 fixtures must use that scope. Validation rejects a manufactured failure labelled as model capability.

Expected fields and scoring metadata are stage-specific. Empty scoring denominators are represented as not applicable and excluded from score normalisation; they are never silently converted to zero.

## Profiles and scheduling

Profile definitions own scenario selection, repetitions, and default timeout budgets. CLI overrides are accepted only within the documented bounds.

- Contract smoke uses deterministic adapters, exercises every scenario validator, emits no recommendation, and must complete within the v5 CI budget.
- Acceptance smoke schedules exactly the six live core scenarios once per selected model, executes models sequentially, and cannot rank or select a model.
- Standard schedules the full v1 suite twice per selected model and produces qualification/ranking evidence suitable for human review.
- Extended schedules three repetitions and may add reviewed private cases from the ignored data area.

The schedule is materialised and persisted before inference. Each attempt has a stable identity derived from the run, model, scenario, repetition, and attempt kind. With two standard repetitions, the schedule contains exactly two SR-01 model-capability direct-report attempts and two SR-02 harness-contract direct-report attempts. E2E-01 contributes a separate model-capability `session_report` attempt only when its terminal report stage is reached.

## Execution flow

1. Validate the manifest, fixtures, privacy rules, hashes, scenario scopes, and model endpoints.
2. Resolve the profile, selected models, scenarios, repetitions, timeout values, and retry policy into an immutable schedule.
3. Capture hashes for protected databases, profile/configuration files, and other v5-protected state.
4. Execute each scheduled attempt. Model-capability scenarios use the selected live model through the production adapter. Harness-contract scenarios use only their declared deterministic failure adapter. E2E-01 uses production Coach services and a temporary database.
5. Run deterministic gates before quality scoring. Ineligible attempts retain gate evidence but do not enter quality denominators.
6. Atomically persist each terminal attempt and bounded partial state as execution progresses.
7. Aggregate model capability independently from harness integrity, apply run-state precedence, and compare protected-state hashes.
8. Render bounded JSON and Markdown reports from persisted evidence.

Official comparisons use the fixed company-research source bundle and never call live retrieval. Synthetic transcript, speech, and video metrics validate downstream contracts; C2 does not rank ASR or browser perception providers.

## Persistence and resume

Run metadata, the immutable schedule, attempt artifacts, aggregate output, and reports live in a run directory. Writes use a temporary sibling followed by atomic replacement so interruption cannot expose a partially written terminal artifact.

Resume requires matching suite hashes, profile, selected models, schedule identity, and relevant harness version. It skips terminal attempts and continues unscheduled or non-terminal work. Timed-out attempts remain terminal unless `--retry-timeouts` is supplied. Restart alone never authorises a retry.

A per-call timeout records the affected attempt and permits later attempts to continue. A per-model timeout records remaining work for that model without stopping later models. A whole-run deadline or process interruption flushes completed and bounded partial evidence before exit and does not start more work.

## Failure classification

Natural live-model timeout, unavailability, malformed output, or contract failure remains model-capability evidence for that model. It does not invalidate the harness.

A terminal harness-contract attempt that fails its declared deterministic expectation sets `invalid_harness_integrity`. A scheduled harness-contract attempt that never starts or never reaches a terminal state because of a deadline or interruption contributes only to the applicable incomplete state.

Prohibited content, secret leakage, absolute protected paths, invalid manifests, or protected-state mutation set `invalid_harness_privacy` or `invalid_harness_integrity`. Invalid harness runs expose only bounded diagnostics and produce no model capability classification or ranking.

Run state uses this exact precedence:

1. `invalid_harness_privacy`
2. `invalid_harness_integrity`
3. `incomplete_deadline`
4. `incomplete_interrupted`
5. `completed_with_model_outcomes`
6. `completed`

Unavailable or invalid evaluations retain empty scores and a null overall score. No report may represent them as completed numeric evaluations.

## Scoring and reporting

`model_capability` attempts alone contribute to model success, degradation, timeout/unavailable, optional-stage, quality, calibration, and ranking denominators. `harness_contract` attempts contribute only to harness-integrity and fallback-fidelity evidence.

Safety-critical gates disqualify the affected model according to v5. Stage gates determine attempt eligibility. Applicable quality dimensions are normalised only over dimensions with a real denominator. Reports expose scheduled and completed counts, exclusions, gates, per-stage evidence, incomplete work, runtime outcomes, protected-state results, and harness diagnostics.

Acceptance smoke reports execution outcomes but never emits a ranking, recommendation, default-model decision, or configuration change. Standard evidence can support a decision only after two independent standard runs and an explicit human/owner decision outside the harness.

## Test strategy

Unit tests cover strict contracts, privacy rules, hashes, forced-failure scope enforcement, production-adapter mapping, validators, gate eligibility, dimension applicability, aggregation, and report rendering.

Runner tests use deterministic adapters and a controllable clock to verify:

- exact profile schedules and repetition counts;
- SR-01, SR-02, and E2E-01 accounting;
- incremental and atomic artifacts;
- per-call, per-model, and whole-run timeout behaviour;
- interruption flushing and resume identity;
- explicit timeout retry;
- complete separation of model and harness denominators;
- exact run-state precedence;
- protected-state immutability;
- suppression of classification/ranking for invalid harness runs.

Contract smoke exercises every scenario validator without live inference and stays inside the specified CI budget. E2E-01 runs a three-question production Coach workflow against a temporary database. CLI tests cover all required commands, profiles, validation errors, exit codes, resume, and reporting. Regression tests verify that the existing writing benchmark remains unchanged.

Final PR verification includes the full backend test suite, changed-file Ruff checks, frontend type-check, fixture/privacy validation, contract smoke, and acceptance smoke against installed loopback models. A live model may terminate as timed out or unavailable while still satisfying acceptance evidence requirements, provided artifacts and classifications are correct.

## Acceptance boundary

C2 is ready for review when the committed synthetic v1 suite validates; contract smoke passes within budget; acceptance smoke reaches a terminal or explicit outcome for each selected local model; partial and resumed runs preserve evidence; model and harness denominators remain separate; protected hashes are unchanged; invalid harness semantics suppress model conclusions; existing writing benchmark behaviour is intact; and no command selects or mutates the production model.

## Out of scope

- C3 OpenTelemetry instrumentation, collector configuration, and telemetry privacy gates.
- Automatic production-model selection or configuration mutation.
- Live company-research freshness as model-ranking evidence.
- ASR, browser perception, or multimodal-provider ranking.
- Refactoring the writing benchmark into a generic framework.
