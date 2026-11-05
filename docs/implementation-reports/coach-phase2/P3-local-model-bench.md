# P3 — local model bench (M8)

Status: **implementation complete, bench runs pending on the reference laptop (owner).**
This file records the catalogue, the pinned runtime and the gate the bench must pass. It never reports a
number that was not measured.

## Pinned runtime

| Item | Value |
|---|---|
| Image | `ghcr.io/ggml-org/llama.cpp:server-b12124@sha256:c0a11067c72bb1eb330b8bddbf9869274c195e596bf4fae55fd527102e644b85` |
| Build | b12124 (≥ b10828 for Spark's `spark2_5`; ≥ b11555 for Ternary-Bonsai-2 `Q2_0`) |
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
| `gemma-4-e2b-q4km-triage` | T | Gemma 4 E2B Q4_K_M, text-only | `0314792d7f1f` | `740185b21d22` | apache-2.0 | candidate |
| `bonsai-1.7b-q1-triage` | T | Bonsai 1.7B Q1_0 | `210a9e99f79c` | `3d7c6c90dd98` | apache-2.0 | candidate |
| `lfm2.5-1.2b-instruct-q4km-triage` | T | LFM2.5 1.2B Instruct Q4_K_M | `8ed288026e23` | `b1b3de114215` | lfm1.0 | candidate |
| `gemma-4-e4b-q4km-primary` | S | Gemma 4 E4B Q4_K_M, text-only | `bfc15c382204` | `85a896a04755` | apache-2.0 | candidate |
| `bonsai-4b-q1-primary` | S | Bonsai 4B Q1_0 | `78f2c2bacd09` | `4524b3f997f0` | apache-2.0 | candidate |
| `bonsai-8b-q1-primary` | S | Bonsai 8B Q1_0 | `48516770dd04` | `284a335aa3fb` | apache-2.0 | candidate |
| `lfm2.5-8b-a1b-q4km-primary` | S | LFM2.5 8B-A1B Q4_K_M | `49c148317070` | `4923ec14f06b` | lfm1.0 | candidate |
| `gemma-4-26b-a4b-ud-q4km-deep` | L | Gemma 4 26B-A4B UD-Q4_K_M | `c099eb48e663` | `f2c28b3dc477` | apache-2.0 | candidate |
| `gemma-4-12b-q4km-deep` | L | Gemma 4 12B Q4_K_M | `fc034cfff751` | `0a270ec9fe6b` | apache-2.0 | candidate |
| `ternary-bonsai-2-27b-q2-deep` | L | Ternary-Bonsai-2 27B Q2_0 | `839bd57023c1` | `4f99aed01b8a` | apache-2.0 | candidate |
| `lfm2-24b-a2b-q4km-deep` | L | LFM2 24B-A2B Q4_K_M | `6247d03b87c2` | `eb4d2d4d4e61` | lfm1.0 | candidate |
| `qwen3.8-27b-ud-q4km-deep` | L | Qwen3.8 27B UD-Q4_K_M | `4ca720788d1e` | `322e194ff797` | apache-2.0 | candidate |

**Licence checks (5 Nov 2026).** Gemma 4 cards link to `https://ai.google.dev/gemma/docs/gemma_4_license`, which
resolves to Google's **Apache License 2.0** page (`https://ai.google.dev/gemma/apache_2`, the full Apache 2.0
text); Gemma 4 is accepted. Liquid AI cards use `license: other` with `license_name: lfm1.0`, now on the approved
list (D18). Bonsai and Qwen3.8 are Apache-2.0; phi-4-mini is MIT. No candidate was skipped for licence.

**Skipped (no catalogue entry).** None of the §9.1 names is missing a GGUF. Bonsai's fork-only `PQ2_0` and
`PTQ1_0` files are not catalogued: they need the PrismML fork (K3); the upstream `Q2_0` file is used instead.


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
