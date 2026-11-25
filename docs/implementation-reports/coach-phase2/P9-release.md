# P9 release — Coach Phase 2 readiness loop (0.20.0)

Acceptance and rollout record for the Phase 2 readiness loop (P1–P9). Owner approval is required before any flag is switched on in a user-facing build; this document records the evidence and the rollout mechanics, not an approval.

## Scope shipped

Practice patterns → focus areas → weekly plan → pre-interview brief → real interview → debrief → signals and proposals, plus the privacy page and cycle-aware execution.

Merged phases:

| Phase | PR / merge |
|---|---|
| P1 coverage map | `main` before P6 |
| P2 debrief capture | `main` before P6 |
| P3 model tiers / bench harness | `main` before P6 |
| P4 patterns | `main` before P6 |
| P5 focus + plan | `main` before P6 |
| P6 source events, cascade, fencing, bindings | PR #87 → `f58e14d` |
| P7 pre-interview brief | PR #88 → `d7ce9c1` |
| P8 signals, extraction, proposals | PR #89 → `3491f0c` |
| P9 What Hatch remembers, journey, acceptance | this branch |

## Acceptance criteria — every Must

| AC | Required outcome | Evidence |
|---|---|---|
| AC01 | One assessed session → `forming` "1 of 2"; attempts in one session count once | `P4-evidence.md`; `tests/test_services/test_coach_patterns.py` |
| AC02 | Two sessions, same group, different difficulty → one group, `focus` when both weak | `P4-evidence.md`; `test_coach_patterns.py` |
| AC03 | Rubric contract versions never merge | `P4-evidence.md`; `test_coach_patterns.py` |
| AC04 | Latest 3 regardless of age; older than 90 days → `stale` "Older", excluded from plan/brief/Explain | `P4-evidence.md`; `test_coach_patterns.py`; P7 brief tests |
| AC05 | Dismiss hides; new evidence reappears labelled; undo works | `P4-evidence.md`; `tests/test_routers/test_coach_patterns_router.py` |
| AC06 | 4th active focus area → `limit_reached`; stale version → 409 keeping the draft | `P5-evidence.md`; `test_coach_focus.py`, `test_coach_focus_plan_router.py` |
| AC07 | Level criterion needs a group and same-group sessions after creation; plan completion alone never meets it | `P5-evidence.md`; `test_coach_focus.py` |
| AC08 | 30-minute plan → ≤ 6 whole items, ≤ 30 minutes, unallocated reported, stable order | `P5-evidence.md`; `test_coach_plan.py` |
| AC09 | Round-targeted plan: every `due_at` = start − 2 h; < 2 h → `invalid_input`; one session completes group practice items; two focus areas share one item | `P5-evidence.md`; `test_coach_plan.py` |
| AC10 | Coverage list misses → matches → skills, deduped by match key, ≤ 12, original text; overrides apply | `P1-evidence.md`; `test_coach_coverage.py` |
| AC11 | Containment scoring: one tag word = 1.0; no `result` never covered; inactive stories excluded | `P1-evidence.md`; `test_coach_coverage.py` |
| AC12 | Future round with AI off → brief "Ready" with all 7 sections, deterministic | `P7-evidence.md`; `test_coach_brief.py::test_brief_ready_with_ai_off_all_sections` |
| AC13 | Unknown story/number enhancement discarded; skeleton kept; `unavailable` | `P7-evidence.md`; `test_bad_enhancement_discarded_skeleton_kept` |
| AC14 | Story edit hides old tips, never `current`, exactly one re-queue; purged text reads `none` | `P7-evidence.md`; `test_fingerprint_change_hides_tips_and_requeues_once`, `test_purged_tips_read_as_none_and_requeue`; P9 journey |
| AC15 | Round time passes or completed → brief archived, debrief due, Today "How did it go?" | `P7-evidence.md`; `tests/test_routers/test_coach_debrief_router.py`; P9 journey |
| AC16 | Debrief save mirrors asked questions via the interview repository and completes the round | `P2-evidence.md`; `tests/test_services/test_coach_debrief.py`; P9 journey |
| AC17 | Round/application delete cascades brief, debrief, overrides; no orphans | `P2/P6 evidence`; `tests/integration/test_coach_debrief_cascade.py`, `test_coach_readiness_cascade.py` |
| AC18 | Practice-session delete keeps debriefs | `P2/P6 evidence`; `test_coach_debrief_cascade.py`; P9 journey |
| AC19 | Two tips requests → one generation, cached result; source edits delete cached tips | `P6-evidence.md`; `tests/runtime/test_coach_readiness_bindings.py` |
| AC20 | Tier map only promoted models; unknown/non-promoted → startup validation error | `P3-evidence.md`; `tests/test_services/test_model_tiers.py` |
| AC21 | Tier S unavailable → deterministic content within 1 s | `P6-evidence.md`; `test_route_unavailable_degrades_within_1s` |
| AC22 | Tier L hidden below 24 GB; enabling keeps Tier S fallback | `P3-evidence.md`; model-tier router tests |
| AC23 | Hard deletion during enhancement purges text at claim, finalise `fenced`, no later text | `P6-evidence.md`; `test_coach_readiness_fencing.py` |
| AC24 | Delete all readiness data removes every Phase 2 row/cache; Phase 1 untouched | `P9-evidence.md`; `test_delete_all_readiness_data_leaves_phase1` |
| AC25 | Flags off → no new briefs/plans/generations; reads and deletes work | `P9-evidence.md`; `test_flags_off_reads_and_deletes_work` |
| AC29 | Transcript delete purges derived text in the same transaction; listener error rolls back and keeps audio | `P6-evidence.md`; `tests/test_services/test_source_events.py` |
| AC30 | Soft-deleted story/archived QB item purges text, leaves coverage/brief/questions, later finalise `fenced` | `P6-evidence.md`; `test_coach_readiness_cascade.py` |
| AC31 | Two concurrent activations with 2 active → one succeeds, other `limit_reached` | `P5-evidence.md`; `tests/integration/test_coach_focus_concurrency.py` |
| AC32 | Cancelled round → brief archived, no debrief due, saved debrief kept; rescheduled follows new time | `P7 evidence`; brief/debrief tests |
| AC33 | Round times stored UTC, returned with `Z`, shown in the display timezone | `P7 evidence`; `InterviewBrief.test.tsx`; P9 General timezone line |
| AC34 | Tier T over budget → input ≤ 1,200 tokens, output ≤ 512, slot ≤ 2,048; chars ÷ 4 | `P3-evidence.md`; `test_competency_extract_input_is_requirement_lines_within_budget`; bench checks |
| AC35 | Model passing the Phase 2 gate but failing the route regression bench stays `qualified`; tier map rejects it | `P3-evidence.md`; tier tests |
| AC36 | No module outside Phase 2 files (and `main.py`) imports `coach_readiness` | `P6-evidence.md`; `tests/architecture/test_coach_readiness_imports.py` |
| AC37 | Trend wording follows the difficulty guard | `P4-evidence.md`; `test_coach_patterns.py` |
| AC38 | Signal only at N ≥ 2; signals never change pattern kind/trend | `P8-evidence.md`; `test_coach_signals.py` |

