---
title: Hatch Coach Phase 2 — Interview Readiness Loop — Implementation Plan
document_type: implementation-plan
status: active
implementation_status: not-started
last_verified: 2026-11-02
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
| Implementer | OpenCode with the OpenCode Go plan | One task per PR: tests (non-HA), code, evidence report | Edits Claude Code's RED tests, the spec, `AGENTS.md`, `CLAUDE.md` or `opencode.json`; merges; pushes without asking |
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
| `opencode.json` | OpenCode | Default model, `argon`, `consult` and `fallback` agents, permissions (no push without asking, no merge, no edits to spec or agent files) |
| `CLAUDE.md` | Claude Code | Imports `AGENTS.md`; sets the reviewer role |
| `.claude/commands/phase2-red.md` | Claude Code | Writes and commits the RED contract tests for an HA task |
| `.claude/commands/phase2-review.md` | Claude Code | Reviews one task's PR |

Switching OpenCode model: press Tab to switch to the `argon`, `consult` or `fallback` agent, or use `/models`. Record every switch and its reason in the evidence report.

### 1.5 Claude Code-authored tests for HA tasks

1. Before OpenCode starts an HA task, Claude Code runs `/phase2-red <task>` on the task branch: it writes the named RED tests from this plan, runs them to show they fail for the right reason, and commits `test(coach): RED contract for <task>`. It writes the commit SHA and test paths to `docs/implementation-reports/coach-phase2/PN-red.md`.
2. OpenCode implements until GREEN. It may add tests but must not edit or delete the files listed in `PN-red.md`.
3. Review check: `git diff --name-only <red-sha>..HEAD -- <listed paths>` prints nothing.
4. If a RED test is wrong, OpenCode stops and reports; Claude Code fixes its own test.

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
| P2 | 0 | Debrief capture: table, API, form, next-action | M6 (no extraction) | **HA** | Flash → Argon; Claude Code RED first (Opus) |
| P3 | 0 | Catalogue/discovery policy, pinned llama.cpp build, tier map, optional `llm-deep` profile, Settings tier table | M8 | — | Flash |
| — | — | **Gate:** Wave 1 readiness check (spec §3.2) recorded in P4's evidence; R7–R9 are paused | §3.2 | — | — |
| P4 | 1 | Patterns: snapshot seam, derivation, dismissals, Readiness page | M1 | — | Flash |
| P5 | 1 | Focus areas + practice plan | M2, M3 | — | Flash |
| P6 | 1 | Runtime bindings, derived-text cache, fencing, deletion cascade hooks, Explain | M7, M9 cascade, §10 | **HA** | Flash → Argon; Claude Code RED first (Opus) |
| P7 | 1 | Brief: skeleton, enhancement, stale/archive, Today actions | M5, S3 | — | Flash |
| P8 | 1 | Debrief extraction (Tier T), competency extraction, QB/story proposals | M6, S2 | — | Flash |
| P9 | 1 | What Hatch remembers page, journey + security tests, rollout evidence | M9, §14, §15 | **HA** | Flash → Argon; Claude Code RED first (Opus) |

Wave 0 PRs must not touch files on R7/R8's lists (`coach_session_queue.py`, `coach_reconciliation.py`, `conversational_session_repository.py`, `coach_attempt_pipeline.py`, `routers/coach.py`, `async_job_service.py`, cover-letter files). Rebase on `main` before review.

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

The owner commits the handoff pack before P0 (spec, this plan, `AGENTS.md`, `CLAUDE.md`, `opencode.json`, `.claude/commands/`, `docs/architecture/coach-phase2-readiness-loop.html`, `docs/visual-evidence/coach-phase2-design/`, and the `docs/README.md` index entries). P0 does not edit those files.

