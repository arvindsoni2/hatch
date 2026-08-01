# Coach Phase 1 PR1 Conversational Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the V6 conversational persistence, server-owned state machine, idempotent command/live APIs, fenced setup and recovery, and legacy-compatible experience dispatch required before capture and evaluation work begins.

**Architecture:** Extend `InterviewSession`, `SessionQuestion`, and `SessionRecording` additively, with `SessionRecording` remaining the attempt aggregate. Put conversational schemas, contracts, repository transactions, state logic, planning, commands, live projection, and router wiring in bounded modules while retaining the legacy router/service/report paths unchanged; every mutation uses conditional SQLite-safe updates, one transaction, persisted events, and ownership/version fences. A deterministic evaluation port makes foundation tests terminal without implementing PR3 model evaluation.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, async SQLAlchemy, Alembic with SQLite batch migrations, `AsyncJobService`, pytest/pytest-asyncio, existing Coach reconciliation and observability facades.

## Global Constraints

- Sole Phase 1 authority: `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md`, SHA-256 `626381be8963340972711bdfa5e47df0c82d521bb4e22ad75f3f873022c19ae8` when this plan was written.
- Approved delivery design: `docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md`, SHA-256 `992f9693d82b5146770e5e002f6f8d7f2485d34716e89d0d6a775662c134ece6`; it adds gates but cannot amend V6.
- Create `phase1/pr1-conversational-foundation` from the fetched integration head after the four plans and two repository-local skills are committed and pushed; target `feature/coach-phase1-phase2`, never `main`.
- PR1 must merge before PR2. Do not base PR2 on an unmerged PR1 branch.
- V6 supersedes Phase 1 v1-v5 and the condensed draft. Preserve existing callers, historical numeric values, video rows, legacy reports/progress, and completed Coach correctness, benchmark, reconciliation, and observability work.
- `SessionRecording` remains the physical answer-attempt aggregate. Do not add an `InterviewAttempt` table, generic workflow engine, second report engine, or bypass `session_repository.py`, `AsyncJobService`, provider routing, reconciliation, or the observability facade.
- Phase 2 is forbidden: no Candidate Intelligence entity, finding, confidence band, governance gateway, mentor persona, or multi-session weakness plan. Phase 1 outputs remain session-scoped.
- `HATCH_COACH_CONVERSATIONAL_ENABLED` defaults to `False`. Disabled mode blocks only new conversational creation; existing conversational reads and future cleanup remain usable. PR1 does not enable rollout.
- `legacy_v1` remains the default when `experience_version` is omitted. Conversational sessions reject legacy submit/end/retry paths where semantics are unsafe; no legacy route is silently translated.
- Conversation state and allowed commands come from one registry. The browser, router, and live service must not maintain competing transition lists.
- Canonical semantic request hashing is lowercase SHA-256 of UTF-8 JSON produced with `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`, after Pydantic `model_dump(mode="json", exclude_unset=False, exclude_none=False)`; `command_id` is excluded.
- Duplicate `(session_id, command_id)` lookup and `(session_id, client_attempt_id)` lookup occur before state/version/budget checks. New mutation, command receipt, state version, event allocation, and rows commit or roll back together.
- Every new route validates safe IDs, parent ownership, contract version, and strict payload shape. Treat IDs, content, metadata, model output, and filenames as untrusted; return only the canonical safe error registry and never log content, user paths, stack traces, prompts, provider details, tokens, transcripts, CV/evidence text, or raw identifiers in metric labels.
- Active security/race tests use bounded synthetic data in an isolated local database only. Never point destructive, fuzz, or adversarial tests at production, shared services, or real user data.
- PR1 excludes final LLM evaluation, MediaRecorder/UI, audio storage implementation, stage execution, retention cleanup, rubric/evidence/coaching/follow-ups, transcript editing, acceptance UI, report/progress/export/deletion flows, observability expansion, benchmarks, and feature rollout. Only persistence/interfaces required by later PRs are created.
- Defaults locked in PR1: setup max attempts `3`; attempts/question `5` (valid 1-20); manual processing retries `2` (valid 0-5); progress groups `20` (valid 1-100); follow-ups/root `2`; transcript characters `30000`; evidence claims `20`; answer duration `600`; silence `4000/9000 ms`; audio failure retention `24 h`; default audio `delete_after_processing`; transcript `retain`.
- Every implementation task follows RED -> minimal GREEN -> focused regression -> commit. Record exact command, exit status, pass/fail count, branch/base/head, migration head, and artifact paths; do not claim a gate without output.
- Request specification-compliance review first. Request code-quality/security review only after compliance passes. Critical/high findings block merge and every medium finding needs disposition.
- Owner disposition on 2026-07-26: the repository-wide fail-closed database-bootstrap branch is parked at `fe56665f5adaf5a2d376389a29fd729aea1caaf8` and is not a PR1 dependency. Historical no-op base revisions mean bare `alembic upgrade head` on an empty database remains unsupported. PR1 must not rewrite that history or rely on blank-chain replay. The repository-supported fresh-install path is current ORM metadata `create_all()` followed by `stamp head`; PR1 tests that path again after the new ORM graph exists. Migration compatibility is independently tested against copies reconstructed from a hash-locked, full-schema `p3q4r5s6t7u8` SQL snapshot captured before any PR1 ORM edit.

---

## Baseline and start gate

- [ ] **Step 1: Verify authority, topology, clean scope, and toolchain before creating the PR branch**

```bash
git fetch origin
git switch feature/coach-phase1-phase2
git pull --ff-only origin feature/coach-phase1-phase2
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/feature/coach-phase1-phase2)"
git merge-base --is-ancestor 3985da09 HEAD
git status --short
git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
git check-ignore -v docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md; test $? -eq 1
sha256sum docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md
python --version
node --version
npm --version
python scripts/check_docs.py
git switch -c phase1/pr1-conversational-foundation
```

Expected: the local integration head equals its fetched remote, both authority hashes match this plan, `3985da09` is an ancestor, tracked/ignore/docs checks pass, the tree contains no unexplained change, and the new branch points at the recorded integration SHA. Stop on authority/hash/topology drift; document and diagnose an existing dirty/baseline failure before implementation.

- [ ] **Step 2: Capture the repository-supported baseline**

