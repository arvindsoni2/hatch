# P3 evidence — local model tiers (M8)

Task / spec sections / ACs: P3, Wave 0, standard. Spec §9 (M8), §13.1 (Settings tier table), §14; AC20, AC22, AC34, AC35.

Baseline SHA → head SHA: `4d072bf` (P2 merged to main) → the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode (harness-reported model ID `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`). The owner confirmed the model and Go entitlement on 2026-11-05. Effort is not exposed to the agent. No model switch during the task.

Claude Code RED commit (HA only): not applicable; P3 is not a high-assurance task.

Files changed (one line each: responsibility):

- `backend/app/config/model_catalog.json` — 5 candidate entries with real revision/sha256 from the HF API, `tiers` and `status`; the 2 existing entries stay `promoted`.
- `backend/app/config/model_discovery_policy.json` — `xhtoken`/`openbmb` publishers, `spark-x2`/`minicpm` families, marker exemption, `image-text-to-text` accepted for text-only use.
- `backend/app/config/model_tiers.json` — T/S route map with incumbents; no L entry until a model is promoted.
- `backend/app/services/model_discovery.py` — per-task listing (deduped), marker exemption, explicit `mmproj` exclusion, fallback restricted to promoted entries.
- `backend/app/services/ai_setup.py` — catalogue validation requires `tiers`/`status`; recommendations only offer promoted models.
- `backend/app/services/coach_readiness/tiers.py` — load/validate the tier map, Tier L RAM gate, token estimate and input fitting (AC34).
- `backend/app/services/setup_intent.py`, `backend/app/schemas/setup.py` — `tier_l_enabled` Settings choice, default off.
- `backend/app/routers/setup.py` — `GET /api/setup/model-tiers` read-only table payload with Tier L availability.
- `backend/app/main.py` — startup validation refuses a tier map naming a non-promoted model.
- `docker-compose.yml`, `docker-compose.local-ai.yml` — pin `server-b12124` by tag and digest; add `llm-deep` under profile `deep` (:8082).
- `frontend/src/components/settings/ModelTierTable.tsx`, `frontend/src/app/settings/ai/page.tsx` — read-only tier table; Tier L opt-in hidden below 24 GB.
- Tests: `backend/tests/test_services/test_model_tiers.py`, `test_model_discovery.py` (extended), `test_ai_setup.py`, `backend/tests/test_routers/test_setup_router.py`, `backend/tests/test_tools/test_docker_contract.py`, `frontend/src/components/settings/__tests__/ModelTierTable.test.tsx`.
- `docs/implementation-reports/coach-phase2/P3-local-model-bench.md` — pinned runtime, catalogue facts, gate to be filled by the owner's bench run.

Path deviations, recorded rather than guessed:

- The plan/spec name `config/model_catalog.json`, `config/model_discovery_policy.json` and `config/model_tiers.json` at repository root. The real files are `backend/app/config/…`, where `ai_setup.py` and `model_discovery.py` already load them; the new files follow those loaders.
- The tier map carries `max_input_tokens` in addition to the spec's five keys, because AC34 needs an explicit 1,200-token Tier T input cap in production and in the bench.
- `tier_l_enabled` lives in the setup intent because spec §14 says Tier L is a Settings choice, not a flag; the plan did not name a persistence mechanism.

RED: test names and failure output (short):

```text
$ python -m pytest -q --no-cov tests/test_services/test_model_tiers.py
E   ImportError: cannot import name 'tiers' from 'app.services.coach_readiness'

$ npx vitest run src/components/settings/__tests__/ModelTierTable.test.tsx
Test Files  1 failed (1)  Tests  no tests
```

GREEN: commands, exit codes, counts:

```text
$ python -m pytest -q --no-cov tests/test_services/test_model_tiers.py \
    tests/test_services/test_model_discovery.py tests/test_services/test_ai_setup.py \
    tests/test_tools/test_docker_contract.py
27 passed

$ python -m pytest -q --no-cov tests/test_routers/test_setup_router.py
17 passed

$ python -m pytest -q --no-cov scripts/tests/test_hatch_cli.py
32 passed

$ npx vitest run src/components/settings/__tests__/ModelTierTable.test.tsx
3 passed

$ ruff check <changed backend files>
All checks passed!

$ npm run type-check
exit 0
```

