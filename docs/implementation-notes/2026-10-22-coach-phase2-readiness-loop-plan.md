---
title: Hatch Coach Phase 2 — Interview Readiness Loop — Implementation Plan
document_type: implementation-plan
status: active
implementation_status: not-started
last_verified: 2026-11-05
approval_status: final-for-implementation (owner, 2026-11-02)
baseline_commit: b7274a6
spec: 2026-10-22-coach-phase2-readiness-loop.md
supersedes:
  - Hatch_Coach_Phase2_Implementation_Plan_v1.md (draft, 13 Oct 2026)
  - Hatch_Coach_Phase2_OpenCode_Handoff_v1.md (draft, 13 Oct 2026)
---

# Coach Phase 2 — Implementation Plan

**For agentic workers:** OpenCode implements one task per PR. Claude Code reviews every PR and writes the RED tests for tasks marked **HA** (high assurance). Do not start a task until its predecessor has merged and you have re-read current `main`. Section numbers (§) refer to the spec.

## 1. Tools, models and roles (checked 2 Nov 2026)

### 1.1 Who does what

| Role | Tool | Does | Never does |
|---|---|---|---|
| Owner | You | Approves the plan, merges PRs, flips flags, runs the P3 bench on the reference laptop | — |
| Implementer | OpenCode with the OpenCode Go plan | One task per PR: tests (non-HA), code, evidence report | Edits Claude Code's RED tests, the spec, this plan, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, `.claude/` or the design folder; merges; pushes, rebases or amends without asking |
| Reviewer | Claude Code | `/phase2-red <task>` for HA tasks before coding starts; `/phase2-review <task>` on every PR | Writes Phase 2 product code |

### 1.2 OpenCode Go: plan and models

**Plan:** Go, $10/month. Each model has its own allowance: 20% of its monthly cap per 5 hours, 50% per week. The default model below has far more allowance than this project needs; the escalation model is the one that can run short. Move to Go Plus ($40) only if Gemini 4 Argon's weekly allowance stops a high-assurance task. Keep **Extra Usage off** so a cap stops work instead of spending pay-as-you-go credit.

| Role | Model ID (confirm with `/models`) | Monthly cap on Go | ≈ requests / 5 h | Retention / training | Use for |
|---|---|---:|---:|---|---|
| Default implementer | `opencode-go/deepseek-v4.1-flash` | $100 | 43,330 | 0 days* / no | First attempt on every task, HA included |
| Escalation | `opencode-go/gemini-4-argon` | $30 | 440 | 0 days / no | After 2 failed repair cycles, or when review finds a Critical/High issue the default model could not fix |
| Hard-problem consult | `opencode-go/kimi-k3.1-pro` | $15 | 147 | 0 days / no | One short session on a single stuck problem (a race, a migration); not whole tasks |
| Fallback, different family | `opencode-go/glm-5.3-flash` | $60 | 6,320 | 0 days / no | Default model unavailable or out of allowance |

\* DeepSeek's zero-retention agreement is renewed monthly; the current one is valid to 30 Nov 2026. If it lapses, make `glm-5.3-flash` the default until it is renewed.

Why these: DeepSeek V4.1 Flash scores 77.0 on DeepSWE v1.1 at about $0.20 a task and has the largest allowance in Go. Gemini 4 Argon is the strongest agentic model in Go with a usable allowance (Terminal-Bench 4.0 57.4, DeepSWE 77.9, vendor-reported). Kimi K3.1 Pro scores higher on Terminal-Bench 4.0 (65.7) but was released on 23 Oct 2026, is verbose and has the smallest allowance. All figures are vendor or third-party benchmarks, not Hatch results; P1 and P2 are the real qualification.

**Do not use:** Muse Spark Contributor and Iceman Contributor Free (they train on prompts). Models with 30-day retention (GPT Luna, Grok, Claude Haiku 5.5, Beam Free) are not needed; keep to the table.

**Monthly check (1st of each month):** run `/models`, re-read the Go privacy table, update this table if a model leaves the plan or changes cap, and note it in the next PR's evidence.

### 1.3 Claude Code: models

| Work | Model | Why |
|---|---|---|
| `/phase2-red` for P2, P6, P9 | Opus 5.5 | The RED tests are the contract a cheaper model implements against; they must be right |
| `/phase2-review` for P2, P6, P9 and the P9 release review | Opus 5.5 | Fencing, deletion and migrations |
| `/phase2-review` for P0, P1, P3, P4, P5, P7, P8 | Sonnet 5.5 | Standard review; switch to Opus if it finds something it cannot settle |

Set the model with `/model` before running the command. The reviewer reads the PR diff, runs the tests itself and checks the UI against the screenshots in `docs/visual-evidence/coach-phase2-design/screens/`.

### 1.4 Files in the repository

| File | Read by | Purpose |
|---|---|---|
| `AGENTS.md` | OpenCode (and Claude Code through `CLAUDE.md`) | Project rules, task loop, stop conditions |
| `opencode.json` | OpenCode | Default model, `argon`, `consult` and `fallback` agents, permissions (ask before push, rebase, amend or reset; no force push, merge or branch deletion; no edits to protected files) |
| `CLAUDE.md` | Claude Code | Imports `AGENTS.md`; sets the reviewer role |
| `.claude/commands/phase2-red.md` | Claude Code | Writes and commits the RED contract tests for an HA task |
| `.claude/commands/phase2-review.md` | Claude Code | Reviews one task's PR |

Switching OpenCode model: press Tab to switch to the `argon`, `consult` or `fallback` agent, or use `/models`. Record every switch and its reason in the evidence report.

### 1.5 Claude Code-authored tests for HA tasks