```bash
cd backend
alembic heads
alembic current
python - <<'PY'
import asyncio
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="hatch-coach-pr1-baseline-") as directory:
    database = Path(directory) / "baseline.db"
    database_url = f"sqlite+aiosqlite:///{database}"
    os.environ["DATABASE_URL"] = database_url

    import app.models  # noqa: F401 — register every mapped table
    from app.database import Base, engine

    async def create_current_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(create_current_schema())
    environment = os.environ.copy()
    subprocess.run(["alembic", "stamp", "head"], check=True, env=environment)
    subprocess.run(["alembic", "current"], check=True, env=environment)
    subprocess.run(["alembic", "check"], check=True, env=environment)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
PY
python -m pytest -q --no-cov tests/test_services/test_coach_contracts.py tests/test_services/test_coach_reconciliation.py tests/test_services/test_coach_session_queue.py tests/test_routers/test_coach_router.py tests/test_routers/test_coach_async.py tests/test_migrations/test_coach_c1_migration.py
cd ../frontend
npm run type-check
npm test -- --run
npm run build
cd ..
make ci
```

Expected: `alembic heads` reports exactly `p3q4r5s6t7u8`; record the repository database's pre-existing `alembic current` output without requiring it to be stamped. The disposable current-metadata database is stamped at and reports revision `p3q4r5s6t7u8`, `alembic check` reports no drift, and SQLite integrity/foreign-key checks pass. This is baseline evidence only: Task 2 separately captures the complete pre-PR1 schema, reconstructs copyable baseline databases from it, exercises the PR1 migration, and repeats the supported fresh-install path against the new-head ORM metadata. Focused legacy Coach tests, frontend checks, and `make ci` exit 0. Record Playwright availability separately; PR1 has no new browser E2E. If a baseline command fails, preserve its output and resolve or obtain owner disposition before attributing any later failure to PR1.

## File structure and locked downstream interfaces

**Create:**

```text
backend/alembic/versions/20260725_0001_q4r5s6t7u8v9_add_conversational_coach_foundation.py
backend/app/repositories/conversational_session_repository.py
backend/app/routers/coach_conversation.py
backend/app/schemas/coach_conversation.py
backend/app/services/coach_conversational_contracts.py
backend/app/services/coach_conversation_state.py
backend/app/services/coach_conversation_commands.py
backend/app/services/coach_live_view.py
backend/app/services/coach_session_plan.py
backend/tests/test_migrations/test_conversational_coach_migration.py
backend/tests/fixtures/coach/p3q4r5s6t7u8_schema.sql
backend/tests/test_repositories/test_conversational_session_repository.py
backend/tests/test_services/test_coach_conversation_state.py
backend/tests/test_services/test_coach_conversation_commands.py
backend/tests/test_services/test_coach_live_view.py
backend/tests/test_services/test_coach_session_plan.py
backend/tests/test_routers/test_coach_conversation_router.py
```

**Modify:**

```text
backend/app/config.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/coach_session.py
backend/app/routers/coach.py
backend/app/schemas/coach.py
backend/app/services/coach_reconciliation.py
backend/app/services/coach_session_queue.py
backend/tests/test_routers/test_coach_router.py
backend/tests/test_services/test_coach_reconciliation.py
backend/tests/test_services/test_coach_session_queue.py
```

The PR2 and PR3 plans consume these exact public names; implementation must preserve them or re-export compatibility aliases:

```python
# backend/app/services/coach_conversational_contracts.py
CONVERSATION_COMMAND_CONTRACT = "coach_conversation_command_v1"
CONVERSATION_COMMAND_RESULT_CONTRACT = "coach_conversation_command_result_v1"
LIVE_VIEW_CONTRACT = "coach_live_view_v1"
SESSION_PLAN_CONTRACT = "coach_session_plan_v1"
RUBRIC_CONTRACT = "coach_conversational_rubric_v1"
EVIDENCE_GROUNDING_CONTRACT = "coach_evidence_grounding_v1"
FOLLOW_UP_CONTRACT = "coach_follow_up_v1"
REPORT_CONTRACT = "coach_conversational_report_v1"
PROGRESS_CONTRACT = "coach_conversational_progress_v2"
DELIVERY_POLICY = "coach_delivery_policy_v1"

# backend/app/repositories/conversational_session_repository.py
class ConversationalSessionRepository:
    async def create_transcript_version(self, *, recording_id: str, source: str,
        transcript: str, expected_attempt_version: int,
        processing_generation: int) -> InterviewTranscriptVersion:
        raise NotImplementedError
    async def create_evaluation_version(self, *, recording_id: str,
        transcript_version_id: str | None, evaluation_version: int,
        processing_generation: int, contract_version: str,
        state: str, async_job_id: str | None = None) -> InterviewAttemptEvaluation:
        raise NotImplementedError
    async def claim_attempt_processing(self, *, recording_id: str,
        expected_generation: int, job_id: str,
        deadline: datetime) -> AttemptProcessingClaim | None:
        raise NotImplementedError
    async def get_attempt_processing_snapshot(self, *, recording_id: str,
        processing_generation: int) -> AttemptProcessingSnapshot | None:
        raise NotImplementedError
    async def finalise_attempt_processing(self, *, claim: AttemptProcessingClaim,
        result: AttemptProcessingResult) -> bool:
        raise NotImplementedError
    async def append_session_events(self, *, session_id: str,
        events: Sequence[SessionEventInput]) -> tuple[InterviewSessionEvent, ...]:
        raise NotImplementedError
    async def accept_attempt(self, *, session_id: str, question_id: str,
        attempt_id: str, expected_state_version: int) -> AcceptanceResult:
        raise NotImplementedError
    async def create_follow_up_question(self, *, claim: FollowUpAdmissionClaim
        ) -> FollowUpCreationResult:
        raise NotImplementedError

# backend/app/services/coach_conversation_commands.py
class ConversationCommandService:
    async def execute(self, *, user_id: str, session_id: str,
        request: ConversationCommandRequest) -> ConversationCommandResult:
        raise NotImplementedError
CoachConversationCommandService = ConversationCommandService

# backend/app/services/coach_live_view.py
class CoachLiveViewService:
    async def get_live_view(self, *, user_id: str,
        session_id: str) -> ConversationLiveView:
        raise NotImplementedError

# PR2 imports these immutable records
@dataclass(frozen=True)
class AttemptProcessingClaim:
    session_id: str
    question_id: str
    recording_id: str
    transcript_version_id: str | None
    evaluation_version_id: str
    processing_generation: int
    job_id: str
    deadline_at: datetime

@dataclass(frozen=True)
class AttemptProcessingResult:
    evaluation_state: Literal["completed", "unavailable"]
    evaluation_json: dict[str, object]
    transcript_version_id: str | None
    diagnostics: dict[str, object]
```