Shoulds: AC27 (QB proposals, P8 evidence) and AC28 (brief print, P7 evidence) shipped. AC26 is deferred by D9.

Known deviation: the P9 journey asserts AC14's rules for a story edit (old tips hidden, never `current`, exactly one re-queue) rather than the loose "Tips out of date" wording. This follows the P9-red owner decisions (24 Nov 2026, item 1), not D19.

## Rollout

All Phase 2 flags default to `false` in `config.py`:

| Flag | Gates |
|---|---|
| `HATCH_COACH_READINESS_ENABLED` | Patterns, focus, plan, explain, privacy page |
| `HATCH_COACH_BRIEF_ENABLED` | Brief creation and enhancement |
| `HATCH_COACH_DEBRIEF_ENABLED` | Debrief prompts/capture, note extraction and proposals |
| `HATCH_COACH_STORY_COVERAGE_ENABLED` | Coverage map, competency overrides, competency extraction |

Rollout order (owner):

1. Merge P9, cut 0.20.0 with every flag off. Reads of existing rows, the privacy page and all deletion work with flags off.
2. Run the P3 bench summary review and accept the tier map (owner item, unchanged by P9).
3. Enable `HATCH_COACH_STORY_COVERAGE_ENABLED` and `HATCH_COACH_READINESS_ENABLED` in the owner's workspace.
4. Enable `HATCH_COACH_BRIEF_ENABLED` and `HATCH_COACH_DEBRIEF_ENABLED`.
5. Measure the success measures in spec §1.1 over the first 30 days before broadening.

Rollback is flags off; no schema downgrade in production. The privacy page and deletion keep working either way.

## Release gates

- [ ] All Must ACs pass (table above; P9 review pending).
- [x] Phase 1 regression suite green: full backend run, 2 skipped, no P9 regressions; the two coverage-load timing flakes pass alone.
- [x] No new migration in P9; heads `6e209652647a`; prior upgrade/downgrade round trips recorded in P2/P7 evidence.
- [x] Bench validation runs: 48 scenarios, 2 models (`benchmarks.coach validate`).
- [ ] P3 bench report accepted (both gates of §9.1, or the D20 short regression run for the two models it names) — owner.
- [ ] Claude Code compliance and quality/security review with zero open Critical/High (P6–P8 reviewed; P9 pending).
- [ ] Owner approval to turn flags on.

## Known limits

- K13 (accepted for 0.20.0): a generation already running when the user deletes all readiness data may write its text afterwards. Finalise fencing re-checks sources, not deletion events. A deletion epoch checked at finalise is the fix if it matters later.
- Competency cache rows are keyed by job-description hash; the old row is not purged when the description changes (no job-edit source hook).
- Full Playwright integration specs need the CI seed/unlocked backend; the P9 specs are mocked and green locally.

## Version

`0.20.0` — Coach Phase 2 readiness loop.
