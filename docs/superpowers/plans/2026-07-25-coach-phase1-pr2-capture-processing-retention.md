# Coach Phase 1 PR2 Capture, Processing, and Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the V6 conversational typed/audio capture, bounded attempt-processing pipeline, truthful audio retention, refresh recovery, and accessible browser controls on top of the merged PR1 foundation.

**Architecture:** The browser renders `GET /live`, keeps only unsent text/media capture locally, and issues PR1 idempotent commands; audio upload is a separate hash-verified operation. Backend workers use `AsyncJobService`, PR1 stage/evaluation rows, one absolute processing deadline, generation/claim fences, and an independently claimed cleanup path. Final rubric, evidence, follow-ups, coaching, acceptance, reports, progress, transcript editing/deletion, hard deletion, export, observability expansion, and rollout remain later-PR work.

**Tech Stack:** Python 3, FastAPI, Pydantic, async SQLAlchemy, Alembic/SQLite, `AsyncJobService`, configured `Transcriber` via `perception_factory`, React 18, Next.js 15, TypeScript, browser MediaRecorder/Web Audio APIs, Vitest/Testing Library, and Playwright.

## Global Constraints

- Authority is `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md`; earlier Phase 1 specs, the PDF, and Phase 2 documents do not amend it.
- Work on `phase1/pr2-capture-processing-retention`, created from `feature/coach-phase1-phase2` only after PR1 is merged; target that integration branch, never `main` or an unmerged PR1 branch.
- PR1 must already provide the V6 state/command/event, question/attempt, transcript/evaluation/stage, repository, live-read, reconciliation, compatibility, and disabled feature-flag contracts. Stop on a material mismatch; do not recreate PR1 inside PR2.
- `SessionRecording` remains the physical answer-attempt aggregate; do not add an `InterviewAttempt` table or bypass `session_repository.py`.
- `HATCH_COACH_CONVERSATIONAL_ENABLED = false` remains the creation default until acceptance evidence authorizes rollout; disabled mode must preserve existing conversational reads and retention cleanup.
- Defaults are exact: processing job 900 seconds; transcription 300; speech analysis 120; conversational evaluation 300; evidence grounding 180; follow-up decision 120; audio cleanup 180; silence warning 4000 ms; finish prompt 9000 ms; answer limit 600 seconds; manual processing retries 2; failed-audio retention 24 hours; audio `delete_after_processing`; transcript `retain`.
- PR2 defines `HATCH_COACH_MEDIA_ROOT` as a validated `Path` setting with repository default `./data/coach-media`; tests and security gates override it with a dedicated temporary directory.
- Audio capture is `MediaRecorder`; conversational voice processing must not depend on browser Web Speech. Typed answers remain available when microphone access fails.
- No automatic submit at silence thresholds, no live filler/WPM/rubric/confidence feedback, and no conversational video, facial, emotion, personality, deception, presence, or confidence analysis.
- Treat audio, transcript, IDs, upload metadata, MIME type, filename, and paths as untrusted. Use safe parent ownership, generated paths, byte/hash/type bounds, exact URI/hash/policy/claim fencing, and content-free errors/logs.
- Use synthetic data and isolated local/ephemeral services for security, E2E, and failure tests. Never run destructive, fuzz, or active security tests against production/shared systems or real candidate data.
- PR2 uses PR1's deterministic evaluation stub to terminate content evaluation as `unavailable` with answer/delivery level `not_assessed`; it must not invent a completed rubric result. It must not implement PR3 rubric/evidence/coaching/follow-up/acceptance behavior or PR4 report/progress/export/hard-deletion/rollout behavior.
- Every implementation task follows RED → minimal GREEN → focused regression → commit. Do not combine commits shown below.

---

## PR1 prerequisite contract and stop gate

The post-PR1 integration head must expose these exact consumable contracts (names may already be re-exported from the shown modules):

```python
# backend/app/schemas/coach_conversation.py
class ConversationCommandRequest(BaseModel):
    command_id: str
    command_type: str
    expected_state_version: int
    payload: dict[str, object]
    contract_version: str

class ConversationCommandResult(BaseModel):
    command_id: str
    result: str
    session_id: str
    state: str
    state_version: int
    active_question_id: str | None
    active_attempt_id: str | None
    async_job_id: str | None
    allowed_commands: list[str]
    contract_version: str

class ConversationLiveView(BaseModel):
    session_id: str
    experience_version: str
    status: str
    conversation_state: str
    state_version: int
    activity_version: int
    retention_version: int
    active_question: dict[str, object] | None
    active_attempt: dict[str, object] | None
    processing: dict[str, object] | None
    progress: dict[str, int]
    retention: dict[str, object]
    allowed_commands: list[str]
    silence_policy: dict[str, int]
    recoverable_error: dict[str, object] | None
    report_state: str
    contract_version: str
```

Required callable signatures are:

- `ConversationalSessionRepository.create_transcript_version(*, recording_id: str, source: str, transcript: str, expected_attempt_version: int, processing_generation: int) -> InterviewTranscriptVersion`
- `ConversationalSessionRepository.create_evaluation_version(*, recording_id: str, transcript_version_id: str | None, evaluation_version: int, processing_generation: int, contract_version: str, state: str, async_job_id: str | None = None) -> InterviewAttemptEvaluation`
- `ConversationalSessionRepository.claim_attempt_processing(*, recording_id: str, expected_generation: int, job_id: str, deadline: datetime) -> AttemptProcessingClaim | None`
- `ConversationalSessionRepository.finalise_attempt_processing(*, claim: AttemptProcessingClaim, result: AttemptProcessingResult) -> bool`
- `ConversationalSessionRepository.append_session_events(*, session_id: str, events: Sequence[SessionEventInput]) -> tuple[InterviewSessionEvent, ...]`
- `ConversationCommandService.execute(*, user_id: str, session_id: str, request: ConversationCommandRequest) -> ConversationCommandResult` (`CoachConversationCommandService` is the PR1 compatibility alias)
- `CoachLiveViewService.get_live_view(*, user_id: str, session_id: str) -> ConversationLiveView`

PR1 must also have ORM rows/fields for `InterviewTranscriptVersion`, `InterviewAttemptEvaluation`, `InterviewAttemptStage`, the extended `InterviewSession`/`SessionQuestion`/`SessionRecording`, and `InterviewAttemptUpload` (V6 §19). If PR1 deliberately leaves only `InterviewAttemptUpload` for PR2, create one additive PR2 migration with `alembic revision -m "add conversational attempt uploads"`, retaining the generated filename/revision and setting `down_revision` to the verified merged PR1 head; do not guess a revision ID or branch Alembic history.

## Scope and file map

**Create:**

- `backend/app/services/coach_attempt_pipeline.py` — stage graph, shared deadline, retry/reuse selection, and fenced finalisation orchestration.
- `backend/app/services/coach_retention.py` — independent default/explicit audio cleanup claims and exact owned-file deletion.
- `backend/app/services/coach_media_storage.py` — streamed temporary upload, hashing, safe generated paths, atomic move, and owned-file removal.
- `backend/tests/test_services/test_coach_attempt_pipeline.py`
- `backend/tests/test_services/test_coach_retention.py`
- `backend/tests/test_repositories/test_conversational_media_repository.py`
- `backend/tests/test_routers/test_coach_conversation_capture.py`
- `frontend/src/components/coach/conversation/ConversationSession.tsx`
- `frontend/src/components/coach/conversation/ConversationQuestion.tsx`
- `frontend/src/components/coach/conversation/ConversationControls.tsx`
- `frontend/src/components/coach/conversation/ConversationRecorder.tsx`
- `frontend/src/components/coach/conversation/SilencePrompt.tsx`
- `frontend/src/components/coach/conversation/ConversationProgress.tsx`
- `frontend/src/components/coach/conversation/RetentionStatus.tsx`
- `frontend/src/components/coach/conversation/__tests__/ConversationSession.test.tsx`
- `frontend/src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx`
- `frontend/src/components/coach/conversation/__tests__/RetentionControls.test.tsx`
- `frontend/e2e/coach-conversation-capture.spec.ts`

