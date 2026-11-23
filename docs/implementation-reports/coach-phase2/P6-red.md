# P6 RED contract — source events, fencing, cascade, Explain

Written by Claude Code (`/phase2-red P6`, Opus) before implementation, per plan §1.5.

- Branch: `coach-p2/p6-source-events`
- Base: `main` at `64f4313` (P5 merged)
- RED commit: `491a6df7065c7bac1327ffbff7b88b9fbdd429c2` (`test(coach): RED contract for P6`)

## Protected test files (OpenCode must not edit or delete)

- `backend/tests/test_services/test_source_events.py`
- `backend/tests/integration/test_coach_readiness_cascade.py`
- `backend/tests/integration/test_coach_readiness_fencing.py`
- `backend/tests/integration/coach_readiness_support.py` (shared harness; import it, do not change it)
- `backend/tests/security/test_coach_readiness_canary.py`
- `backend/tests/architecture/test_coach_readiness_imports.py`

Review check: `git diff --name-only 491a6df..HEAD -- <the six paths>` must print nothing.

The plan asks Claude Code for the hook, fencing, dedupe, cascade, import-direction and canary tests. OpenCode writes the other named P6 tests in files that are not protected:

| Named test | Suggested file |
|---|---|
| `test_one_generation_plus_one_repair_max`, `test_deadline_absolute_across_repair_including_queue`, `test_ai_mode_none_creates_no_requests`, `test_route_unavailable_degrades_within_1s`, `test_thinking_text_stripped_from_output` | `backend/tests/runtime/test_coach_readiness_bindings.py` (plan path) |
| `test_grounding_rejects_unknown_ids_and_new_numbers`, `test_explain_word_limits` | `backend/tests/test_services/test_coach_grounding.py` (plan path) |

OpenCode may import the helpers in `coach_readiness_support.py` (for example `fake_llama` and `model_dispatches`, which count every HTTP request to the model server, SDK retries included).

## RED tests and observed failures

Run with Python 3.12: `python -m pytest -q --no-cov <file>` on the RED commit.

| Test | File | Observed failure |
|---|---|---|
| `test_notify_runs_listeners_in_callers_transaction` | `test_services/test_source_events.py` | collection: `ModuleNotFoundError: No module named 'app.services.source_events'` |
| `test_listener_error_rolls_back_source_change` | same | same |
| `test_notify_runs_before_media_removal` | same | same |
| `test_transcript_delete_purges_derived_text` | `integration/test_coach_readiness_cascade.py` | collection: `ModuleNotFoundError: No module named 'app.repositories.coach_readiness_repository'` |
| `test_claim_purges_and_finalise_purges_again` | same | same |
| `test_story_edit_and_soft_delete_purge_derived_text` | same | same |
| `test_qb_edit_and_archive_purge_derived_text` | same | same |
| `test_supporting_session_edit_purges_tips` | same | same |
| `test_session_deleted_mid_generation_is_fenced` | `integration/test_coach_readiness_fencing.py` | same |
| `test_activity_version_change_fences_generation` | same | same |
| `test_generation_after_story_soft_delete_is_fenced` | same | same |
| `test_same_fingerprint_dedupes_to_one_generation` | same | same |
| `test_content_canary_absent_from_runtime_records_events_logs` | `security/test_coach_readiness_canary.py` | same |
| `test_existing_domains_do_not_import_coach_readiness` | `architecture/test_coach_readiness_imports.py` | `AssertionError: missing services/source_events.py` |

Every failure is missing behaviour (a module or the seam), not a syntax or fixture error. `ruff check` on the six files passes. The scan in the import test finds no violations on `main` today. It fails only because the `source_events` seam is missing.

**Satisfiability check.** I ran the tests against a throwaway probe implementation in a scratch worktree outside the repository: the interfaces below, minimal tables, a listener, `finalise_generation`, and an in-memory tips route. All 14 passed, and three repeat runs were stable. I then broke the probe five ways, and each break was caught by the intended test:

| Probe change | Caught by |
|---|---|
| `notify` moved after media removal in `finalise_hard_deletion` | `test_notify_runs_before_media_removal` |
| Finalise ignores `deletion_state` | `test_session_deleted_mid_generation_is_fenced` |
| Finalise ignores `is_active` | `test_generation_after_story_soft_delete_is_fenced` |
| Prompt logged | the canary test |
| Listener skips `deactivated` | `test_claim_purges_and_finalise_purges_again` and `test_session_deleted_mid_generation_is_fenced` |

The probe is deleted and not committed. It is not a reference implementation.

## How the tests work

