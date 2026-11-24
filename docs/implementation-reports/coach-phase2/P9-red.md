# P9 RED contract — What Hatch remembers, delete-all, journey

Written by Claude Code (`/phase2-red P9`, Opus) before implementation, per plan §1.5.

- Branch: `coach-p2/p9-remembers-rollout`
- Base: `main` at `3491f0c` (P8 merged)
- RED commit: `2815de5755bd565d6fac28fb7a2a55a966227a5e` (`test(coach): RED contract for P9`)

## Protected test files (OpenCode must not edit or delete)

- `backend/tests/integration/test_coach_readiness_journey.py`
- `backend/tests/security/test_coach_readiness_security.py`

Review check: `git diff --name-only 2815de5..HEAD -- <the two paths>` must print nothing.

The P6 protected files listed in `P6-red.md` stay protected. These tests import `coach_readiness_support.py` and `test_coach_report_privacy_flow.deletion_request` and change neither.

OpenCode writes the rest of P9 in files that are not protected: `frontend/e2e/coach-readiness.spec.ts`, the `RemembersList` Vitest tests, the Settings → General timezone line, and `P9-release.md`.

## RED tests and observed failures

Run on `2815de5` with `python -m pytest -q --no-cov <file>`. Result: 6 failed. The P6 cascade, fencing and canary files run in the same command still pass (10 passed).

| Test | File | Observed failure |
|---|---|---|
| `test_inventory_counts_match_rows` | journey | `AttributeError: 'ReadinessPrivacy' object has no attribute 'inventory'` |
| `test_delete_all_readiness_data_leaves_phase1` (AC24) | journey | `AttributeError: 'ReadinessPrivacy' object has no attribute 'delete_all'`. Seeding put rows in all 8 Phase 2 tables first. |
| `test_flags_off_reads_and_deletes_work` (AC25) | journey | `GET /api/coach/readiness/memory` returns 404. Every earlier assertion passed: with flags off, creation is refused, no brief row or model call is made, and reads of existing rows work. |
| `test_debrief_delete_optionally_clears_round_questions` (§7.8) | journey | `AttributeError: 'ReadinessPrivacy' object has no attribute 'delete_kind'` |
| `test_readiness_journey_end_to_end` (plan journey) | journey | `DELETE /api/coach/readiness/memory` returns 404, at the last step (line 732). Every step before it passes on `main`, in 3 of 3 runs. |
| `test_api_rejects_unknown_fields_and_oversize_text` (§12) | security | `GET /api/coach/readiness/memory` returns 404. All 20 existing-route rejections already return 422. |

## How the tests work

- **Real code throughout.** The routes run on the real `get_db`, which commits the way production does, against a file-backed SQLite database with foreign keys on (`coach_database`). The readiness listener is the real `ReadinessPrivacy`, registered the way `main.py` registers it. Every assertion reads from a fresh session.
- **Model.** Only the local model server is faked, at its HTTP boundary (`…/chat/completions`). Model calls are counted at that boundary.
- **Phase 1 untouched.** The test snapshots every row of every table not in the §11 list before delete-all and compares it after. The audio files on disk must still be there.
- **Journey (plan P9):**
  1. Two practice sessions in one group give a `focus` pattern.
  2. Focus area, then plan created and started.
  3. Round scheduled: with AI off the brief state is `active`, enhancement `none` ("Ready"), and all sections are present with no model call.
  4. AI on: Explain tips cached, citing both sessions. Brief enhanced to `current` with 1 model call.
  5. Story edited through `StoryRepository.update`: the tips text is purged, three concurrent reads show no talking point and never `current`, and exactly one re-queue happens (2 model calls in total). The brief returns to `current` with the new text.
  6. Round time passes (`InterviewRepository.update`): brief `archived`, debrief `due`.
  7. Debrief saved; the Question Bank proposal is accepted, creating exactly 1 item.
  8. Practice session hard-deleted (claim, then `_process_hard_deletion`): no text citing it remains, and the debrief is kept.
  9. Story soft-deleted: it leaves coverage and the brief.
  10. `DELETE /memory`: all Phase 2 tables are empty and the Phase 1 snapshot is unchanged.
- **Inventory timestamps.** `last_updated` is the newest timestamp among the kind's rows: `dismissed_at` for dismissals, `updated_at` for focus areas, plans, debriefs and overrides, and `created_at` for cached text. The tests seed distinct times for every kind.

## Plan / code mismatches (owner decision needed before OpenCode starts)