**Modify:**

- `backend/app/config.py` — exact V6 limits/timeouts and validation bounds.
- `backend/app/models/coach_session.py` and `backend/app/models/__init__.py` only if PR1 omitted the V6 upload model while intentionally assigning it to PR2.
- `backend/app/repositories/conversational_session_repository.py` — upload identity, pipeline/stage claims, retry/reuse, and retention claim/finalisation transactions.
- `backend/app/schemas/coach_conversation.py` — typed upload/read/processing/retention payloads.
- `backend/app/services/coach_conversation_commands.py` — PR2 implementations for typed/audio `finish_answer`, `keep_speaking`, pause/resume, cancel, `retry_processing`, and future-attempt retention updates.
- `backend/app/services/coach_live_view.py` — processing counters/stage, retention projection, and browser silence/duration policy.
- `backend/app/services/coach_reconciliation.py` — stale attempt/stage and pending cleanup recovery while retaining one startup entry point.
- `backend/app/routers/coach_conversation.py` — multipart audio upload route and post-commit pipeline dispatch.
- `backend/app/services/speech_analyser.py` — V6 observable metric result without prohibited inference fields.
- `frontend/src/lib/api.ts` — discriminated conversational types, live/upload/command helpers, and safe conflict handling.
- `frontend/src/app/coach/session/[id]/page.tsx` — experience dispatch only; retain legacy implementation/components.
- `frontend/src/__tests__/setup.ts` — deterministic MediaRecorder, media-stream, AudioContext, ResizeObserver, and visibility mocks required by component tests.
- `frontend/e2e/api-flows.spec.ts` — capability contract assertion only if PR1 has not already updated it.

**Do not modify in PR2:** `frontend/src/app/coach/report/[id]/page.tsx`, legacy `EvaluationCard`, `ScoreRadar`, `FeedbackReport`, benchmark fixtures/profiles, report/progress services, evidence/grounding/coaching/follow-up services, or Phase 2 files.

## Traceability matrix

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §14.4, §15, §17, §21.1-§21.9 / AC-05 — typed finish creates immutable transcript/evaluation/stages and reaches review | `test_typed_finish_claims_generation_and_pipeline`: RED because PR1 stub has no PR2 pipeline | command service, conversational repository, `coach_attempt_pipeline.py` | `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_attempt_pipeline.py -k typed` | Required GREEN: exit 0; stub terminates `unavailable`, answer/delivery are `not_assessed`, and no numeric user score exists |
| §19, §30.4-§30.6 — upload ownership, streaming hash, idempotency, generated path | `test_audio_upload_is_hash_verified_and_idempotent` plus cross-session/path/hash cases | media storage, repository, router, schemas | `cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_capture.py tests/test_repositories/test_conversational_media_repository.py` | Required GREEN: one completed upload; failed/duplicate temp files absent; safe errors contain no path |
| §20 / AC-06, AC-07 — MediaRecorder capture, calibrated silence prompt, manual override | recorder unit tests and Playwright voice scenario | recorder, silence prompt, controls, test setup, E2E | `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx` | Required GREEN: Finish/Keep Speaking shown; warning never submits; mic denial leaves text enabled |
| §8.5-§8.6, §10.5 / AC-02, AC-06 — pause/resume and refresh recovery use server state | `ConversationSession.test.tsx` refresh/conflict/paused capture cases | session shell, API helper, command service/live view | `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationSession.test.tsx` | Required GREEN: `/live` wins; no false recorder-resumed claim; same command ID survives network retry |
| §21.3-§21.10 / AC-28 — ordered stages, one 900-second deadline, bounded retry/reuse, restart recovery | deadline, unavailable, reuse, stale finalizer, reconciliation tests | pipeline, repository, reconciliation, config | `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_attempt_pipeline.py tests/test_services/test_coach_reconciliation.py` | Required GREEN: stale worker mutates no authority; failures yield unavailable/recoverable, never a low level |
| §22.1-§22.2 — observable delivery only | `test_conversational_metrics_exclude_prohibited_fields` | `speech_analyser.py`, pipeline schemas | `cd backend && python -m pytest -q --no-cov tests/test_services/test_speech_analyser.py -k conversational` | Required GREEN: only duration/word/WPM/filler/hedging/pause/long-pause/restart fields |
| §29.1-§29.4 / AC-08, AC-09, AC-26 — default cleanup is early, retained policy blocks cleanup, explicit deletion preserves analytical data | retention claim/failure/stale replacement/version tests | retention service, repository, pipeline/reconciliation | `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_retention.py` | Required GREEN: transcript/evaluation survive; state/retention versions increment exactly once; activity version unchanged |
| §8.5, §9.3/§9.9, §10.3, §11.3, §20.7, §29.3-§29.4, §37.3/§37.7/§37.12, AC-31/AC-32 — approved cancelled-cleanup retry and ten-minute technical hard-stop contracts | Task 10 contract-addendum documentation review before implementation | V6, command/live/retention/reconciliation/recorder contracts | `python scripts/check_docs.py` | Required GREEN: V6 records `record_capture_hard_stop`, `answer_capture_hard_limit_reached`, nullable retry ID, exact `asking` reuse of `delete_audio`, cancelled `delete_failed` exclusion from general cleanup, job-ID/token/deadline/fence-digest retry generations without a numeric schema field, and bounded stable candidate discovery/reconciliation/race rules |
| §33.1-§33.5, §33.10-§33.11 / AC-02, AC-05-AC-07, AC-25 — state-driven accessible shell with no live score | shell/recorder/retention tests and E2E text/voice scenarios | page dispatch, conversation components, API types | `cd frontend && npm test -- --run src/components/coach/conversation` | Required GREEN: keyboard controls, live region, visible text states, no ScoreRadar/filler/WPM/confidence UI |
| §34 / AC-29 — legacy route and numeric UI unchanged | existing Coach frontend/backend regression | page dispatch and router branch only | `cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_router.py tests/test_routers/test_coach_async.py && cd ../frontend && npm test -- --run src/__tests__/components/coach` | Required GREEN: all legacy assertions pass unchanged |
| §37.6-§37.7, §37.12-§37.15, §42.2-§42.7 — retries/races/privacy/accessibility/E2E | complete PR2 suite | all PR2 files | commands in Task 10 | Required GREEN: typed/audio E2E, default deletion, pause/resume, restart, no-live-score, stale cleanup all pass |

### Task 1: Gate on merged PR1 and lock PR2 interfaces

**Files:**
- Test: existing PR1 files and tests listed in the prerequisite contract
- Create later: no file in this task

**Interfaces:**
- Consumes: merged PR1 contracts shown above.
- Produces: recorded base SHA, V6/design SHA-256 values, one Alembic head, clean baseline outputs, and a confirmed file/signature map for Tasks 2-10.

- [ ] **Step 1: Verify ancestry, branch, authority, and clean state**

```bash
git fetch origin
git switch feature/coach-phase1-phase2
git pull --ff-only
git log -1 --format='%H %s'
git status --short
git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
sha256sum docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md
```

Expected: integration is current, status is empty, and both authority documents are tracked/hashable.

- [ ] **Step 2: Prove PR1 is merged before branching**

```bash
test -f backend/app/services/coach_conversation_commands.py
test -f backend/app/services/coach_live_view.py
test -f backend/app/repositories/conversational_session_repository.py
rg -n 'class (InterviewTranscriptVersion|InterviewAttemptEvaluation|InterviewAttemptStage|InterviewAttemptUpload)' backend/app/models
rg -n 'HATCH_COACH_CONVERSATIONAL_ENABLED.*false|HATCH_COACH_CONVERSATIONAL_ENABLED.*False' backend/app/config.py
cd backend && alembic heads
```

