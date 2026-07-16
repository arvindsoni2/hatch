# Local Writing Model Benchmark — 15 July 2026

**Status:** Historical baseline evidence  
**Run ID:** `20260715T183303Z-8d9f4a72`  
**Historical source commit:** `4726aa8`  
**Case:** `tds-delivery-manager`  
**Repetitions:** Three shared seeds per model (`11`, `23`, and `41`)

## Outcome

All 15 CV and cover-letter pairs completed, but none passed every hard gate. Every cover letter was below the required 250–350 body-word range, so no pair was eligible for a writing-quality score and the run cannot support a model ranking or default-model change.

The common length failure across all five models identifies the shared cover-letter prompt, generator, and validation path as the first reliability problem to address. The run covered one Delivery Manager case and is not a universal model verdict.

## Safety and reliability

| Model | Successful pairs | Failed | Unavailable | Hard-gate pass rate | Blocking gates |
|---|---:|---:|---:|---:|---|
| Qwen3.5 4B (`qwen35-4b`) | 3/3 | 0 | 0 | 0% | Cover-letter word count (3); unsupported numeric token (1) |
| Qwen3.5 9B (`qwen35-9b`) | 3/3 | 0 | 0 | 0% | Cover-letter word count (3) |
| Qwen3 8B (`qwen3-8b`) | 3/3 | 0 | 0 | 0% | Cover-letter word count (3) |
| Gemma4 e2b (`gemma4-e2b`) | 3/3 | 0 | 0 | 0% | Cover-letter word count (3) |
| Gemma4 e4b (`gemma4-e4b`) | 3/3 | 0 | 0 | 0% | Cover-letter word count (3); unsupported numeric token (1) |

All generated CVs passed the structural hard gates covering roles, bullet counts, education, certifications, placeholders, and length preservation.

## Cover-letter body-word counts

| Model | Seed 11 | Seed 23 | Seed 41 |
|---|---:|---:|---:|
| Qwen3.5 4B | 207 | 216 | 218 |
| Qwen3.5 9B | 182 | 209 | 165 |
| Qwen3 8B | 208 | 213 | 194 |
| Gemma4 e2b | 165 | 160 | 167 |
| Gemma4 e4b | 215 | 185 | 196 |

These values are application-computed body counts recorded by the hard-gate results, not model-reported counts.

## Operational results

| Model | Median pair latency |
|---|---:|
| Qwen3.5 4B | 21.32 minutes |
| Qwen3.5 9B | 14.97 minutes |
| Qwen3 8B | 27.72 minutes |
| Gemma4 e2b | 3.80 minutes |
| Gemma4 e4b | 9.84 minutes |

Latency cannot determine the preferred model because no output pair passed all hard gates.

## Numeric fidelity

- Qwen3.5 4B introduced unsupported `20+` in one cover letter.
- Gemma4 e4b changed approved evidence `120+` to `120` in one cover letter, producing an unsupported numeric token.
- Qwen3.5 9B paraphrased CV evidence more aggressively and produced additional advisory similarity warnings.
- The other recorded pairs did not produce a blocking unsupported-numeric-token finding.

Similarity warnings are advisory and are not proof of factual correctness.

## Writing quality

No CV, cover-letter, or combined writing-quality ranking was possible. The benchmark deliberately excludes pairs that fail any hard gate from quality scoring.

## Previously reported but not machine-recorded

The operator previously reported that:

- 847 tests passed and 2 were skipped;
- database and profile hashes were unchanged;
- backend health passed; and
- the frontend returned HTTP 200.

The historical machine-readable report did not capture the exact commands, timestamps, exit codes, hashes, or health responses supporting those statements. They are retained here as operator-reported context, not independently auditable baseline evidence. Future official runs must record them in `run_manifest.json`.

## Provenance and privacy

This summary is derived from the historical ignored report and per-pair result records for run `20260715T183303Z-8d9f4a72`, executed from source commit `4726aa8`. Raw responses, private fixtures, generated documents, and detailed run artifacts remain under ignored `data/benchmarks/` paths and are not required to inspect this summary in a fresh clone.

This document intentionally excludes full prompts and responses, private CV and job-description content, generated documents, secrets, database or profile contents, and machine-specific absolute paths.