Regressions run:

```text
$ python -m pytest -q --no-cov tests/test_services tests/test_routers tests/test_scripts
1896 passed, 15 warnings in 360.09s

$ npx vitest run
681 passed (108 files)

$ npm run build
exit 0

$ python -m pytest -q --no-cov tests/runtime
471 passed, 1 skipped in 109.67s

$ python -m pytest -q --no-cov tests/runtime tests/integration
570 passed, 1 failed, 1 skipped in 429.72s
# the failure is tests/runtime/test_shadow_retention.py::test_application_lifespan_installs_real_shadow_maintenance,
# which passes in isolation and in the focused runtime run above; order-dependent pre-existing flake
# (the test runs the real lifespan against a global APScheduler instance).
```

Model calls in tests: fake / live: none. P3 changes configuration and validation only; the live bench is the owner's run on the reference laptop (plan §1.1, P3).

Privacy / deletion / fencing evidence: synthetic fixtures only; no `data/`, `.env`, CV, transcript or recording was read. The catalogue stores public model metadata only.

Migration: none.

Not run / known limits:

- The §9.4 bench and the §9.1 dual gate are **not measured yet**; `P3-local-model-bench.md` records the protocol and leaves measured cells pending. The tier map therefore keeps the incumbents and has no Tier L model.
- `tests/test_tools/test_embedder.py` and `test_semantic_scorer.py` fail in this environment with `CUDA error: no kernel image is available` (Quadro P520 sm_61 is unsupported by the installed torch build). Unrelated to P3; recorded rather than hidden.
- Full migration chain from empty SQLite remains blocked by the pre-existing `c30577e861e2` revision (P2 note); P3 adds no migration.

Ready for review: yes — code, catalogue, policy, tier map, compose pin and Settings surface are complete; the owner runs the bench and fills the measured cells before the P3 merge decision.

## D18 follow-up (5 Nov 2026)

Merged `main` at `1d8c583` (no rebase) before this work, so the spec's D18 candidate families and the plan's
revised P3 tests are the basis. The spec, plan and HTML page were not edited.

Changes on top of the first P3 commit:

- `backend/app/config/model_discovery_policy.json` — publishers `prism-ml`, `LiquidAI`, `google`, `Qwen` (matched
  case-insensitively); families `bonsai`, `lfm2`, `gemma-4`, `qwen3.8`; `lfm1.0` approved; `bonsai_quantizations`
  holds `Q2_0`, `Q1_0`.
- `backend/app/services/model_discovery.py` — publisher allowlist compared lower-case; family match prefers the
  longest family (`qwen3.8` no longer collapses to `qwen3`); `_license` honours `cardData.license_name` (Liquid AI
  cards say `license: other` + `license_name: lfm1.0`); quantisation matching is whole-token, and only the
  `bonsai` family adds `Q1_0`/`Q2_0`, so fork-only `PQ2_0`/`PTQ1_0` never match.
- `backend/app/config/model_catalog.json` — 12 new `candidate` entries (T: Gemma 4 E2B, Bonsai 1.7B, LFM2.5
  1.2B; S: Gemma 4 E4B, Bonsai 4B, Bonsai 8B, LFM2.5 8B-A1B; L: Gemma 4 26B-A4B, Gemma 4 12B,
  Ternary-Bonsai-2 27B Q2_0, LFM2 24B-A2B, Qwen3.8 27B), each with the real revision and file sha256 read from
  the Hugging Face tree API. Incumbents stay `promoted`; `model_tiers.json` is unchanged.
- Licence findings: Gemma 4 cards link to Google's licence page, whose canonical URL is
  `https://ai.google.dev/gemma/apache_2` and whose body is the Apache License 2.0 text — accepted. Liquid AI
  cards use `lfm1.0` — accepted. Bonsai/Qwen3.8 are Apache-2.0. No licence skip.
- Skipped: Bonsai `PQ2_0`/`PTQ1_0` (PrismML fork only, K3); the upstream `Q2_0` file is catalogued. No §9.1 name
  lacked a GGUF.
- Pinned build `server-b12124` is ≥ `b11555` (the Ternary-Bonsai-2 `Q2_0` floor) as well as ≥ `b10828` (Spark).

