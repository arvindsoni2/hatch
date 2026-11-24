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

## Acceptance matrix (Must)

| Area | ACs | Status | Evidence |
|---|---|---|---|
| Readiness baseline | AC01–AC05, AC37–AC38 | pass | P4/P5 evidence; P8 signals tests; P9 journey |
| Debrief capture | AC16–AC18 | pass | P2 evidence; P9 journey (claim/finalise, debrief kept) |
| Deletion and fencing | AC23–AC25 | pass | P6 evidence; P9 `test_delete_all_readiness_data_leaves_phase1`, `test_flags_off_reads_and_deletes_work` |
| Brief | AC12–AC15, AC28, AC32–AC33 | pass | P7 evidence; P9 journey |
| Signals and proposals | AC27, AC38 | pass | P8 evidence; P9 journey (QB proposal accepted once) |
| Privacy page | AC24 | pass | P9 `test_inventory_counts_match_rows`, delete-all tests |
| Cost-aware execution | AC06–AC11 | pass | P3 evidence; P6 bindings |
| Validation safety | §12 | pass | P9 `test_api_rejects_unknown_fields_and_oversize_text` |
| Journey | plan P9 | pass | `test_readiness_journey_end_to_end` |

Known deviation: the journey asserts AC14's rules for a story edit (old tips hidden, never `current`, exactly one re-queue) rather than the loose "Tips out of date" wording — owner decision D19.

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
3. Enable `HATCH_COACH_STORY_COVERAGE_ENABLED` and `HATCH_COACH_READINESS_ENABLED` for the first cohort.
4. Enable `HATCH_COACH_BRIEF_ENABLED` and `HATCH_COACH_DEBRIEF_ENABLED`.
5. Watch model call counts and the readiness surfaces for a week before broadening.

Rollback is flags off; no schema downgrade in production. The privacy page and deletion keep working either way.

## Release gates

- [x] All Must ACs pass (`P9-evidence.md`, phase evidence).
- [x] Phase 1 regression suite green: full backend run, 2 skipped, no P9 regressions; the two coverage-load timing flakes pass alone.
- [x] No new migration in P9; heads `6e209652647a`; prior upgrade/downgrade round trips recorded in P2/P7 evidence.
- [x] Bench validation: 48 scenarios, 2 models (`benchmarks.coach validate`).
- [x] Claude Code compliance and quality/security review with zero open Critical/High (P6–P8 review cycles; P9 review pending).
- [ ] Owner approval to turn flags on (bench summary review outstanding).

## Known limits

- K13 (accepted for 0.20.0): a generation already running when the user deletes all readiness data may write its text afterwards. Finalise fencing re-checks sources, not deletion events. A deletion epoch checked at finalise is the fix if it matters later.
- Competency cache rows are keyed by job-description hash; the old row is not purged when the description changes (no job-edit source hook).
- Full Playwright integration specs need the CI seed/unlocked backend; the P9 specs are mocked and green locally.

## Version

`0.20.0` — Coach Phase 2 readiness loop.
