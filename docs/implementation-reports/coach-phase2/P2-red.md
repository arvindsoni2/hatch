# P2 RED contract — debrief capture

Written by Claude Code (`/phase2-red P2`, Opus) before implementation, per plan §1.5.

- Branch: `coach-p2/p2-debrief-capture`
- Base: `main` at `f783dc1` (P1 merged)
- RED commit: `0161bb773de746cb18ce8a7c835381c0a62d3185` (`test(coach): RED contract for P2`)

## Protected test files (OpenCode must not edit or delete)

- `backend/tests/test_migrations/test_coach_debrief_migration.py`
- `backend/tests/test_services/test_coach_debrief.py`
- `backend/tests/integration/test_coach_debrief_cascade.py`

Review check: `git diff --name-only 0161bb7..HEAD -- <the three paths>` must print nothing.

OpenCode writes the remaining named P2 tests in **new** files, because the plan's `test_coach_debrief.py` is now protected:

| Named test | Suggested file |
|---|---|
| `test_questions_capped_and_text_limits`, `test_questions_json_item_shape` | `backend/tests/test_services/test_coach_debrief_rules.py` |
| `test_likely_questions_order_and_archived_excluded` | `backend/tests/test_services/test_coach_questions.py` (plan path; not protected) |
| `test_next_actions_includes_debrief_prompt`, `test_round_times_returned_as_utc_z` | `backend/tests/test_routers/test_coach_debrief_router.py` |
| `DebriefForm.test.tsx`, `formatInterviewTime.test.ts` | plan paths (not protected) |

## RED tests and observed failures

Run with Python 3.12 (`python -m pytest -q --no-cov <file>`) on the RED commit.

| Test | File | Observed failure |
|---|---|---|
| `test_migration_single_head_and_fk_cascade` | `test_migrations/test_coach_debrief_migration.py` | `AssertionError: expected one revision named 'add coach interview debriefs'` (`assert 0 == 1`) |
| `test_debrief_due_when_completed_or_time_passed` | `test_services/test_coach_debrief.py` | collection: `ImportError: cannot import name 'debrief' from 'app.services.coach_readiness'` |
| `test_cancelled_round_never_due_saved_debrief_kept` | same | same ImportError |
| `test_rescheduled_round_moves_due_time` | same | same ImportError |
| `test_save_mirrors_questions_into_round_via_repository` | same | same ImportError |
| `test_skip_then_start_later` | same | same ImportError |
| `test_round_delete_cascades_debrief` | `integration/test_coach_debrief_cascade.py` | collection: `ImportError: cannot import name 'DebriefQuestion' from 'app.services.coach_readiness.contracts'` |
| `test_application_delete_leaves_no_orphans` | same | same ImportError |
| `test_practice_session_delete_keeps_debrief` | same | same ImportError |

Every failure is the missing behaviour (module, contract names or revision), not a syntax or fixture error. `ruff check` on the three files passes.

**Satisfiability check.** Before committing, the tests were run against a throwaway probe implementation in a scratch worktree outside the repository: the interfaces below, a minimal model, a migration and a skip route. All 9 passed, so the tests contain no fixture bugs. The probe was deleted and is not committed. It is not a reference implementation.

## Plan / code mismatches (owner decision needed before OpenCode starts)

1. **Application "delete" is a soft delete.** `DELETE /api/applications/{id}` calls `ApplicationRepository.soft_delete` (`is_active = False`). No code path physically deletes an application, so on the user's path nothing cascades and the round and debrief stay. Separately, `interview_rounds.application_id` has no `ON DELETE` clause; only the ORM relationship (`cascade="all, delete-orphan"`) removes rounds. `test_application_delete_leaves_no_orphans` therefore proves the physical path: deleting the `Application` through the ORM removes rounds, debriefs and overrides, with no orphan. **Decide:** should readiness reads (`get_or_due`, next actions) ignore rounds of inactive applications? Recommended: yes, tested by OpenCode in its router or next-actions tests. Deleting a soft-deleted application's debrief stays with the privacy page (P9).
2. **`InterviewRepository` has no get-by-id.** AC16 and the plan's import check forbid direct SQL on `interview_rounds` from `debrief.py`, but the service must read a round. This needs a small additive method in `backend/app/repositories/interview_repository.py`, which is outside P2's file list (see Assumed interfaces). **Approve** the addition.
3. **No `draft` transition in §10.1.** §8.5 has `due → draft` and `skipped → draft`, but `DebriefService` only has `get_or_due`, `save` and `skip`. The RED test treats "start later" as `save` from `skipped` (→ `saved`). A stored `draft` (P8 `notes_text`) is not exercised in P2.
4. **Carry-over from P1 review (Medium).** `backend/tests/runtime/test_schema_migration.py` lost its `down_revision == "z3a4b5c6d7e8"` assertion. OpenCode should restore it as a check on the fixed revision `a4b5c6d7e8f9` in P2. The file is outside P2's list, so it needs owner approval.
5. **Spec drift, no P2 action.** Spec §11 lists `coach_competency_overrides` columns `match_key`, `display_text`, but P1 shipped `original`. Fix in the spec or a later task.