PR1 creates `InterviewAttemptUpload` persistence so PR2 can implement bytes/storage without another migration. `accept_attempt` and `create_follow_up_question` exist as transactionally safe repository primitives for PR3 but are not exposed as active PR1 command behavior; the deterministic PR1 stub may finalise an attempt for tests but must not implement rubric, evidence, coaching, or follow-up policy.

### Task 1: Centralize feature flags, contracts, errors, and state registry

**Files:** Create `backend/app/services/coach_conversational_contracts.py`; create `backend/app/services/coach_conversation_state.py`; modify `backend/app/config.py`; test `backend/tests/test_services/test_coach_conversation_state.py`.

**Interfaces:** Produces `ERROR_REGISTRY`, `TRANSITIONS`, `allowed_commands(session)`, `require_transition(session, command_type)`, canonical contract constants, and all PR1 settings.

- [ ] **Step 1: Write the RED registry/transition/config tests**

```python
def test_allowed_commands_are_derived_from_transition_registry() -> None:
    assert allowed_commands(state="ready", status="setup") == (
        "start", "rebuild_plan", "update_retention"
    )
    assert allowed_commands(state="processing_answer", status="active") == ()
    assert "begin_answer" in allowed_commands(state="asking", status="active")

def test_error_registry_is_complete_and_rejects_forbidden_alias() -> None:
    assert ERROR_REGISTRY["coach_conversation_version_conflict"].http_status == 409
    assert "coach_progress_incompatible_session" in ERROR_REGISTRY
    assert "coach_session_incompatible_for_progress" not in ERROR_REGISTRY
    assert all(item.message and isinstance(item.retryable, bool) for item in ERROR_REGISTRY.values())

def test_conversational_defaults_are_disabled_and_bounded() -> None:
    assert settings.HATCH_COACH_CONVERSATIONAL_ENABLED is False
    assert settings.HATCH_COACH_MAX_ATTEMPTS_PER_QUESTION == 5
    assert settings.HATCH_COACH_MAX_PROCESSING_RETRIES_PER_ATTEMPT == 2
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_state.py`

Expected: FAIL during import because both conversational modules are absent.

- [ ] **Step 3: Implement the immutable registry and settings**

```python
from types import MappingProxyType
from typing import Final, Mapping

@dataclass(frozen=True)
class TransitionRule:
    projections: frozenset[tuple[str, str]]

_TRANSITIONS: dict[str, TransitionRule] = {
    "start": TransitionRule(frozenset({("ready", "setup")})),
    "begin_answer": TransitionRule(frozenset({("asking", "active")})),
    # Populate every remaining command from V6 Appendix A as exact
    # (conversation_state, status) pairs. Never store independent state/status
    # sets: their Cartesian product authorizes unlisted transitions.
}
TRANSITIONS: Final[Mapping[str, TransitionRule]] = MappingProxyType(_TRANSITIONS)
```

This PR1 registry intentionally records the complete V6 coarse command contract, including completed-session `record_self_assessment`; do not pre-narrow the base contract in PR1. PR3 owns the temporary removal of `completed` from that rule and from `/live.allowed_commands` while no atomic reflection/report transaction exists. PR4 restores the original PR1/V6 rule only in the same task that implements atomic completed reflection persistence, report invalidation, and rebuild claim.

Implement all Section 31.7 errors as `ErrorDefinition(http_status, retryable, message)` in one private dictionary exposed through a `Final[Mapping[...]]` `MappingProxyType`, with command-defined state predicates layered over this coarse registry (setup/attempt/report scopes, paused draft resolution, acceptance pointer, retry limits). Tests must cover every Appendix A projection, reject every unlisted state/status pair, reject mutation of both public registries, and lock each error's HTTP status and retryability. Add exact `Field` bounds/defaults from V6 Section 36 to `Settings`, testing model-field defaults independently of ambient environment.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_services/test_coach_conversation_state.py tests/test_services/test_coach_contracts.py
git add app/config.py app/services/coach_conversational_contracts.py app/services/coach_conversation_state.py tests/test_services/test_coach_conversation_state.py
git commit -m "feat(coach): define conversational state contracts"
```

Expected: PASS; the commit contains no persistence/router change.

### Task 2: Add the single-head SQLite-safe conversational migration and ORM graph

**Files:** Create the fixed migration above; modify `backend/app/models/coach_session.py`, `backend/app/models/__init__.py`; create `backend/tests/test_migrations/test_conversational_coach_migration.py`.

**Interfaces:** Produces extended `InterviewSession`, `SessionQuestion`, `SessionRecording`; `ConversationCommandResultRecord`, `InterviewSessionEvent`, `CoachSessionEvidenceRecord`, `InterviewTranscriptVersion`, `InterviewAttemptEvaluation`, `InterviewAttemptStage`, and `InterviewAttemptUpload`.

- [ ] **Step 1: Capture the full prior-head fixture, then write RED migration and fresh-install tests**

```python
def test_upgrade_backfills_legacy_without_changing_report_or_scores(migrated_legacy_db):
    session = migrated_legacy_db.row("interview_sessions", "legacy-session")
    assert (session["experience_version"], session["conversation_state"], session["state_version"], session["event_version"]) == ("legacy_v1", None, 0, 0)
    assert session["report_json"] == LEGACY_REPORT_JSON
    attempts = migrated_legacy_db.rows("session_recordings", order_by="question_id, attempt_number")
    assert [row["attempt_number"] for row in attempts] == [1, 2, 3]
    assert [row["attempt_kind"] for row in attempts] == ["primary", "retry", "retry"]
    assert migrated_legacy_db.scalar("PRAGMA foreign_key_check") is None

def test_latest_terminal_legacy_skip_outranks_earlier_completion(migrated_legacy_db):
    question = migrated_legacy_db.row("session_questions", "legacy-question")
    assert question["question_state"] == "skipped"
    assert question["accepted_recording_id"] is None
```

Before modifying ORM models, record the PR1 branch's source integration commit, create a disposable database from the complete current `Base.metadata`, stamp it at `p3q4r5s6t7u8`, and require `alembic check`, integrity and foreign-key checks to pass. Export the full SQL schema (including tables, constraints, indexes, triggers and `alembic_version`) to `backend/tests/fixtures/coach/p3q4r5s6t7u8_schema.sql` in canonical `sqlite_schema.type, sqlite_schema.name` order, with normalized LF endings, one semicolon-terminated statement per block, and a header containing the source integration SHA and revision. Record the resulting SQL SHA-256 in the test. The test reconstructs one immutable template database from that hash-checked full-schema snapshot and copies the template for each vector; it must assert the source revision is exactly `p3q4r5s6t7u8` before inserting representative legacy rows or invoking Alembic. Never regenerate this fixture from the post-PR1 ORM graph.

Against independent copies of that full baseline database, test zero/one/multiple attempts, equal timestamps ordered by ID, failed-only recordings -> `pending`, valid latest completed -> `answered`, unknown category unchanged, `upgrade head`, `alembic current`, `downgrade p3q4r5s6t7u8`, re-upgrade, data preservation, foreign keys, integrity, and exactly one head. Also add a separate supported fresh-install test that starts with an empty disposable database, creates the complete post-PR1 ORM schema with `Base.metadata.create_all()`, stamps `q4r5s6t7u8v9`, and verifies `alembic current`, `alembic check`, integrity, foreign keys, plus every required PR1 table, column, constraint and index. Do not invoke the unsupported historical chain on a blank database.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_migrations/test_conversational_coach_migration.py`