1. Before OpenCode starts an HA task, Claude Code runs `/phase2-red <task>` on the task branch: it writes the named RED tests from this plan, runs them to show they fail for the right reason, and commits `test(coach): RED contract for <task>`. It writes the commit SHA and test paths to `docs/implementation-reports/coach-phase2/PN-red.md`.
2. OpenCode implements until GREEN. It may add tests but must not edit or delete the files listed in `PN-red.md`.
3. Review check: `git diff --name-only <red-sha>..HEAD -- <listed paths>` prints nothing.
4. If a RED test is wrong, OpenCode stops and reports; Claude Code fixes its own test.
5. RED tests use only the interfaces in spec §10.1 and names already in the codebase. If a test needs anything else (a helper, a fixture factory, a DTO field), Claude Code lists it under **Assumed interfaces** in `PN-red.md`; the owner approves the list before OpenCode starts, and the list is then binding for the implementation.

**Protected files.** `opencode.json` denies OpenCode edits to the spec, this plan, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, `.claude/` and the design folder, but a shell command could still change them. Every `/phase2-review` therefore runs `git diff --name-only <base>..HEAD -- <protected paths>`; any output is a **Critical** finding.

Why: cheaper models sometimes write tests that mock their own mistakes. Separating who writes the contract from who implements it removes that failure.

### 1.6 Qualification by real tasks

No separate pilot tasks. P1 (pure functions plus small UI) qualifies the default model for standard work. P2 (migration plus FK cascade, HA) qualifies it for high-assurance work. Record each in the PR evidence:

```json
{"harness": "opencode", "opencode_version": "…", "model_id": "opencode-go/…", "effort": "…",
 "task_class": "standard | high_assurance", "qualifying_task": "P1 | P2",
 "review_verdict": "qualified | rejected", "baseline_sha": "…", "date": "2026-…"}
```

A model change, or a serious ownership or deletion regression, re-opens qualification on the next task of that class.

## 2. Delivery order

| PR | Wave | Outcome | Spec | HA | Model |
|---|---|---|---|---|---|
| P0 | 0 | Handoff pack checked, gate report, Phase 2 bench suite + harness profile | §3, §9.4 | — | Flash |
| P1 | 0 | Story coverage map (backend + Stories strip + application view) | M4 | — | Flash |
| P2 | 0 | Debrief capture: table, readiness routes, form, readiness next-actions + Today merge, display timezone | M6 (no extraction) | **HA** | Flash → Argon; Claude Code RED first (Opus) |
| P3 | 0 | Catalogue/discovery policy (licence + status), pinned llama.cpp build, tier map, optional `llm-deep` profile, Settings tier table, bench runs with the dual gate | M8 | — | Flash |
| — | — | **Gate:** Wave 1 readiness check (spec §3.2) recorded in P4's evidence; R7–R9 are paused | §3.2 | — | — |
| P4 | 1 | Patterns: `load_learning_snapshots` seam, derivation, dismissals, Readiness page | M1 | — | Flash |
| P5 | 1 | Focus areas + practice plan | M2, M3 | — | Flash |
| P6 | 1 | `source_events` hooks, runtime bindings, derived-text cache, fencing, cascade, Explain | M7, M9 cascade, §10 | **HA** | Flash → Argon; Claude Code RED first (Opus) |
| P7 | 1 | Brief: skeleton, enhancement fingerprint, scheduler, archive, brief next-actions | M5, S3 | — | Flash |
| P8 | 1 | Real-interview signals, debrief extraction (Tier T), competency extraction, QB/story proposals | M1 signals, M6, S2 | — | Flash |
| P9 | 1 | What Hatch remembers page, journey + security tests, rollout evidence | M9, §14, §15 | **HA** | Flash → Argon; Claude Code RED first (Opus) |

Wave 0 PRs must not touch files on R7/R8's lists (`coach_session_queue.py`, `coach_reconciliation.py`, `conversational_session_repository.py`, `coach_attempt_pipeline.py`, `routers/coach.py`, `async_job_service.py`, cover-letter files). No Phase 2 PR changes `routers/interviews.py` or `routers/applications.py` (spec §12). Bring the branch up to date with `git merge main` before review; rebase only after asking the owner.

## 3. Common workflow (every PR)

1. `git switch main && git pull --ff-only`; record `git rev-parse HEAD`; `git switch -c coach-p2/<task-id>-<short-name>` (for HA tasks, check out the branch Claude Code created with the RED commit).
2. Read the spec sections listed for the task and the files named below.
3. Write (or, for HA, receive from Claude Code) the named tests; run them; record the RED failure.
4. Implement the minimum to pass. No unrelated refactors.
5. Run focused tests plus the listed regressions; `ruff check` on changed backend files; `npm run type-check` when frontend changed; `git diff --check`.
6. Write `docs/implementation-reports/coach-phase2/PN-evidence.md` (template §6).
7. Commit exact paths with the listed message. Ask the owner before pushing; open the PR. Stop for Claude Code review.
8. Fix findings; at most 2 repair cycles before escalation (plan §1.2).

## 4. Wave 0 tasks

### P0 — Check the handoff pack, gate report, bench suite

The owner commits the handoff pack before P0 (spec, this plan, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, `.claude/commands/`, `docs/architecture/coach-phase2-readiness-loop.html`, `docs/visual-evidence/coach-phase2-design/`) and adds the one-line `docs/README.md` index entry by hand (HANDOFF.md). P0 does not edit those files.