1. **"Tips out of date" after a story edit.** The plan's journey says a story edit shows "Tips out of date". But a story edit purges the cited text through `source_events`, and AC14's last sentence says that when the text was purged the state reads `none`, never `current`. The current brief code does exactly that. The journey therefore asserts AC14's rules (tips hidden, never `current`, exactly one re-queue) and not the label. **Recommend:** accept, and treat the plan wording as loose.
2. **Memory kinds.** §10.1 says `MemoryKind` is "the closed set of rows in §7.8". "Patterns" is derived and has no delete of its own, so it is left out. "Focus areas, plans" is one §7.8 row, so it is one kind (`focus_areas_and_plans`), counted as focus areas plus plans. **Decide:** keep one-to-one with §7.8 (as written), or split into `focus_areas` and `practice_plans`. Splitting would mean changing the RED tests before OpenCode starts.
3. **Cached text outside §7.8.** P8's competency cache (`kind="competency"`, built from the job description) belongs to no §7.8 row, and `plan_wording` is specified but not built. The tests require delete-all to remove all cached text, and require that the competency cache is not counted under Briefs or Explain tips. **Decide:** whether the page should list "Job description competencies" as a further row. That would be a spec addition, and the tests would change.
4. **"Also clear questions on the round".** The tests read this as clearing the whole `questions_asked` list on each round whose debrief is deleted, including questions typed before the debrief. Rounds without a debrief keep theirs. The alternative is to remove only the questions the debrief added, but nothing records which ones those were. **Recommend:** accept the whole-list reading. The page's confirm text should say so.
5. **Validation error bodies echo input.** Readiness 422 responses use FastAPI's default body, which echoes the rejected input back (for example oversize rough notes). §12 says errors use "registered safe codes"; the app redacts echoes only on the Coach conversation routes. The security test asserts only the 422 status. **Decide:** whether P9 should add a readiness branch to the `RequestValidationError` handler in `main.py` that returns `{"detail": "invalid_input"}`. If so, I'll tighten the test before OpenCode starts.
6. **A generation that finishes after delete-all.** Finalise fencing (§10) re-checks sources, not a deletion event. A brief or tips generation already in flight when the user deletes everything can still write its text afterwards. The tests wait for in-flight work before deleting, so they don't cover this. **Decide:** accept as a known limit for 0.20.0 (the text is purged again by the next delete), or specify a fence, for example a deletion epoch that finalise checks.

## Assumed interfaces (need owner approval; binding once approved)

All in `backend/app/services/coach_readiness/privacy.py` unless stated otherwise.

```python
MemoryKind = Literal[
    "dismissed_patterns",
    "focus_areas_and_plans",
    "briefs",
    "debriefs",
    "explain_tips",
    "competency_overrides",
]
MEMORY_KINDS: tuple[MemoryKind, ...]  # the six kinds, in the order above (§7.8 page order)

@dataclass(frozen=True)
class MemoryKindSummary:
    kind: MemoryKind
    count: int
    last_updated: datetime | None   # UTC; naive values are read as UTC; None when count == 0

@dataclass(frozen=True)
class MemoryInventory:
    kinds: tuple[MemoryKindSummary, ...]   # one per kind, MEMORY_KINDS order

@dataclass(frozen=True)
class MemoryDeletionResult:
    removed: dict[MemoryKind, int]   # one entry per kind, counted as in the inventory

class ReadinessPrivacy:
    async def inventory(self) -> MemoryInventory: ...
    async def delete_kind(
        self, kind: MemoryKind, *, clear_round_questions: bool = False
    ) -> int: ...                                  # rows of that kind removed
    async def delete_all(self) -> MemoryDeletionResult: ...
```

- **Signature addition beyond §10.1:** `delete_kind` gains the keyword-only `clear_round_questions` (default `False`), for §7.8's "also clear questions on the round". It applies only to `debriefs`. Round questions are cleared through `InterviewRepository.update`, never by writing `interview_rounds` directly (boundary rule, spec §5.1).
- **Own sessions.** `inventory`, `delete_kind` and `delete_all` open their own session from `self.repository.session_factory` and commit it. The router builds `ReadinessPrivacy(CoachReadinessRepository(app.database.AsyncSessionLocal))`, looking the factory up at request time, the way `get_db` does, so tests reach the patched test database.
- **Count and delete per kind:**

  | Kind | Counts and deletes |
  |---|---|
  | `dismissed_patterns` | `coach_pattern_dismissals` rows |
  | `focus_areas_and_plans` | `coach_focus_areas` plus `coach_practice_plans` rows |
  | `briefs` | `coach_derived_text` rows with `kind="brief"` (their sources cascade). Brief state rows may stay, and the brief re-assembles. |
  | `debriefs` | `coach_interview_debriefs` rows |
  | `explain_tips` | `coach_derived_text` rows with `kind="explain"` |
  | `competency_overrides` | `coach_competency_overrides` rows |

- **`delete_all`** empties all 8 §11 tables, including brief state rows and every `coach_derived_text` kind (`competency` included). It never changes a Phase 1 row: round `questions_asked` is kept.
- **Routes** (in `routers/coach_readiness.py`, spec §12). Each works with every flag off (§14).
  - `GET /api/coach/readiness/memory` returns 200 with `{"kinds": [{"kind": str, "count": int, "last_updated": str | null}]}`, in `MEMORY_KINDS` order. `last_updated` is ISO 8601 UTC ending in `Z`.
  - `DELETE /api/coach/readiness/memory/{kind}?clear_round_questions=false` returns 200 with `{"kind": kind, "removed": int}`. A kind outside `MemoryKind` (including `patterns`) returns 422.
  - `DELETE /api/coach/readiness/memory` returns 200 with `{"removed": {kind: int, …}}`, one entry per kind. It is idempotent: a second call returns all zeros.
- **Brief task registry.** The tests wait on `app.services.coach_readiness.brief._TASKS`, the existing set of in-flight enhancement tasks (P7). It must keep that name and type (a set of `asyncio.Task`).