- **Hook and cascade.** These tests call the real existing domain methods: `delete_attempt_transcript`, `claim_hard_deletion`, `finalise_hard_deletion` (through `_process_hard_deletion`), `StoryRepository.update` and `soft_delete`, and `update_question_bank_item` and `archive_question_bank_item`. They use a file-backed SQLite database with foreign keys on, and they reload the database before every assertion. Derived text is seeded with plain SQL on the §11 columns.
- **Fencing.** These tests call `finalise_generation` (§10.1) and change sources through the real domain methods. To bump `activity_version`, one test runs a direct SQL update; this stands in for new Phase 1 activity.
- **Dedupe, tips purge and canary.** These tests drive the real readiness router over HTTP: `GET /patterns`, `POST /patterns/{fingerprint}/tips` and `GET /operations/{id}`. Only the local model server is faked, at its HTTP boundary (the OpenAI-compatible `…/chat/completions` endpoint), with `pytest-httpx` (already in `requirements-dev.txt`, which CI installs). The fake counts every request that reaches the server, so SDK retries count as dispatches.
- **Canary.** A unique string is put in report excerpts, transcripts and a story. The test first asserts that the string reached the model request. Then it asserts that the string appears in no database table except the three tables the test seeded (`interview_sessions`, `session_recordings`, `stories`), in no log record at DEBUG level, in no telemetry span, attribute, event or metric label, and in no `llm_factory` trace. This means `coach_derived_text`, async jobs, runtime records and runtime events must never hold prompt or excerpt text.

## Plan / code mismatches (owner decision needed before OpenCode starts)

1. **`CoachReadinessRepository` does not exist.** Spec §10.1 constructs `ReadinessPrivacy(repository: CoachReadinessRepository)`, and §5.2 names `backend/app/repositories/coach_readiness_repository.py`, but P6's file list does not include it. The listener is registered once at start-up, so the repository cannot hold a request session. **Approve:** add the file with a constructor that takes a session factory (see Assumed interfaces). P9 can reuse it for `inventory`, `delete_kind` and `delete_all`.
2. **AC19 "editing a supporting session".** Spec §5.3 has only one session "edit" call site: `delete_attempt_transcript` (`edited`). A transcript *edit* (`claim_transcript_edit`) does not notify. `test_supporting_session_edit_purges_tips` therefore treats transcript deletion as the edit. **Recommended: accept.** A transcript edit rebuilds the report, and the cached tips are keyed by the pattern fingerprint and fenced on `activity_version`. Adding a call site in `claim_transcript_edit` would widen P6's file scope.
3. **Tests build the app from the readiness router alone, without a lifespan** (as in the P2 and P4 tests). The tips route must therefore not depend on objects that `main.py` lifespan puts on `app.state`. **Approve** this constraint (see Assumed interfaces). Production wiring in lifespan stays allowed, as long as the route also works without it, for example by building lazily.
4. **Story versions do not change on soft delete.** `StoryRepository.soft_delete` sets `is_active = False` without bumping `version`. A finalise check on versions alone would pass after a soft delete. The fencing test requires the `is_active` check that §7.8 already names. No decision needed; this is a reminder for the implementation.
5. **Carry-over from the P4 repair.** Readiness writes now bypass `AISetupGateMiddleware`. The tips route must enforce AI mode None itself (§10: "requests are not created"). OpenCode's `test_ai_mode_none_creates_no_requests` must cover this through the route, not only the service.
6. **New test dependency in use.** `pytest-httpx==0.36.0` is pinned in `requirements-dev.txt` but no test used it until now. No new dependency is added.

## Owner decisions (17 Nov 2026)

1. Approved: add `backend/app/repositories/coach_readiness_repository.py` with `CoachReadinessRepository(session_factory)`.
2. Accepted: transcript deletion is the AC19 "edit"; no call site is added in `claim_transcript_edit`.
3. Approved: the tips and operations routes work in an app built from the readiness router alone, with no lifespan state.
4. Noted: mismatches 4–6 need no decision.

The Assumed interfaces below are approved and binding.

## Assumed interfaces (approved and binding)

Beyond spec §10.1 and names already in the codebase:

**`backend/app/services/source_events.py`**
- `SourceChange(kind, source_id, change)` is a frozen dataclass with value equality; positional and keyword construction both work.
- `unregister_listener(listener) -> None` removes a registered listener. It is a no-op when the listener is not registered. Tests need it for isolation; lifespan shutdown can use it.
- `notify(session, change)`:
  - awaits every registered listener in registration order, with the caller's session;
  - re-raises a listener's exception unchanged;
  - never commits, flushes a commit or ends the caller's transaction.

**§5.3 call sites** (existing files; additive)
- Each method calls `notify` exactly once per call, with these exact values:
  - `StoryRepository.update`: `SourceChange("story", id, "edited")`
  - `StoryRepository.soft_delete`: `SourceChange("story", id, "deleted")`
  - `update_question_bank_item`: `SourceChange("question_bank_item", id, "edited")`
  - `archive_question_bank_item`: `SourceChange("question_bank_item", id, "deleted")`
  - `delete_attempt_transcript`: `SourceChange("coach_session", session_id, "edited")`
  - `claim_hard_deletion`, on the path that creates a new claim: `SourceChange("coach_session", session_id, "deactivated")`
  - `finalise_hard_deletion`: `SourceChange("coach_session", session_id, "deleted")`
