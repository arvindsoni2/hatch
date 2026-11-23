# P8 evidence — signals, extraction and proposals (M1 signals, M6, S2)

Task / spec sections / ACs: P8, Wave 1. Spec §7.1.5, §7.4, §7.5 §4, §7.6, §10, §12, §13; AC27, AC34, AC38.

Baseline SHA → head SHA: `d7ce9c1` (P7 merge) → head is the P8 commit on `coach-p8/signals-proposals`.

Model: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`, owner-confirmed 2026-11-05. No switch.

Files changed:

- `backend/app/services/coach_readiness/signals.py` (new) — pure tagging and aggregation; `load_signals(db, application_id=None)` reads saved debriefs through `InterviewRound` → `Application`, tags each asked question with (a) the referenced Question Bank item's skills/tags and (b) coverage match keys contained in the question text, then aggregates per key: "Asked in N real interviews" (distinct rounds) and "You rated yourself 2 or less in N debriefs". A signal appears at N ≥ 2. Nothing is stored and `derive_patterns` is never called.
- `backend/app/services/coach_readiness/brief.py` — watch-outs take the practice `focus` patterns first, then real-interview signals fill the remaining slots up to the §7.5 limit of 2; signal watch-outs carry `source: "real_interview"`.
- `backend/app/services/coach_readiness/debrief.py` — notes-only draft saves (`overall=None` + `notes_text`, status `draft`); S2 proposals computed on every save and stored in `proposals_json`; `accept_proposal` writes through `create_question_bank_item` (deduped by normalised text, so idempotent) and `StoryService.record_use`; `extract_notes` passes the debrief id, reads `notes_text` by id, calls Tier T once, validates with `grounding.py` and returns a proposal only — nothing is saved without the candidate's confirm.
- `backend/app/services/coach_readiness/coverage.py` — optional Tier T `coach.readiness.competency_extract` when the deterministic list has < 5 competencies: `requirement_lines()` sends only bullets and skill-word lines, truncated to ≤ 4,500 characters (≤ 1,200 tokens, AC34); the result is grounded, finalised against a new `job` source and cached in `coach_derived_text` by description hash; extracted items are labelled "from the job description" and capped at 4.
- `backend/app/services/coach_readiness/contracts.py` — `SourceKind` gains the `job` branch in `finalise_generation` (exists + same `updated_at`); `RealInterviewSignal`, `DebriefProposal`, `Competency.label`, `CoverageOverview.signals`, `DebriefRead.proposals`, notes-only `overall`.
- `backend/app/routers/coach_readiness.py`, `backend/app/schemas/coach_readiness.py` — signals in the coverage overview response; `POST /rounds/{round_id}/debrief/extract`; `POST /rounds/{round_id}/debrief/proposals/{proposal_id}/accept`; `temporarily_unavailable` → 503.
- `frontend/src/components/coach/readiness/RealInterviewSignals.tsx` (new) — Readiness "From your real interviews" section: asked count, low-rating warning at N ≥ 2, "Draft a story" link.
- `frontend/src/components/coach/readiness/DebriefNotesExtract.tsx` (new) — "Paste rough notes" (≤ 2,500 characters), notes saved as a draft first, extraction proposes questions the candidate ticks into the checklist.
- `frontend/src/components/coach/readiness/DebriefProposals.tsx` (new) — one batch card per proposal with Accept / Not now; dismiss stores nothing.
- `frontend/src/components/coach/readiness/DebriefForm.tsx`, `frontend/src/app/coach/readiness/page.tsx`, `frontend/src/lib/coachReadinessApi.ts` — wiring, typed client, overview fetch; a full save keeps the stored notes.
- Tests: `backend/tests/test_services/test_coach_signals.py`, `backend/tests/test_services/test_coach_debrief_proposals.py`, `backend/tests/test_routers/test_coach_debrief_router.py` (extract/accept/draft routes), `RealInterviewSignals.test.tsx`, `DebriefNotesExtract.test.tsx`, `DebriefProposals.test.tsx`, readiness page order test.

No new flags: extraction gates are the existing `HATCH_COACH_DEBRIEF_ENABLED` (notes extraction and proposals) and `HATCH_COACH_STORY_COVERAGE_ENABLED` (competency extraction) plus AI mode local/custom, matching spec §14. Signals derive on read and work with every flag off.

GREEN:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_signals.py \
    tests/test_services/test_coach_debrief_proposals.py \
    tests/test_services/test_coach_debrief.py tests/test_services/test_coach_brief.py \
    tests/test_services/test_coach_coverage.py tests/test_routers/test_coach_debrief_router.py \
    tests/test_routers/test_coach_coverage_router.py tests/integration/test_coach_debrief_cascade.py \
    tests/integration/test_coach_brief_enhancement.py tests/test_services/test_coach_readiness_scheduler.py
64 passed in 9.29s

$ python -m pytest -q --no-cov tests/test_services/test_source_events.py \
    tests/integration/test_coach_readiness_cascade.py \
    tests/integration/test_coach_readiness_fencing.py \
    tests/security/test_coach_readiness_canary.py \
    tests/architecture/test_coach_readiness_imports.py \
    tests/runtime/test_coach_readiness_bindings.py \
    tests/test_services/test_coach_grounding.py tests/benchmarks/coach/test_phase2_suite.py
45 passed in 12.53s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness
46 passed (46)

$ PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test \
    e2e/coach-readiness-brief.spec.ts --project=chromium
1 passed (4.7s)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app/ tests/
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0

$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4141 passed, 2 skipped in 712.11s
```

