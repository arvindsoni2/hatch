---
title: Cover Letter Contract PR1 Root Cause Note
document_type: implementation-note
status: active
created: 2026-07-16
related_spec: docs/implementation-specs/active/Hatch_Prompt_Skill_Local_Writing_Reliability_Codex_Spec_v4.md
---

# Cover Letter Contract PR1 Root Cause Note

PR1 starts from accepted baseline merge `a5a4d729a4dfddcabb2ec4ca54c91120f616f6de` and baseline PR #36.

The shared benchmark failure is rooted in the current cover-letter generation boundary, not in one local model:

1. `CoverLetterGenerator.generate(...)` validates only an upper bound. Drafts over 350 words trigger one trim retry, but drafts below 250 words are accepted.
2. `_parse_cover_letter(...)` trusts the model-provided `word_count` when present, so generator decisions can be based on self-reported metadata instead of application-computed body metrics.
3. Existing word counts use `str.split()` over concatenated body paragraphs. This misses the locked tokenizer contract and is not shared with generation validation, API metadata, tests, and benchmark scoring.
4. `backend/app/prompts/cl_generation.j2` asks for four paragraphs and concise output, while PR1 requires five body paragraphs with paragraph budgets and an internal 285-315 body-word target.
5. `backend/app/skills/cover-letter/SKILL.md` says "never pad below 250", which conflicts with the new under-length repair requirement.
6. Numeric grounding currently checks the full cover letter against tailored-CV and personal source text only. It does not distinguish candidate evidence numbers, job-description numbers, and unsupported numbers, and it cannot detect selected evidence tokens that were mutated, such as `120+` becoming `120`.
7. The accepted baseline benchmark recorded final score artifacts but did not capture PR1-required first-pass and post-repair metrics, repair counts, run-manifest provenance, protected hashes, or health evidence.

The first implementation slice should therefore introduce a canonical body metric helper and make `CoverLetterResult.word_count` application-computed. Repair and numeric-fidelity behaviour should build on that deterministic validation boundary.

## Locked PR1 benchmark policy

PR1 validates the generation contract and benchmark instrumentation. It does not select a new default writing model.

The required PR-blocking benchmark is the `acceptance-smoke` profile: one repetition per configured local writing model. The three-repetition matrix remains available as the `extended` profile and is non-blocking PR1 evidence.

The smoke run must prove that invalid cover letters are measured by application code, repair attempts are recorded, final hard-gate failures become `review_required`, invalid pairs are excluded from writing-quality scoring and ranking, numeric-fidelity issues are surfaced, model execution outcomes are distinguishable, and partial evidence is persisted when a model fails or times out.

Required command:

```bash
cd /tmp/hatch-writing-pr1/backend

python -m benchmarks validate \
  --case /home/asoni/Downloads/Assignment/Job_Pilot_v2/data/benchmarks/tds-delivery-manager

python -m benchmarks run \
  --case /home/asoni/Downloads/Assignment/Job_Pilot_v2/data/benchmarks/tds-delivery-manager \
  --models qwen35-4b,qwen35-9b,qwen3-8b,gemma4-e2b,gemma4-e4b \
  --repetitions 1 \
  --profile acceptance-smoke \
  --output-root ../data/benchmarks/results
```

Acceptance-smoke timeout defaults:

- per generation or repair call: 20 minutes;
- per model: 45 minutes;
- whole run: 3 hours.

Exit code `3` is acceptable for PR1 when the report is complete and failures are model execution outcomes. Exit codes `1`, `4`, and `5` remain blocking.
