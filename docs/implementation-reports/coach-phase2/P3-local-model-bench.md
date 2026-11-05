# P3 — local model bench (M8)

Status: **implementation complete, bench runs pending on the reference laptop (owner).**
This file records the catalogue, the pinned runtime and the gate the bench must pass. It never reports a
number that was not measured.

## Pinned runtime

| Item | Value |
|---|---|
| Image | `ghcr.io/ggml-org/llama.cpp:server-b12124@sha256:c0a11067c72bb1eb330b8bddbf9869274c195e596bf4fae55fd527102e644b85` |
| Build | b12124 (≥ b10828, required for Spark's `spark2_5` architecture) |
| Used by | `docker-compose.yml` (primary, triage), `docker-compose.local-ai.yml` (primary, triage, deep) |
| Deep route | `llm-deep` :8082, profile `deep`, off by default (spec §9.2.5) |

## Candidates and catalogue entries

Revisions and file hashes were read from the Hugging Face API (`tree?recursive=true&blobs=true`) on 2026-11-05, not
pre-filled. Existing entries stay `promoted`; candidates are `candidate` until the gate below passes twice.

| Catalogue id | Tier(s) | Model | Revision | File sha256 (first 12) | Licence | Status |
|---|---|---|---|---|---|---|
| `qwen3.5-0.8b-q8-triage` | T | Qwen3.5 0.8B Q8_0 (incumbent) | `f36b1ea49a33` | `7182e2362766` | apache-2.0 | promoted |
| `qwen3.5-4b-q4km-primary` | S | Qwen3.5 4B Q4_K_M (incumbent) | `4168f45a16a1` | `13c16f426047` | apache-2.0 | promoted |
| `minicpm-v-4.7-1b-q8-triage` | T | MiniCPM-V 4.7 1B Q8_0, text-only | `345adbfa02c4` | `32322779352e` | apache-2.0 | candidate |
| `minicpm5-2b-q4km-triage` | T, S | MiniCPM5 2B Q4_K_M | `2079a22f3bea` | `ec2d58016400` | apache-2.0 | candidate |
| `spark-x2.6-4b-q4km-primary` | S | Spark-X2.6 4B Q4_K_M | `3c33ab387468` | `91cb2811aebb` | apache-2.0 | candidate |
| `phi-4-mini-instruct-q4km-primary` | S | Phi-4 mini instruct Q4_K_M | `78eb92a46fc3` | `88c002299140` | mit | candidate |
| `minicpm-v-4.7-35b-a3b-q4km-deep` | L | MiniCPM-V 4.7 35B-A3B Q4_K_M, text-only | `cf943fbe32f8` | `9ecf91e814d7` | apache-2.0 | candidate |

Gemma 4 12B is **not** in the catalogue: its licence is not in `approved_licenses` (spec §9.2.2). Phi-4 mini is
MIT (unsloth quantisation of the official Microsoft model).

## Gate (spec §9.4) — to be filled by the owner's run

Run `python -m benchmarks.coach run --profile phase2 …` per candidate on: reference CPU-only, reference with GPU
offload, and the floor profile (T and S only). Two independent holdout runs; owner blind-rates 10 outputs.

| Criterion | T | S | L |
|---|---|---|---|
| Schema-valid | ≥ 98 % | ≥ 95 % | ≥ 95 % |
| Grounding violations | 0 | 0 | 0 |
| p95 latency, reference CPU-only | ≤ 30 s | ≤ 90 s | ≤ 180 s |
| Peak RSS | ≤ 3 GB | ≤ 6 GB | ≤ 20 GB |
| Owner blind rating, mean | ≥ 3.5 | ≥ 3.5 | ≥ 3.8 |
| Floor profile | must pass T | must pass S, else incumbent stays | n/a |

Measured values: **pending**. The tier map keeps the incumbents (`T` → Qwen 0.8B, `S` → Qwen 4B) and has no `L`
entry until a candidate is `promoted`.

## Dual gate (spec §9.1)

For every T/S candidate that passes §9.4, run the route's existing regression bench on the same pinned build:
- Tier S: `python -m benchmarks.coach run --profile acceptance-smoke` (Phase 1 Coach).
- Tier T: the job-scoring triage checks in `docs/operations/REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md`.

A candidate that fails the route bench stays `qualified`, never `promoted` (AC35). Only a model that passes both
becomes the tier default in `backend/app/config/model_tiers.json`.

## Reproduce

```bash
docker compose -f docker-compose.local-ai.yml --profile local-primary --profile local-triage up -d
docker compose -f docker-compose.local-ai.yml --profile deep up -d llm-deep   # only after Tier L is enabled
cd backend
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/phase2_v1
python -m benchmarks.coach run --profile phase2 --help
```
