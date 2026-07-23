# Hatch Coach model benchmark

The Coach benchmark measures whether a local model can satisfy Hatch Coach's production prompt and service contracts. It covers company research, question generation, evidence-grounded model answers, answer evaluation, rubric enrichment, session reports, technical drills, and one isolated three-question session.

The committed v1 suite is fictional and synthetic. Results describe this suite and these prompt/schema versions; they are not a universal verdict on a model.

## Quick start

Run commands from `backend/`:

```bash
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/v1
python -m benchmarks.coach smoke --suite benchmarks/coach/fixtures/v1
```

`validate` performs strict fixture, hash, reference, loopback-endpoint, and privacy checks without inference. `smoke` uses deterministic fake model responses through the same production adapters and validators as a live run. It runs every committed scenario for all manifest models by default, makes no live model call, and has 90-second call, model, and whole-run bounds.

Live profiles require an explicit comma-separated model list:

```bash
python -m benchmarks.coach run \
  --suite benchmarks/coach/fixtures/v1 \
  --models qwen35-4b \
  --profile acceptance-smoke

python -m benchmarks.coach run \
  --suite benchmarks/coach/fixtures/v1 \
  --models qwen35-4b,qwen35-9b \
  --profile standard

python -m benchmarks.coach run \
  --suite benchmarks/coach/fixtures/v1 \
  --models qwen35-4b \
  --profile extended
```

The model IDs and loopback runtime endpoints come from the suite manifest. Missing or unavailable models produce terminal model outcomes; they do not discard evidence from later models.

## Profiles and timeouts

| Profile | Repetitions | Scenarios | Call | Model | Whole run | Classification/ranking |
|---|---:|---|---:|---:|---:|---|
| `contract-smoke` | 1 | Full v1 | 90 s | 90 s | 90 s | No |
| `acceptance-smoke` | 1 | Six core scenarios | 10 min | 60 min | 5 h | No |
| `standard` | 2 | Full v1 | 15 min | 3 h | 15 h | Yes |
| `extended` | 3 | Full v1 plus optional private cases | 20 min | 6 h | 30 h | Yes |

Timeout overrides may only reduce a profile's bounds and must remain ordered `call <= model <= whole run`:

```bash
python -m benchmarks.coach run \
  --suite benchmarks/coach/fixtures/v1 \
  --models qwen35-4b \
  --profile acceptance-smoke \
  --call-timeout-seconds 300 \
  --model-timeout-seconds 1800 \
  --run-timeout-seconds 7200
```

A call timeout is a recorded terminal result. A model deadline does not stop later models. A whole-run deadline atomically flushes completed evidence before returning.

Exit codes are stable:

| Code | Meaning |
|---:|---|
| 0 | Completed without adverse model outcomes |
| 1 | Suite, file, or I/O validation failure |
| 2 | Invalid command or bounded-configuration error |
| 3 | Completed with one or more adverse model outcomes |
| 4 | Incomplete because of a deadline or interruption |
| 5 | Invalid harness privacy or integrity evidence |

## Resume and reports

Runs are written atomically below `../data/benchmarks/coach/results/<run_id>/` by default. Resume an existing run with the same immutable suite/profile/model identity:

```bash
python -m benchmarks.coach run \
  --suite benchmarks/coach/fixtures/v1 \
  --models qwen35-4b \
  --profile standard \
  --resume <run_id>
```

Terminal attempts are skipped. Timed-out attempts are also skipped unless the operator explicitly adds `--retry-timeouts`; that flag is accepted only with `--resume`. Timeout bounds cannot change during resume.

Regenerate the privacy-safe Markdown report from a saved summary:

```bash
python -m benchmarks.coach report \
  --run ../data/benchmarks/coach/results/<run_id>
```

Each run contains:

```text
manifest.json
run_manifest.json
progress.json
summary.json
aggregate.json
report.md
scenarios/<model>/<scenario>/repetition-<n>.json
```

The report contains terminal counts, completion state, harness validity, protected hashes, stage metrics, exact fractions plus display percentages, gates, exclusions, capability classifications, eligible ranking, and relative artifact paths. It does not render raw prompts, raw private outputs, auth headers, commands, or absolute protected paths.

## Capability and ranking

Only `standard` and `extended` runs classify models. Harness-contract attempts never enter model denominators. Minimum evidence includes at least 80% valid scheduled attempts per core stage, four valid attempts per core stage, eight completed answer evaluations, two direct model reports, two terminal fallback-contract reports, and four valid attempts per optional stage.

`coach_capable` requires zero safety-critical failures, at least 95% core structured success, at least 90% core hard-gate pass, at least 80% answer-evaluation band agreement, mean absolute calibration error no greater than 1.5, 100% model report score/count fidelity, no more than 5% timeout/unavailable outcomes, no unclassified fallback, and at least 90% success for each optional stage. Passing core evidence with a weaker optional stage is `coach_capable_with_optional_degradation`. Sufficient failing core evidence is `not_coach_capable`; insufficient or incomplete evidence is `inconclusive`.

Eligible models are ranked lexicographically by safety pass rate, core hard-gate rate, median core quality, calibration, population variance, question-repair rate, core latency, then model ID. Optional judge fields never affect classification or ranking.

Acceptance smoke never recommends or changes a model. Any default-model or routing decision requires two independent completed standard runs with the same suite, prompt/schema versions, model matrix, and qualifying winner, plus matching protected hashes, blind human review of the top two eligible models, and a separate owner-approved change.

## Privacy and limitations

- Keep private reviewed suites under `data/benchmarks/coach/private/`; the entire benchmark data area is ignored by Git.
- Official service-level ranking must not write to the production database. E2E-01 creates and removes its own temporary SQLite database.
- Profile and SQLite main/WAL/SHM hashes are recorded before and after a run. A mutation invalidates the harness and suppresses classification/ranking.
- Forced provider failures are `harness_contract` evidence. Their expected unavailable, invalid, and fallback outcomes never penalise a model.
- The v1 benchmark does not rank ASR transcription or browser face-analysis providers.
- Published official reports use dated filenames and are committed only after an intentional privacy review.