**Files**
- Add: `backend/benchmarks/coach/fixtures/phase2_v1/` — manifest + 48 synthetic cases (spec §9.4): `explain_*.json` ×15, `brief_enhance_*.json` ×15, `debrief_extract_*.json` ×10, `competency_extract_*.json` ×8; tuning/holdout split recorded in the manifest
- Modify: `backend/benchmarks/coach/profiles.py` — add `phase2` profile (scenario ids from the manifest, timeouts per tier maxima spec §9.3)
- Modify: `backend/benchmarks/coach/contracts.py` / `runner.py` only through existing extension points to score: schema-valid, grounding violations (stub interface; real checks arrive with `grounding.py` in P6 — until then the harness imports a local copy under `benchmarks/coach/phase2_checks.py`), latency, TTFT, tokens/s, peak RSS
- Add: `backend/tests/benchmarks/coach/test_phase2_suite.py`
- Add: `docs/implementation-reports/coach-phase2/P0-entry.md`

**Steps**
- [ ] Record HEAD, migration head (`alembic heads`), Python/Node versions, status of R7/R8/R9 (merged PRs and report presence). Gate verdict: Wave 0 = GO; Wave 1 = pending its readiness check (spec §3.2), run at the start of P4.
- [ ] Confirm the Go model IDs in plan §1.2 with `/models` and the Go privacy table; if any differ, stop and report (the owner updates plan §1.2 and `opencode.json`). Write qualification placeholders.
- [ ] Confirm `python scripts/check_docs.py` passes with the handoff pack installed.
- [ ] Tests: suite manifest loads; every case validates against its task schema; no case contains strings from `data/` (scan for email/phone patterns); harness refuses non-loopback endpoints for the `phase2` profile.
- [ ] Run `python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py`; RED, then GREEN.
- [ ] Run `python scripts/check_docs.py` and `python scripts/check_readme_contract.py`.
- [ ] Commit: `test(coach): add phase 2 bench suite and entry report`

The actual model bench runs happen in P3 once the pinned llama.cpp build exists.

### P1 — Story coverage map (M4)

**Read first:** `services/story_matcher.py`, `services/story_service.py`, `models/story.py`, `models/job.py`, `models/job_score.py`, `routers/stories.py`.

**Files**
- Add: `backend/app/services/coach_readiness/__init__.py`, `contracts.py` (coverage DTOs only for now), `coverage.py`
- Add: `backend/app/models/coach_readiness.py` with `coach_competency_overrides` only
- Add: Alembic revision `add coach competency overrides` (generate with `alembic revision`; do not hand-pick `down_revision`)
- Add: `backend/app/schemas/coach_readiness.py` (coverage), `backend/app/routers/coach_readiness.py` (coverage routes only), register in `main.py`
- Modify: `backend/app/config.py` — `HATCH_COACH_STORY_COVERAGE_ENABLED=False`, `HATCH_COACH_COVERAGE_COVERED_MIN=0.55`, `HATCH_COACH_COVERAGE_THIN_MIN=0.35`
- Add: `frontend/src/lib/coachReadinessApi.ts`, `frontend/src/components/coach/readiness/CoverageMap.tsx`, `CoverageStrip.tsx`
- Modify: Stories page (strip) and application detail (coverage panel) via their existing components
- Tests: `backend/tests/test_services/test_coach_coverage.py`, `backend/tests/test_routers/test_coach_coverage_router.py`, `frontend/src/components/coach/readiness/__tests__/CoverageMap.test.tsx`

**Named tests**
| Test | Asserts |
|---|---|
| `test_competency_order_misses_then_matches_then_skills` | Order and de-duplication per §7.4; cap 12 |
| `test_normalisation_is_stable` | Case, whitespace, plural rule; idempotent |
| `test_story_without_result_is_never_covered` | AC11 |
| `test_thresholds_come_from_config` | Changing config changes status; no literals in `coverage.py` |
| `test_overrides_rename_and_hide` | Overrides applied after normalisation |
| `test_overview_counts_gaps_across_interview_applications` | Only applications in `interview` status |
| `test_flag_off_blocks_override_writes_but_allows_reads` | AC25 pattern for this feature |
| `CoverageMap.test.tsx` | Three statuses render with icon + text; "Draft a story" links with competency prefilled; keyboard reachable |

**Calibration:** add `backend/tests/fixtures/coach_coverage/` with 10 synthetic JD/story pairs labelled by hand; record precision/recall of `covered` and the chosen thresholds in the evidence report. Change config defaults only if the fixtures justify it.