Expected: every file/symbol exists, feature creation remains disabled by default, and exactly one post-PR1 head is printed. If any assertion fails, stop and report PR1 as unmerged/incomplete; do not branch or edit application code.

- [ ] **Step 3: Create the PR2 branch from the verified head**

```bash
git switch -c phase1/pr2-capture-processing-retention
git merge-base --is-ancestor feature/coach-phase1-phase2 HEAD
git rev-parse HEAD
```

Expected: ancestry exits 0 and HEAD equals the recorded integration SHA.

- [ ] **Step 4: Run the pre-change baseline**

```bash
python scripts/check_docs.py
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_state.py tests/test_services/test_coach_conversation_commands.py tests/test_services/test_coach_live_view.py tests/test_repositories/test_conversational_session_repository.py tests/test_migrations/test_conversational_coach_migration.py
cd ../frontend && npm run type-check && npm test && npm run build
```

Expected: all commands exit 0. Diagnose any pre-existing failure before PR2 and preserve its exact output separately.

### Task 2: Add bounded configuration and PR2 schemas

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/schemas/coach_conversation.py`
- Create: `backend/tests/test_services/test_coach_conversational_contracts.py`

**Interfaces:**
- Consumes: PR1 contract constants and error registry.
- Produces: validated timing/size settings; `AttemptAudioUploadRead`; `AttemptProcessingClaim`; `AttemptProcessingResult`; `RetentionStatus`.

- [ ] **Step 1: Write failing schema/config tests**

```python
from pathlib import Path


def test_pr2_defaults_and_bounds():
    assert Settings().HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS == 900
    assert Settings().HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS == 180
    assert Settings().HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS == 24
    assert Settings().HATCH_COACH_MEDIA_ROOT == Path("./data/coach-media")
    with pytest.raises(ValidationError):
        Settings(HATCH_COACH_MAX_ANSWER_DURATION_SECONDS=0)

def test_upload_read_rejects_non_hex_hash():
    with pytest.raises(ValidationError):
        AttemptAudioUploadRead(
            attempt_id="attempt-1", upload_id="upload-1", result="completed",
            content_sha256="not-a-hash", byte_size=3, mime_type="audio/webm",
            audio_retention_state="temporary",
            contract_version="coach_attempt_audio_upload_v1",
        )
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_contracts.py -k 'pr2_defaults or upload_read'`

Expected: FAIL because the settings/models are absent.

- [ ] **Step 3: Add exact settings and bounded schemas**

```python
HATCH_COACH_MEDIA_ROOT: Path = Path("./data/coach-media")
HATCH_COACH_TIMEOUT_CONVERSATIONAL_JOB_SECONDS: int = Field(default=900, ge=60, le=3600)
HATCH_COACH_TIMEOUT_TRANSCRIPTION_SECONDS: int = Field(default=300, ge=10, le=900)
HATCH_COACH_TIMEOUT_SPEECH_ANALYSIS_SECONDS: int = Field(default=120, ge=10, le=900)
HATCH_COACH_TIMEOUT_CONVERSATIONAL_EVALUATION_SECONDS: int = Field(default=300, ge=10, le=900)
HATCH_COACH_TIMEOUT_EVIDENCE_GROUNDING_SECONDS: int = Field(default=180, ge=10, le=900)
HATCH_COACH_TIMEOUT_FOLLOWUP_DECISION_SECONDS: int = Field(default=120, ge=10, le=900)
HATCH_COACH_TIMEOUT_AUDIO_CLEANUP_JOB_SECONDS: int = Field(default=180, ge=10, le=900)
HATCH_COACH_SILENCE_WARNING_MS: int = Field(default=4000, ge=1000, le=30000)
HATCH_COACH_SILENCE_FINISH_PROMPT_MS: int = Field(default=9000, ge=2000, le=60000)
HATCH_COACH_MAX_ANSWER_DURATION_SECONDS: int = Field(default=600, ge=60, le=1800)
HATCH_COACH_MAX_AUDIO_BYTES: int = Field(default=50 * 1024 * 1024, ge=1024, le=250 * 1024 * 1024)
HATCH_COACH_AUDIO_FAILURE_RETENTION_HOURS: int = Field(default=24, ge=1, le=168)
```

Add Pydantic literals for upload result `pending|completed|failed|deleted`, retention state `not_applicable|temporary|retained|delete_pending|deleted|delete_failed`, the 8 fixed stage names and 9 fixed stage states. Validate lowercase 64-hex SHA-256, positive bytes, and bounded MIME strings.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_contracts.py
cd .. && git add backend/app/config.py backend/app/schemas/coach_conversation.py backend/tests/test_services/test_coach_conversational_contracts.py
git commit -m "feat(coach): define capture processing contracts"
```

Expected: PASS; commit contains only settings/schema/test changes.

### Task 3: Implement streamed, idempotent audio upload

**Files:**
- Create: `backend/app/services/coach_media_storage.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/routers/coach_conversation.py`
- Create: `backend/tests/test_repositories/test_conversational_media_repository.py`
- Create: `backend/tests/test_routers/test_coach_conversation_capture.py`

**Interfaces:**
- Consumes: `InterviewAttemptUpload`, PR1 active attempt/state ownership, `_require_safe_id`, and canonical JSON hashing.
- Produces: `coach_upload_temp_dir(storage_root: Path) -> Path`; `stream_audio_upload(upload: UploadFile, *, max_bytes: int, temp_dir: Path) -> StagedAudio`; `resolve_owned_audio_path(storage_root: Path, session_id: str, attempt_id: str, upload_id: str, suffix: str) -> Path`; `persist_audio_upload(*, session_id: str, attempt_id: str, upload_id: str, declared_sha256: str, staged: StagedAudio, destination: Path) -> AttemptAudioUploadRead`; `POST /api/coach/sessions/{session_id}/attempts/{attempt_id}/audio`.

- [ ] **Step 1: Write RED tests for success, replay, and trust boundaries**

```python
@pytest.mark.asyncio
async def test_audio_upload_is_hash_verified_and_idempotent(client, seeded_listening_audio_attempt):
    body = b"synthetic-webm"
    digest = hashlib.sha256(body).hexdigest()
    first = await client.post(URL, data={"upload_id": "upload-1", "content_sha256": digest}, files={"audio": ("../../x.webm", body, "audio/webm")})
    replay = await client.post(URL, data={"upload_id": "upload-1", "content_sha256": digest}, files={"audio": ("different.webm", body, "audio/webm")})
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert await count_completed_uploads() == 1

@pytest.mark.parametrize("case", ["wrong_session", "wrong_attempt", "bad_hash", "too_large", "bad_mime", "symlink_escape"])
async def test_audio_upload_rejects_untrusted_case_without_persistence(case, client, seeded_listening_audio_attempt):
    response = await exercise_case(case, client)
    assert response.status_code in {400, 404, 409, 413, 422}
    assert await count_completed_uploads() == 0
    assert no_temporary_uploads_remain()

@pytest.mark.asyncio
async def test_audio_upload_uses_only_configured_media_root(tmp_path, settings, client):
    settings.HATCH_COACH_MEDIA_ROOT = tmp_path / "isolated-coach-media"
    await upload_synthetic_audio(client)
    root = settings.HATCH_COACH_MEDIA_ROOT.resolve()
    assert all(path.resolve().is_relative_to(root) for path in persisted_and_temporary_paths())
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_capture.py tests/test_repositories/test_conversational_media_repository.py`

Expected: FAIL because route/storage/repository methods are absent.

- [ ] **Step 3: Implement storage and repository transaction**