Expected: FAIL because revision `q4r5s6t7u8v9` and new columns/tables do not exist.

- [ ] **Step 3: Implement exact additive columns and tables**

The revision is `q4r5s6t7u8v9`, `down_revision = "p3q4r5s6t7u8"`. Add all V6 Section 8.2/12.1 fields to sessions, including `experience_version`, setup/deletion/event/retention versions and claims, planning/plan/contracts/compatibility/retention JSON, amendment version, `report_build_reason`; widen the report-state check to include `invalidated`. Add all Section 13.1 fields to questions and all Section 14.1 fields to recordings. Add these exact tables/keys:

```text
coach_conversation_command_results  UNIQUE(session_id, command_id)
interview_session_events            UNIQUE(session_id, sequence_number)
coach_session_evidence_records      UNIQUE(session_id, evidence_id)
interview_transcript_versions       UNIQUE(recording_id, version_number)
interview_attempt_evaluations       UNIQUE(recording_id, version_number)
interview_attempt_stages            UNIQUE(recording_id, evaluation_version_id, stage_name)
interview_attempt_uploads            UNIQUE(attempt_id, upload_id)
coach_session_deletion_results       UNIQUE(session_key_hash, command_id)
session_recordings                  UNIQUE(question_id, attempt_number), UNIQUE(session_id, client_attempt_id)
session_questions                   UNIQUE(session_id, asked_sequence)
```

Use nullable additions -> SQL backfill -> non-null/check/unique constraints through `batch_alter_table`. Backfill sessions/questions/recordings exactly per V6 Section 18.3. Do not create transcript/evaluation/event/evidence rows for legacy content. Add all Section 18.4 indexes (`idx_interview_sessions_experience_state` through `idx_command_results_session_command`) plus upload/event supporting indexes. Specify `foreign_keys` on ambiguous question-recording/self-question ORM relationships, or expose accepted/root pointers as FK fields without backrefs.

- [ ] **Step 4: Run migration and mapper GREEN**

```bash
cd backend
python -m pytest -q --no-cov tests/test_migrations/test_conversational_coach_migration.py
python -c 'from sqlalchemy.orm import configure_mappers; from app.models import *; configure_mappers()'
alembic heads
```

Expected: PASS; `alembic heads`, the upgraded copies of the full prior-head fixture, and the supported fresh-install fixture report only `q4r5s6t7u8v9`; both fixture paths pass `alembic check`, integrity, and foreign-key checks, and legacy JSON/scores are byte-for-byte unchanged.

- [ ] **Step 5: Commit**

```bash
git add app/models/coach_session.py app/models/__init__.py alembic/versions/20260725_0001_q4r5s6t7u8v9_add_conversational_coach_foundation.py tests/fixtures/coach/p3q4r5s6t7u8_schema.sql tests/test_migrations/test_conversational_coach_migration.py
git commit -m "feat(coach): add conversational persistence foundation"
```

### Task 3: Add strict creation, command, live, and downstream schemas

**Files:** Create `backend/app/schemas/coach_conversation.py`; modify `backend/app/schemas/coach.py`; test `backend/tests/test_services/test_coach_session_plan.py` and `backend/tests/test_routers/test_coach_conversation_router.py`.

**Interfaces:** Produces discriminated creation dispatch, `ConversationCommandRequest/Result`, `ConversationLiveView`, plan/question/attempt/version reads, and stable exports from `coach.py`.

- [ ] **Step 1: Write RED schema tests**

```python
def test_omitted_experience_preserves_legacy_request() -> None:
    request = CreateSessionRequest(company_name="Example", role_title="Architect")
    assert request.experience_version == "legacy_v1"
    assert request.conversational_config is None

def test_conversational_request_normalizes_locale_and_rejects_video() -> None:
    request = CreateSessionRequest.model_validate(VALID_CONVERSATIONAL_REQUEST)
    assert request.conversational_config.locale == "zh-Hant-TW"
    invalid = copy.deepcopy(VALID_CONVERSATIONAL_REQUEST)
    invalid["conversational_config"]["allowed_answer_modes"] = ["video"]
    with pytest.raises(ValidationError):
        CreateSessionRequest.model_validate(invalid)

def test_command_payload_is_discriminated_and_forbids_extra_fields() -> None:
    parsed = ConversationCommandRequest.model_validate(BEGIN_ANSWER)
    assert isinstance(parsed.payload, BeginAnswerPayload)
    with pytest.raises(ValidationError):
        ConversationCommandRequest.model_validate({**BEGIN_ANSWER, "unknown": True})
```

Cover valid locale scripts/numeric regions, invalid variants/private-use, role `other` label rules, unique/bounded focus/evidence IDs/answer modes, draft consent, JD fallback, date/code-point bounds, supported contract versions, UUID/ULID-like IDs, nonnegative state version, NaN/Infinity rejection, and one typed payload model for all 23 commands.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_session_plan.py tests/test_routers/test_coach_conversation_router.py`

Expected: FAIL because conversational schemas do not exist and legacy `CreateSessionRequest` lacks dispatch fields.

- [ ] **Step 3: Implement schemas without changing legacy numeric types**

```python
class ConversationCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=SAFE_TOKEN)]
    command_type: CommandType
    expected_state_version: Annotated[int, Field(ge=0)]
    payload: CommandPayload
    contract_version: Literal["coach_conversation_command_v1"]

class ConversationCommandResult(BaseModel):
    command_id: str
    result: CommandResult
    session_id: str
    state: str
    state_version: int
    active_question_id: str | None
    active_attempt_id: str | None
    async_job_id: str | None
    allowed_commands: list[str]
    contract_version: Literal["coach_conversation_command_result_v1"]
