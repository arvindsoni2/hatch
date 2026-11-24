# P9 RED contract — What Hatch remembers, delete-all, journey

Written by Claude Code (`/phase2-red P9`, Opus) before implementation, per plan §1.5.

- Branch: `coach-p2/p9-remembers-rollout`
- Base: `main` at `3491f0c` (P8 merged)
- RED commits: `2815de5755bd565d6fac28fb7a2a55a966227a5e` (`test(coach): RED contract for P9`), then `2337ae76de2a5e10b5786c0858a3556a9b5da660` (`test(coach): tighten P9 RED contract after owner decisions`, 24 Nov 2026)
- Spec change: `f25595511dc527eb3d63dcc565999afc6e0d00aa` (`docs(coach): record P9 owner decisions in the spec`). The owner asked for it (decision D19). It is the only change to a protected document on this branch.

## Protected test files (OpenCode must not edit or delete)

- `backend/tests/integration/test_coach_readiness_journey.py`
- `backend/tests/security/test_coach_readiness_security.py`

Review checks:

- `git diff --name-only 2337ae7..HEAD -- <the two paths>` must print nothing.
- For the protected documents, use `f255955` as the base, not the merge base: `git diff --name-only f255955..HEAD -- <protected documents>` must print nothing.

The P6 protected files listed in `P6-red.md` stay protected. These tests import `coach_readiness_support.py` and `test_coach_report_privacy_flow.deletion_request` and change neither.

OpenCode writes the rest of P9 in files that are not protected: `frontend/e2e/coach-readiness.spec.ts`, the `RemembersList` Vitest tests, the Settings → General timezone line, and `P9-release.md`.

## RED tests and observed failures

Run on `2337ae7` with `python -m pytest -q --no-cov <file>`. Result: 6 failed. The P6 cascade, fencing and canary files still pass (10 passed on `2815de5`; the tightening commit changes only the two P9 files).

| Test | File | Observed failure |
|---|---|---|
| `test_inventory_counts_match_rows` | journey | `AttributeError: 'ReadinessPrivacy' object has no attribute 'inventory'` |
| `test_delete_all_readiness_data_leaves_phase1` (AC24) | journey | `AttributeError: 'ReadinessPrivacy' object has no attribute 'delete_all'`. Seeding put rows in all 8 Phase 2 tables first. |
| `test_flags_off_reads_and_deletes_work` (AC25) | journey | `GET /api/coach/readiness/memory` returns 404. Every earlier assertion passed: with flags off, creation is refused, no brief row or model call is made, and reads of existing rows work. |
| `test_debrief_delete_optionally_clears_round_questions` (§7.8) | journey | `AttributeError: 'ReadinessPrivacy' object has no attribute 'delete_kind'` |
| `test_readiness_journey_end_to_end` (plan journey) | journey | `DELETE /api/coach/readiness/memory` returns 404, at the last step (line 732). Every step before it passes on `main`, in 3 of 3 runs. |
| `test_api_rejects_unknown_fields_and_oversize_text` (§12) | security | The first rejected request returns 422 with FastAPI's default body, which echoes the input (`{"detail":[{"type":"extra_forbidden","loc":["body","unexpected"],…,"input":true}]}`), not `{"detail": "invalid_input"}`. All 20 rejections already return 422 status through the production app (checked with a throwaway probe). |

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
- **Production app for validation.** The security test sends its requests through `app.main.app`, with `dependency_overrides` emptied, so `main.py`'s `RequestValidationError` handler applies. The other tests use a bare app with only the readiness router.
- **Inventory timestamps.** `last_updated` is the newest timestamp among the kind's rows: `dismissed_at` for dismissals, `updated_at` for focus areas, plans, debriefs and overrides, and `created_at` for cached text. The tests seed distinct times for every kind.

## Plan / code mismatches and owner decisions (24 Nov 2026)

The owner decided all six on 24 Nov 2026 (spec D19).

1. **"Tips out of date" after a story edit.** A story edit purges the cited text, so AC14 makes the state `none`, not `outdated`. The journey asserts AC14's rules (tips hidden, never `current`, exactly one re-queue), not the label. **Decision:** accepted; the plan wording is loose.
2. **Memory kinds.** **Decision:** do not split. "Focus areas, plans" stays one kind, `focus_areas_and_plans`, counted as focus areas plus plans.
3. **Cached job-description competencies.** **Decision:** add the row. Spec §7.8 now lists "Job description competencies" (`coach_derived_text` rows with `kind="competency"`). The tests now have seven kinds; `job_competencies` is last. §11 also lists `competency` as a derived-text kind.
4. **"Also clear questions on the round".** **Decision:** accepted. It clears the whole `questions_asked` list on each round whose debrief is deleted. Rounds without a debrief keep theirs. The confirm text must say so (spec §7.8).
5. **Validation error bodies.** **Decision:** tighten. Every readiness validation error returns exactly `{"detail": "invalid_input"}` and never echoes input (spec §12). P9 adds a readiness branch to the `RequestValidationError` handler in `backend/app/main.py`. This is an owner-approved file beyond the plan's P9 list; it changes only the handler, not any route.
6. **A generation that finishes after delete-all.** **Decision:** known limit for 0.20.0 (spec K13). No fence is required; the tests wait for in-flight work before deleting.

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
    "job_competencies",
]
MEMORY_KINDS: tuple[MemoryKind, ...]  # the seven kinds, in the order above (§7.8 page order)

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
  | `job_competencies` | `coach_derived_text` rows with `kind="competency"` (their sources cascade) |

- **`delete_all`** empties all 8 §11 tables, including brief state rows and every `coach_derived_text` kind (`competency` included). It never changes a Phase 1 row: round `questions_asked` is kept.
- **Routes** (in `routers/coach_readiness.py`, spec §12). Each works with every flag off (§14).
  - `GET /api/coach/readiness/memory` returns 200 with `{"kinds": [{"kind": str, "count": int, "last_updated": str | null}]}`, in `MEMORY_KINDS` order. `last_updated` is ISO 8601 UTC ending in `Z`.
  - `DELETE /api/coach/readiness/memory/{kind}?clear_round_questions=false` returns 200 with `{"kind": kind, "removed": int}`. A kind outside `MemoryKind` (including `patterns`) returns 422.
  - `DELETE /api/coach/readiness/memory` returns 200 with `{"removed": {kind: int, …}}`, one entry per kind. It is idempotent: a second call returns all zeros.
- **Validation errors** (`backend/app/main.py`). The `RequestValidationError` handler returns 422 with exactly `{"detail": "invalid_input"}` for any path under `/api/coach/readiness`. Other routes keep their current behaviour.
- **Brief task registry.** The tests wait on `app.services.coach_readiness.brief._TASKS`, the existing set of in-flight enhancement tasks (P7). It must keep that name and type (a set of `asyncio.Task`).