```python
@dataclass(frozen=True)
class StagedAudio:
    temporary_path: Path
    content_sha256: str
    byte_size: int
    mime_type: str

async def stream_audio_upload(upload: UploadFile, *, max_bytes: int, temp_dir: Path) -> StagedAudio:
    digest = hashlib.sha256()
    size = 0
    fd, raw_path = tempfile.mkstemp(dir=temp_dir, prefix="coach-upload-")
    path = Path(raw_path)
    try:
        with os.fdopen(fd, "wb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise CoachMediaError("coach_attempt_upload_conflict")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        return StagedAudio(path, digest.hexdigest(), size, normalize_audio_mime(upload.content_type))
    except BaseException:
        path.unlink(missing_ok=True)
        raise

def resolve_owned_audio_path(storage_root: Path, session_id: str, attempt_id: str, upload_id: str, suffix: str) -> Path:
    root = storage_root.resolve()
    candidate = (root / session_id / f"{attempt_id}-{upload_id}{suffix}").resolve()
    if not candidate.is_relative_to(root) or (candidate.exists() and candidate.is_symlink()):
        raise CoachMediaError("coach_attempt_upload_conflict")
    return candidate
```

Create the configured root and required parents before opening files. Both the temporary upload directory and every persisted destination must be descendants of `settings.HATCH_COACH_MEDIA_ROOT.resolve()`; reject symlink or resolution escapes. Tests must override this setting so no media path depends on the checkout or process working directory.

Repository order must be: verify streamed bytes/hash → load `(attempt_id, upload_id)` → return matching completed result after deleting duplicate temp → reject changed request hash → conditionally require conversational/listening/active attempt/draft/audio ownership → atomically move to generated path → insert result/update attempt to `uploaded`. Never use the client filename. Roll back DB and remove the moved file on transaction failure.

- [ ] **Step 4: Mount the route and return the exact V6 response**

```python
@router.post(
    "/sessions/{session_id}/attempts/{attempt_id}/audio",
    response_model=AttemptAudioUploadRead,
)
async def upload_attempt_audio(
    session_id: str,
    attempt_id: str,
    upload_id: Annotated[str, Form(min_length=1, max_length=64)],
    content_sha256: Annotated[str, Form(pattern=r"^[0-9a-f]{64}$")],
    audio: UploadFile = File(),
    db: AsyncSession = Depends(get_db),
) -> AttemptAudioUploadRead:
    _require_safe_id(session_id, "session_id")
    _require_safe_id(attempt_id, "attempt_id")
    storage_root = settings.HATCH_COACH_MEDIA_ROOT
    staged = await stream_audio_upload(
        audio,
        max_bytes=settings.HATCH_COACH_MAX_AUDIO_BYTES,
        temp_dir=coach_upload_temp_dir(storage_root),
    )
    destination = resolve_owned_audio_path(storage_root, session_id, attempt_id, upload_id, ".webm")
    return await ConversationalSessionRepository(db).persist_audio_upload(
        session_id=session_id,
        attempt_id=attempt_id,
        upload_id=upload_id,
        declared_sha256=content_sha256,
        staged=staged,
        destination=destination,
    )
```

- [ ] **Step 5: Run GREEN, leak scan, and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_capture.py tests/test_repositories/test_conversational_media_repository.py
cd .. && rg -n 'filename|audio_uri|temporary_path' backend/app/routers/coach_conversation.py backend/app/services/coach_media_storage.py
git add backend/app/services/coach_media_storage.py backend/app/repositories/conversational_session_repository.py backend/app/routers/coach_conversation.py backend/tests/test_repositories/test_conversational_media_repository.py backend/tests/test_routers/test_coach_conversation_capture.py
git commit -m "feat(coach): add fenced conversational audio upload"
```

Expected: PASS; inspection confirms filenames are metadata only and paths never enter response/error/log text.

### Task 4: Implement typed and audio stage processing

**Files:**
- Create: `backend/app/services/coach_attempt_pipeline.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/speech_analyser.py`
- Create: `backend/tests/test_services/test_coach_attempt_pipeline.py`
- Modify: `backend/tests/test_services/test_speech_analyser.py`

**Interfaces:**
- Consumes: `get_transcriber().transcribe(audio_path) -> TranscriptionResult`, `SpeechAnalyserService.analyse_from_timestamps`, PR1 deterministic evaluation stub, stage/evaluation repository claims.
- Produces and exports from `backend/app/services/coach_attempt_pipeline.py`: `AttemptStage`, `AttemptProcessingContext`, `StageResult`, `SpeechMetricsSnapshot`, `SessionEvidenceSnapshot`; `queue_attempt_processing(claim: AttemptProcessingClaim) -> None`; `run_attempt_pipeline(claim: AttemptProcessingClaim, stages: Sequence[AttemptStage]) -> AttemptProcessingResult`; typed/audio `finish_answer` command behavior. PR3 imports these five public types directly and must not redefine them.

- [ ] **Step 1: Write RED happy-path tests**

```python
from dataclasses import fields
from inspect import signature
from typing import get_type_hints
from app.services.coach_attempt_pipeline import (
    AttemptProcessingContext, AttemptStage, SessionEvidenceSnapshot,
    SpeechMetricsSnapshot, StageResult,
)

def test_pr3_pipeline_interfaces_are_stable_and_exported():
    assert get_type_hints(AttemptStage) == {"name": str}
    assert tuple(signature(AttemptStage.run).parameters) == ("self", "context")
    assert [field.name for field in fields(AttemptProcessingContext)] == [
        "session_id", "question_id", "recording_id", "transcript_version_id",
        "evaluation_version_id", "processing_generation", "deadline_at",
        "recording_type", "normalized_transcript", "speech_metrics", "evidence_records",
    ]
    assert [field.name for field in fields(StageResult)] == [
        "stage_name", "stage_state", "output", "error_code", "retryable",
        "attempt_count", "repair_count",
    ]
    assert [field.name for field in fields(SpeechMetricsSnapshot)] == [
        "duration_ms", "word_count", "words_per_minute", "filler_count",
        "filler_rate_per_minute", "hedging_count", "pause_count",
        "long_pause_count", "restart_count",
    ]
    assert [field.name for field in fields(SessionEvidenceSnapshot)] == [
        "evidence_id", "source_type", "source_record_id", "source_record_version",
        "source_path", "snapshot_text", "approval_state", "content_hash", "snapshot_hash",
    ]

@pytest.mark.asyncio
async def test_typed_finish_claims_generation_and_pipeline(repo, command_service):
    result = await finish_text(command_service, transcript="I led the synthetic migration.")
    attempt, evaluation, stages = await load_claimed_rows(repo, result.active_attempt_id)
    assert attempt.attempt_state == "pending_processing"
    assert attempt.processing_generation == 1
    assert evaluation.transcript_version_id == attempt.current_transcript_version_id
    assert stage_states(stages, "audio_persist", "transcription", "speech_analysis") == ["not_applicable"] * 3
    assert result.async_job_id

@pytest.mark.asyncio
async def test_audio_pipeline_binds_transcript_and_delivery_without_prohibited_fields(pipeline, audio_claim):
    outcome = await pipeline.run(audio_claim)
    assert outcome.evaluation_state == "unavailable"
    assert outcome.answer_level == "not_assessed"
    assert set(outcome.speech_metrics) <= {"duration_ms", "word_count", "words_per_minute", "filler_count", "filler_rate_per_minute", "hedging_count", "pause_count", "long_pause_count", "restart_count"}

def test_audio_context_is_valid_before_transcription(audio_context):
    assert audio_context.transcript_version_id is None
    assert audio_context.normalized_transcript is None

@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["transcript_version_id", "normalized_transcript"])
async def test_content_stages_reject_missing_bound_transcript_without_persistence(missing, pipeline, audio_context):
    context = replace(audio_context, transcript_version_id="tv-1", normalized_transcript="synthetic answer")
    context = replace(context, **{missing: None})
    result = await pipeline.run_content_stages(context)
    assert result.error_code == "coach_attempt_stage_dependency_missing"
    assert result.retryable is False
    assert await downstream_result_count(context.recording_id) == 0
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_attempt_pipeline.py -k 'typed or audio_pipeline'`

Expected: FAIL because orchestration is absent.

- [ ] **Step 3: Implement the fixed stage graph and post-commit dispatch**

```python
@dataclass(frozen=True)
class SpeechMetricsSnapshot:
    duration_ms: int
    word_count: int
    words_per_minute: float
    filler_count: int
    filler_rate_per_minute: float
    hedging_count: int
    pause_count: int
    long_pause_count: int
    restart_count: int | None