- `notify` runs before the method's own data change and before any media removal.
- Each module imports `app.services.source_events`, and none imports `coach_readiness`.

**`backend/app/repositories/coach_readiness_repository.py`** (new; mismatch 1)
- `CoachReadinessRepository(session_factory: async_sessionmaker[AsyncSession])`.

**`backend/app/services/coach_readiness/privacy.py`**
- `ReadinessPrivacy(CoachReadinessRepository(factory))`.
- `on_source_change(session, change)`:
  - deletes, through the given session, every `coach_derived_text` row that has a `coach_derived_sources` row with `(change.kind, change.source_id)`;
  - does this for every `ChangeKind`;
  - never commits.

**Tables** (`backend/app/models/coach_readiness.py`, registered in `models/__init__.py`, plus the migration)
- `coach_derived_text`:
  - columns `id`, `kind` (`explain` / `brief` / `plan_wording` / `extract`), `cache_key` (unique), `text_json`, `model_identity`, `prompt_version`, `created_at`;
  - no other NOT NULL column without a default.
- `coach_derived_sources`:
  - columns `derived_text_id` (FK to `coach_derived_text.id`, `ON DELETE CASCADE`), `source_kind`, `source_id`, `source_version`;
  - primary key `(derived_text_id, source_kind, source_id)`;
  - index on `(source_kind, source_id)`.
- Tests insert `text_json` as a JSON string and `created_at` as naive UTC.

**`backend/app/services/coach_readiness/contracts.py`**
- `GenerationRequest`:
  - keyword fields `task_id: str`, `kind: str`, `cache_key: str`, `input_fingerprint: str`, `sources: tuple[SourceRef, ...]`;
  - any further field has a default.
- `ValidatedOutput`: keyword fields `text_json: Mapping[str, Any]`, `model_identity: str`, `prompt_version: str`.
- `GenerationOutcome`: `.status` is `"succeeded"` or `"fenced"`; `.derived_text_id: str | None`.
- `input_fingerprint(task_id: str, sources: Sequence[SourceRef], params: Mapping[str, str] | None = None) -> str`:
  - the fingerprint the request carries;
  - `finalise_generation` recomputes it from the sources' current versions;
  - a request whose `SourceRef` versions all match the current state must pass.
- `SourceRef.version` strings:
  - `coach_session`: `str(activity_version)`;
  - `story`: `str(version)`.
- `finalise_generation(session, request, output, now)`:
  - `now` is timezone-aware UTC;
  - does not commit;
  - on success writes one `coach_derived_text` row with `request.kind` and `request.cache_key`, and one `coach_derived_sources` row per `SourceRef` with `source_version = ref.version`;
  - fences, writing nothing, when:
    - a session is missing or its `deletion_state` is not `not_requested`;
    - an `activity_version` differs;
    - a story is missing or inactive;
    - the recomputed fingerprint differs.

**`backend/app/routers/coach_readiness.py`**
- `POST /api/coach/readiness/patterns/{fingerprint}/tips`:
  - takes no request body;
  - returns `202 {"operation_id": str, ...}` when no cached tips exist;
  - returns `200 {"tips": [str, ...], ...}` when cached;
  - two concurrent requests for the same fingerprint get the same `operation_id`.
- `GET /api/coach/readiness/operations/{id}`:
  - returns `200 {"status": str, ...}`, where `status` is one of the §8.6 states and `succeeded`, `degraded` and `fenced` are terminal;
  - the body contains no candidate content.
- Both routes work in an app that includes only this router, with `get_db` overridden and no lifespan (mismatch 3).
- Background generation opens its sessions through `app.database.AsyncSessionLocal`, looked up at call time (`database.AsyncSessionLocal()`, not a name imported at module load), so the test's patched session factory is used.

**Model transport and AI mode**
- Tier S and Tier T calls go over HTTP to the route's OpenAI-compatible `…/chat/completions` endpoint, through httpx (directly, or via the openai SDK or langchain-openai).
- The structured output is read from `choices[0].message.content`. For Explain, that content is the JSON `{"tips": [...]}`.
- `GET` health or model probes are allowed.
- The Explain prompt includes the Why? excerpt text, resolved at execution time by the context provider.
- AI mode is read from the existing setup state in `HATCH_CONFIG_DIR`: `ai_setup.load_runtime()` and/or `load_intent()`. `ai_mode == "local"` with the promoted tier map in `config/model_tiers.json` means generation may run.
- Any telemetry Phase 2 emits goes through `app.observability.runtime.get_telemetry()` at call time.