## Owner decisions (3 Nov 2026)

1. Approved: readiness reads (`get_or_due`, next actions, overview) ignore rounds whose application has `is_active = false`. OpenCode adds a test for this in its own test file.
2. Approved: add `InterviewRepository.get` to `backend/app/repositories/interview_repository.py` (additive only).
3. Accepted: no stored `draft` transition in P2; "start later" is `save` from `skipped`.
4. Approved: restore the parent assertion in `backend/tests/runtime/test_schema_migration.py` as `scripts.get_revision("a4b5c6d7e8f9").down_revision == "z3a4b5c6d7e8"`, keeping the dynamic one-head check.
5. Noted: the §11 override-column drift needs no P2 action.

The Assumed interfaces below are approved and binding.

## Assumed interfaces (binding once the owner approves)

Beyond spec §10.1 and names already in the codebase:

**`backend/app/services/coach_readiness/debrief.py`**
- `DebriefService(session: AsyncSession)`: the constructor takes the request session; the service does not commit.
- `now` arguments are timezone-aware UTC. Stored naive `scheduled_at` values are treated as UTC (§7.5).
- `get_or_due(round_id, now)`:
  - returns the stored debrief whatever the round's status (including `cancelled`);
  - with no stored debrief, returns a read with `status == "due"` when due (§7.6, default duration 60 min), else `None`;
  - the returned `version` is the `expected_version` for the first `save` or `skip`. With no stored row the tests pass `0` to `skip`.
- `save(round_id, command, now)`:
  - legal from `due` and `skipped`, and for edits of `saved`; the result has `status == "saved"`;
  - mirrors the `asked` question texts, in order, into `InterviewRound.questions_asked` and sets `status = "completed"` if the round was `scheduled` or `rescheduled`, both through `InterviewRepository.update`;
  - cancelling the round later does not change the debrief or its `version`.
- `skip(round_id, expected_version, now)`:
  - legal only from `due`;
  - from `skipped` or `saved`, or for a round that is not due (future or `cancelled`), raises `ReadinessError` with `code == "invalid_state"`;
  - the state check comes before the version check.
- The module imports `app.repositories.interview_repository`, does not import `InterviewRound`, and does not contain the text `interview_rounds`.

**`backend/app/services/coach_readiness/contracts.py`**
- `DebriefQuestion`: keyword-constructible fields `id: str`, `text: str`, `source_ref: {kind, id} | None`, `asked: bool`, `rating: int | None`, `story_id: str | None`, `note: str | None` (the §7.6 `questions_json` item).
- `SaveDebriefCommand`: keyword-constructible fields `expected_version: int`, `overall: int`, `expectation: "yes" | "unsure" | "no" | None`, `questions: Sequence[DebriefQuestion]`, `went_well: str | None`, `do_differently: str | None`, `notes_text: str | None`.
- `DebriefRead`: attributes `status` (`"due" | "draft" | "saved" | "skipped"`), `version: int`, `overall: int | None`, `went_well: str | None` and `questions: Sequence[DebriefQuestion]` in saved order. Other fields are free.
- `ReadinessError(Exception)` with `.code: str`, one of the §12 safe codes.

**`backend/app/repositories/interview_repository.py`** (existing file, additive; see mismatch 2)
- `async def get(self, interview_id: str) -> InterviewRoundRead | None`

**`backend/app/routers/coach_readiness.py`**
- `POST /api/coach/readiness/rounds/{round_id}/debrief/skip` with body `{"expected_version": int}`.
- `ReadinessError("invalid_state")` → HTTP 409 with body `{"detail": "invalid_state"}`, the P1 convention (`HTTPException(detail=<code>)`).

**`backend/app/config.py`**
- `HATCH_COACH_DEBRIEF_ENABLED: bool = False` (plan). The tests set it to `True`.

**Alembic revision**
- Message exactly `add coach interview debriefs`; `down_revision = "9a0421e6f32b"`.
- Creates `coach_interview_debriefs` with the §11 columns `id`, `interview_round_id`, `version`, `status`, `overall`, `expectation`, `questions_json`, `went_well`, `do_differently`, `notes_text` (nullable), `proposals_json`, `created_at`, `updated_at`.
- `interview_round_id` is unique, with a FK to `interview_rounds.id` `ON DELETE CASCADE`. No other NOT NULL column without a default.
- Downgrade drops the table.
- The ORM model in `models/coach_readiness.py` matches, so `Base.metadata.create_all` builds the same table.