Named P8 tests (all passing):

| Test | Asserts |
|---|---|
| `test_question_tagging_uses_source_item_and_contained_keys` | §7.1.5 tagging: QB skills/tags plus contained coverage keys; no keys from an unrelated question |
| `test_signal_needs_two_rounds` | AC38: one round → no signal; two → "asked in 2", "rated ≤ 2 in 2" |
| `test_signals_never_change_pattern_kind_or_trend` | AC38: `derive_patterns` output identical before and after debriefs exist |
| `test_brief_watchouts_include_signals_after_practice_patterns` | §7.5 §4: signals alone fill the slots; with a practice pattern it takes slot 1 and the signal slot 2 |
| `test_only_unsourced_new_questions_proposed` | ticked (sourced) questions and QB duplicates never proposed; unasked never proposed |
| `test_qb_proposal_accept_is_idempotent` | AC27: accepted twice, exactly one QB item, linked to the application, `interview_prep` source |
| `test_story_use_recorded_through_public_route` | no direct table writes: `StoryService.record_use` spy plus one usage row |
| `test_notes_saved_before_extraction_and_passed_by_id` | §10: notes-only draft saved first; the model sees the notes; a canary proves no persisted record contains them |
| `test_extract_is_a_proposal_until_confirmed` | extraction returns ≤ 12 × ≤ 120 characters and saves nothing (`questions_json` unchanged, status still `draft`) |
| `test_competency_extract_input_is_requirement_lines_within_budget` | AC34: bullets only, no marketing prose, ≤ 4,500 characters sent |
| `test_extracted_competencies_labelled_and_capped` | labelled "from the job description", duplicates dropped, ≤ 4 |

Model calls in tests: none live. Note extraction and competency extraction use the same local-only route resolution as Explain and Brief (`_route_base_url`), pass ids and resolve content at call time, and hold no DB transaction across the HTTP call.

Not run / known limits:

- The P3 bench/acceptance-smoke owner items remain open (unchanged from P7).
- `competency_extract` result is cached by description hash; a job description edit writes a new row under the new hash and the old row stays until the description hash repeats. No `source_events` hook exists for job edits, so the listener never purges these rows.
- Debrief proposal ids are stable hashes of the proposed texts, so an accept after a re-save with different questions targets the new batch.

## Repair cycle 1

Findings from the review of `2d088e6` and fixes, one commit per item:

- **Concurrent accept (AC27):** `accept_proposal` claims the accept with a version-guarded UPDATE (`WHERE id = :id AND version = :read_version`) before any domain write. A loser re-reads and returns the state the winner wrote; only the winner creates Question Bank items or records the story use. Tests race three accepts through the router with a committing session override: exactly one Question Bank item, exactly one story use.
- **Notes on a saved debrief:** a notes-only save on an existing row updates only `notes_text`, `version` and `updated_at`; a saved debrief stays saved with rating, questions and went-well/do-differently intact. Status moves to draft only from a skipped row (a new row starts as a draft as before).
- **No model call on read:** `coverage_for_application` consumes only a cached extraction. A cache miss returns the deterministic list straight away and starts one background generation per job + description hash, deduped in process and tracked in a `_TASKS` set like the P7 brief; a failure marks the key for 10 minutes so a failed extraction is not retried on every read. Three reads with the model failing make exactly 1 model call.
- **Brief watch-outs:** signals now come from `load_signals(db)` across all saved debriefs (spec §7.1.5), not scoped to the round's application.
- **Extract questions:** changed notes are saved as a draft before the extraction request reads them.
- **Debrief suggestions UI:** matches the design screen and the README rows — a "Suggestions from this debrief" panel with a success "Saved" badge; the Question Bank card shows the question text ("… is not in your bank yet.") with a default "Add to Question Bank"; the story card shows "Record that you used …" with an outline "Record use"; the rough notes sit behind a "Paste rough notes instead" link under "Another question".
- Evidence correction: a job description edit writes a competency cache row under the new description hash; the old row is not replaced and the listener never purges these rows (no job-edit hook exists).

GREEN (real output):

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_signals.py \
    tests/test_services/test_coach_debrief_proposals.py \
    tests/test_services/test_coach_debrief.py tests/test_services/test_coach_brief.py \
    tests/test_services/test_coach_coverage.py tests/test_routers/test_coach_debrief_router.py \
    tests/test_routers/test_coach_coverage_router.py tests/integration/test_coach_debrief_cascade.py \
    tests/integration/test_coach_brief_enhancement.py tests/test_services/test_coach_readiness_scheduler.py
69 passed in 10.43s

$ python -m pytest -q --no-cov tests/test_services/test_source_events.py \
    tests/integration/test_coach_readiness_cascade.py \
    tests/integration/test_coach_readiness_fencing.py \
    tests/security/test_coach_readiness_canary.py \
    tests/architecture/test_coach_readiness_imports.py \
    tests/runtime/test_coach_readiness_bindings.py \
    tests/test_services/test_coach_grounding.py tests/benchmarks/coach/test_phase2_suite.py
45 passed in 12.31s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness
48 passed (48)

$ PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test \
    e2e/coach-readiness-brief.spec.ts --project=chromium
1 passed (6.9s)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app/ tests/
All checks passed!

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0

$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4146 passed, 2 skipped in 699.75s
```

`answer_draft="Draft"` is left as it is for the owner to decide, per the review.