@dataclass(frozen=True)
class SessionEvidenceSnapshot:
    evidence_id: str
    source_type: str
    source_record_id: str
    source_record_version: str
    source_path: str
    snapshot_text: str
    approval_state: str
    content_hash: str
    snapshot_hash: str

@dataclass(frozen=True)
class StageResult:
    stage_name: str
    stage_state: Literal["completed", "unavailable", "failed_retryable", "failed_terminal"]
    output: Mapping[str, object] | None
    error_code: str | None
    retryable: bool
    attempt_count: int
    repair_count: int

@dataclass(frozen=True)
class AttemptProcessingContext:
    session_id: str
    question_id: str
    recording_id: str
    transcript_version_id: str | None
    evaluation_version_id: str
    processing_generation: int
    deadline_at: datetime
    recording_type: Literal["text", "audio"]
    normalized_transcript: str | None
    speech_metrics: SpeechMetricsSnapshot | None
    evidence_records: tuple[SessionEvidenceSnapshot, ...]

class AttemptStage(Protocol):
    name: str
    async def run(self, context: AttemptProcessingContext) -> StageResult:
        raise NotImplementedError

__all__ = (
    "AttemptStage", "AttemptProcessingContext", "StageResult",
    "SpeechMetricsSnapshot", "SessionEvidenceSnapshot",
)

PIPELINE_ORDER = (
    "audio_persist", "transcription", "speech_analysis", "content_evaluation",
    "evidence_grounding", "follow_up_decision", "coaching_enrichment", "audio_cleanup",
)

def effective_timeout(deadline: datetime, ceiling_seconds: int, now: datetime) -> float:
    remaining = (deadline - now).total_seconds()
    if remaining <= 0:
        raise AttemptPipelineError("coach_attempt_job_budget_exhausted", retryable=True)
    return min(float(ceiling_seconds), remaining)

def require_bound_transcript(context: AttemptProcessingContext) -> tuple[str, str]:
    if context.transcript_version_id is None or context.normalized_transcript is None:
        raise AttemptPipelineError("coach_attempt_stage_dependency_missing", retryable=False)
    return context.transcript_version_id, context.normalized_transcript
```

Typed attempts normalize NFC/LF, create transcript/evaluation/stages in the command transaction, mark three media stages `not_applicable`, then run the PR1 deterministic evaluator stub. The stub returns terminal `unavailable` plus `not_assessed`, preserving the transcript and permitting review/retry/explicit continuation without a fabricated rubric. Audio contexts begin with `transcript_version_id=None` and `normalized_transcript=None`; tests must prove this pre-transcription state is valid. Audio attempts require the completed upload ID/hash, bind a worker-produced immutable transcript before content evaluation, and run transcription and speech analysis as independent siblings. Call `require_bound_transcript` before content evaluation, evidence grounding, or follow-up work; a missing transcript must produce the canonical non-retryable stage dependency error and persist no downstream result. Do not add final PR3 evaluation logic.

- [ ] **Step 4: Implement V6 observable speech projection**

Return `duration_ms`, `word_count`, `words_per_minute`, `filler_count`, `filler_rate_per_minute`, `hedging_count`, `pause_count`, `long_pause_count`, and `restart_count` only when the restart method is deterministic; do not call voice-emotion/video analyzers and do not persist their fields for `conversational_v1`.

- [ ] **Step 5: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_attempt_pipeline.py -k 'typed or audio_pipeline or pr3_pipeline_interfaces' tests/test_services/test_speech_analyser.py
cd .. && git add backend/app/services/coach_attempt_pipeline.py backend/app/services/coach_conversation_commands.py backend/app/repositories/conversational_session_repository.py backend/app/services/speech_analyser.py backend/tests/test_services/test_coach_attempt_pipeline.py backend/tests/test_services/test_speech_analyser.py
git commit -m "feat(coach): process typed and audio attempts"
```

### Task 5: Enforce deadlines, retry/reuse, stale fencing, and restart recovery

**Files:**
- Modify: `backend/app/services/coach_attempt_pipeline.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/coach_reconciliation.py`
- Modify: `backend/tests/test_services/test_coach_attempt_pipeline.py`
- Modify: `backend/tests/test_services/test_coach_reconciliation.py`

**Interfaces:**
- Consumes: PR1 `retry_processing`, stage claim rows, generic jobs, `processing_generation` fences.
- Produces: `select_restart_stage(previous_stages, immutable_inputs) -> str`; idempotent stale processing reconciliation.

- [ ] **Step 1: Write RED deadline/retry/race tests**

```python
@pytest.mark.asyncio
async def test_stage_retries_never_extend_absolute_deadline(fake_clock, pipeline):
    outcome = await pipeline.run(claim(deadline=fake_clock.now + timedelta(seconds=2)))
    assert outcome.error_code == "coach_attempt_job_budget_exhausted"
    assert all(call.started_at <= outcome.job_deadline_at for call in provider_calls)

@pytest.mark.asyncio
async def test_retry_reuses_only_valid_upstream_and_reruns_downstream(repo):
    claim = await repo.claim_retry_processing(recording_id=RID)
    assert states(claim.stages) == {"transcription": "reused", "speech_analysis": "reused", "content_evaluation": "pending", "evidence_grounding": "pending", "follow_up_decision": "pending"}

@pytest.mark.asyncio
async def test_old_generation_finaliser_is_stale_without_mutation(repo):
    before = await authority_snapshot(repo)
    stale_claim = claim(processing_generation=1)
    assert await repo.finalise_attempt_processing(
        claim=stale_claim,
        result=new_generation_result(),
    ) is False
    assert await authority_snapshot(repo) == before
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_attempt_pipeline.py -k 'deadline or retry or stale' tests/test_services/test_coach_reconciliation.py -k conversational`

Expected: FAIL on missing retry/reconciliation semantics.

- [ ] **Step 3: Implement exact retry selection and fences**

Use earliest incomplete/retryably failed applicable stage; create all new-generation rows; mark valid prior stages `reused` only with identical input hashes, source transcript/audio hash, and contract versions; rerun the restart stage and every downstream applicable stage. Duplicate command lookup remains before retry budget validation, manual retry increments once, and internal stage retries do not consume `processing_retry_count`.

- [ ] **Step 4: Extend reconciliation**

Reconcile only conditional matches on session state, active recording, job ID, evaluation ID, processing generation, stage claim token, source version/hash, and deadline. Terminal completed/unavailable work advances to `awaiting_next_action`; retryable failures enter attempt/session `recoverable_error`; stale workers write content-free generic-job diagnostics only. Repeat reconciliation and assert zero additional events/version increments.