```

Implement the V6 Section 7 creation model and Section 10 live shape, including activity/retention versions, root/active question, active attempt retry budget, bounded processing/progress/retention/silence/error/report projections. Extend `SessionListItem` only with optional `experience_version`, `conversation_state`, `session_level`, and `retention_summary`. Do not alter `AnswerEvaluation`, `SessionFeedbackReport`, `RubricDimension`, or `SessionRubric`.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_services/test_coach_session_plan.py tests/test_routers/test_coach_conversation_router.py tests/test_routers/test_coach_router.py
git add app/schemas/coach.py app/schemas/coach_conversation.py tests/test_services/test_coach_session_plan.py tests/test_routers/test_coach_conversation_router.py
git commit -m "feat(coach): define conversational API schemas"
```

### Task 4: Implement canonical hashing, event allocation, command claims, and atomic attempt reservation

**Files:** Create `backend/app/repositories/conversational_session_repository.py`; create `backend/tests/test_repositories/test_conversational_session_repository.py`.

**Interfaces:** Produces `canonical_request_hash`, `claim_conversation_command`, `complete_conversation_command`, `append_session_events`, `reserve_conversational_attempt`, and the locked version-row/finalisation methods.

- [ ] **Step 1: Write RED repository transaction and race tests**

```python
def test_canonical_hash_collapses_key_order_and_default_representation() -> None:
    assert canonical_request_hash(REQUEST_A, session_id="s1") == canonical_request_hash(REQUEST_B, session_id="s1")

@pytest.mark.asyncio
async def test_duplicate_receipt_precedes_stale_version(repository, started_session):
    first = await repository.execute_atomic_command(START_REQUEST)
    started_session.state_version += 7
    replay = await repository.execute_atomic_command(START_REQUEST)
    assert replay.result == "duplicate"
    assert replay.state_version == first.state_version
    assert await repository.count_events("session_started") == 1

@pytest.mark.asyncio
async def test_concurrent_sixth_attempt_creates_none(repository, asking_question_at_limit):
    results = await asyncio.gather(*[repository.reserve_conversational_attempt(**args) for args in distinct_clients], return_exceptions=True)
    assert sum(isinstance(value, AttemptReservation) for value in results) == 0
    assert await repository.attempt_count(asking_question_at_limit.id) == 5
```