- [ ] RED → GREEN; regressions: `tests/test_services/test_story*`, `tests/test_routers/test_stories*`.
- [ ] Commit: `feat(coach): add story coverage map for interview competencies`

### P2 — Debrief capture (M6, without extraction) — HA

**Claude Code writes RED tests first** (plan §1.5) for the migration, cascade and round-mirroring tests below.

**Read first:** `models/application.py` (`InterviewRound`), `routers/interviews.py`, `repositories` used by interviews, `services/application_service.py` (`get_next_actions`), application deletion path.

**Files**
- Modify: `backend/app/models/coach_readiness.py` — add `coach_interview_debriefs`
- Add: Alembic revision `add coach interview debriefs`
- Add: `backend/app/services/coach_readiness/debrief.py`
- Modify: `schemas/coach_readiness.py`, `routers/coach_readiness.py` or `routers/interviews.py` (debrief routes under `/interviews/{round_id}/debrief` — follow the existing router that owns `/interviews`)
- Modify: `services/application_service.py` / next-actions route — add "How did it go?" action
- Modify: `config.py` — `HATCH_COACH_DEBRIEF_ENABLED=False`
- Add: `frontend/src/components/coach/readiness/DebriefForm.tsx`; wire into the interview round view
- Tests: `backend/tests/test_migrations/test_coach_debrief_migration.py`, `backend/tests/test_services/test_coach_debrief.py`, `backend/tests/integration/test_coach_debrief_cascade.py`, `frontend/src/components/coach/readiness/__tests__/DebriefForm.test.tsx`

**Named tests**
| Test | Asserts |
|---|---|
| `test_migration_single_head_and_fk_cascade` | One head; FK enforced; downgrade/upgrade on disposable DB |
| `test_debrief_due_when_completed_or_time_passed` | AC15 debrief side; default duration 60 min when unset |
| `test_save_mirrors_questions_into_round_via_repository` | AC16; no direct SQL on `interview_rounds` from `debrief.py` (import check) |
| `test_round_delete_cascades_debrief` / `test_application_delete_leaves_no_orphans` | AC17 |
| `test_questions_capped_and_text_limits` | ≤ 20 questions; ≤ 200 chars each; free text ≤ 1,000 |
| `test_skip_then_start_later` | §8.5 transitions; illegal transition → 409 `invalid_state` |
| `test_next_actions_includes_debrief_prompt` | Only for rounds due and not saved/skipped |
| `DebriefForm.test.tsx` | Checklist first; save with only overall rating; 409 keeps draft; keyboard and labels |

- [ ] RED (Claude Code) → GREEN; regressions: `tests/test_routers/test_interviews*`, `tests/test_services/test_application_service.py`.
- [ ] Commit: `feat(coach): capture real-interview debriefs on interview rounds`

### P3 — Local model tiers: catalogue, pinned runtime, bench runs (M8)

**Read first:** `config/model_catalog.json`, `config/model_discovery_policy.json`, `services/model_discovery.py`, `scripts/hatch_cli.py` (catalogue use), `docker-compose*.yml`, `runtime/intelligence/registry.py`.

**Files**
- Modify: `docker-compose.yml`, `docker-compose.local-ai.yml` — pin llama.cpp server image to a build ≥ b10828 by tag **and** digest; add `llm-deep` service under profile `deep` (port 8082, same image)
- Modify: `config/model_discovery_policy.json` — publishers, families, marker and task rules (§9.2)
- Modify: `services/model_discovery.py` — honour the family-allowlist exemption and text-only use of `image-text-to-text`
- Modify: `config/model_catalog.json` — candidate entries with real revisions and sha256 taken from the downloaded files; add `tiers`
- Add: `config/model_tiers.json` + loader/validator in `backend/app/services/coach_readiness/tiers.py` (or the existing model registry module if it already owns config loading — follow the registry)
- Modify: Settings AI page — read-only tier table; Tier L opt-in hidden below 24 GB RAM
- Tests: `tests/test_services/test_model_discovery.py` (extend), `tests/test_services/test_model_tiers.py`, `tests/test_scripts/` catalogue checks, Settings component test
- Add: `docs/implementation-reports/coach-phase2/P0-local-model-bench.md` (bench results)