- [ ] **Step 5: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_attempt_pipeline.py tests/test_services/test_coach_reconciliation.py
cd .. && git add backend/app/services/coach_attempt_pipeline.py backend/app/services/coach_conversation_commands.py backend/app/repositories/conversational_session_repository.py backend/app/services/coach_reconciliation.py backend/tests/test_services/test_coach_attempt_pipeline.py backend/tests/test_services/test_coach_reconciliation.py
git commit -m "feat(coach): fence retries and processing recovery"
```

### Task 6: Implement default and explicit audio cleanup

**Files:**
- Create: `backend/app/services/coach_retention.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/coach_attempt_pipeline.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/services/coach_live_view.py`
- Modify: `backend/app/services/coach_reconciliation.py`
- Create: `backend/tests/test_services/test_coach_retention.py`

**Interfaces:**
- Consumes: attempt-snapshotted policy, `audio_cleanup` stage, exact media ownership helper.
- Produces: `claim_default_cleanup(recording_id: str, now: datetime) -> AudioCleanupClaim | None`; `finalise_audio_cleanup(claim: AudioCleanupClaim, result: Literal["deleted", "delete_failed", "stale_claim"]) -> bool`; `delete_audio` and `update_retention` command behavior.

- [ ] **Step 1: Write RED retention tests**

```python
@pytest.mark.asyncio
async def test_default_cleanup_claims_before_evaluation_finishes(retention, seeded_audio):
    mark_transcription_committed_and_speech_terminal(seeded_audio)
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    claim = await retention.claim_default_cleanup(seeded_audio.id, now)
    assert claim is not None
    assert seeded_audio.audio_retention_state == "delete_pending"
    assert content_evaluation_is_pending(seeded_audio)

@pytest.mark.asyncio
async def test_cleanup_fence_cannot_delete_replacement(retention, seeded_audio):
    now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    claim = await retention.claim_default_cleanup(seeded_audio.id, now)
    replace_uri_and_hash(seeded_audio)
    assert await retention.delete_claimed_audio(claim) == "stale_claim"
    assert replacement_file_exists()

@pytest.mark.asyncio
async def test_explicit_delete_preserves_transcript_evaluation_and_activity_version(retention, seeded_audio):
    before = analytical_snapshot(seeded_audio)
    await retention.delete_audio(seeded_audio.id)
    assert analytical_snapshot(seeded_audio) == before
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_retention.py`

Expected: FAIL because retention service/claims are absent.

- [ ] **Step 3: Implement exact claim/finalisation behavior**

Claim only after transcript commit and speech terminal, independently of evaluation. Require URI, hash, snapshotted policy, retention state, generation/job/token, and resolved owned path. Success clears URI and increments attempt version + session state/retention versions once, never activity version. Failure sets `delete_failed` and increments those versions once per cleanup generation. For failed transcription, set eligibility at `failed_at + 24 hours`; reconciliation claims only when due.

- [ ] **Step 4: Implement live retention and future-policy update**

`update_retention` changes only the session policy and amendment metadata for future attempts; existing attempt snapshots never change. `/live.retention` returns current policy and active-attempt audio state truthfully. `delete_audio` is idempotent and preserves transcript/evaluation/speech metrics.

- [ ] **Step 5: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_retention.py tests/test_services/test_coach_attempt_pipeline.py tests/test_services/test_coach_reconciliation.py
cd .. && git add backend/app/services/coach_retention.py backend/app/repositories/conversational_session_repository.py backend/app/services/coach_attempt_pipeline.py backend/app/services/coach_conversation_commands.py backend/app/services/coach_live_view.py backend/app/services/coach_reconciliation.py backend/tests/test_services/test_coach_retention.py
git commit -m "feat(coach): delete conversational audio by default"
```

### Task 7: Add typed API client and experience-dispatched shell

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/coach/session/[id]/page.tsx`
- Create: `frontend/src/components/coach/conversation/ConversationSession.tsx`
- Create: `frontend/src/components/coach/conversation/ConversationQuestion.tsx`
- Create: `frontend/src/components/coach/conversation/ConversationControls.tsx`
- Create: `frontend/src/components/coach/conversation/ConversationProgress.tsx`
- Create: `frontend/src/components/coach/conversation/RetentionStatus.tsx`
- Create: `frontend/src/components/coach/conversation/__tests__/ConversationSession.test.tsx`

**Interfaces:**
- Consumes: PR1 `/live`, command result, experience discriminator; PR2 upload response.
- Produces: `getCoachConversationLive`; `sendCoachConversationCommand`; `uploadCoachAttemptAudio`; `LegacyCoachSession`/`ConversationSession` dispatch.

- [ ] **Step 1: Write RED server-authority/conflict/security tests**

```tsx
it("renders the refreshed server state and does not infer advancement locally", async () => {
  mockLive({ conversation_state: "processing_answer", allowed_commands: [] });
  render(<ConversationSession sessionId="session-1" />);
  expect(await screen.findByText("Reviewing answer")).toBeVisible();
  expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
});

it("refreshes live state on 409 without duplicating the command", async () => {
  mockCommandConflict();
  await user.click(screen.getByRole("button", { name: "Pause interview" }));
  expect(commandBodies()).toHaveLength(1);
  expect(liveFetchCount()).toBe(2);
});

it("renders transcript markup as text", async () => {
  mockLiveWithTranscript('<img src=x onerror="window.__pwned=1">');
  render(<ConversationSession sessionId="session-1" />);
  expect(await screen.findByText(/<img/)).toBeVisible();
  expect(document.querySelector("img")).toBeNull();
});
```

- [ ] **Step 2: Run RED**

Run: `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationSession.test.tsx`

Expected: FAIL because client types/shell are absent.

- [ ] **Step 3: Implement discriminated types and stable command IDs**

```typescript
export async function sendCoachConversationCommand(
  sessionId: string,
  command: ConversationCommandRequest,
): Promise<ConversationCommandResult> {
  return apiFetch(`/api/coach/sessions/${sessionId}/commands`, {
    method: "POST",
    body: JSON.stringify(command),
  });
}
```

Generate one UUID when the user action starts; reuse it only for network retry; never silently retry 409. On 409 fetch `/live`, preserve unsent text/blob, and announce that the interview changed. Use server `allowed_commands`; do not duplicate a client transition registry.

- [ ] **Step 4: Refactor page dispatch without changing legacy flow**

Move the existing page body intact behind `LegacyCoachSession`. The page loads the session summary and chooses by `experience_version`; conversational rendering must not import `LiveFeedback`, `ScoreRadar`, `FaceCapture`, or legacy submit helpers.

- [ ] **Step 5: Run GREEN, legacy regression, and commit**

```bash
cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationSession.test.tsx src/__tests__/components/coach && npm run type-check
cd .. && git add frontend/src/lib/api.ts 'frontend/src/app/coach/session/[id]/page.tsx' frontend/src/components/coach/conversation
git commit -m "feat(coach): render conversational server state"
```

### Task 8: Add MediaRecorder capture, silence prompt, and truthful pause recovery

**Files:**
- Create: `frontend/src/components/coach/conversation/ConversationRecorder.tsx`
- Create: `frontend/src/components/coach/conversation/SilencePrompt.tsx`
- Modify: `frontend/src/components/coach/conversation/ConversationControls.tsx`
- Modify: `frontend/src/components/coach/conversation/ConversationSession.tsx`
- Modify: `frontend/src/__tests__/setup.ts`
- Create: `frontend/src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx`

**Interfaces:**
- Consumes: `begin_answer`, upload, `finish_answer`, `keep_speaking`, `pause`, `resume`, `cancel_attempt`; live silence/duration policy.
- Produces: local capture state `{recorder, stream, chunks, elapsedMs, calibratedNoiseDb, speechSeen, unsentBlob}` and accessible controls.

- [ ] **Step 1: Write RED recorder tests**

```tsx
it("shows Finish and Keep speaking after calibrated silence and never auto-submits", async () => {
  vi.useFakeTimers();
  render(<ConversationRecorder sessionId="session-1" attemptId="attempt-1" mode="audio" onFinish={onFinish} />);
  await user.click(screen.getByRole("button", { name: "Start audio answer" }));
  feedNoiseCalibration(-52); feedSpeech(-25); feedSilence(-55);
  vi.advanceTimersByTime(9000);
  expect(screen.getByRole("alert")).toHaveTextContent("Are you finished?");
  expect(onFinish).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Keep speaking" })).toBeEnabled();
});