Tests added or extended:

- `test_policy_accepts_spark_and_minicpm_families_only_from_allowlisted_publishers` — now also asserts the D18
  families from `prism-ml`, `LiquidAI`, `google` and `Qwen`, with a non-allowlisted publisher rejected.
- `test_bonsai_accepts_upstream_1_and_2_bit_quants_only` — `Q1_0`/`Q2_0` accepted for Bonsai; `PQ2_0`/`PTQ1_0`
  refused; `Q1_0` refused for a non-Bonsai family.
- `test_unapproved_licence_rejected` — `cc-by-nc-4.0` refused, `lfm1.0` accepted.
- `test_catalog_entries_have_revision_sha_tiers_and_status` — asserts all 12 D18 entries, their tiers, status and
  approved licences.

Follow-up gates:

```text
$ python -m pytest -q --no-cov tests/test_services/test_model_discovery.py \
    tests/test_services/test_model_tiers.py tests/test_services/test_ai_setup.py
22 passed

$ python -m pytest -q --no-cov tests/test_services tests/test_routers
1894 passed, 15 warnings in 267.70s

$ python -m pytest -q --no-cov tests/runtime
471 passed, 1 skipped in 132.40s

$ npx vitest run src/components/settings/__tests__/ModelTierTable.test.tsx \
    src/__tests__/components/SettingsAIPage.test.tsx
4 passed (2 files)

$ ruff check app tests
All checks passed

$ npm run type-check
exit 0
```

## Repair cycle 1 (9 Nov 2026)

Review findings addressed:

- **H1** — `GET /api/setup/model-tiers` moved to `GET /api/coach/readiness/model-tiers` in
  `backend/app/routers/coach_readiness.py`; `backend/app/routers/setup.py` is reverted to `main` (no
  `coach_readiness` import there). `ModelTierTable.tsx` and both frontend tests point at the new path. The route
  test moved to `backend/tests/test_routers/test_coach_model_tiers_router.py`.
- **M1** — `scripts/hatch_cli.py::model_buckets` skips entries whose status is not `promoted`, so a hardware probe
  never recommends a bench candidate; `models install --primary/--triage <id>` still resolves candidate ids through
  `catalog()`. Test: `test_model_buckets_never_recommend_candidates`.
- **M2** — `backend/tests/runtime/test_model_tier_startup.py` sets the T tier to a candidate and asserts the real
  lifespan raises `RuntimeError("invalid model tier configuration: …")`.
- **L1** — `_license` reads `cardData.license_name` only when `cardData.license == "other"`; a concrete
  `cc-by-nc-4.0` card with a spoofed `license_name: apache-2.0` is refused
  (`test_license_name_does_not_override_a_concrete_license`).
- **L2** — the test is renamed `test_tier_t_budget_enforced` and asserts
  `300 + max_input_tokens + max_output_tokens <= 2048` for Tier T.
- **L3** — the readiness tier route ignores a stored `tier_l_enabled` while probe RAM is below 24 GB
  (`enabled` is false); the moved router test covers it.
- **L4** — `docker-compose.yml` comment now says the image is pinned to b12124 by tag and digest, not rolling.
- **L5** — `P3-local-model-bench.md` has a pending owner checklist for the thinking-override check and the Phase 1
  `acceptance-smoke` rerun with the incumbents on b12124.

Repair gates:

```text
$ python -m pytest -q --no-cov tests/test_routers/test_coach_model_tiers_router.py \
    tests/test_services/test_model_discovery.py tests/test_services/test_model_tiers.py \
    tests/test_services/test_ai_setup.py tests/runtime/test_model_tier_startup.py \
    ../scripts/tests/test_hatch_cli.py
58 passed

$ python -m pytest -q --no-cov tests/test_services tests/test_routers tests/test_scripts tests/runtime
2370 passed, 1 skipped in 394.84s

$ npx vitest run src/components/settings/__tests__/ModelTierTable.test.tsx \
    src/__tests__/components/SettingsAIPage.test.tsx
4 passed (2 files)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app tests ../scripts/hatch_cli.py ../scripts/tests/test_hatch_cli.py
All checks passed

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```