**Named tests**
| Test | Asserts |
|---|---|
| `test_policy_accepts_spark_and_minicpm_families_only_from_allowlisted_publishers` | Allowlist, not wildcard |
| `test_vision_repo_accepted_text_only_without_mmproj` | No projector file selected |
| `test_catalog_entries_have_revision_sha_and_tiers` | Schema; no empty hashes |
| `test_tier_map_rejects_non_promoted_model` | AC20 |
| `test_tier_l_hidden_below_24gb` | AC22 |
| `test_phase1_routes_unchanged` | Existing Coach routes still resolve to their current models |

**Bench runs (owner machine, synthetic data only)**
- [ ] Start pinned llama-server per candidate; run `python -m benchmarks.coach run --profile phase2 …` (exact CLI per existing harness) for: Tier T — MiniCPM-V-4.7-1B (text), MiniCPM5-2B, Qwen3.5-0.8B; Tier S — Spark-X2.6-4B (thinking off, then low), Qwen3.5-4B, MiniCPM5-2B, phi4-mini; Tier L — MiniCPM-V-4.7-35B-A3B Q4, gemma4:12b.
- [ ] Each on reference CPU-only, reference with GPU offload, and floor profile (T and S only).
- [ ] Two independent runs on holdout; owner blind-rates 10 outputs per candidate.
- [ ] Apply §9.4 gate; set `model_tiers.json` to promoted models only; set deadlines per §9.3.
- [ ] Rerun the Phase 1 `acceptance-smoke` profile on the new llama.cpp build with the existing Phase 1 models; record any change. If Phase 1 regresses, keep the old image for Phase 1 routes and pin the new one only for the new tier routes.
- [ ] Commit: `feat(runtime): add bench-gated local model tiers for coach readiness`

## 5. Wave 1 tasks (after the readiness check)

**P4 starts by recording the four-point readiness check from spec §3.2 in its evidence report.** If any point fails, stop and report; do not start P4 code.

### P4 — Patterns (M1)

**Files**
- Modify: `services/coach_conversational_progress.py` — add `evaluation_contract_version`, `difficulty` to `ProgressSnapshot`
- Modify: `repositories/conversational_session_repository.py` — populate them in `load_progress_snapshots` (only this change)
- Add: `services/coach_readiness/patterns.py`; extend `contracts.py`
- Modify: `models/coach_readiness.py` + migration — `coach_pattern_dismissals`
- Modify: schemas/router — pattern routes (§12)
- Modify: `config.py` — `HATCH_COACH_READINESS_ENABLED=False`, `HATCH_COACH_PATTERN_WINDOW_DAYS=90`
- Add: `frontend/src/app/coach/readiness/page.tsx`, components `PatternCard.tsx`, `PatternGroup.tsx`, `WhyPanel.tsx`
- Tests: `tests/test_services/test_coach_patterns.py`, `tests/test_routers/test_coach_patterns_router.py`, `__tests__/PatternCard.test.tsx`

**Named tests** (parameterised from spec Appendix A)
| Test | Asserts |
|---|---|
| `test_attempts_in_one_session_do_not_recur` | AC01 |
| `test_difficulty_not_in_group` | AC02 |
| `test_contract_versions_never_merge` | AC03 |
| `test_stale_after_window` | AC04, injected clock |
| `test_dismissal_reappears_on_new_support` | AC05 |
| `test_improving_guard_requires_same_or_harder_difficulty` | §7.1.4 |
| `test_why_is_deterministic_and_uses_stored_excerpts_only` | §7.7 Why |
| `test_existing_progress_trend_unchanged` | Phase 1 progress regressions |
| `PatternCard.test.tsx` | Forming shows "1 of 2"; kind uses icon + text; dismiss/undo; glossary copy (§13.4) |

- [ ] Regressions: `tests/test_services/test_coach_conversational_progress.py` and Phase 1 report/progress UI tests.
- [ ] Commit: `feat(coach): derive practice patterns across sessions`

