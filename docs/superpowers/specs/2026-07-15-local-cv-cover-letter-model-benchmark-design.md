# Local CV and Cover-Letter Model Benchmark Design

**Date:** 2026-07-15  
**Status:** Approved design, pending implementation plan  
**Scope:** A reusable, fully automatic benchmark for Hatch CV-tailoring and cover-letter generation on the current local machine.

## Goal

Build a reproducible benchmark that measures how well locally available language models perform in Hatch's real CV-tailoring and cover-letter generation paths. The benchmark must determine whether observed weaknesses are best addressed by retaining the current model, changing prompts or skills, or changing the primary model.

The first benchmark case uses the supplied two-page master CV and the Test Driven Solutions Delivery Manager job description. The harness must support additional private cases later without committing personal data.

## Constraints

- Run entirely on the current machine; no cloud providers, API keys, or network-hosted inference.
- Use fully automatic evaluation. Do not use an LLM-as-judge or claim to measure subjective persuasiveness as ground truth.
- Exercise the real `CVTailor` and `CoverLetterGenerator` components and their prompt/skill injection.
- Freeze the JD analysis per case so the benchmark isolates writing performance rather than conflating it with JD extraction quality.
- Do not mutate `data/profile.yaml`, application records, or the normal Hatch databases.
- Do not restart or reconfigure production containers as part of a benchmark run.
- Keep personal source CVs, case data, generated documents, and raw model output out of Git.
- Continue after individual model or repetition failures and preserve partial results.

## Initial Model Matrix

| Benchmark ID | Runtime | Model | Purpose |
|---|---|---|---|
| `qwen35-4b` | Existing llama.cpp endpoint | Qwen3.5 4B Q4_K_M | Current Hatch baseline |
| `qwen35-9b` | Local Ollama | `qwen3.5:9b` | Larger same-family comparison |
| `qwen3-8b` | Local Ollama | `qwen3:8b` | Previous-family compact comparison |
| `gemma4-e2b` | Local Ollama | `gemma4:e2b` | Small Gemma4 comparison |
| `gemma4-e4b` | Local Ollama | `gemma4:e4b` | Larger Gemma4 comparison |

`gemma4-coding` and `ornith:9b` are excluded initially because they are specialised variants rather than clean general-writing comparisons. The model registry must be extensible so they can be added later without changing runner logic.

## Benchmark Case Contract

Private benchmark cases live below ignored `data/benchmarks/<case-id>/` and contain:

- `case.json`: case metadata, expected files, and scoring configuration.
- `master_cv.json`: normalised source CV used by Hatch.
- `job_description.txt`: exact source JD.
- `jd_analysis.json`: frozen, reviewed `JDAnalysisResult` input.
- `expected_facts.json`: source identities, numeric facts, role/bullet counts, education, certifications, and any case-specific approved vocabulary.

The runner validates the case before inference and records SHA-256 checksums of every input. An anonymised miniature example case may be committed solely for tests and documentation.

The supplied PDF may be used to prepare the private case, but the benchmark input is the parsed and reviewed master-CV JSON. This removes PDF parser variability from the writing comparison.

## Execution Architecture

The harness is a Python package under `backend/benchmarks/` with four bounded responsibilities:

1. **Case loader** — validates private case files, schemas, checksums, and expected facts.
2. **Model adapter** — exposes a common completion interface for the existing llama.cpp OpenAI-compatible endpoint and local Ollama models without changing Hatch profile configuration.
3. **Pipeline runner** — injects a benchmark client into `CVTailor` and `CoverLetterGenerator`, executes three repetitions per model, and records raw and parsed results.
4. **Scorer/reporter** — applies hard gates, computes deterministic quality scores, aggregates repetitions, ranks eligible models, and writes JSON and Markdown reports.

The main writing track supplies the same frozen JD analysis and normalised master CV to every model. It uses the live repository prompts and skill files so prompt or skill changes are measurable. Prompt, skill, and Git hashes are stored in each run manifest.

Runs are sequential by default. This avoids cross-model CPU, GPU, memory, and thermal contention on the current 4-core/8-thread CPU and 4 GB GPU. The model adapter may keep the active model loaded when its runtime supports it, but it must not run two candidates concurrently.