**Files**
- Add: `backend/benchmarks/coach/fixtures/phase2_v1/` — manifest + 48 synthetic cases (spec §9.4): `explain_*.json` ×15, `brief_enhance_*.json` ×15, `debrief_extract_*.json` ×10, `competency_extract_*.json` ×8; tuning/holdout split recorded in the manifest. Tier T cases fit the budget in spec §9.1 (instructions ≤ 300, input ≤ 1,200, output ≤ 512 tokens), and at least a third of each task's cases are sized within 20 % of that task's input maximum (spec §9.4). Input limits follow spec §7.6 and §10 (debrief notes ≤ 2,500 characters; explain tips ≤ 40 words each and ≤ 120 in total; debrief output ≤ 12 questions of ≤ 120 characters).
- Modify: `backend/benchmarks/coach/profiles.py` — add `phase2` profile (scenario ids from the manifest, timeouts per tier maxima spec §9.3)
- Modify: `backend/benchmarks/coach/contracts.py` / `runner.py` only through existing extension points to score: schema-valid, grounding violations, latency including queue time, TTFT, tokens/s, peak RSS
- Add: `backend/benchmarks/coach/phase2_checks.py` — **real** grounding checks (every cited story or fingerprint id was supplied; every number in the text appears in the supplied story; no capitalised name absent from the supplied text; word and character limits per spec §10), not a stub that returns no violations. P6 replaces it with a re-export of `grounding.py`
- Add: a bench-only execution path for the stages `explain`, `brief_enhance`, `debrief_extract` and `competency_extract` (file chosen by the implementer through the harness's existing adapter extension point; do not add them to `production_adapter.py` unless that is the only extension point, and say so in the evidence). It sends a versioned bench prompt per task to the loopback llama-server, parses and validates the output with `phase2_checks`, and records latency including queue time, TTFT, tokens/s and the server's peak RSS (how it is captured, e.g. `docker stats` or `/proc`, is written in the evidence). Output caps and per-case deadlines come from the task's tier (T: 512 tokens and 60 s; S: 600 tokens and 180 s)
- Modify: `backend/benchmarks/coach/fixtures/phase2_v1/models.json` — `context_size` matches production (`llm-triage` 4096 with 2 slots, i.e. 2,048 per request; `llm-primary` 16384)
- Add: `backend/tests/benchmarks/coach/test_phase2_suite.py`
- Add: `docs/implementation-reports/coach-phase2/P0-entry.md`

**Steps**
- [ ] Record HEAD, migration head (`alembic heads`), Python/Node versions, status of R7/R8/R9 (merged PRs and report presence). Gate verdict: Wave 0 = GO; Wave 1 = pending its readiness check (spec §3.2), run at the start of P4.
- [ ] Confirm the Go model IDs in plan §1.2 with `/models` and the Go privacy table; if any differ, stop and report (the owner updates plan §1.2 and `opencode.json`). Write qualification placeholders.
- [ ] Confirm `python scripts/check_docs.py` passes with the handoff pack installed.
- [ ] Tests: suite manifest loads; every case validates against its task schema; Tier T cases fit the token budget (count with the tokenizer the harness already uses, or 4 characters per token if none); no case contains strings from `data/` (scan for email/phone patterns); every model in `phase2_v1/models.json` is loopback and the loader rejects a non-loopback `phase2` suite; `phase2_checks` flags an unknown id, a number absent from the story, and an over-length text (positive and negative cases); the bench-only execution path runs all four stages against a **fake loopback HTTP server** (no live model) and records latency, TTFT, tokens/s and a peak-RSS value.
- [ ] Run `python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py`; RED, then GREEN.
- [ ] Run `python scripts/check_docs.py` and `python scripts/check_readme_contract.py`.
- [ ] Commit: `test(coach): add phase 2 bench suite and entry report`

The suite is built here; the model bench **runs** happen in P3 once the pinned llama.cpp build exists.

### P1 — Story coverage map (M4)

**Read first:** `services/story_service.py`, `repositories/story_repository.py`, `models/story.py`, `models/job.py`, `models/job_score.py`, `routers/stories.py`, `benchmarks/coach/fixtures/stopwords_en.txt`. `StoryMatcher` is **not** used (spec §7.4).

**Files**
- Add: `backend/app/services/coach_readiness/__init__.py`, `contracts.py` (coverage DTOs only for now), `coverage.py`, `stopwords_en.txt` (copy of the benchmark list; a test keeps them identical)
- Add: `backend/app/models/coach_readiness.py` with `coach_competency_overrides` only
- Add: Alembic revision `add coach competency overrides` (generate with `alembic revision`; do not hand-pick `down_revision`)
- Add: `backend/app/schemas/coach_readiness.py` (coverage), `backend/app/routers/coach_readiness.py` (coverage routes only), register in `main.py`
- Modify: `backend/app/config.py` — `HATCH_COACH_STORY_COVERAGE_ENABLED=False`, `HATCH_COACH_COVERAGE_COVERED_MIN=0.67`, `HATCH_COACH_COVERAGE_THIN_MIN=0.34`
- Add: `frontend/src/lib/coachReadinessApi.ts`, `frontend/src/components/coach/readiness/CoverageMap.tsx`, `CoverageStrip.tsx`
- Modify: Stories page (strip) and application detail (coverage panel) via their existing components
- Tests: `backend/tests/test_services/test_coach_coverage.py`, `backend/tests/test_routers/test_coach_coverage_router.py`, `frontend/src/components/coach/readiness/__tests__/CoverageMap.test.tsx`

**Named tests**
| Test | Asserts |
|---|---|
| `test_competency_order_misses_then_matches_then_skills` | Order and de-duplication by match key per §7.4; cap 12 |
| `test_match_key_never_shown_original_text_kept` | "process" stays "process" in the response; match key is internal (AC10) |
| `test_stopwords_copy_matches_benchmark_list` | The two files are identical |
| `test_containment_one_word_competency_in_tags_scores_one` | AC11 |
| `test_story_without_result_is_never_covered` | AC11 |
| `test_inactive_story_never_counts` | AC11; `is_active = false` excluded |
| `test_has_metric_is_information_only` | Status unchanged by `metrics` |
| `test_thresholds_come_from_config` | Changing config changes status; no literals in `coverage.py` |
| `test_overrides_rename_and_hide` | Overrides apply by match key |
| `test_overview_counts_gaps_across_interview_applications` | Only applications in `interview` status |
| `test_flag_off_blocks_override_writes_but_allows_reads` | AC25 pattern for this feature |
| `CoverageMap.test.tsx` | Three statuses render with icon + text; "Draft a story" links with competency prefilled; keyboard reachable |

**Calibration:** add `backend/tests/fixtures/coach_coverage/` with 10 synthetic JD/story pairs labelled by hand; record precision/recall of `covered` and the chosen thresholds in the evidence report. Change config defaults only if the fixtures justify it.

- [ ] RED → GREEN; regressions: `tests/test_services/test_story*`, `tests/test_routers/test_stories*`.
- [ ] Commit: `feat(coach): add story coverage map for interview competencies`

### P2 — Debrief capture (M6, without extraction) — HA

**Claude Code writes RED tests first** (plan §1.5) against the `DebriefService` interface in spec §10.1, for the migration, cascade, round-mirroring and status tests below.

**Read first:** `models/application.py` (`InterviewRound`), `routers/interviews.py`, the repository used by interviews, `interviews_ical.py` (UTC rule), the frontend round form, `services/question_bank.py`, the application deletion path.

**Files**
- Modify: `backend/app/models/coach_readiness.py` — add `coach_interview_debriefs` including the nullable `notes_text` column (used from P8)
- Add: Alembic revision `add coach interview debriefs`
- Add: `backend/app/services/coach_readiness/questions.py` (likely questions, spec §7.5 section 2; archived items excluded), `debrief.py`, `next_actions.py` (debrief action only for now)
- Modify: `schemas/coach_readiness.py`, `routers/coach_readiness.py` — routes `/coach/readiness/rounds/{round_id}/debrief`, `.../debrief/skip`, and `GET /coach/readiness/next-actions` (spec §12). **No change to `routers/interviews.py` or `routers/applications.py`.**
- Modify: `config.py` — `HATCH_COACH_DEBRIEF_ENABLED=False`, `HATCH_DISPLAY_TIMEZONE` (optional IANA name, validated at startup)
- Add: `frontend/src/components/coach/readiness/DebriefForm.tsx`; wire into the interview round view; Today page requests `/coach/readiness/next-actions` alongside `/applications/next-actions` and merges the lists; a shared `formatInterviewTime` helper for the display timezone
- **Timezone check:** find how the round form submits `scheduled_at`. If it sends browser-local time without an offset, fix it in the frontend round form: convert to UTC before sending, with a Vitest test (do not change existing rows), and note the finding in the evidence. Do not change `routers/interviews.py`; if you think it must change, stop and ask the owner.
- Tests: `backend/tests/test_migrations/test_coach_debrief_migration.py`, `backend/tests/test_services/test_coach_debrief.py`, `backend/tests/test_services/test_coach_questions.py`, `backend/tests/integration/test_coach_debrief_cascade.py`, `frontend/src/components/coach/readiness/__tests__/DebriefForm.test.tsx`, `frontend/src/lib/__tests__/formatInterviewTime.test.ts`

**Named tests**
| Test | Asserts |
|---|---|
| `test_migration_single_head_and_fk_cascade` | One head; FK enforced; downgrade/upgrade on disposable DB |
| `test_debrief_due_when_completed_or_time_passed` | AC15 debrief side; `scheduled` and `rescheduled` both; default duration 60 min when unset |
| `test_cancelled_round_never_due_saved_debrief_kept` | AC32 |
| `test_rescheduled_round_moves_due_time` | AC32 |
| `test_save_mirrors_questions_into_round_via_repository` | AC16; no direct SQL on `interview_rounds` from `debrief.py` (import check) |
| `test_round_delete_cascades_debrief` / `test_application_delete_leaves_no_orphans` | AC17 |
| `test_practice_session_delete_keeps_debrief` | AC18 |
| `test_questions_capped_and_text_limits` | ≤ 20 questions; ≤ 200 chars each; free text ≤ 1,000; `notes_text` ≤ 2,500 |
| `test_questions_json_item_shape` | `{id, text, source_ref, asked, rating, story_id, note}` (spec §7.6) |
| `test_likely_questions_order_and_archived_excluded` | Linked → role family → session plan; archived QB items never appear |
| `test_skip_then_start_later` | §8.5 transitions; illegal transition → 409 `invalid_state` |
| `test_next_actions_includes_debrief_prompt` | Only for rounds due and not saved/skipped; served by the readiness router |
| `test_round_times_returned_as_utc_z` | AC33 backend side |
| `DebriefForm.test.tsx` | Checklist first; save with only overall rating; 409 keeps draft; keyboard and labels |
| `formatInterviewTime.test.ts` | AC33: `HATCH_DISPLAY_TIMEZONE` wins, else browser zone; abbreviation shown |

- [ ] RED (Claude Code) → GREEN; regressions: `tests/test_routers/test_interviews*`, `tests/test_services/test_application_service.py`, Today page tests.
- [ ] Commit: `feat(coach): capture real-interview debriefs on interview rounds`

### P3 — Local model tiers: catalogue, pinned runtime, bench runs (M8)

**Read first:** `config/model_catalog.json`, `config/model_discovery_policy.json`, `services/model_discovery.py`, `scripts/hatch_cli.py` (catalogue use), `docker-compose*.yml`, `runtime/intelligence/registry.py`, `docs/operations/REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md`.

**Files**
- Modify: `docker-compose.yml`, `docker-compose.local-ai.yml` — pin llama.cpp server image to a build ≥ b10828 by tag **and** digest; add `llm-deep` service under profile `deep` (port 8082, same image)
- Modify: `config/model_discovery_policy.json` — publishers, families, marker, task and Bonsai quantisation rules (§9.2, D18); add `lfm1.0` to `approved_licenses` (owner-approved, D18)
- Modify: `services/model_discovery.py` — honour the family-allowlist exemption and text-only use of `image-text-to-text`
- Modify: `config/model_catalog.json` — candidate entries with real revisions and sha256 taken from the downloaded files; add `tiers` and `status`; existing entries get `status: "promoted"`
- Add: `config/model_tiers.json` + loader/validator in `backend/app/services/coach_readiness/tiers.py` (or the existing model registry module if it already owns config loading — follow the registry)
- Modify: Settings AI page — read-only tier table; Tier L opt-in hidden below 24 GB RAM
- Tests: `tests/test_services/test_model_discovery.py` (extend), `tests/test_services/test_model_tiers.py`, `tests/test_scripts/` catalogue checks, Settings component test
- Add: `docs/implementation-reports/coach-phase2/P3-local-model-bench.md` (bench results, both gates)

**Named tests**
| Test | Asserts |
|---|---|
| `test_policy_accepts_spark_and_minicpm_families_only_from_allowlisted_publishers` | Allowlist, not wildcard; the same holds for the D18 families (`bonsai`, `lfm2`, `gemma-4`, `qwen3.8`) |
| `test_bonsai_accepts_upstream_1_and_2_bit_quants_only` | `Q1_0`/`Q2_0` accepted for `bonsai` only; fork-only `PQ2_0`/`PTQ1_0` refused |
| `test_vision_repo_accepted_text_only_without_mmproj` | No projector file selected |
| `test_unapproved_licence_rejected` | An entry whose licence is not in `approved_licenses` (for example `cc-by-nc-4.0`) is refused; an `lfm1.0` entry is accepted |
| `test_catalog_entries_have_revision_sha_tiers_and_status` | Schema; no empty hashes; existing entries `promoted` |
| `test_tier_map_rejects_non_promoted_model` | AC20, AC35 |
| `test_tier_t_budget_enforced` | AC34: input truncated to ≤ 1,200 tokens, output cap 512 |
| `test_tier_l_hidden_below_24gb` | AC22 |
| `test_phase1_routes_unchanged` | Existing Coach routes still resolve to their current models |

**Bench runs (owner machine, synthetic data only)**
- [ ] **Thinking check first:** on the pinned build, send one request with `chat_template_kwargs: {"enable_thinking": true}` to a server started with `--reasoning off`. Record whether reasoning text appears. If it does not, bench thinking off only (spec §9.1).
- [ ] **Licence check:** re-read each candidate's model card; skip any whose licence is not in `approved_licenses` (Gemma 4 unless its linked licence page is plain Apache-2.0; `lfm1.0` is approved) and record why.
- [ ] Start pinned llama-server per candidate with the production flags (`llm-triage`: `--ctx-size 4096 --parallel 2`; `llm-primary`: `--ctx-size 16384 --parallel 1`; both `--reasoning off`); run `python -m benchmarks.coach run --profile phase2 …` (exact CLI per existing harness) for the spec §9.1 bench order: Tier T — MiniCPM-V-4.7-1B (text), MiniCPM5-2B, Gemma 4 E2B (text), Bonsai 1.7B, LFM2.5-1.2B-Instruct, Qwen3.5-0.8B; Tier S — Spark-X2.6-4B, Gemma 4 E4B (text), Bonsai 4B, Bonsai 8B, LFM2.5-8B-A1B, MiniCPM5-2B, phi4-mini, Qwen3.5-4B; Tier L — MiniCPM-V-4.7-35B-A3B Q4, Gemma 4 26B-A4B, Gemma 4 12B, Ternary-Bonsai-2-27B Q2_0, LFM2-24B-A2B, Qwen3.8-27B. Licence-gated models are run only after the licence check passes. A newer release in an allowlisted family (for example a Qwen3.8 model of 4B or less) is added as a `candidate` and benched the same way; a name with no GGUF, or one the pinned mainline build cannot load, is recorded as skipped.
- [ ] Each on reference CPU-only, reference with GPU offload, and floor profile (T and S only).
- [ ] Two independent runs on holdout; owner blind-rates 10 outputs per candidate.
- [ ] **Dual gate (spec §9.1):** for every T or S candidate that passes the §9.4 gate, run the route's existing regression bench on the same build — Tier S: Phase 1 `python -m benchmarks.coach run --profile acceptance-smoke`; Tier T: the job-scoring triage checks in `REPRESENTATIVE_LOCAL_MODEL_BENCHMARK.md`. Only a model that passes both becomes `promoted`; otherwise it stays `qualified` and the incumbent stays.
- [ ] Rerun the Phase 1 `acceptance-smoke` profile on the new llama.cpp build with the existing Phase 1 models; record any change. If Phase 1 regresses, keep the old image for Phase 1 routes and pin the new one only for `llm-deep`.
- [ ] Set `model_tiers.json` to promoted models only; set deadlines per §9.3 from p95 including queue time.
- [ ] Commit: `feat(runtime): add bench-gated local model tiers for coach readiness`

## 5. Wave 1 tasks (after the readiness check)

**P4 starts by recording the four-point readiness check from spec §3.2 in its evidence report.** If any point fails, stop and report; do not start P4 code.

### P4 — Patterns (M1)

**Files**
- Modify: `services/coach_conversational_progress.py` — add `evaluation_contract_version`, `difficulty` to `ProgressSnapshot` with defaults (spec §7.1.6)
- Modify: `repositories/conversational_session_repository.py` — add `load_learning_snapshots(*, limit=1000)` only; existing methods unchanged
- Add: `services/coach_readiness/patterns.py`; extend `contracts.py`
- Modify: `models/coach_readiness.py` + migration — `coach_pattern_dismissals`
- Modify: schemas/router — pattern routes (§12)
- Modify: `config.py` — `HATCH_COACH_READINESS_ENABLED=False`, `HATCH_COACH_PATTERN_WINDOW_DAYS=90`
- Add: `frontend/src/app/coach/readiness/page.tsx`, components `PatternCard.tsx`, `PatternGroup.tsx`, `WhyPanel.tsx`
- Tests: `tests/test_services/test_coach_patterns.py`, `tests/test_repositories/test_load_learning_snapshots.py`, `tests/test_routers/test_coach_patterns_router.py`, `__tests__/PatternCard.test.tsx`

**Named tests** (parameterised from spec Appendix A)
| Test | Asserts |
|---|---|
| `test_attempts_in_one_session_do_not_recur` | AC01 |
| `test_difficulty_not_in_group` | AC02 |
| `test_contract_versions_never_merge` | AC03 |
| `test_latest_three_kept_regardless_of_age_then_marked_stale` | AC04, injected clock |
| `test_dismissal_reappears_on_new_support` | AC05 |
| `test_trend_labels_respect_difficulty` | AC37: improving/easier, getting weaker/harder |
| `test_load_learning_snapshots_all_groups_and_unspecified_role` | Sessions without role family included as `unspecified` |
| `test_load_learning_snapshots_excludes_sessions_being_deleted` | `deletion_state != 'not_requested'` excluded |
| `test_why_is_deterministic_and_uses_stored_excerpts_only` | §7.7 Why |
| `test_existing_progress_trend_unchanged` | Phase 1 progress regressions |
| `PatternCard.test.tsx` | Forming shows "1 of 2"; kind uses icon + text; trend labels; dismiss/undo; glossary copy (§13.4) |

- [ ] Regressions: `tests/test_services/test_coach_conversational_progress.py`, the conversational session repository tests, and Phase 1 report/progress UI tests.
- [ ] Commit: `feat(coach): derive practice patterns across sessions`

### P5 — Focus areas and practice plan (M2, M3)

**Files**
- Add: `services/coach_readiness/focus.py`, `plan.py`
- Modify: models + migration — `coach_focus_areas` (with `active_slot`, checks and unique index, spec §11), `coach_practice_plans` (partial unique index on active plan)
- Modify: schemas/router — focus and plan routes
- Add: components `FocusAreas.tsx`, `FocusAreaEditor.tsx`, `PracticePlan.tsx`
- Phase 1 session setup: accept prefilled role family, interview type and difficulty via query parameters on the existing setup route (frontend only; no Phase 1 backend change)
- Tests: `tests/test_services/test_coach_focus.py`, `tests/test_services/test_coach_plan.py`, `tests/integration/test_coach_focus_concurrency.py`, router tests, component tests

**Named tests**
| Test | Asserts |
|---|---|
| `test_fourth_active_focus_area_rejected` | AC06 limit |
| `test_concurrent_activation_one_wins` | AC31: two sessions, two activations with 2 active → one success, one `limit_reached` |
| `test_stale_version_conflict_keeps_state` | AC06 409 |
| `test_level_criterion_requires_group` | AC07 |
| `test_level_criterion_counts_only_post_creation_same_group` | AC07 |
| `test_practice_items_never_satisfy_level_criterion` | AC07 |
| `test_plan_fits_whole_items_and_reports_unallocated` | AC08 |
| `test_focus_areas_in_one_group_share_one_practice_item` | AC09 |
| `test_met_focus_areas_skipped` | §7.3 rule 1 |
| `test_round_within_seven_days_orders_story_review_story_practice` | §7.3 rule 2 |
| `test_plan_due_at_round_minus_two_hours` | AC09 |
| `test_round_under_two_hours_is_invalid_input` | AC09 |
| `test_one_session_completes_every_open_practice_item_in_group` | AC09 |
| `test_single_active_plan_enforced_by_index` | Two concurrent starts → one active |
| `test_plan_expiry_after_14_days_or_round_passed` | §8.3 |

- [ ] Commit: `feat(coach): add focus areas and interview-aware practice plans`

### P6 — Source events, runtime bindings, cache, fencing, cascade, Explain — HA

**Claude Code writes RED tests first** (plan §1.5) against the interfaces in spec §10.1, for the hook, fencing, dedupe, cascade, import-direction and canary tests.

**Files**
- Add: `services/source_events.py` (spec §5.3)
- Modify: `repositories/conversational_session_repository.py` — `source_events.notify` in `delete_attempt_transcript` (`edited`), `claim_hard_deletion` (`deactivated`), `finalise_hard_deletion` (`deleted`), each in the method's own transaction; nothing else
- Modify: `repositories/story_repository.py` — `notify` in `update` (`edited`) and `soft_delete` (`deleted`)
- Modify: `services/question_bank.py` — `notify` in `update_question_bank_item` (`edited`) and `archive_question_bank_item` (`deleted`)
- Modify: `main.py` lifespan — `source_events.register_listener(ReadinessPrivacy(...))`
- Add: `runtime_bindings/tasks/coach_readiness.py` — 5 TaskSpecs (§10), prompts versioned, output schemas, thinking off
- Add: `runtime_bindings/context/coach_readiness.py` — content providers that resolve references at execution time (including the requirement-line pre-extraction for `competency_extract`, §10)
- Modify: `runtime_bindings/capabilities/registry.py` — register local-capable capabilities (declare local execution correctly; do not weaken egress policy)
- Add: `services/coach_readiness/grounding.py`, `explain.py`, `privacy.py` (`ReadinessPrivacy` listener only; inventory and deletion arrive in P9), `finalise_generation` in `contracts.py`
- Modify: `benchmarks/coach/phase2_checks.py` — replace the P0 copy with a re-export of `grounding.py` so bench and production use one implementation
- Modify: models + migration — `coach_derived_text`, `coach_derived_sources` (index on `source_kind`, `source_id`)
- Modify: router — tips + operations routes
- Add: `PatternTips.tsx` (instant skeleton, live region for arriving text)
- Tests: `tests/test_services/test_source_events.py`, `tests/runtime/test_coach_readiness_bindings.py`, `tests/test_services/test_coach_grounding.py`, `tests/integration/test_coach_readiness_fencing.py`, `tests/integration/test_coach_readiness_cascade.py`, `tests/security/test_coach_readiness_canary.py`, `tests/architecture/test_coach_readiness_imports.py`

**Named tests**
| Test | Asserts |
|---|---|
| `test_notify_runs_listeners_in_callers_transaction` | Listener sees the caller's session; does not commit |
| `test_listener_error_rolls_back_source_change` | AC29 second half |
| `test_notify_runs_before_media_removal` | AC29: with a failing listener, the transcript audio file is still present after the rollback; same for `finalise_hard_deletion` |
| `test_transcript_delete_purges_derived_text` | AC29 |
| `test_claim_purges_and_finalise_purges_again` | AC23 |
| `test_session_deleted_mid_generation_is_fenced` | AC23; reload DB; no derived text references the session |
| `test_activity_version_change_fences_generation` | §10 fencing |
| `test_story_edit_and_soft_delete_purge_derived_text` | AC30 |
| `test_qb_edit_and_archive_purge_derived_text` | AC30 |
| `test_generation_after_story_soft_delete_is_fenced` | AC30 |
| `test_existing_domains_do_not_import_coach_readiness` | AC36 (AST scan of `backend/app`) |
| `test_same_fingerprint_dedupes_to_one_generation` | AC19 |
| `test_supporting_session_edit_purges_tips` | AC19 |
| `test_one_generation_plus_one_repair_max` | Counts real dispatches including SDK retries |
| `test_deadline_absolute_across_repair_including_queue` | §9.3 |
| `test_grounding_rejects_unknown_ids_and_new_numbers` | AC13 (shared with P7) |
| `test_explain_word_limits` | ≤ 3 tips, ≤ 40 words each, ≤ 120 total |
| `test_ai_mode_none_creates_no_requests` | §10 |
| `test_route_unavailable_degrades_within_1s` | AC21 |
| `test_content_canary_absent_from_runtime_records_events_logs` | §15 canary |
| `test_thinking_text_stripped_from_output` | §9.1 |

- [ ] Regressions: `tests/runtime/` (full), Phase 1 privacy and deletion suites, story and Question Bank suites.
- [ ] Commit: `feat(coach): add fenced local generation and derived-data cascade`

### P7 — Pre-interview brief (M5, S3)

**Files**
- Add: `services/coach_readiness/brief.py`, `scheduler.py`
- Modify: `next_actions.py` — brief actions ("Interview in 3 days — brief ready", "Add your interview date to get a brief")
- Modify: models + migration — `coach_interview_briefs` (`enhancement_state`, `enhancement_fingerprint`, `enhanced_text_id`, `archived_at`)
- Modify: router — `GET /coach/readiness/rounds/{round_id}/brief`, `POST .../brief/tips`
- Modify: `main.py` lifespan — register the scheduler job (every 30 min) on the existing APScheduler instance
- Modify: `config.py` — `HATCH_COACH_BRIEF_ENABLED=False`
- Add: components `InterviewBrief.tsx`, `BriefSection.tsx`, print stylesheet; Brief tab on the interview round view; Readiness "Next interview" card. **No Refresh button** (spec §13.2 rule 10).
- Tests: `tests/test_services/test_coach_brief.py`, `tests/integration/test_coach_brief_lifecycle.py`, `tests/test_services/test_coach_readiness_scheduler.py`, component tests, `frontend/e2e/coach-readiness-brief.spec.ts`

**Named tests**
| Test | Asserts |
|---|---|
| `test_brief_ready_with_ai_off_all_sections` | AC12 |
| `test_section_limits_and_source_order` | §7.5 table |
| `test_round_type_maps_to_practice_interview_types` | §7.5 mapping table |
| `test_role_family_from_latest_linked_session` | §7.5; none → "Practise for this role to get watch-outs" |
| `test_skeleton_reflects_edits_on_next_read` | AC14 first half; skeleton never stored |
| `test_fingerprint_change_hides_tips_and_requeues_once` | AC14 |
| `test_bad_enhancement_discarded_skeleton_kept` | AC13 |
| `test_purged_tips_read_as_none_and_requeue` | AC14: text row purged → state `none`, never `current`; one enhancement queued with AI on |
| `test_brief_archives_after_round_time_or_completed` | AC15 |
| `test_cancelled_round_archives_brief` | AC32 |
| `test_scheduler_enhances_rounds_in_next_seven_days_only` | §7.5; skipped when AI off or flag off |
| `test_brief_without_round_date` | §7.5 anchor |
| `test_brief_times_in_display_timezone` | AC33 (component) |
| `test_print_layout_one_page` (e2e) | AC28 |

- [ ] Commit: `feat(coach): build pre-interview briefs from your own evidence`

### P8 — Signals, extraction and proposals (M1 signals, M6, S2)

**Files**
- Add: `services/coach_readiness/signals.py` (spec §7.1.5, derived on read)
- Modify: `brief.py` — watch-outs may include real-interview signals (spec §7.5 section 4)
- Modify: `debrief.py` — save rough notes into `notes_text`; extract route `POST .../debrief/extract` passes the **debrief id** to `coach.readiness.debrief_extract`; proposals (QB add for asked questions with no `source_ref` not already in the QB, story use)
- Modify: `coverage.py` — optional `competency_extract` (job id) when < 5 deterministic competencies
- Modify: router — signals in the overview response; extract and proposal routes
- Components: `RealInterviewSignals.tsx` (Readiness "From your real interviews" section), `DebriefNotesExtract.tsx`, `DebriefProposals.tsx`
- Tests: `tests/test_services/test_coach_signals.py`, `tests/test_services/test_coach_debrief_proposals.py`, component tests

**Named tests**
| Test | Asserts |
|---|---|
| `test_question_tagging_uses_source_item_and_contained_keys` | §7.1.5 tagging |
| `test_signal_needs_two_rounds` | AC38 |
| `test_signals_never_change_pattern_kind_or_trend` | AC38 |
| `test_brief_watchouts_include_signals_after_practice_patterns` | §7.5 section 4 |
| `test_notes_saved_before_extraction_and_passed_by_id` | §10; no note text in runtime records (canary) |
| `test_extract_is_a_proposal_until_confirmed` | Nothing saved without confirm; ≤ 12 questions × ≤ 120 chars |
| `test_qb_proposal_accept_is_idempotent` | AC27 |
| `test_only_unsourced_new_questions_proposed` | AC27; ticked likely questions never proposed |
| `test_story_use_recorded_through_public_route` | No direct table writes |
| `test_competency_extract_input_is_requirement_lines_within_budget` | AC34 |
| `test_extracted_competencies_labelled_and_capped` | ≤ 4, labelled |

- [ ] Commit: `feat(coach): add real-interview signals and debrief proposals`

### P9 — What Hatch remembers, acceptance, rollout — HA

**Claude Code writes RED tests first** (plan §1.5) against `ReadinessPrivacy.inventory`, `delete_kind` and `delete_all` (spec §10.1), for deletion-all and the journey.

**Files**
- Modify: `privacy.py` — inventory and delete-by-kind/all
- Modify: router — memory routes
- Add: `frontend/src/app/settings/privacy/remembers/page.tsx` (or the existing settings privacy route) + `RemembersList.tsx`; display-timezone line in Settings → General
- Add: `tests/integration/test_coach_readiness_journey.py`, `tests/security/test_coach_readiness_security.py`, `frontend/e2e/coach-readiness.spec.ts`
- Add: `docs/implementation-reports/coach-phase2/P9-release.md`

**Journey test:** two practice sessions in one group → pattern → focus area → plan started → round scheduled → brief "Ready" (AI off) → enhancement (fake model) → story edited → "Tips out of date" and one re-queue → round passes → debrief saved → QB proposal accepted → practice session hard-deleted (claim then finalise) → cached text gone, debrief kept → story soft-deleted → it leaves coverage and the brief → delete all readiness data → only Phase 1 data remains.

**Named tests**
| Test | Asserts |
|---|---|
| `test_delete_all_readiness_data_leaves_phase1` | AC24 |
| `test_flags_off_reads_and_deletes_work` | AC25 |
| `test_inventory_counts_match_rows` | Privacy page accuracy |
| `test_debrief_delete_optionally_clears_round_questions` | §7.8 |
| `test_api_rejects_unknown_fields_and_oversize_text` | §12 |

- [ ] Run the full CI-equivalent suite (§7). Owner runs the bench summary review and approves flags on.
- [ ] Commit: `docs(coach): record readiness loop acceptance and rollout`

## 6. Evidence template (`PN-evidence.md`)

```text
Task / spec sections / ACs:
Baseline SHA → head SHA:
OpenCode version · model ID · effort · switches (with reasons):
Claude Code RED commit (HA only) and untouched-tests check output:
Files changed (one line each: responsibility):
RED: test names and failure output (short):
GREEN: commands, exit codes, counts:
Regressions run:
Model calls in tests: fake / live (live only in P3 bench):
Privacy / deletion / fencing evidence:
Migration: heads before/after, downgrade/upgrade result:
Not run / known limits:
Ready for review: yes / no — why
```

Never paste credentials, real CV or transcript content, or `data/` paths.

## 7. Verification commands

Repo root: `python scripts/check_readme_contract.py`, `python scripts/check_docs.py`, `git diff --check`, `python scripts/dead_code_check.py`

Backend: `ruff check app/ tests/`, `python -m pytest -q --no-cov tests/runtime`, `python -m pytest --cov=app -q`, `alembic heads`, `python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/phase2_v1`

Frontend: `npm ci`, `npx vitest run`, `npm run type-check`, `npm run build`, `npx playwright test` (extend the integrated config to include the new specs)

Run the full suites at P4 start (readiness baseline), P6, and P9; focused suites otherwise.

## 8. Starting OpenCode on a task

In the repository root, start OpenCode (it reads `AGENTS.md` and `opencode.json`) and send:

> Task PN. Follow AGENTS.md. Read the plan section for PN and the spec sections it lists. First reply: task id, current HEAD, wave and gate status, your exact model ID, the files you will touch, and the first failing test you will run.

For HA tasks (P2, P6, P9) run `/phase2-red PN` in Claude Code first and push the branch, then start OpenCode on that branch.

## 9. Reviewing a task in Claude Code

When OpenCode reports "Ready for review", set the model (plan §1.3) and run `/phase2-review PN`. It returns findings ordered by severity, a compliance verdict and a quality/security verdict. Paste the findings to OpenCode; after fixes, run `/phase2-review PN` again on the new head. Merge only after both verdicts pass with no open Critical or High findings.

## 10. Requirement coverage

| Spec | PRs | AC |
|---|---|---|
| M1 | P4 (+P8 signals) | AC01–05, AC37, AC38 |
| M2, M3 | P5 | AC06–09, AC31 |
| M4 | P1 (+P8 extraction) | AC10–11 |
| M5 | P7 (+P2 timezone) | AC12–15, AC32 (brief), AC33 |
| M6 | P2, P8 | AC15–18, AC32 (debrief) |
| M7 | P6 | AC19 |
| M8 | P3, P6, P8 | AC20–22, AC34, AC35 |
| M9 | P6, P9 | AC23–25, AC29, AC30, AC36 |
| S1 (deferred) | — | AC26 deferred |
| S2 | P8 | AC27 |
| S3 | P7 | AC28 |