### P5 — Focus areas and practice plan (M2, M3)

**Files**
- Add: `services/coach_readiness/focus.py`, `plan.py`
- Modify: models + migration — `coach_focus_areas`, `coach_practice_plans` (partial unique index on active plan)
- Modify: schemas/router — focus and plan routes
- Add: components `FocusAreas.tsx`, `FocusAreaEditor.tsx`, `PracticePlan.tsx`
- Phase 1 session setup: accept prefilled role family, interview type and difficulty via query parameters on the existing setup route (frontend only; no Phase 1 backend change)
- Tests: `tests/test_services/test_coach_focus.py`, `tests/test_services/test_coach_plan.py`, router tests, component tests

**Named tests**
| Test | Asserts |
|---|---|
| `test_fourth_active_focus_area_rejected` | AC06 limit |
| `test_stale_version_conflict_keeps_state` | AC06 409 |
| `test_level_criterion_counts_only_post_creation_same_group` | AC07 |
| `test_practice_items_never_satisfy_level_criterion` | AC07 |
| `test_plan_fits_whole_items_and_reports_unallocated` | AC08 |
| `test_plan_due_before_round_minus_two_hours` | AC09 |
| `test_practice_item_autocompletes_on_matching_session` | AC09 |
| `test_single_active_plan_enforced_by_index` | Two concurrent starts → one active |
| `test_plan_expiry_after_14_days_or_round_passed` | §8.3 |

- [ ] Commit: `feat(coach): add focus areas and interview-aware practice plans`

### P6 — Runtime bindings, cache, fencing, cascade, Explain — HA

**Claude Code writes RED tests first** (plan §1.5) for fencing, dedupe, cascade and canary tests.

**Files**
- Add: `runtime_bindings/tasks/coach_readiness.py` — 5 TaskSpecs (§10), prompts versioned, output schemas, thinking parameter per tier
- Add: `runtime_bindings/context/coach_readiness.py` — content providers that resolve references at execution time
- Modify: `runtime_bindings/capabilities/registry.py` — register local-capable capabilities (declare local execution correctly; do not weaken egress policy)
- Add: `services/coach_readiness/grounding.py`, `explain.py`, `privacy.py`
- Modify: `benchmarks/coach/phase2_checks.py` — replace the P0 copy with a re-export of `grounding.py` so bench and production use one implementation
- Modify: models + migration — `coach_derived_text`, `coach_derived_sources`
- Modify: `services/coach_privacy.py` — call `ReadinessPrivacy.on_session_deleted` inside the hard-delete transaction
- Modify: `services/story_service.py`, `services/question_bank.py` delete paths — call `on_source_deleted` in the same transaction
- Modify: router — tips + operations routes
- Add: `PatternTips.tsx` (instant skeleton, live region for arriving text)
- Tests: `tests/runtime/test_coach_readiness_bindings.py`, `tests/test_services/test_coach_grounding.py`, `tests/integration/test_coach_readiness_fencing.py`, `tests/integration/test_coach_readiness_cascade.py`, `tests/security/test_coach_readiness_canary.py`

**Named tests**
| Test | Asserts |
|---|---|
| `test_same_fingerprint_dedupes_to_one_generation` | AC19 |
| `test_session_deleted_mid_generation_is_fenced` | AC23; reload DB; no derived text references the session |
| `test_story_delete_cascades_derived_text` | §11 hooks |
| `test_one_generation_plus_one_repair_max` | Counts real dispatches including SDK retries |
| `test_deadline_absolute_across_repair` | §9.3 |
| `test_grounding_rejects_unknown_ids_and_new_numbers` | AC13 (shared with P7) |
| `test_ai_mode_none_creates_no_requests` | §10 |
| `test_route_unavailable_degrades_within_1s` | AC21 |
| `test_content_canary_absent_from_runtime_records_events_logs` | §15 canary |
| `test_thinking_text_stripped_from_output` | §9.1 |