## Generation Controls

Each model receives equivalent controls where supported:

- Temperature: `0.3` by default, matching Hatch configuration.
- Three repetitions using declared seeds.
- Identical CV and cover-letter output-token budgets.
- Sufficient context for the complete benchmark input; context truncation is a failed repetition.
- Reasoning disabled for the primary writing comparison unless a separate benchmark configuration explicitly enables it for every comparable model.

If a runtime ignores or cannot support a control, the run records that limitation. Results must not imply perfect seed determinism across different runtimes.

## Hard Gates

A repetition is ineligible for quality ranking if either generated document violates a critical contract:

- Structured output cannot be parsed after the configured application-level repair/retry policy.
- A new unsupported metric, employer, role, certification, qualification, or other protected factual entity appears.
- Role, company, period, education, or certification identity is altered or omitted.
- A source role or achievement bullet is omitted, duplicated, or added.
- Bracketed placeholders or LaTeX markup appear.
- The cover letter is outside 250–350 words.
- The CV is outside the configured source-length tolerance.
- Required document content is empty.

The existing grounding validator and structure-preservation behavior remain part of the pipeline. Benchmark gates add deterministic source-to-output checks and expose each finding separately. A model cannot compensate for a hard-gate failure with high ATS coverage or speed.

## Automatic Quality Scoring

Only hard-gate-passing repetitions receive quality scores.

### CV score

| Dimension | Weight | Deterministic evidence |
|---|---:|---|
| Grounding and factual preservation | 30% | Protected entities, numeric tokens, source evidence matching, grounding findings |
| JD requirement and keyword coverage | 25% | Frozen must-haves and ATS keyword coverage, with unsupported gaps excluded from the target |
| Structural and format compliance | 20% | Roles, bullet counts, section identities, length, categories, prohibited markup |
| Evidence relevance and specificity | 15% | Requirement-to-source proof overlap and penalties for unsupported or generic claims |
| Readability and repetition | 10% | Sentence/word-length bounds, duplicate n-grams, repeated openings, boilerplate and verbosity penalties |

### Cover-letter score

| Dimension | Weight | Deterministic evidence |
|---|---:|---|
| Grounding and factual preservation | 35% | Protected facts, metrics, company/role identity, source proof matching |
| JD requirement and keyword coverage | 25% | Coverage of the frozen top requirements and supported target vocabulary |
| Structural and format compliance | 15% | Word count, paragraphs, opening/closing presence, prohibited markup |
| Evidence relevance and specificity | 15% | Concrete source proof linked to requirements and generic-language penalties |
| Readability and repetition | 10% | Readability bounds, duplication, repeated CV sentences, boilerplate and verbosity |

The combined writing score is `60% CV + 40% cover letter`. Scoring functions must return both the numeric component and an auditable list of observations. No opaque model-generated judging is permitted.

## Reliability and Operational Metrics

Operational measurements are reported separately from writing quality:

- Successful repetition and hard-gate pass rates.
- Timeout, context overflow, malformed-output, repair, and retry counts.
- Median, minimum, maximum, and variance of writing scores.
- Wall-clock latency per stage and per complete pair.
- Prompt and completion token counts when supplied by the runtime.
- Effective output throughput when token counts are available.
- Peak model memory or runtime-reported size when available.
- Runtime/model load time, recorded separately from warm generation time.

Quality and operational metrics must not be collapsed into a single opaque weighted number.

## Ranking and Recommendation Rules

Models are ranked lexicographically:

1. Highest hard-gate pass rate.
2. Highest median combined writing score.
3. Lowest writing-score variance.
4. Lowest median latency, followed by lower memory use.

The report classifies next action from observed failure patterns:

- **Keep current model:** the baseline has full or jointly best gate reliability and no materially worse median quality than alternatives.
- **Prompt/skill change:** multiple capable models fail or lose points on the same instruction-sensitive dimension, suggesting a shared prompt, schema, or skill problem.
- **Model change:** another model is consistently safer or materially better on the same prompts across repetitions without unacceptable runtime cost.
- **Inconclusive:** too few passing repetitions, unavailable candidates, excessive variance, or only one benchmark case.