Also prove same command ID/different hash conflicts, rollback leaves no receipt/event/mutation, N events allocate contiguous unique sequences through `event_version`, duplicate client attempt precedes `listening` and limit validation, same client ID/different question/type conflicts, concurrent begin creates at most one active attempt, attempt numbers are contiguous, cancellation/deletion never refunds the monotonic budget, safe parent ownership, and a stale processing finaliser returns `False` with no current-pointer mutation. Per V6 Section 21.11, draft reservation increments `state_version` once but does not increment `activity_version`; attempt submission is the report-input mutation that increments `activity_version`.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_repositories/test_conversational_session_repository.py`

Expected: FAIL because the repository module is absent.

- [ ] **Step 3: Implement short conditional transactions**

```python
def canonical_request_hash(request: ConversationCommandRequest, *, session_id: str) -> str:
    canonical = {
        "session_id": session_id,
        "command_type": request.command_type,
        "expected_state_version": request.expected_state_version,
        "payload": request.payload.model_dump(mode="json", exclude_unset=False, exclude_none=False),
        "contract_version": request.contract_version,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

Use conditional `UPDATE` row counts, not `SELECT FOR UPDATE` or `max()+1`. Reserve attempts by atomically incrementing `attempts_created_count WHERE attempts_created_count < configured_limit`, use its committed value as `attempt_number`, then insert the attempt, snapshot retention/retry limit, transfer/reset pending hints, set active IDs/listening, increment `state_version` once without changing `activity_version`, allocate events, and persist the receipt in one transaction. Increment `activity_version` later when the attempt is submitted and becomes a report input, as required by V6 Section 21.11. Implement version-row creation with unique version allocation and current-pointer/claim predicates. Repository methods flush but the outer command service owns commit/rollback.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_repositories/test_conversational_session_repository.py
git add app/repositories/conversational_session_repository.py tests/test_repositories/test_conversational_session_repository.py
git commit -m "feat(coach): add conversational repository transactions"
```

### Task 5: Persist a complete fenced session plan before `ready`

**Files:** Create `backend/app/services/coach_session_plan.py`; modify `backend/app/services/coach_session_queue.py`; modify `backend/tests/test_services/test_coach_session_queue.py`; expand `backend/tests/test_services/test_coach_session_plan.py`.

**Interfaces:** Produces `SessionPlanBuilder.build(request, sources) -> SessionPlanBuild`; `claim_session_setup`; `persist_session_plan`; `finalise_session_setup`; deterministic `compatibility_key` and immutable bounded evidence package.

- [ ] **Step 1: Write RED plan/setup fence tests**

```python
@pytest.mark.asyncio
async def test_setup_finalises_plan_questions_and_evidence_atomically(plan_service, request):
    claim = await plan_service.claim_initial_setup(request)
    result = await plan_service.run_claim(claim)
    session = await load_session(result.session_id)
    assert session.conversation_state == "ready"
    assert session.status == "setup"
    assert session.setup_generation == session.setup_attempt_count == 1
    assert session.session_plan_contract_version == "coach_session_plan_v1"
    assert await count_planned_questions(session.id) == 6
    assert await evidence_package_hash(session.id) == session.session_plan_json["evidence_snapshot"]["package_hash"]

@pytest.mark.asyncio
async def test_stale_setup_worker_cannot_replace_new_generation(plan_service, retried_setup):
    assert await plan_service.finalise(old_claim, OLD_PLAN) is False
    assert (await load_session(retried_setup.id)).session_plan_json != OLD_PLAN
```

Cover duration defaults, mixed/category distribution, canonical lowercase categories, exact `other` role label NFKC/casefold/whitespace hash, exact compatibility components, evidence order/package hash, max 30 records/2000 each/40000 total, draft consent/approval labels, unsupported locale route, rebuild preserving old audit plan until success, max attempt 3, and stale/expired/deleting predicates.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_session_plan.py tests/test_services/test_coach_session_queue.py`

Expected: FAIL because conversational setup dispatch and builder are absent.

- [ ] **Step 3: Implement experience dispatch and setup ownership**

```python
async def queue_coach_session(request, db, service=None, *, deduplicate_application=False):
    if request.experience_version == "legacy_v1":
        return await queue_legacy_coach_session(request, db, service, deduplicate_application=deduplicate_application)
    if not settings.HATCH_COACH_CONVERSATIONAL_ENABLED:
        raise CoachConversationError("coach_conversation_not_enabled")
    return await queue_conversational_session_setup(request, db)
```

Initial claim persists normalized `planning_request_json`, generation/attempt `1`, job/token/lease/timestamps, `status=setup`, `conversation_state=planning`, and `session_plan_started` before dispatch. Worker uses a fresh `AsyncSessionLocal`. Finalisation conditionally matches status/state/job/token/generation/unexpired/deletion state and atomically replaces staged questions/evidence/plan, clears claim/error, sets completed time/`ready`, increments state once, emits completion/rebuild event. Retryable failure clears ownership and enters setup-scoped `recoverable_error`; exhausted/terminal failure sets both statuses `failed`. Never log plan/evidence bodies.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_services/test_coach_session_plan.py tests/test_services/test_coach_session_queue.py
git add app/services/coach_session_plan.py app/services/coach_session_queue.py tests/test_services/test_coach_session_plan.py tests/test_services/test_coach_session_queue.py
git commit -m "feat(coach): add fenced conversational planning"
```

### Task 6: Implement idempotent foundation command semantics and deterministic terminal stub

**Files:** Create `backend/app/services/coach_conversation_commands.py`; expand service/repository tests.

**Interfaces:** Produces `ConversationCommandService.execute`; PR1-active commands `start`, `begin_answer`, foundation `finish_answer`, `keep_speaking`, `pause`, `resume`, `cancel_attempt`, `retry_answer`, `retry_setup`, `rebuild_plan`, `request_hint`, `update_retention`, `skip_question`; later commands validate registry but return safe `coach_conversation_invalid_state`/resource-blocked until their owning PR.

- [ ] **Step 1: Write RED command tests**

```python
@pytest.mark.asyncio
async def test_start_receipt_state_and_events_are_one_transaction(command_service, ready_session):
    result = await command_service.execute(user_id="local", session_id=ready_session.id, request=START)
    assert (result.state, result.state_version) == ("asking", 1)
    assert await event_types(ready_session.id) == ["session_started", "question_presented"]
    assert await receipt_result(ready_session.id, START.command_id) == result.model_dump(mode="json")

@pytest.mark.asyncio
async def test_stale_command_does_not_mutate(command_service, asking_session):
    response = await execute_error(command_service, BEGIN.model_copy(update={"expected_state_version": 0}))
    assert response.code == "coach_conversation_version_conflict"
    assert await attempt_count(asking_session.id) == 0

@pytest.mark.asyncio
async def test_deterministic_stub_never_emits_scores(command_service, listening_text_attempt):
    result = await command_service.execute(user_id="local", session_id=listening_text_attempt.session_id, request=FINISH_TEXT)
    assert result.state == "awaiting_next_action"
    evaluation = await current_evaluation(listening_text_attempt.id)
    assert evaluation.state == "unavailable"
    assert "score" not in json.dumps(evaluation.rubric_json or {})
```

Test every PR1 legal transition and representative illegal transition; exact hint transfer; retention affects future attempts only; pause stores exact resume state and preserves draft; cancel clears active and marks cancelled; retry preserves attempts and respects budget; skip marks aggregate and advances; start allocates asked sequence once; text finish creates transcript/evaluation/stages and applies a generation-fenced deterministic `unavailable/not_assessed` stub; replay after restart; concurrent commands; rollback on event/receipt failure. Test command routes cannot accept cross-session question/attempt IDs.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_repositories/test_conversational_session_repository.py`

Expected: FAIL because command service is absent.

- [ ] **Step 3: Implement execute order and stub port**

```python
class DeterministicEvaluationStub:
    async def evaluate(self, claim: AttemptProcessingClaim) -> AttemptProcessingResult:
        return AttemptProcessingResult(
            evaluation_state="unavailable",
            evaluation_json={"answer_level": "not_assessed", "contract_version": RUBRIC_CONTRACT},
            transcript_version_id=claim.transcript_version_id,
            diagnostics={"code": "coach_evaluation_unavailable", "execution_mode": "deterministic_stub"},
        )

async def execute(self, *, user_id: str, session_id: str, request: ConversationCommandRequest) -> ConversationCommandResult:
    request_hash = canonical_request_hash(request, session_id=session_id)
    duplicate = await self.repository.get_command_result(session_id=session_id, command_id=request.command_id)
    if duplicate:
        return duplicate.replay_or_raise(request_hash)
    session = await self.repository.require_owned_conversational_session(user_id=user_id, session_id=session_id)
    self.repository.require_state_version(session, request.expected_state_version)
    result = await self._dispatch(session, request)
    await self.repository.persist_completed_command(session=session, request=request, request_hash=request_hash, result=result)
    await self.repository.commit()
    return result
```

Catch `IntegrityError` from concurrent receipt insert, roll back, reload receipt, and replay only on matching hash. Queue actual background work only after claim transaction commit; test mode may invoke stub synchronously through the same claim/finalisation methods. Unsupported PR2/PR3/PR4 semantics must not create successful receipts or partial rows.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_repositories/test_conversational_session_repository.py
git add app/services/coach_conversation_commands.py tests/test_services/test_coach_conversation_commands.py tests/test_repositories/test_conversational_session_repository.py
git commit -m "feat(coach): execute idempotent conversation commands"
```

### Task 7: Add targeted reconciliation and authoritative live projection

**Files:** Create `backend/app/services/coach_live_view.py`; modify `backend/app/services/coach_reconciliation.py`, `backend/app/main.py`; create/modify live and reconciliation tests.

**Interfaces:** Produces `reconcile_conversational_session(db, session_id, now) -> int`, extends the one `reconcile_stale_coach_state(batch_size=100)`, and `CoachLiveViewService.get_live_view`.

- [ ] **Step 1: Write RED stale-claim/transient/live tests**

```python
@pytest.mark.asyncio
async def test_expired_setup_claim_is_fenced_once(db_session, expired_setup):
    assert await reconcile_conversational_session(db_session, expired_setup.id, NOW) == 1
    assert await reconcile_conversational_session(db_session, expired_setup.id, NOW) == 0
    session = await load_session(expired_setup.id)
    assert session.conversation_state == "recoverable_error"
    assert session.recoverable_error_code == "coach_setup_claim_expired"
    assert session.setup_job_id is session.setup_claim_token is None
    assert await event_count(session.id, "session_plan_claim_expired") == 1

@pytest.mark.asyncio
async def test_live_reconciles_then_projects_safe_server_state(live_service, stale_advancing):
    view = await live_service.get_live_view(user_id="local", session_id=stale_advancing.id)
    assert view.conversation_state == "asking"
    assert view.allowed_commands == list(allowed_commands_for(await load_session(stale_advancing.id)))
    assert "transcript" not in json.dumps(view.recoverable_error or {})
```

Cover setup budget exhausted -> failed; mismatched/newer generation no-op; `processing_answer` within deadline no-op; terminal evaluation with missed transition -> awaiting; failed/expired attempt -> recoverable/unavailable; `advancing` and `asking_follow_up` finish once without duplicate question/follow-up; existing legacy answer/report reconciliation unchanged; startup and `/live` both use the shared routine.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_live_view.py tests/test_services/test_coach_reconciliation.py`

Expected: FAIL because live service and conversational reconciliation are absent.

- [ ] **Step 3: Implement bounded conditional recovery and projection**

Live order is fixed: require safe owned conversational session -> targeted reconciliation -> reload -> verify status/state invariants -> project registry-derived commands -> bounded safe response. It never generates questions/evaluation/report. Reconciliation conditionally matches every ownership field, increments state/event exactly once, updates generic async job content-free state, and never spends retry budget automatically. Keep one startup entry point in `main.py`; extend its bounded candidate query rather than registering another startup job.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_services/test_coach_live_view.py tests/test_services/test_coach_reconciliation.py
git add app/services/coach_live_view.py app/services/coach_reconciliation.py app/main.py tests/test_services/test_coach_live_view.py tests/test_services/test_coach_reconciliation.py
git commit -m "feat(coach): reconcile and project live conversation state"
```

### Task 8: Mount strict command/live routes and preserve every legacy route

**Files:** Create `backend/app/routers/coach_conversation.py`; modify `backend/app/routers/coach.py`, `backend/app/main.py`; expand router tests and legacy router regression.

**Interfaces:** Produces `POST /api/coach/sessions/{session_id}/commands`, `GET /api/coach/sessions/{session_id}/live`; extends create/list/detail/capabilities dispatch without changing legacy response meanings.

- [ ] **Step 1: Write RED route, ownership, flag, and compatibility tests**

```python
@pytest.mark.asyncio
async def test_command_route_returns_canonical_conflict(client, seeded_asking_session):
    response = await client.post(f"/api/coach/sessions/{seeded_asking_session.id}/commands", json=STALE_BEGIN_JSON)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversation_version_conflict"
    assert set(response.json()["error"]) >= {"message", "retryable", "current_state", "current_state_version", "correlation_id", "details"}

@pytest.mark.asyncio
async def test_legacy_submit_rejects_conversational_session_without_mutation(client, seeded_conversational_session):
    response = await client.post(f"/api/coach/sessions/{seeded_conversational_session.id}/submit-answer", json={"transcript": "synthetic"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "coach_conversational_command_required"
    assert await recording_count(seeded_conversational_session.id) == 0
```

Test flag-off conversational create -> safe rejection, omitted/legacy create still 202, existing conversational `/live` works flag-off, unsafe/malformed/traversal IDs, wrong parent IDs, unsupported contract, error redaction canaries, unknown/legacy session live conflicts, `/sessions/{id}/retry` conversational 409, legacy video/report/progress unchanged, capabilities truthfully reports feature disabled and `video_analysis_for_conversational=false`.

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_router.py tests/test_routers/test_coach_router.py`

Expected: FAIL with 404 for new routes and missing experience guards.

- [ ] **Step 3: Mount the same-prefix router and guards**

```python
router = APIRouter(prefix="/api/coach", tags=["coach"])

@router.post("/sessions/{session_id}/commands", response_model=ConversationCommandResult)
async def execute_command(session_id: str, request: ConversationCommandRequest,
    db: AsyncSession = Depends(get_db)) -> ConversationCommandResult:
    _require_safe_id(session_id, "session_id")
    return await ConversationCommandService(ConversationalSessionRepository(db)).execute(
        user_id="local", session_id=session_id, request=request
    )

@router.get("/sessions/{session_id}/live", response_model=ConversationLiveView)
async def get_live(session_id: str, db: AsyncSession = Depends(get_db)) -> ConversationLiveView:
    _require_safe_id(session_id, "session_id")
    return await CoachLiveViewService(ConversationalSessionRepository(db)).get_live_view(
        user_id="local", session_id=session_id
    )
```

Use the existing app-lock/auth boundary and shared `_require_safe_id`; do not invent multi-user ownership. Add conversational router once in `main.py`. Legacy route guards load experience before side effects/job creation. Extend summaries with optional fields only.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_router.py tests/test_routers/test_coach_router.py tests/test_routers/test_coach_async.py
git add app/routers/coach_conversation.py app/routers/coach.py app/main.py tests/test_routers/test_coach_conversation_router.py tests/test_routers/test_coach_router.py
git commit -m "feat(coach): expose conversational command and live APIs"
```

### Task 9: Lock legacy report, schema, async, and migration regressions

**Files:** Modify only existing Coach tests where an explicit fixture/assertion is needed; do not modify legacy production report/evaluator/aggregation code.

**Interfaces:** Proves `legacy_v1` remains byte/numeric compatible and new dispatch cannot reinterpret it.

- [ ] **Step 1: Add RED-before-fix regression assertions**

```python
@pytest.mark.asyncio
async def test_legacy_fixture_report_is_identical_after_conversational_migration(legacy_report_fixture, db_session):
    before = legacy_report_fixture.expected_json
    actual = await CoachService().get_report(legacy_report_fixture.session_id, db_session)
    assert actual.model_dump(mode="json") == before

def test_legacy_openapi_schemas_keep_numeric_contract(client):
    schema = client.app.openapi()["components"]["schemas"]
    assert schema["RubricDimension"]["properties"]["score"]["maximum"] == 10
    assert "session_level" not in schema["SessionFeedbackReport"]["properties"]
```

Add assertions for omitted experience creation, legacy latest-completed canonical resolver, video row readability, numeric progress/trend, retry-session chaining, async create/answer/report reconciliation, and no migration mutation of `report_json`, `overall_score`, `evaluation_json`, `speech_metrics`, or `video_metrics`.

- [ ] **Step 2: Run regression and fix only dispatch/schema leakage**

```bash
cd backend
python -m pytest -q --no-cov \
  tests/test_routers/test_coach_router.py \
  tests/test_routers/test_coach_async.py \
  tests/test_services/test_coach_session_queue.py \
  tests/test_services/test_coach_reconciliation.py \
  tests/test_migrations/test_coach_c1_migration.py \
  tests/test_migrations/test_conversational_coach_migration.py
```

Expected initially: any new assertion exposing dispatch leakage fails. Minimal GREEN changes may touch only the PR1 dispatch/schema/repository files already listed; do not alter legacy aggregation logic.

- [ ] **Step 3: Commit regression evidence**

```bash
git add backend/tests
git commit -m "test(coach): lock conversational legacy compatibility"
```

Expected: focused legacy and conversational suite PASS; no production legacy evaluator/report file in the commit.

### Task 10: Run security, migration, traceability, and review gates

**Files:** No application changes unless a failing binding test drives a new RED/GREEN fix in its owning task.

- [ ] **Step 1: Run focused PR1 gate**

```bash
cd backend
python -m pytest -q --no-cov \
  tests/test_services/test_coach_conversation_state.py \
  tests/test_services/test_coach_conversation_commands.py \
  tests/test_services/test_coach_live_view.py \
  tests/test_services/test_coach_session_plan.py \
  tests/test_repositories/test_conversational_session_repository.py \
  tests/test_routers/test_coach_conversation_router.py \
  tests/test_migrations/test_conversational_coach_migration.py
```

Expected: PASS with exact count recorded. Verify negative (safe ID/ownership/state/version/type/bounds), adversarial (payload/content/error canaries), replay/race (receipt/client ID/setup/worker/transient), and safe failure (no partial persistence or disclosure) classes. Record omitted upload-path/media/deletion/model-output tests as later-PR scope, not silent gaps.

- [ ] **Step 2: Run migration and full backend gates**

```bash
cd backend
alembic heads
python -m pytest -q --no-cov -s tests/test_migrations/test_conversational_coach_migration.py
python -m pytest tests/ -v --tb=short
cd ..
python scripts/check_docs.py
make ci
git status --short
git diff --check feature/coach-phase1-phase2...HEAD
```

Expected: one script head `q4r5s6t7u8v9`; the migration test visibly runs `alembic current` and proves revision `q4r5s6t7u8v9` on upgraded copies of the hash-locked full `p3q4r5s6t7u8` fixture and on the supported fresh-install fixture. Full tests/docs/CI exit 0; no whitespace errors; only PR1-scoped files differ. Capture command output without transcript/evidence/raw IDs/paths/secrets.

- [ ] **Step 3: Complete traceability with observed RED/GREEN evidence**

Copy this table into the PR evidence and replace each planned outcome with actual exit status/count/hash/path; do not delete rows:

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §0.1-0.6, §39.2 — tracked authority and correct base/target | Start gate: hash/topology mismatch must stop | tracked V6/design; branch metadata | baseline commands above | Record base/head/target and hashes |
| §7, §12, AC-01 — versioned creation and complete fenced plan | `test_setup_finalises_plan_questions_and_evidence_atomically`: missing builder | schemas, plan service, queue, repository | plan/queue tests | Record RED/GREEN and count |
| §8, Appendix A, AC-02 — one state/allowed-command authority | `test_allowed_commands_are_derived_from_transition_registry`: import failure | state/contracts services | state/live tests | Record parity result |
| §9.4-9.7, AC-03/04 — semantic hash, duplicate-before-version, atomic receipt | `test_duplicate_receipt_precedes_stale_version`: missing repository | repository, command service | repository/command tests | Record restart/replay/race result |
| §9.9, §13-17, AC-10/11/19/20 — attempts and version/fence primitives | command/reservation/stale finaliser tests fail before models | migration/models/repository/commands | focused PR1 suite | Record exact cases |
| §11 — event allocator and privacy | contiguous event/rollback tests fail before table | models/migration/repository | repository tests | Record unique sequences/leak scan |
| §18, §44.1-44.2 — SQLite-safe migration/backfill/ORM | migration revision absent | migration/models | migration tests; Alembic commands | Record one head, FK/downgrade |
| §21.10, AC-11 — stale setup/attempt/transient reconciliation | expired setup test is unrecovered | reconciliation/live/main | reconciliation/live tests | Record first=1, repeat=0 |
| §31.7, §35, AC-30 — one safe error registry | forbidden alias/unknown code test fails | contracts/router | state/router tests | Record registry/redaction result |
| §32, §34, AC-29 — union dispatch and legacy preservation | legacy report/OpenAPI fixture mismatch if leaked | schemas/router/queue/tests | legacy regression commands | Record byte/numeric parity |
| §36.1 — feature default off | flag test fails before setting | config/router/queue | state/router tests | Record create blocked/read allowed |
| §37.2-37.7, §42.1-42.2 — state/idempotency/concurrency gates | mapped RED cases above | all PR1 implementation files | focused/full backend | Record pass counts |

- [ ] **Step 4: Request the two mandatory reviews in order**

Specification-compliance review packet: V6/design hashes, integration base/head/target, scope/exclusions, complete traceability table, RED/GREEN evidence, migration head/FK/backfill evidence, flag-off proof, legacy fixture proof, and explicit confirmation of no Phase 2 work. Resolve every finding and rerun affected commands.

Only after compliance passes, request code-quality/security review with transaction boundaries, SQLite conditional updates, ORM ambiguity handling, idempotency races, ownership/safe-ID/error leakage tests, stale-worker fences, and test quality. Critical/high findings block merge; record owner/disposition and verification for every medium.

- [ ] **Step 5: Produce merge-readiness record without merging**

```bash
git log --oneline feature/coach-phase1-phase2..HEAD
git diff --stat feature/coach-phase1-phase2...HEAD
git status --short
```

Record PR scope/exclusions; base/head/target; commits; completed traceability; RED/GREEN outputs; compliance verdict; quality/security verdict; one-head migration evidence; targeted/full/CI counts; synthetic-isolated security statement; leakage review; limitations/unexecuted later-PR gates; and merge readiness. PR1 is not ready if the flag is on, a later-PR behavior is partially implemented, any required evidence is missing, or either review has unresolved binding findings.

## PR2 handoff gate

After PR1 merges into `feature/coach-phase1-phase2`, PR2 must inspect—not assume—the locked interfaces at the start of this plan. The merged head must provide:

```text
experience dispatch and flag-off creation/read behavior
single canonical transition/error/contract registries
command receipt and session event persistence
extended session/question/recording ORM rows
transcript/evaluation/stage/upload ORM tables
atomic attempt reservation and event sequencing
setup generation/job/token/lease fencing
processing generation/version/finalisation primitives
ConversationCommandRequest, ConversationCommandResult, ConversationLiveView
ConversationCommandService / CoachConversationCommandService alias
CoachLiveViewService
ConversationalSessionRepository locked signatures
startup and lazy conversational reconciliation
unchanged legacy numeric/report/progress/canonical-attempt behavior
```

If any signature is materially absent or behavior differs from V6, stop PR2 and correct PR1 through its integration-targeted fix process. Do not recreate or reinterpret the foundation in PR2.