- [ ] Regressions: `tests/runtime/` (full), Phase 1 privacy and deletion suites.
- [ ] Commit: `feat(coach): add fenced local generation and derived-data cascade`

### P7 — Pre-interview brief (M5, S3)

**Files**
- Add: `services/coach_readiness/brief.py`
- Modify: models + migration — `coach_interview_briefs`
- Modify: router — brief routes; next-actions additions
- Modify: `config.py` — `HATCH_COACH_BRIEF_ENABLED=False`
- Add: components `InterviewBrief.tsx`, `BriefSection.tsx`, print stylesheet; Brief tab on the interview round view; Readiness "Next interview" card
- Tests: `tests/test_services/test_coach_brief.py`, `tests/integration/test_coach_brief_lifecycle.py`, component tests, `frontend/e2e/coach-readiness-brief.spec.ts`

**Named tests**
| Test | Asserts |
|---|---|
| `test_brief_ready_with_ai_off_all_sections` | AC12 |
| `test_section_limits_and_source_order` | §7.5 table |
| `test_bad_enhancement_discarded_skeleton_kept` | AC13 |
| `test_input_change_marks_stale_and_reassembles_on_open` | AC14 |
| `test_brief_archives_after_round_time` | AC15 |
| `test_brief_without_round_date` | §7.5 anchor |
| `test_print_layout_one_page` (e2e) | AC28 |

- [ ] Commit: `feat(coach): build pre-interview briefs from your own evidence`

### P8 — Extraction and proposals (M6, S2)

**Files**
- Modify: `debrief.py` — extract route using `coach.readiness.debrief_extract`; proposals (QB add, story use)
- Modify: `coverage.py` — optional `competency_extract` when < 5 deterministic competencies
- Components: `DebriefNotesExtract.tsx`, `DebriefProposals.tsx`
- Tests: `tests/test_services/test_coach_debrief_proposals.py`, component tests

**Named tests**
| Test | Asserts |
|---|---|
| `test_extract_is_a_proposal_until_confirmed` | Nothing saved without confirm |
| `test_qb_proposal_accept_is_idempotent` | AC27 |
| `test_duplicate_questions_not_proposed` | AC27 normalised text |
| `test_story_use_recorded_through_public_route` | No direct table writes |
| `test_extracted_competencies_labelled_and_capped` | ≤ 4, labelled |

- [ ] Commit: `feat(coach): turn debrief notes into question bank and story proposals`

### P9 — What Hatch remembers, acceptance, rollout — HA

**Claude Code writes RED tests first** (plan §1.5) for deletion-all and the journey.

**Files**
- Modify: `privacy.py` — inventory and delete-by-kind/all
- Modify: router — memory routes
- Add: `frontend/src/app/settings/privacy/remembers/page.tsx` (or the existing settings privacy route) + `RemembersList.tsx`
- Add: `tests/integration/test_coach_readiness_journey.py`, `tests/security/test_coach_readiness_security.py`, `frontend/e2e/coach-readiness.spec.ts`
- Add: `docs/implementation-reports/coach-phase2/P9-release.md`

**Journey test:** two practice sessions in one group → pattern → focus area → plan started → round scheduled → brief ready (AI off) → enhancement (fake model) → round passes → debrief saved → QB proposal accepted → practice session hard-deleted → cached text gone, debrief kept → delete all readiness data → only Phase 1 data remains.

**Named tests**
| Test | Asserts |
|---|---|
| `test_delete_all_readiness_data_leaves_phase1` | AC24 |
| `test_flags_off_reads_and_deletes_work` | AC25 |
| `test_inventory_counts_match_rows` | Privacy page accuracy |
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
| M1 | P4 | AC01–05 |
| M2, M3 | P5 | AC06–09 |
| M4 | P1 (+P8 extraction) | AC10–11 |
| M5 | P7 | AC12–15 |
| M6 | P2, P8 | AC15–18 |
| M7 | P6 | AC19 |
| M8 | P3, P6 | AC20–22 |
| M9 | P6, P9 | AC23–25 |
| S1 (deferred) | — | AC26 deferred |
| S2 | P8 | AC27 |
| S3 | P7 | AC28 |