The first single-case result is evidence for this Delivery Manager scenario, not a universal model verdict. The report must state that broader model selection requires a multi-role corpus.

## CLI and Outputs

The command surface is:

```bash
cd backend

python -m benchmarks.cli init-case \
  --case-id tds-delivery-manager \
  --destination ../data/benchmarks/tds-delivery-manager \
  --master-cv /path/to/master_cv.json \
  --job-description /path/to/job_description.txt \
  --jd-analysis /path/to/jd_analysis.json \
  --expected-facts /path/to/expected_facts.json

python -m benchmarks.cli validate \
  --case ../data/benchmarks/tds-delivery-manager

python -m benchmarks.cli smoke \
  --case ../data/benchmarks/tds-delivery-manager

python -m benchmarks.cli run \
  --case ../data/benchmarks/tds-delivery-manager \
  --models qwen35-4b,qwen35-9b,qwen3-8b,gemma4-e2b,gemma4-e4b \
  --repetitions 3

python -m benchmarks.cli report \
  --run ../data/benchmarks/results/<run-id>
```

Each result directory contains:

- `manifest.json`: source, Git, prompt, skill, model, runtime, and generation metadata.
- `runs/<model>/<repetition>/`: raw response, parsed CV/letter JSON, timing, errors, gates, and score details.
- `summary.json`: aggregate metrics, ranking, and recommendation classification.
- `report.md`: readable leaderboard, findings, limitations, and recommendation rationale.

The report must show CV and cover-letter results separately before the combined ranking.

## Failure Handling

- An unavailable model is recorded as `unavailable`; remaining models continue.
- Timeout, transport error, malformed output, context overflow, and validation failure are typed repetition results rather than runner crashes.
- Partial results remain reportable.
- Reports distinguish model-generation failures from scorer or harness failures.
- An invalid case fails before any inference begins.
- Unexpected scorer exceptions fail the benchmark command rather than silently assigning a score.
- The runner writes repetition artifacts atomically so an interrupted run preserves completed work without presenting an incomplete summary as final.

## Privacy and Repository Hygiene

- `data/benchmarks/` and benchmark result directories must be ignored explicitly.
- The supplied CV, extracted text, personal master-CV JSON, raw outputs, and reports are never committed.
- Tests use synthetic identities and facts.
- Reports retain personal information locally because their purpose is detailed evidence review; the CLI must warn before a user selects an output path outside ignored benchmark storage.
- The harness must not send inputs anywhere except configured loopback endpoints.

## Testing Strategy

Unit tests cover:

- Case/schema validation and input hashing.
- Protected-entity, numeric-token, placeholder, LaTeX, role, bullet, education, certification, and word-count gates.
- Every scoring dimension and boundary.
- Aggregate medians, variance, lexicographic ranking, ties, and recommendation classification.
- Stable JSON/Markdown rendering from fixed synthetic results.
- Atomic artifact writes and partial-run recovery.

Integration tests use mocked llama.cpp and Ollama adapters for a two-model, multi-repetition run through real `CVTailor` and `CoverLetterGenerator` prompt rendering and parsing. They verify that no profile or database write occurs.

A live smoke command validates endpoint reachability and one minimal completion per installed model. Live inference is opt-in and is not part of normal CI.

## Acceptance Criteria

- The synthetic test suite passes without local models running.
- The private Delivery Manager case validates against the supplied CV-derived master data and frozen JD analysis.
- All five configured candidates are attempted for three repetitions without changing Hatch runtime configuration.
- Each repetition produces auditable gates, component scores, runtime metrics, and artifacts.
- The final report identifies whether current evidence supports retaining Qwen3.5 4B, changing prompts/skills, changing model, or declaring the result inconclusive.
- A failed or unsafe model cannot win because of ATS score, latency, or partial output.
- The current application databases and profile remain byte-for-byte unchanged by the benchmark.

## Deferred Scope

- Cloud-model comparisons.
- LLM-as-judge grading.
- Subjective human review scores.
- Automated PDF visual/layout evaluation.
- Automatic production model switching.
- Benchmark UI in the frontend.
- General model selection from a single Delivery Manager case.