it("keeps typed answering available when microphone permission is denied", async () => {
  denyMicrophone();
  render(<ConversationSession sessionId="session-1" />);
  await user.click(screen.getByRole("button", { name: "Start audio answer" }));
  expect(screen.getByRole("textbox", { name: "Your answer" })).toBeEnabled();
});
```

- [ ] **Step 2: Run RED**

Run: `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx`

Expected: FAIL because recorder/silence components are absent.

- [ ] **Step 3: Implement capture and calibrated silence state machine**

Use a short noise-floor sample, a relative threshold, debounced speech/silence, `minimum_speech_before_silence_prompt_ms = 1500`, warning at server-provided 4000 ms, prompt at 9000 ms, neutral warning at 5 minutes, and hard local stop at 10 minutes. `Pause` calls `MediaRecorder.pause()` and command `pause`; `resume` calls `MediaRecorder.resume()` only when the same in-memory recorder exists.

- [ ] **Step 4: Implement refresh truthfulness and navigation safety**

When `/live` says `listening` but no local recorder/blob exists, show exactly two recovery paths: discard/cancel then retry, or upload a still-available captured blob. Never claim recording resumed. Register `beforeunload` only while an unsent local recording/blob exists; processing and later states do not block navigation.

- [ ] **Step 5: Add accessibility and reduced-motion behavior**

All actions are native buttons with action+state labels, focus remains on the invoked control unless a user opens the finish prompt, status changes use one polite `aria-live` region, capture health/elapsed time have text equivalents, and animation classes are guarded by reduced-motion styles.

- [ ] **Step 6: Run GREEN and commit**

```bash
cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx src/components/coach/conversation/__tests__/ConversationSession.test.tsx && npm run type-check
cd .. && git add frontend/src/components/coach/conversation/ConversationRecorder.tsx frontend/src/components/coach/conversation/SilencePrompt.tsx frontend/src/components/coach/conversation/ConversationControls.tsx frontend/src/components/coach/conversation/ConversationSession.tsx frontend/src/__tests__/setup.ts frontend/src/components/coach/conversation/__tests__/ConversationRecorder.test.tsx
git commit -m "feat(coach): add accessible conversational recording"
```

### Task 9: Add retention UI and browser E2E acceptance scenarios

**Files:**
- Modify: `frontend/src/components/coach/conversation/RetentionStatus.tsx`
- Modify: `frontend/src/components/coach/conversation/ConversationSession.tsx`
- Create: `frontend/src/components/coach/conversation/__tests__/RetentionControls.test.tsx`
- Create: `frontend/e2e/coach-conversation-capture.spec.ts`

**Interfaces:**
- Consumes: live retention projection and `update_retention`/`delete_audio` allowed commands.
- Produces: future-attempt policy disclosure/control, current-attempt immutable status, typed/audio/default deletion/pause/restart browser evidence.

- [ ] **Step 1: Write RED retention/accessibility tests**

```tsx
it("distinguishes future policy from the current attempt snapshot", async () => {
  mockLive({ retention: { audio_policy: "retain_until_deleted", current_audio_state: "temporary" } });
  render(<RetentionStatus sessionId="session-1" live={currentLiveView()} onCommand={sendCommand} />);
  expect(screen.getByText(/future answers/i)).toBeVisible();
  expect(screen.getByText(/this answer.*delete after processing/i)).toBeVisible();
});

it("contains no live score or confidence output", () => {
  render(<ConversationSession sessionId="session-1" />);
  expect(screen.queryByText(/wpm|filler|confidence|score|good answer|bad answer/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run RED**

Run: `cd frontend && npm test -- --run src/components/coach/conversation/__tests__/RetentionControls.test.tsx`

Expected: FAIL until policy/snapshot copy and controls exist.

- [ ] **Step 3: Implement truthful retention UI**

Render text states for `temporary`, `retained`, `delete_pending`, `deleted`, and `delete_failed`; enable actions strictly from `allowed_commands`. State that policy changes apply to future attempts and cannot rescue deleted audio or retroactively delete retained audio. Do not imply transcript/evaluation deletion from audio deletion.

- [ ] **Step 4: Add Playwright scenarios with mocked MediaRecorder and synthetic media**

```typescript
const sessionSummary = {
  id: "session-e2e", experience_version: "conversational_v1", status: "active",
  company_name: "Synthetic Ltd", role_title: "Test Engineer", overall_score: null,
  questions: [], created_at: "2026-07-25T00:00:00Z",
};

function live(state: string, version: number, overrides: Record<string, unknown> = {}) {
  return {
    session_id: "session-e2e", experience_version: "conversational_v1", status: "active",
    conversation_state: state, state_version: version, activity_version: 1,
    retention_version: 0,
    active_question: { id: "question-1", text: "Describe a synthetic delivery.", attempts_created_count: 1, attempt_limit: 5, attempts_remaining: 4 },
    active_attempt: { id: "attempt-1", recording_type: "text", transcript: "Synthetic answer", processing_retry_count: 0, processing_retry_limit: 2, processing_retries_remaining: 2 },
    processing: null, progress: { planned_questions_total: 3, planned_questions_completed: 0, follow_ups_completed: 0, current_planned_position: 1 },
    retention: { audio_policy: "delete_after_processing", current_audio_state: "not_applicable" },
    allowed_commands: state === "asking" ? ["begin_answer", "pause"] : [],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000, max_answer_duration_seconds: 600 },
    recoverable_error: null, report_state: "not_started", contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

async function installRoutes(page: Page, states: Array<Record<string, unknown>>) {
  let liveRead = 0;
  const commands: Array<Record<string, unknown>> = [];
  await page.route("**/api/coach/sessions/session-e2e", route => route.fulfill({ json: sessionSummary }));
  await page.route("**/api/coach/sessions/session-e2e/live", route => {
    const body = states[Math.min(liveRead, states.length - 1)];
    liveRead += 1;
    return route.fulfill({ json: body });
  });
  await page.route("**/api/coach/sessions/session-e2e/commands", async route => {
    const body = route.request().postDataJSON();
    commands.push(body);
    return route.fulfill({ json: { command_id: body.command_id, result: "completed", session_id: "session-e2e", state: "processing_answer", state_version: body.expected_state_version + 1, active_question_id: "question-1", active_attempt_id: "attempt-1", async_job_id: "job-1", allowed_commands: [], contract_version: "coach_conversation_command_result_v1" } });
  });
  return { commands, liveReads: () => liveRead };
}

test("typed answer survives refresh and reaches unavailable review", async ({ page }) => {
  const routes = await installRoutes(page, [live("asking", 1), live("processing_answer", 3), live("awaiting_next_action", 4, { allowed_commands: ["retry_answer", "accept_attempt"] })]);
  await page.goto("/coach/session/session-e2e");
  await page.getByRole("button", { name: "Type answer" }).click();
  await page.getByRole("textbox", { name: "Your answer" }).fill("Synthetic answer");
  await page.getByRole("button", { name: "Finish typed answer" }).click();
  await page.reload();
  await expect(page.getByText("Answer review unavailable")).toBeVisible();
  expect(routes.commands.filter(command => command.command_type === "finish_answer")).toHaveLength(1);
});

test("voice silence prompt keeps speaking then shows deleted audio with transcript", async ({ page }) => {
  await page.addInitScript(() => {
    class Recorder {
      state = "inactive"; mimeType = "audio/webm"; ondataavailable: ((event: { data: Blob }) => void) | null = null; onstop: (() => void) | null = null;
      start() { this.state = "recording"; }
      pause() { this.state = "paused"; }
      resume() { this.state = "recording"; }
      stop() { this.ondataavailable?.({ data: new Blob(["synthetic"], { type: this.mimeType }) }); this.state = "inactive"; this.onstop?.(); }
      static isTypeSupported() { return true; }
    }
    Object.defineProperty(window, "MediaRecorder", { value: Recorder });
  });
  await installRoutes(page, [live("asking", 1), live("listening", 2, { allowed_commands: ["finish_answer", "keep_speaking", "pause"] }), live("awaiting_next_action", 5, { retention: { audio_policy: "delete_after_processing", current_audio_state: "deleted" }, allowed_commands: ["retry_answer"] })]);
  await page.goto("/coach/session/session-e2e");
  await page.getByRole("button", { name: "Start audio answer" }).click();
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("coach:test-silence", { detail: { elapsedMs: 9000, speechSeenMs: 1500 } })));
  await expect(page.getByRole("alert")).toContainText("Are you finished?");
  await page.getByRole("button", { name: "Keep speaking" }).click();
  await page.getByRole("button", { name: "Finish answer" }).click();
  await expect(page.getByText("Audio deleted after processing")).toBeVisible();
  await expect(page.getByText("Synthetic answer")).toBeVisible();
});

test("paused capture does not submit and refresh offers recovery", async ({ page }) => {
  const routes = await installRoutes(page, [live("listening", 2, { allowed_commands: ["finish_answer", "pause"] }), live("paused", 3, { allowed_commands: ["resume", "cancel_attempt"] })]);
  await page.goto("/coach/session/session-e2e");
  await page.getByRole("button", { name: "Pause interview" }).click();
  await page.reload();
  await expect(page.getByText("Recording cannot be resumed in this browser tab")).toBeVisible();
  await expect(page.getByRole("button", { name: "Discard and retry" })).toBeVisible();
  expect(routes.commands.some(command => command.command_type === "finish_answer")).toBe(false);
});

test("backend restart resumes processing without duplicate begin", async ({ page }) => {
  const routes = await installRoutes(page, [live("processing_answer", 3), live("processing_answer", 3), live("awaiting_next_action", 4, { allowed_commands: ["retry_answer"] })]);
  await page.goto("/coach/session/session-e2e");
  await expect(page.getByText("Reviewing answer")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Answer review unavailable")).toBeVisible();
  expect(routes.commands.filter(command => command.command_type === "begin_answer")).toHaveLength(0);
  expect(routes.liveReads()).toBeGreaterThanOrEqual(3);
});
```

Add the `coach:test-silence` listener only in non-production test builds (`process.env.NODE_ENV === "test"`), routing its payload through the same debounced silence-state function as the Web Audio analyser. Route fixtures contain only synthetic IDs/text/media. Also assert request retries reuse stable command/upload IDs and the page contains no live numeric scoring or confidence language.

- [ ] **Step 5: Run GREEN and commit**

```bash
cd frontend && npm test -- --run src/components/coach/conversation && npm run type-check && npx playwright test e2e/coach-conversation-capture.spec.ts --project=chromium
cd .. && git add frontend/src/components/coach/conversation/RetentionStatus.tsx frontend/src/components/coach/conversation/ConversationSession.tsx frontend/src/components/coach/conversation/__tests__/RetentionControls.test.tsx frontend/e2e/coach-conversation-capture.spec.ts
git commit -m "test(coach): cover capture recovery and retention"
```

### Task 10: Run PR2 security, regression, and review gates

**Files:**
- Modify only files required to resolve a demonstrated PR2 failure.
- Evidence: PR description or repository-approved external evidence record; do not add generated logs containing sensitive content.

**Interfaces:**
- Consumes: completed Tasks 1-9.
- Produces: reproducible RED/GREEN record, traceability completion, two ordered review verdicts, and merge-readiness decision.

- [ ] **Step 1: Run focused backend and frontend suites**

```bash
cd backend && python -m pytest -q --no-cov \
  tests/test_services/test_coach_conversation_state.py \
  tests/test_services/test_coach_conversation_commands.py \
  tests/test_services/test_coach_live_view.py \
  tests/test_services/test_coach_attempt_pipeline.py \
  tests/test_services/test_coach_retention.py \
  tests/test_repositories/test_conversational_session_repository.py \
  tests/test_repositories/test_conversational_media_repository.py \
  tests/test_routers/test_coach_conversation_router.py \
  tests/test_routers/test_coach_conversation_capture.py \
  tests/test_services/test_coach_reconciliation.py \
  tests/test_services/test_speech_analyser.py
cd ../frontend && npm test -- --run src/components/coach/conversation src/__tests__/components/coach && npm run type-check
```

Expected: exit 0 with pass counts recorded.

- [ ] **Step 2: Run isolated PR2 security cases and leakage scan**

```bash
cd backend && python -m pytest -q --no-cov \
  tests/test_routers/test_coach_conversation_capture.py \
  tests/test_repositories/test_conversational_media_repository.py \
  tests/test_services/test_coach_attempt_pipeline.py \
  tests/test_services/test_coach_retention.py \
  -k 'ownership or hash or mime or size or path or symlink or idempot or stale or deadline or leak or redaction'
cd ../frontend && npm test -- --run src/components/coach/conversation -t 'markup|conflict|microphone|refresh|retention|score|confidence'
```

Expected: exit 0; synthetic canaries do not appear in captured error bodies, logs, diagnostics, metric labels, screenshots, or traces. Record omitted threat classes with a concrete reason; critical/high findings block merge and every medium finding receives an explicit disposition.

- [ ] **Step 3: Run migration, full repository, build, and E2E gates**

```bash
cd backend && alembic heads && alembic upgrade head && alembic current
python -m pytest tests/ -v --tb=short
cd ../frontend && npm test && npm run type-check && npm run build && npx playwright test e2e/coach-conversation-capture.spec.ts --project=chromium
cd .. && python scripts/check_docs.py && make ci
```

Expected: one Alembic head; every command exits 0. If the full Playwright environment is unavailable, PR2 is not merge-ready until the exact missing dependency/service is supplied and the gate is rerun.

- [ ] **Step 4: Verify scope and forbidden content**

```bash
git diff --name-only feature/coach-phase1-phase2...HEAD
git diff --check feature/coach-phase1-phase2...HEAD
rg -n 'Candidate Intelligence|mentor persona|confidence band|governance gateway|ScoreRadar|LiveFeedback|FaceCapture' backend/app/services/coach_attempt_pipeline.py backend/app/services/coach_retention.py frontend/src/components/coach/conversation || true
```

Expected: only PR2 files appear; diff check is empty; no Phase 2 entity/persona or conversational legacy scoring/perception import exists.

- [ ] **Step 5: Request reviews in binding order**

First request specification-compliance review against V6 §§14-15, 17, 19-22, 29.1-29.4, 32-37, 39 PR2, 40-46 and AC-02/05/06/07/08/09/25/26/28/29/30. Only after it passes, request code-quality/security review of transaction fences, upload/path safety, local capture lifecycle, accessibility, and test quality. Resolve findings and rerun every affected command.

- [ ] **Step 6: Complete evidence and commit gate fixes separately**

For each traceability row, replace “Required GREEN” in the PR evidence (not this plan) with the exact command, exit status, pass count, SHA, and artifact path. The approved Task 10 addendum must first bind the exact V6 hard-stop and cancelled-cleanup retry contracts listed in the traceability matrix, then record the resulting V6 SHA-256 in its implementation evidence. Record scope/exclusions, integration base/head/target, RED failures, GREEN results, one-head output, both review verdicts, known limitations, synthetic-data statement, leakage review, and merge readiness.

```bash
git status --short
git log --oneline feature/coach-phase1-phase2..HEAD
```

Expected: only intentional PR2 changes remain and the commit list matches Tasks 2-9 plus narrowly scoped review fixes.

## Explicit PR2 exclusions

The following remain for PR3: final named rubric/delivery classification, immutable evidence-package construction/grounding, coaching, adaptive follow-ups, transcript editing/re-evaluation UI, explicit acceptance, answer comparison/review, and benchmark smoke profiles. The following remain for PR4: conversational report/report UI, compatible progress, transcript and hard-session deletion, report rebuild, synchronous exports/print view, observability expansion, standard benchmark/security hardening, documentation updates, and rollout-default changes. PR2 implements only audio deletion/retention required by V6 §§29.1-29.4; it does not pre-implement §§29.5-29.12.
