# Coach Phase 1 PR4 Report, Privacy, and Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 1 with deterministic conversational reports and compatible progress, privacy-safe deletion and synchronous exports, production observability and diagnostics, accessible report UX, standard benchmark/security evidence, and a controlled disabled-by-default rollout.

**Architecture:** PR4 consumes the merged PR1–PR3 state, repository, pipeline, evaluation, grounding, and UI interfaces; it adds separate conversational report/progress services and keeps the legacy numeric builder and routes unchanged. Privacy mutations use repository-owned conditional transactions and generation/claim fences, while exports and reads use one version-consistent snapshot. Telemetry, diagnostics, benchmarks, and active security tests expose only bounded content-free contracts and run with synthetic data in isolated environments.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, async SQLAlchemy, SQLite/Alembic, pytest/pytest-asyncio/httpx; Next.js 15.5, React 18, TypeScript 5, Vitest/Testing Library, Playwright; existing `backend/benchmarks/coach` and Hatch observability facade.

## Global Constraints

- Sole Phase 1 authority: `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md`, SHA-256 `626381be8963340972711bdfa5e47df0c82d521bb4e22ad75f3f873022c19ae8` when this plan was written.
- Approved delivery design: `docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md`, SHA-256 `992f9693d82b5146770e5e002f6f8d7f2485d34716e89d0d6a775662c134ece6`; it adds gates but cannot amend V6.
- Create `phase1/pr4-report-privacy-hardening` from `feature/coach-phase1-phase2` only after PR1, PR2, and PR3 are merged in order; target the integration branch, never `main` or an unmerged sibling.
- Stop if a predecessor interface below is absent or materially different. Record the mismatch and impact; do not recreate or reinterpret PR1–PR3 in PR4.
- `SessionRecording` remains the answer-attempt aggregate. Use `conversational_session_repository.py`, `AsyncJobService`, the one Coach reconciliation entry point, existing provider routing, and the shared telemetry facade.
- Keep `legacy_v1` numeric schemas, report builder, reports, progress routes, video records, legacy submit/retry behavior, and historical fixtures unchanged. New conversational routes dispatch by `experience_version` and never map old scores to named levels.
- Conversational levels are exactly `needs_work`, `developing`, `interview_ready`, `strong`, `not_assessed`; trends are exactly `improving`, `stable`, `mixed`, `declining`, `not_enough_evidence`. Never expose conversational percentages or 0–10 scores.
- Persisted analytical reports exclude the live `retention_summary`; report reads and exports overlay it from the same captured `retention_version`. Audio-only mutations never increment `activity_version` or rebuild analytical report JSON.
- Transcript deletion physically removes transcript versions and derived evaluation/evidence/coaching, always removes owned audio, increments `processing_generation`, and excludes the deleted source bundle. Hard deletion is not abandonment and is available from every lifecycle state.
- Hard-deletion receipts contain only the domain-separated session hash, command/request hashes, result state, stable error code, and timestamps. Default receipt retention is 30 days, valid configuration range 7–90 days.
- Synchronous JSON/Markdown export creates no database row or server artifact, includes no raw-audio link, is `no-store`, uses safe filenames, and returns byte-identical bytes/ETags for an identical request at identical activity/retention versions.
- Treat transcript, evidence, CV/job text, model output, IDs, filenames, MIME types, paths, report narratives, and metadata as untrusted. Validate parent ownership and safe IDs; render text safely; expose no stack, prompt, secret, restricted evidence, raw path, or internal exception.
- `hatch.coach.state_version` is trace-only and must be dropped from all metric attributes. Metric labels contain no session/question/attempt IDs or content. Logs, spans, diagnostics, benchmark artifacts, and test evidence contain no transcript/evidence/CV/prompt/model body, raw media, or user path.
- Run DAST, penetration, fuzz, race, deletion, and load probes only against an isolated local/ephemeral app with synthetic candidates, jobs, transcripts, evidence, and media. Stop if the target could contain real data or affect a shared service.
- Keep `HATCH_COACH_CONVERSATIONAL_ENABLED = false` as the repository default. Prove enabled and disabled behavior in isolation; an owner-authorized deployment may opt in through configuration only after every PR4 and promotion gate passes.
- Phase 2 is forbidden: no Candidate Intelligence entities/findings/confidence bands/governance gateways, mentor personas, weakness-driven cross-session plans, recruiter sharing, persisted export jobs, server PDF generation, WebSocket/WebRTC, or multi-tenant infrastructure.
- Every behavior task uses RED → minimal GREEN → focused regression → commit. Do not combine the commits specified below. All evidence records exact command, exit status, counts, revision, authority hashes, and artifact paths.

---

## PR1–PR3 Stop Gates and Locked Interfaces

The verified integration head must contain these files before the PR4 branch is created:

```text
backend/app/services/coach_conversational_contracts.py
backend/app/repositories/conversational_session_repository.py
backend/app/services/coach_conversation_commands.py
backend/app/services/coach_live_view.py
backend/app/services/coach_attempt_pipeline.py
backend/app/services/coach_retention.py
backend/app/services/coach_conversational_evaluator.py
backend/app/services/coach_evidence_grounder.py
backend/app/services/coach_followup_policy.py
backend/app/services/coach_coaching.py
backend/app/routers/coach_conversation.py
backend/app/schemas/coach_conversation.py
frontend/src/components/coach/conversation/ConversationSession.tsx
frontend/src/components/coach/conversation/AnswerReview.tsx
```

PR4 consumes these exact logical contracts; imports may be stable re-exports from the named modules:

```python
class ConversationLiveView(BaseModel):
    session_id: str
    experience_version: str
    status: str
    conversation_state: str
    state_version: int
    activity_version: int
    retention_version: int
    report_state: str
    allowed_commands: list[str]

class ConversationalSessionRepository:
    async def get_attempt_processing_snapshot(
        self, *, recording_id: str, processing_generation: int,
    ) -> AttemptProcessingSnapshot | None: ...
    async def accept_attempt(
        self, *, session_id: str, question_id: str, attempt_id: str,
        expected_state_version: int,
    ) -> AcceptanceResult: ...
    async def delete_attempt_audio(
        self, *, claim: AudioDeletionClaim,
    ) -> AudioDeletionResult: ...

class ConversationCommandService:
    async def execute(
        self, *, user_id: str, session_id: str,
        request: ConversationCommandRequest,
    ) -> ConversationCommandResult: ...

CoachConversationCommandService = ConversationCommandService

def normalize_contract_text(text: str) -> str: ...
def validate_code_point_span(
    text: str, start: int, end: int, excerpt: str,
) -> ValidatedSpan: ...
```

PR3 must expose accepted attempts with current completed `InterviewAttemptEvaluation` rows, persisted follow-up target/aggregation roles, validated evidence findings, content-safe coaching, candidate self-assessment, and the benchmark suite `coach_conversational_v1` with `contract-smoke` and `acceptance-smoke` profiles. PR1 must already have the V6 schema fields and `coach_session_deletion_results` table because V6 §39 assigns the migration to PR1. If a schema item is missing, stop; do not create a second PR4 migration or branch Alembic history.

PR2 must also define `Settings.HATCH_COACH_MEDIA_ROOT: Path` with repository default `Path("./data/coach-media")`, and its storage/retention services must consume that setting rather than a literal path. PR4 security and deletion gates consume this locked interface and override it with a dedicated temporary directory. If the merged PR2 does not expose it, stop and repair PR2 before branching PR4; do not add a competing PR4 media-root setting.

PR4 itself produces `claim_completed_session_report_rebuild`, `finalise_completed_session_report_rebuild`, `invalidate_report_for_deleted_input`, and the remaining report/privacy repository methods. Their absence before Task 3 is expected and is not a predecessor stop condition.

## File Structure

**Create:**

- `backend/app/services/coach_conversational_report.py` — named-level bundle/session aggregation, deterministic narrative skeleton, snapshot assembly, fallback, and retention overlay.
- `backend/app/services/coach_conversational_progress.py` — exact/filtered grouping, deterministic ordering/truncation, and named trend derivation.
- `backend/app/services/coach_privacy.py` — transcript deletion, hard-deletion claim/finalisation/failure, receipt cleanup, and worker fencing orchestration.
- `backend/app/services/coach_report_export.py` — deterministic JSON/Markdown bytes, inclusion policy, safe filename, hash/ETag, and two-version recheck.
- `backend/app/services/coach_support_diagnostics.py` — owner-scoped, content-free operational projection derived from registry codes and persisted states.
- `backend/tests/test_services/test_coach_conversational_report.py`
- `backend/tests/test_services/test_coach_conversational_progress.py`
- `backend/tests/test_services/test_coach_privacy.py`
- `backend/tests/test_services/test_coach_report_export.py`
- `backend/tests/test_services/test_coach_support_diagnostics.py`
- `backend/tests/test_repositories/test_conversational_privacy_repository.py`
- `backend/tests/test_routers/test_coach_conversation_report.py`
- `backend/tests/test_routers/test_coach_conversation_privacy.py`
- `backend/tests/test_observability/test_coach_conversation_privacy.py`
- `backend/tests/security/test_coach_conversational_security.py`
- `backend/tests/security/test_coach_conversational_dast.py`
- `frontend/src/components/coach/conversation/ConversationalReport.tsx`
- `frontend/src/components/coach/conversation/ConversationalProgress.tsx`
- `frontend/src/components/coach/conversation/PrivacyControls.tsx`
- `frontend/src/components/coach/conversation/ReportExportControls.tsx`
- `frontend/src/components/coach/conversation/SupportDiagnostics.tsx`
- `frontend/src/components/coach/conversation/__tests__/ConversationalReport.test.tsx`
- `frontend/src/components/coach/conversation/__tests__/ConversationalProgress.test.tsx`
- `frontend/src/components/coach/conversation/__tests__/PrivacyControls.test.tsx`
- `frontend/e2e/coach-conversation-report-privacy.spec.ts`
- `backend/benchmarks/coach/fixtures/conversational_v1/scenarios/*.json` — extend the PR3 directory suite with PR4 standard-profile cases.
- `docs/architecture/COACH_CONVERSATIONAL.md`

**Modify:**

- `backend/app/config.py` — validated progress-group and deletion-receipt settings; default flag stays false.
- `backend/app/repositories/conversational_session_repository.py` — report snapshot, progress reads, transcript/hard deletion, receipt, export snapshot, and conditional finalisers.
- `backend/app/schemas/coach_conversation.py` — report/progress/deletion/export/diagnostic schemas and response unions.
- `backend/app/services/coach_conversational_contracts.py` — report/progress/export/deletion constants, canonical error metadata, and Task 3 restoration of completed `record_self_assessment` in the shared transition registry.
- `backend/app/services/coach_conversation_commands.py` — `end_session`, completed `record_self_assessment`, `retry_report`, and transcript-deletion report-claim dispatch.
- `backend/app/services/coach_live_view.py` — Task 3 restoration of completed reflection advertisement only after the atomic persistence/invalidation/claim path exists.
- `backend/app/services/coach_reconciliation.py` — stale completed-report and hard-deletion claims plus expired receipt cleanup, retaining one entry point.
- `backend/app/routers/coach_conversation.py` — conversational report/progress/export/deletion/diagnostic routes and safe response headers.
- `backend/app/routers/coach.py` — experience dispatch only where the stable legacy report route is shared.
- `backend/app/observability/attributes.py`, `backend/app/observability/coach.py`, `backend/app/observability/runtime.py` — V6 names, allowlists, instruments, and metric sanitizer.
- `backend/benchmarks/coach/contracts.py`, `profiles.py`, `production_adapter.py`, `runner.py`, `validators.py`, `reporting.py` — standard conversational groups, hard gates, metrics, privacy-safe manifest/report.
- `backend/tests/benchmarks/coach/test_contracts.py`, `test_profiles.py`, `test_runner.py`, `test_validators.py`, `test_reporting.py`, `test_observability.py`, `test_e2e_session.py`.
- `frontend/src/lib/api.ts` — discriminated report/progress/export/deletion/diagnostic contracts and helpers.
- `frontend/src/app/coach/report/[id]/page.tsx` — `legacy_v1`/`conversational_v1` dispatch and print mode.
- `frontend/src/components/coach/conversation/ConversationSession.tsx` — privacy actions and completed-report navigation.
- `frontend/playwright.config.ts` only for an isolated synthetic Coach project/configuration.
- `README.md`, `docs/user-guide/INTERVIEW_PREP.md`, `docs/architecture/SECURITY_AND_PRIVACY.md`, `docs/operations/BACKUP_AND_RECOVERY.md` — user/architecture/operations/rollout truth.

**Must remain unchanged in meaning:** `backend/app/services/coach_aggregation.py::build_deterministic_report`, `SessionFeedbackReport`, legacy `/progress/{application_id}` and `/progress/{session_id}/trend`, `FeedbackReport`, `ScoreRadar`, existing video/media reads, and Phase 2 documents.

---

### Task 1: Prove the Sequential Base and Freeze PR4 Interfaces

**Files:**
- Inspect: all PR1–PR3 files and tests named above
- Evidence only: terminal output attached to the PR

**Interfaces:**
- Consumes: merged PR1–PR3 interfaces in the stop-gate section.
- Produces: verified base SHA, authority hashes, one Alembic head, clean baselines, and exact imported symbol map for Tasks 2–12.

- [ ] **Step 1: Verify authority, ancestry, target, and clean integration state**

```bash
git fetch origin
git switch feature/coach-phase1-phase2
git pull --ff-only
git log -1 --format='%H %s'
git status --short
git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
sha256sum docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md
```

Expected: clean status; both files tracked; hashes match Global Constraints or the changed hashes are reviewed against V6/design before continuing.

- [ ] **Step 2: Prove PR1–PR3 are merged and schema ownership is complete**

```bash
for path in backend/app/services/coach_conversation_commands.py backend/app/services/coach_attempt_pipeline.py backend/app/services/coach_conversational_evaluator.py backend/app/services/coach_evidence_grounder.py backend/app/services/coach_followup_policy.py backend/app/repositories/conversational_session_repository.py; do test -f "$path" || exit 1; done
rg -n 'coach_session_deletion_results|report_build_reason|deletion_generation|retention_version|activity_version' backend/app/models backend/alembic/versions
rg -n 'coach_conversational_v1|acceptance-smoke' backend/benchmarks/coach
cd backend && alembic heads
```

Expected: every file/symbol exists and one Alembic head prints. Any failure is a stop condition, not a PR4 implementation task.

- [ ] **Step 3: Run predecessor acceptance baselines before branching**

```bash
(cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_services/test_coach_attempt_pipeline.py tests/test_services/test_coach_conversational_evaluator.py tests/test_services/test_coach_evidence_grounder.py tests/test_services/test_coach_followup_policy.py)
(cd frontend && npm test -- --run src/components/coach/conversation)
```

Expected: exit 0. Diagnose a baseline failure on the owning PR before PR4.

- [ ] **Step 4: Create the PR4 branch**

```bash
git switch -c phase1/pr4-report-privacy-hardening
git branch --show-current
git merge-base --is-ancestor feature/coach-phase1-phase2 HEAD
```

Expected: branch name is exact and ancestry exits 0. No commit is made for this gate.

### Task 2: Centralize PR4 Contracts, Schemas, and Safe Errors

**Files:**
- Modify: `backend/app/services/coach_conversational_contracts.py`
- Modify: `backend/app/schemas/coach_conversation.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_services/test_coach_conversational_contracts.py`
- Test: `backend/tests/test_services/test_coach_support_diagnostics.py`

**Interfaces:**
- Consumes: PR1 canonical registry and V6 model fields.
- Produces: `REPORT_CONTRACT`, `PROGRESS_CONTRACT`, `EXPORT_CONTRACT`, `HARD_DELETE_CONTRACT`; `ConversationalReportRead`, `ConversationalProgressRead`, `ReportExportRequest`, `HardDeletionCommandRequest`, `DeletionCommandResult`, `SupportDiagnosticsRead`; `error_contract(code: str) -> CoachErrorContract`.

- [ ] **Step 1: Write RED registry/schema/config tests**

```python
def test_pr4_contracts_are_strict_and_registry_derived(settings):
    assert REPORT_CONTRACT == "coach_conversational_report_v1"
    assert PROGRESS_CONTRACT == "coach_conversational_progress_v2"
    assert EXPORT_CONTRACT == "coach_report_export_v1"
    assert HARD_DELETE_CONTRACT == "coach_session_hard_delete_v1"
    assert error_contract("coach_progress_incompatible_session").status == 409
    with pytest.raises(KeyError):
        error_contract("coach_session_incompatible_for_progress")
    assert settings.HATCH_COACH_DELETION_RECEIPT_DAYS == 30
```

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_contracts.py tests/test_services/test_coach_support_diagnostics.py
```

Expected: FAIL because PR4 constants/schemas/settings are absent.

- [ ] **Step 3: Add strict types and one canonical error mapping**

```python
class ReportExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["json", "markdown"]
    expected_activity_version: int = Field(ge=0)
    expected_retention_version: int = Field(ge=0)
    include_transcript: bool = False
    include_evidence_details: bool = False
    include_attempt_history: bool = False
    include_candidate_reflection: bool = True
    contract_version: Literal["coach_report_export_v1"]

class HardDeletionCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: str = Field(min_length=1, max_length=64)
    confirmation: Literal["DELETE"]
    contract_version: Literal["coach_session_hard_delete_v1"]
```

Add validated `HATCH_COACH_PROGRESS_MAX_GROUPS` range 1–100 and deletion receipt days range 7–90. Extend the existing error registry entries without duplicating status/message/retryability in schemas, routes, diagnostics, or frontend.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_contracts.py tests/test_services/test_coach_support_diagnostics.py
git add app/config.py app/schemas/coach_conversation.py app/services/coach_conversational_contracts.py tests/test_services/test_coach_conversational_contracts.py tests/test_services/test_coach_support_diagnostics.py
git commit -m "feat(coach): define PR4 report and privacy contracts"
```

Expected: exit 0; registry rejects the prohibited alias and every code has exactly one safe mapping.

### Task 3: Build the Deterministic Conversational Report

**Files:**
- Create: `backend/app/services/coach_conversational_report.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/coach_conversational_contracts.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/services/coach_live_view.py`
- Modify: `backend/app/services/coach_reconciliation.py`
- Test: `backend/tests/test_services/test_coach_conversational_report.py`
- Test: `backend/tests/test_services/test_coach_conversational_contracts.py`
- Test: `backend/tests/test_services/test_coach_live_view.py`
- Test: `backend/tests/test_repositories/test_conversational_session_repository.py`

**Interfaces:**
- Consumes: accepted recording/current evaluation/evidence/follow-up/self-assessment rows from PR3 and report claim fields from PR1.
- Produces: `aggregate_root_bundle(root: AcceptedAnswer, followups: Sequence[AcceptedAnswer], dimension: str) -> BundleDimension`; `derive_session_level(levels: Mapping[str, Level]) -> Level`; `build_conversational_report(snapshot: ReportInputSnapshot) -> ConversationalReportSnapshot`; `claim_initial_conversational_report(session_id: str, expected_activity_version: int, build_reason: Literal["initial_completion", "manual_retry"], job_id: str, now: datetime) -> ReportBuildClaim | None`; `claim_completed_session_report_rebuild(session_id: str, expected_activity_version: int, build_reason: Literal["transcript_deletion_rebuild", "reflection_update_rebuild"], job_id: str, now: datetime) -> ReportBuildClaim | None`; `finalise_conversational_report(claim: ReportBuildClaim, report_json: dict[str, object], report_state: Literal["completed", "fallback"]) -> bool`; `finalise_completed_session_report_rebuild(claim: ReportBuildClaim, report_json: dict[str, object], report_state: Literal["completed", "fallback"]) -> bool`; `run_conversational_report(claim: ReportBuildClaim) -> None`.

- [ ] **Step 1: Write RED aggregation vectors and snapshot tests**

```python
@pytest.mark.parametrize(("levels", "expected"), [
    (("developing",) * 5 + ("not_assessed",) * 2, "developing"),
    (("needs_work",) + ("interview_ready",) * 4 + ("developing", "not_assessed"), "developing"),
    (("strong",) * 5 + ("interview_ready", "developing"), "interview_ready"),
    (("strong",) * 5 + ("interview_ready", "needs_work"), "interview_ready"),
    (("strong", "strong", "needs_work", "strong", "strong", "interview_ready", "interview_ready"), "developing"),
    (("strong",) * 4 + ("not_assessed",) * 3, "not_assessed"),
])
def test_session_readiness_exact_thresholds(levels, expected):
    assert derive_session_level(dict(zip(CONTENT_DIMENSIONS, levels))) == expected
```

Also test: accepted attempts only; gap repair raises at most one; adverse primary evidence wins; lower median uses lower item; minimum two bundles; exact contributor IDs/reason; deterministic counts; fixed priority tie-breaking; no numeric keys; enrichment failure yields `fallback`; stale claim cannot publish; retention summary is absent from stored JSON and overlaid on read.

Add command-ownership RED tests with these exact names and assertions:

```python
async def test_end_session_atomically_claims_initial_report_and_dispatches_after_commit():
    result = await commands.execute(user_id=USER, session_id=SESSION, request=end_session())
    assert result.state == "reporting"
    assert repository.report_claim.build_reason == "initial_completion"
    assert repository.report_claim.activity_version == repository.session.activity_version
    assert queue.calls == [repository.report_claim]

async def test_completed_self_assessment_invalidates_and_claims_reflection_rebuild():
    await commands.execute(user_id=USER, session_id=SESSION, request=self_assessment())
    assert repository.session.conversation_state == "completed"
    assert repository.report_claim.build_reason == "reflection_update_rebuild"

async def test_retry_report_owns_both_initial_and_completed_rebuild_modes():
    assert (await commands.execute(user_id=USER, session_id=INITIAL_FAILED, request=retry_report())).state == "reporting"
    assert repository.claims[-1].build_reason == "manual_retry"
    assert (await commands.execute(user_id=USER, session_id=REBUILD_FAILED, request=retry_report())).state == "completed"
    assert repository.claims[-1].build_reason == "transcript_deletion_rebuild"

async def test_initial_report_worker_uses_initial_finaliser_fence():
    await run_conversational_report(initial_claim(activity_version=7))
    assert repository.initial_finaliser_calls == 1
    assert repository.completed_rebuild_finaliser_calls == 0

async def test_completed_self_assessment_worker_uses_rebuild_finaliser_fence():
    await run_conversational_report(reflection_claim(activity_version=8))
    assert repository.initial_finaliser_calls == 0
    assert repository.completed_rebuild_finaliser_calls == 1

async def test_completed_live_advertises_self_assessment_only_with_atomic_reflection_rebuild():
    rule = TRANSITIONS["record_self_assessment"]
    assert "completed" in rule.states and "completed" in rule.statuses
    view = await live_service.get_view(COMPLETED_SESSION)
    assert "record_self_assessment" in view.allowed_commands
    result = await commands.execute(user_id=USER, session_id=COMPLETED_SESSION, request=self_assessment())
    assert repository.atomic_completed_reflection_calls == 1
    assert result.conversation_state == "completed"
    assert repository.session.report_state == "building"
    assert repository.report_claim.build_reason == "reflection_update_rebuild"
```

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_report.py tests/test_services/test_coach_conversational_contracts.py tests/test_services/test_coach_live_view.py tests/test_repositories/test_conversational_session_repository.py -k 'report or bundle or readiness or completed_live or self_assessment'
```

Expected: FAIL because the conversational builder/repository snapshot methods are absent and the PR3 registry/live view still omit completed `record_self_assessment`; retain this output as the restoration RED evidence.

- [ ] **Step 3: Implement ordered pure algorithms and fenced persistence**

```python
def lower_median(levels: Sequence[Level]) -> Level:
    values = sorted(LEVEL_TO_ORDINAL[level] for level in levels if level != "not_assessed")
    return "not_assessed" if len(values) < 2 else ORDINAL_TO_LEVEL[values[(len(values) - 1) // 2]]

async def run_conversational_report(claim: ReportBuildClaim) -> None:
    snapshot = await repository.load_report_input_snapshot(claim)
    deterministic = build_conversational_report(snapshot)
    finaliser = (
        repository.finalise_completed_session_report_rebuild
        if claim.build_reason in {"transcript_deletion_rebuild", "reflection_update_rebuild"}
        else repository.finalise_conversational_report
    )
    published = await finaliser(claim, deterministic.persisted_json(), deterministic.report_state)
    if not published:
        telemetry.record_stale_claim("conversational_report")
```

Use exact V6 §§27.4–27.10 ordering, no legacy helper mutation, and transactionally captured `activity_version`/`retention_version` for response overlay.

After the atomic completed-reflection repository method exists, restore PR1's full V6 registry rule exactly: `record_self_assessment` states `awaiting_next_action|coaching|completed`, statuses `active|completed`. `coach_live_view.py` continues deriving `allowed_commands` from that shared registry; do not add a second frontend/live allowlist. The restoration and repository/command implementation ship in this one Task 3 commit, never as separate commits that could advertise a non-atomic command.

- [ ] **Step 4: Add deletion/reflection rebuild and reconciliation tests**

Implement and test ownership at the command/repository boundary:

- `end_session` performs V6 §9.9 resolution, increments activity/state once, creates the `initial_completion` claim in the same transaction, moves to `reporting`, and dispatches only after commit. Initial finalisation requires matching job/activity, `report_state=building`, reason `initial_completion` or `manual_retry`, and `conversation_state=reporting`.
- `record_self_assessment` on a completed session calls one repository operation that updates reflection and attempt/activity/state versions, invalidates and clears the old snapshot/job, creates and stores the `reflection_update_rebuild` claim, and persists the command result in the same transaction; it preserves completed status/state and dispatches only after commit. Active-session reflection does not claim a report.
- The `/live` regression's RED run on the merged PR3 base fails because completed `record_self_assessment` is absent; its GREEN run proves Task 3 restores the registry/live advertisement alongside the atomic repository workflow. A completed live view must never advertise the command when the atomic repository capability is unavailable.
- `retry_report` owns two exclusive modes: recoverable initial failure claims `manual_retry` and returns to `reporting`; completed failed deletion/reflection rebuild preserves its original rebuild reason, completed status/state, and claims the current activity version. Reuse of a stale activity/job or an in-flight claim makes no mutation.
- The worker selects `finalise_conversational_report` for initial/manual claims and `finalise_completed_session_report_rebuild` for deletion/reflection claims. Both clear the matching job atomically; neither can overwrite a newer activity or claim.

Test no remaining accepted attempts, old worker versus new activity, failed rebuild hidden until explicit `retry_report`, queue failure after commit remaining reconcilable, and stale completed-session build reconciliation without changing completed status/state.

- [ ] **Step 5: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_report.py tests/test_services/test_coach_conversational_contracts.py tests/test_services/test_coach_live_view.py tests/test_repositories/test_conversational_session_repository.py tests/test_services/test_coach_reconciliation.py
git add app/services/coach_conversational_report.py app/services/coach_conversational_contracts.py app/services/coach_conversation_commands.py app/services/coach_live_view.py app/services/coach_reconciliation.py app/repositories/conversational_session_repository.py tests/test_services/test_coach_conversational_report.py tests/test_services/test_coach_conversational_contracts.py tests/test_services/test_coach_live_view.py tests/test_repositories/test_conversational_session_repository.py tests/test_services/test_coach_reconciliation.py
git commit -m "feat(coach): build deterministic conversational reports"
```

Expected: exit 0; report bytes/data are stable and late workers make no authoritative mutation.

### Task 4: Implement Compatibility-grouped Progress

**Files:**
- Create: `backend/app/services/coach_conversational_progress.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Test: `backend/tests/test_services/test_coach_conversational_progress.py`

**Interfaces:**
- Consumes: completed visible conversational report snapshots and persisted exact compatibility keys.
- Produces: `derive_trend(levels: Sequence[Level]) -> Trend`; `get_progress(selector: ProgressSelector, group_limit: int) -> ConversationalProgressRead`.

- [ ] **Step 1: Write RED selector, grouping, bounds, and trend tests**

```python
@pytest.mark.parametrize(("levels", "expected"), [
    (("needs_work", "developing"), "improving"),
    (("needs_work", "strong"), "improving"),
    (("strong", "developing"), "declining"),
    (("developing", "developing"), "stable"),
    (("needs_work", "interview_ready", "developing"), "mixed"),
    (("interview_ready", "needs_work", "developing"), "mixed"),
    (("needs_work", "needs_work", "interview_ready"), "improving"),
    (("needs_work", "interview_ready", "interview_ready"), "stable"),
])
def test_trend_vectors(levels, expected):
    assert derive_trend(levels) == expected
```

Test exact mode conflicts with broad filters, filtered AND semantics, application producing multiple exact groups, session/group tie ordering, invalidated/deleted/legacy exclusion, `not_assessed` skipping, pre-truncation totals, cap 1/20/100, and no percentage field.

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_progress.py
```

Expected: FAIL because progress service is absent.

- [ ] **Step 3: Implement deterministic group partitioning**

```python
def derive_trend(levels: Sequence[Level]) -> Trend:
    assessed = [LEVEL_TO_ORDINAL[value] for value in levels if value != "not_assessed"][-3:]
    if len(assessed) < 2:
        return "not_enough_evidence"
    if len(assessed) == 3 and (assessed[1] - assessed[0]) * (assessed[2] - assessed[1]) < 0:
        return "mixed"
    return "improving" if assessed[-1] > assessed[-2] else "declining" if assessed[-1] < assessed[-2] else "stable"
```

Query only owner-visible, completed/fallback conversational reports; partition by persisted compatibility key before applying the configured group limit.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_progress.py
git add app/services/coach_conversational_progress.py app/repositories/conversational_session_repository.py tests/test_services/test_coach_conversational_progress.py
git commit -m "feat(coach): add compatibility-grouped progress"
```

Expected: exit 0; groups are never merged and metadata truthfully reports truncation.

### Task 5: Complete Transcript and Hard-deletion Ownership

**Files:**
- Create: `backend/app/services/coach_privacy.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Modify: `backend/app/services/coach_conversation_commands.py`
- Modify: `backend/app/services/coach_reconciliation.py`
- Test: `backend/tests/test_services/test_coach_privacy.py`
- Test: `backend/tests/test_repositories/test_conversational_privacy_repository.py`

**Interfaces:**
- Consumes: PR2 exact media ownership removal, PR1 command hash/event/version primitives, report rebuild from Task 3.
- Produces: `delete_attempt_transcript(claim: TranscriptDeletionClaim) -> TranscriptDeletionResult`; `claim_hard_deletion(session_id: str, request: HardDeletionCommandRequest) -> HardDeletionClaim | DeletionCommandResult`; `run_hard_deletion(claim: HardDeletionClaim) -> DeletionCommandResult`; `expire_deletion_receipts(now: datetime, limit: int) -> int`.

- [ ] **Step 1: Write RED physical-deletion and active/completed-state tests**

Test all eleven V6 §29.5 mutations, exact `[Deleted follow-up question]`, root-bundle exclusion without deleting a separate follow-up transcript, one replacement acceptance generation, active selected versus historical destinations, single state/activity increment, immediate completed-report hiding, rebuild with zero accepted attempts, and failure remaining hidden.

- [ ] **Step 2: Write RED hard-deletion replay/race/failure tests**

```python
async def test_hard_delete_fences_every_worker_and_retains_only_receipt(seed_session):
    claim = await service.claim_hard_deletion(seed_session.id, deletion_request("cmd-1"))
    await stale_setup.finalise()
    await stale_attempt.finalise()
    await stale_report.finalise()
    result = await service.run_hard_deletion(claim)
    assert result.result_state == "completed"
    assert await repository.normal_read(seed_session.id) is None
    assert await repository.receipt_payload("cmd-1") == CONTENT_FREE_RECEIPT
```

Cover every lifecycle state; identical replay before/after row removal; same ID/different hash; failed command replay; new-ID retry; expired lease; wrong generation/job/command/token; media failure; database failure; already removed owned file; expired receipt cleanup at boundary; session absent from list/live/report/progress/export while deleting/failed.

- [ ] **Step 3: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_privacy.py tests/test_repositories/test_conversational_privacy_repository.py
```

Expected: FAIL because PR4 privacy orchestrator/repository finalisers are absent.

- [ ] **Step 4: Implement conditional claim/finalisation and cleanup**

```python
def session_deletion_key(session_id: str) -> str:
    return hashlib.sha256(f"coach-session-deletion-v1:{session_id}".encode("utf-8")).hexdigest()

async def run_hard_deletion(claim: HardDeletionClaim) -> DeletionCommandResult:
    try:
        await media.delete_all_owned(claim.media)
        return await repository.finalise_hard_deletion(claim)
    except Exception:
        return await repository.fail_hard_deletion(claim, "coach_session_deletion_failed")
```

The repository conditionally increments setup/attempt/report generations, clears claims, marks jobs stale/cancelled, deletes children and session in FK-safe order, never stores raw ID/content/path in the receipt, and never appends an event after event deletion.

- [ ] **Step 5: Run GREEN, race repetition, and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_privacy.py tests/test_repositories/test_conversational_privacy_repository.py tests/test_services/test_coach_reconciliation.py
for run in 1 2 3 4 5; do python -m pytest -q --no-cov tests/test_services/test_coach_privacy.py -k 'race or stale or concurrent' || exit 1; done
git add app/services/coach_privacy.py app/services/coach_conversation_commands.py app/services/coach_reconciliation.py app/repositories/conversational_session_repository.py tests/test_services/test_coach_privacy.py tests/test_repositories/test_conversational_privacy_repository.py tests/test_services/test_coach_reconciliation.py
git commit -m "feat(coach): fence transcript and session deletion"
```

Expected: all runs exit 0; stale workers restore no deleted authority and receipts remain bounded/pseudonymous.

### Task 6: Add Version-consistent Synchronous Exports

**Files:**
- Create: `backend/app/services/coach_report_export.py`
- Modify: `backend/app/repositories/conversational_session_repository.py`
- Test: `backend/tests/test_services/test_coach_report_export.py`

**Interfaces:**
- Consumes: completed/fallback report plus current retention/deletion visibility from a single repository snapshot.
- Produces: `render_report_export(snapshot: ExportSnapshot, request: ReportExportRequest) -> ExportPayload`; `export_report(session_id: str, request: ReportExportRequest) -> ExportPayload` where payload has `body: bytes`, `media_type: str`, `filename: str`, `etag: str`, `activity_version: int`, `retention_version: int`.

- [ ] **Step 1: Write RED byte/header/race/inclusion tests**

Test deterministic sorted JSON/newline and Markdown section ordering; repeated identical bytes/ETag; safe opaque filename; no raw audio/link; Hatch source-matching disclaimer; include flags after transcript/evidence/history/reflection deletion; stale entry versions; mutation between render and response recheck; invalidated/building/failed report; no export row/file.

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_report_export.py
```

Expected: FAIL because export service is absent.

- [ ] **Step 3: Implement stable bytes and two-version fencing**

```python
def make_etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'

async def export_report(session_id: str, request: ReportExportRequest) -> ExportPayload:
    snapshot = await repository.load_export_snapshot(session_id, request)
    payload = render_report_export(snapshot, request)
    if not await repository.export_versions_match(
        session_id, snapshot.activity_version, snapshot.retention_version
    ):
        raise CoachContractError("coach_export_source_changed")
    return payload
```

Use canonical JSON (`sort_keys=True`, compact separators, UTF-8, final LF) and fixed Markdown ordering/escaping. Do not call evaluation/provider services.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_report_export.py
git add app/services/coach_report_export.py app/repositories/conversational_session_repository.py tests/test_services/test_coach_report_export.py
git commit -m "feat(coach): add deterministic synchronous exports"
```

Expected: exit 0; unchanged request/version pairs yield byte-identical bodies and ETags.

### Task 7: Mount Owner-safe Report, Progress, Privacy, Export, and Diagnostic Routes

**Files:**
- Create: `backend/app/services/coach_support_diagnostics.py`
- Modify: `backend/app/routers/coach_conversation.py`
- Modify: `backend/app/routers/coach.py`
- Test: `backend/tests/test_routers/test_coach_conversation_report.py`
- Test: `backend/tests/test_routers/test_coach_conversation_privacy.py`
- Test: `backend/tests/test_services/test_coach_support_diagnostics.py`

**Interfaces:**
- Consumes: Tasks 2–6 services and existing auth/lock/`_require_safe_id` dependencies.
- Produces: `GET /api/coach/sessions/{id}/report`, `GET /api/coach/conversational-progress`, `POST /api/coach/sessions/{id}/exports`, `POST /api/coach/sessions/{id}/deletion-commands`, and owner-only `GET /api/coach/sessions/{id}/diagnostics`.

- [ ] **Step 1: Write RED route contract and IDOR tests**

Test unauthenticated, cross-owner, cross-session question/attempt, malformed/traversal IDs, hidden deleting session, report union dispatch, selector conflict, response-version headers, export content disposition/cache/ETag, deletion replay, and safe canonical errors. Assert identical not-found behavior prevents existence disclosure.

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_report.py tests/test_routers/test_coach_conversation_privacy.py
```

Expected: FAIL because routes are not mounted.

- [ ] **Step 3: Add thin routes and content-free diagnostics**

```python
@router.post("/sessions/{session_id}/exports")
async def export_conversational_report(session_id: str, request: ReportExportRequest):
    _require_safe_id(session_id, "session_id")
    payload = await export_service.export_report(session_id, request)
    return Response(payload.body, media_type=payload.media_type, headers=payload.headers())
```

Diagnostics may return state names, stage names, bounded timestamps, stable error/gate codes, retryability, and correlation ID. They must never return transcript/evidence/CV/prompt/model bodies, report narrative, user paths, provider exception text, secrets, or raw media metadata.

- [ ] **Step 4: Run GREEN, legacy regressions, and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_report.py tests/test_routers/test_coach_conversation_privacy.py tests/test_services/test_coach_support_diagnostics.py tests/test_routers/test_coach_router.py tests/test_routers/test_coach_async.py
git add app/routers/coach.py app/routers/coach_conversation.py app/services/coach_support_diagnostics.py tests/test_routers/test_coach_conversation_report.py tests/test_routers/test_coach_conversation_privacy.py tests/test_services/test_coach_support_diagnostics.py
git commit -m "feat(coach): expose privacy-safe PR4 routes"
```

Expected: exit 0; legacy routes and schemas remain byte/fixture compatible.

### Task 8: Extend Telemetry Without Content or Cardinality Leaks

**Files:**
- Modify: `backend/app/observability/attributes.py`
- Modify: `backend/app/observability/coach.py`
- Modify: `backend/app/observability/runtime.py`
- Create: `backend/tests/test_observability/test_coach_conversation_privacy.py`
- Modify: `backend/tests/test_observability/test_privacy.py`
- Modify: `backend/tests/test_observability/test_coach_runtime.py`

**Interfaces:**
- Consumes: existing `SafeSpan`, `TelemetryRuntime`, allowlist and `sanitize_metric_attributes`.
- Produces: V6 span constants, bounded counters/histograms, `record_conversation_metric(name, value, attributes) -> None`, and guaranteed trace-only `COACH_STATE_VERSION`.

- [ ] **Step 1: Write RED canary and metric-sanitizer tests**

```python
def test_state_version_is_trace_only_and_content_canaries_never_escape(runtime, caplog):
    attrs = {COACH_STATE_VERSION: 9, COACH_COMMAND_TYPE: "delete_transcript", "transcript": "CANARY-TRANSCRIPT-7f2"}
    assert sanitize_attributes(attrs)[COACH_STATE_VERSION] == 9
    assert COACH_STATE_VERSION not in sanitize_metric_attributes(attrs)
    assert "CANARY-TRANSCRIPT-7f2" not in caplog.text
```

Seed unique canaries for transcript, evidence, CV, prompt, model body, filename/path, IDs, and secret; force report/progress/export/deletion success/failure; scan captured logs, spans, metrics, diagnostics, and errors.

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/test_observability/test_coach_conversation_privacy.py tests/test_observability/test_privacy.py tests/test_observability/test_coach_runtime.py
```

Expected: FAIL because PR4 safe attributes/instruments are absent.

- [ ] **Step 3: Extend allowlists and facade-owned instruments**

Add V6 span names and counters/histograms exactly. Permit only bounded enum/boolean/non-negative integer values; keep IDs/correlation values trace-only where already allowed and remove all from metrics. `state_version` must be explicitly in the metric-deny set even if correlation sets change.

- [ ] **Step 4: Run GREEN and commit**

```bash
cd backend && python -m pytest -q --no-cov tests/test_observability tests/test_services/test_coach_support_diagnostics.py
git add app/observability tests/test_observability
git commit -m "feat(coach): add privacy-safe conversational telemetry"
```

Expected: exit 0; stable content-free codes remain observable while every canary is absent.

### Task 9: Deliver Accessible Report, Progress, Privacy, Export, and Print UI

**Files:**
- Create: five frontend components and three tests listed in File Structure
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/coach/report/[id]/page.tsx`
- Modify: `frontend/src/components/coach/conversation/ConversationSession.tsx`

**Interfaces:**
- Consumes: server-authored report/progress/deletion/diagnostic schemas and version headers from Task 7.
- Produces: `getCoachConversationalReport`, `getCoachConversationalProgress`, `exportCoachConversationalReport`, `requestCoachSessionDeletion`, `getCoachSupportDiagnostics`; accessible conversational report/progress/privacy/print views.

- [ ] **Step 1: Write RED UI and untrusted-rendering tests**

Test experience dispatch; named levels with text; no `ScoreRadar`, percentage, numeric score, or confidence language; grouped compatibility context/trends; truncation notice; deletion confirmation and failed/retry states; include-flag disabling after deletion; print view; keyboard/focus/live-region behavior; reduced motion; malicious `<script>`, event handler, `javascript:` URL, bidi/Unicode content rendered as text without execution/navigation.

- [ ] **Step 2: Run RED**

```bash
cd frontend && npm test -- --run src/components/coach/conversation/__tests__/ConversationalReport.test.tsx src/components/coach/conversation/__tests__/ConversationalProgress.test.tsx src/components/coach/conversation/__tests__/PrivacyControls.test.tsx
```

Expected: FAIL because PR4 components/helpers are absent.

- [ ] **Step 3: Add discriminated API helpers and server-driven components**

```typescript
export async function exportCoachConversationalReport(
  sessionId: string,
  request: CoachReportExportRequest,
): Promise<{ blob: Blob; etag: string; filename: string }> {
  return apiAttachment(`/api/coach/sessions/${encodeURIComponent(sessionId)}/exports`, request);
}
```

Use semantic headings/lists/tables, text equivalents, native buttons, visible focus, polite bounded announcements, and browser text rendering. Privacy actions must come from `allowed_commands`; no client-inferred deletion/report completion.

- [ ] **Step 4: Run GREEN, type-check, and commit**

```bash
cd frontend && npm test -- --run src/components/coach/conversation
npm run type-check
git add src/lib/api.ts 'src/app/coach/report/[id]/page.tsx' src/components/coach/conversation
git commit -m "feat(coach): add accessible conversational report and privacy UI"
```

Expected: exit 0; legacy numeric report component still renders only for `legacy_v1`.

### Task 10: Complete the Standard Conversational Benchmark

**Files:**
- Create/modify: benchmark files and tests listed in File Structure

**Interfaces:**
- Consumes: PR3 suite/adapters and existing artifact/manifest/timeout/profile conventions.
- Produces: `standard` profile coverage for rubric, grounding, follow-up, coaching, prohibited inference, and end-to-end; hard-gate result and privacy-safe manifest/report.

- [ ] **Step 1: Write RED fixture/profile/hard-gate/manifest tests**

Assert all V6 §38.5 groups and cases exist; hard gates reject invalid schema/span/evidence ID/numeric score/prohibited inference/ungrounded or third follow-up/false wording/technical-low/model-answer evidence/stale-worker mutation; metrics and manifest include suite/profile/model route/model ID/provider/contract/prompt versions/timeouts/repair budgets/fixture hashes/repository SHA/timestamp.

- [ ] **Step 2: Run RED**

```bash
cd backend && python -m pytest -q --no-cov tests/benchmarks/coach/test_contracts.py tests/benchmarks/coach/test_profiles.py tests/benchmarks/coach/test_validators.py tests/benchmarks/coach/test_reporting.py tests/benchmarks/coach/test_e2e_session.py
```

Expected: FAIL because standard conversational cases/gates are incomplete.

- [ ] **Step 3: Extend the existing harness, never a parallel runner**

Use `CoachProfile`, `RunRequest`, `CoachRunSummary`, atomic artifact writers, production adapter, and existing CLI. Keep fixtures entirely synthetic; reports show content-free scenario IDs/gates/aggregate metrics, never fixture prose or model bodies.

- [ ] **Step 4: Run GREEN and deterministic smoke**

```bash
cd backend
python -m pytest -q --no-cov tests/benchmarks/coach
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/conversational_v1
python -m benchmarks.coach smoke --suite benchmarks/coach/fixtures/conversational_v1 --profile contract-smoke --models deterministic-contract --output-root /tmp/hatch-coach-pr4-benchmark
```

Expected: tests/validation exit 0; smoke emits a run directory with `manifest.json`, `summary.json`, and `report.md`, all passing privacy scan.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/coach tests/benchmarks/coach
git commit -m "test(coach): complete conversational benchmark standard profile"
```

### Task 11: Add Isolated Security, Adversarial, Race, and Browser E2E Gates

**Files:**
- Create: `backend/tests/security/test_coach_conversational_security.py`
- Create: `backend/tests/security/test_coach_conversational_dast.py`
- Create: `frontend/e2e/coach-conversation-report-privacy.spec.ts`
- Modify: `frontend/playwright.config.ts` only if an isolated project is required

**Interfaces:**
- Consumes: synthetic temporary SQLite/data roots, PR2 `Settings.HATCH_COACH_MEDIA_ROOT`, dependency-overridden ASGI app, Tasks 3–9 routes/UI.
- Produces: reproducible negative/adversarial/replay/safe-failure and browser acceptance evidence with no real/shared target.

- [ ] **Step 1: Write RED isolated API penetration cases**

For report/progress/export/deletion/diagnostics cover missing/invalid auth, IDOR, malformed/traversal IDs, hostile filenames/title, selector amplification/group cap+1, command replay/collision, stale versions, concurrent export mutation, deletion during setup/attempt/report, duplicate finalisers, expired claims, and canary leakage. Assert no data existence leak, mutation on rejection, stale bytes, replacement deletion, or unsafe detail.

- [ ] **Step 2: Add stored/reflected UI injection and deletion E2E**

Use synthetic script/event-handler/unsafe-URL strings in transcript/evidence/report fields; exercise named report, grouped progress, deterministic export, transcript deletion/rebuild, back navigation after deletion, hard-delete retry, keyboard-only operation, print view, and legacy numeric report. Assert no script/navigation, stale content, audio-only barrier, false deletion claim, or legacy change.

- [ ] **Step 3: Run focused RED then GREEN after wiring fixtures**

```bash
pr4_isolated_root="$(mktemp -d)"
trap 'rm -rf -- "$pr4_isolated_root"' EXIT
mkdir -p "$pr4_isolated_root/coach-media"
export DATABASE_URL="sqlite+aiosqlite:///$pr4_isolated_root/coach.db"
export HATCH_COACH_MEDIA_ROOT="$pr4_isolated_root/coach-media"
export HATCH_E2E_SYNTHETIC=1
(cd backend && alembic upgrade head)
(cd backend && python -m pytest -q --no-cov tests/security/test_coach_conversational_security.py tests/security/test_coach_conversational_dast.py)
(cd frontend && npm run test:e2e -- coach-conversation-report-privacy.spec.ts)
test -z "$(find "$pr4_isolated_root/coach-media" -type f -print -quit)"
rm -rf -- "$pr4_isolated_root"
trap - EXIT
test ! -e "$pr4_isolated_root"
```

Expected RED: missing fixtures/cases before completion. Expected GREEN: migration, API security tests, and Playwright exit 0 using only the explicit temporary SQLite database and Coach media root; the media root is empty before removal and the entire isolated root is absent after cleanup. Never source `.env` or point either variable at a shared/real-data path.

- [ ] **Step 4: Run dependency/static/secret gates without mutating dependencies**

```bash
for requirement_profile in requirements.txt requirements-core.txt requirements-dev.txt requirements-test.txt requirements-browser.txt requirements-local-ai.txt requirements-perception.txt requirements-observability.txt requirements-full.txt; do
  (cd backend && python -m pip_audit -r "$requirement_profile") || exit 1
done
(cd backend && ruff check app/ tests/)
pr4_npm_audit_json="$(mktemp)"
pr4_npm_audit_status=0
(cd frontend && npm audit --package-lock-only --audit-level=moderate --json) >"$pr4_npm_audit_json" || pr4_npm_audit_status=$?
test "$pr4_npm_audit_status" -le 1
node - "$pr4_npm_audit_json" <<'NODE'
const fs = require("fs");
const audit = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const counts = audit.metadata?.vulnerabilities ?? {};
console.log(JSON.stringify({ moderate: counts.moderate ?? 0, high: counts.high ?? 0, critical: counts.critical ?? 0 }));
if ((counts.high ?? 0) > 0 || (counts.critical ?? 0) > 0) process.exit(1);
NODE
(cd frontend && npm run type-check)
secret_pattern="BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|api[_-]?key[[:space:]]*=[[:space:]]*(['\"][^'\"]+)"
if git grep -nEI "$secret_pattern" -- ':!*.lock' ':!docs/archive/**'; then exit 1; fi
rm -f -- "$pr4_npm_audit_json"
```

Expected: all nine canonical backend requirement profiles audit individually and exit 0; Ruff/type-check pass; npm JSON reports zero critical/high. Every reported moderate npm finding receives an explicit finding ID, affected package/path, evidence, owner, and `fix`, `accepted risk`, `deferred proposal`, or `false positive` disposition before merge. The secret scan has no match and its shell syntax passes `bash -n`. A critical/high finding blocks merge; optional hardening proposals are labelled non-binding.

- [ ] **Step 5: Commit security and E2E coverage**

```bash
git add backend/tests/security frontend/e2e/coach-conversation-report-privacy.spec.ts frontend/playwright.config.ts
git commit -m "test(coach): add isolated privacy and adversarial gates"
```

### Task 12: Document Operations, Privacy, Recovery, and Controlled Rollout

**Files:**
- Create: `docs/architecture/COACH_CONVERSATIONAL.md`
- Modify: `README.md`
- Modify: `docs/user-guide/INTERVIEW_PREP.md`
- Modify: `docs/architecture/SECURITY_AND_PRIVACY.md`
- Modify: `docs/operations/BACKUP_AND_RECOVERY.md`
- Test: `scripts/check_docs.py`

**Interfaces:**
- Consumes: verified behavior and flags from Tasks 2–11.
- Produces: exact user/admin truth for legacy versus conversational, typed/audio parity, privacy defaults/deletions, cloud disclosure, recovery, no prohibited inference, diagnostics, benchmark/security evidence, and rollout/rollback.

- [ ] **Step 1: Write documentation content tied to executable commands**

Document repository default `HATCH_COACH_CONVERSATIONAL_ENABLED=false`; opt-in only after gates; disabling blocks new creation but preserves existing reads and cleanup; privacy consequences of audio/transcript/hard delete; receipt 30-day default; exports and print; cloud data categories; diagnostic safe codes; standard benchmark invocation; rollback by disabling creation rather than undoing privacy jobs.

- [ ] **Step 2: Add backup/restore smoke decision**

The repository release process documents Hatch-managed update backups but no Coach-specific database restore command. Record PR4 backup/restore smoke as not executed/not required for this application PR, cite `docs/operations/BACKUP_AND_RECOVERY.md`, and retain the integration promotion requirement to run the supported release-process backup/restore rehearsal when a release artifact is promoted. Do not invent a destructive restore command.

- [ ] **Step 3: Validate docs and flag behavior**

```bash
python scripts/check_docs.py
rg -n 'HATCH_COACH_CONVERSATIONAL_ENABLED|delete_after_processing|no emotion|hard delete|coach_conversational_v1' README.md docs/user-guide/INTERVIEW_PREP.md docs/architecture/COACH_CONVERSATIONAL.md docs/architecture/SECURITY_AND_PRIVACY.md docs/operations/BACKUP_AND_RECOVERY.md
cd backend && python -m pytest -q --no-cov tests/test_routers/test_coach_conversation_router.py -k 'feature_flag or disabled or cleanup'
```

Expected: docs check exits 0; disabled creation, enabled synthetic creation, existing reads, and cleanup assertions pass.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md docs/user-guide/INTERVIEW_PREP.md docs/architecture/COACH_CONVERSATIONAL.md docs/architecture/SECURITY_AND_PRIVACY.md docs/operations/BACKUP_AND_RECOVERY.md
git commit -m "docs(coach): document conversational privacy and rollout"
```

### Task 13: Run Full Gates, Capture Rollout Evidence, and Perform Ordered Reviews

**Files:**
- Verify: entire PR4 diff
- Evidence: PR description/artifacts outside source tree unless repository policy names a tracked evidence path

**Interfaces:**
- Consumes: all PR4 commits.
- Produces: complete traceability, exact verification outputs, leakage review, finding dispositions, specification review, quality review, and merge-readiness verdict.

- [ ] **Step 1: Run targeted backend PR4 suite**

```bash
cd backend && python -m pytest -q --no-cov tests/test_services/test_coach_conversational_report.py tests/test_services/test_coach_conversational_progress.py tests/test_services/test_coach_privacy.py tests/test_services/test_coach_report_export.py tests/test_services/test_coach_support_diagnostics.py tests/test_repositories/test_conversational_privacy_repository.py tests/test_routers/test_coach_conversation_report.py tests/test_routers/test_coach_conversation_privacy.py tests/test_observability/test_coach_conversation_privacy.py tests/security/test_coach_conversational_security.py tests/security/test_coach_conversational_dast.py
```

Expected: exit 0; record pass count and duration.

- [ ] **Step 2: Run migration, full backend, frontend, and repository gates**

```bash
cd backend && alembic heads && alembic upgrade head && alembic current
python -m pytest tests/ -v --tb=short
cd ../frontend && npm run type-check && npm test && npm run build && HATCH_E2E_SYNTHETIC=1 npm run test:e2e
cd .. && python scripts/check_docs.py && make ci
```

Expected: one Alembic head; all commands exit 0. Record exact counts; do not summarize a failure as passing.

- [ ] **Step 3: Run standard benchmark and preserve manifest/gate summary**

```bash
rm -rf /tmp/hatch-coach-pr4-standard
cd backend && python -m benchmarks.coach run --suite benchmarks/coach/fixtures/conversational_v1 --models configured-local --profile standard --output-root /tmp/hatch-coach-pr4-standard
find /tmp/hatch-coach-pr4-standard -maxdepth 2 -type f -name 'manifest.json' -o -name 'summary.json' -o -name 'report.md'
```

Expected: exit 0 only when the configured synthetic/local standard adapter is supported; otherwise record the exact unexecuted model-dependent gate and block stable promotion until it runs in an approved isolated environment. Never substitute `contract-smoke` for the required standard profile.

- [ ] **Step 4: Run leakage scan and synthetic cleanup review**

```bash
rg -n 'CANARY-(TRANSCRIPT|EVIDENCE|CV|PROMPT|MODEL|PATH|SECRET)' /tmp/hatch-coach-pr4-standard backend/test-results frontend/test-results 2>/dev/null && exit 1 || true
find /tmp -maxdepth 2 -type f -path '*hatch-coach-pr4*' -name '*.wav' -o -name '*.webm' -o -name '*.mp3'
git status --short
git diff --check feature/coach-phase1-phase2...HEAD
```

Expected: no canary or retained synthetic media match; only intended source changes appear; diff check exits 0. Remove isolated synthetic artifacts after evidence hashes/results are captured.

- [ ] **Step 5: Complete the traceability table below with actual evidence**

For each row replace “Required” with observed RED failure, GREEN exit/count, SHA, and artifact path in the PR description. Missing evidence leaves the row incomplete and blocks merge.

- [ ] **Step 6: Request specification-compliance review first**

Reviewer checks V6 §§0, 4, 27–38, 39 PR4, 40–46; PR1–3 base; Phase 2 exclusion; all AC mappings; deletion/export ownership; legacy preservation; exact commands/artifacts. Resolve findings and rerun affected gates. Required verdict: `PASS` with no unresolved binding finding.

- [ ] **Step 7: Request code-quality/security review only after specification PASS**

Reviewer checks transaction fences, deterministic algorithms, auth/IDOR/path safety, rendering, telemetry cardinality/privacy, test isolation, maintainability, and evidence quality. Resolve findings and rerun affected gates. Required verdict: `PASS`; no critical/high finding and every medium has explicit owner/disposition.

- [ ] **Step 8: Prove controlled rollout and merge readiness**

Run isolated acceptance once with flag false and once true; false rejects new creation while reads/cleanup continue, true completes typed/voice/report/progress/export/deletion flows. Record config source without secrets, commands, results, rollback instruction (set false), known limitations, owner manual-acceptance status, and the promotion blockers. Do not change the checked-in default to true.

---

## Traceability Matrix

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| §27.2–§27.12 / AC-20, AC-22, AC-23, AC-25 — separate accepted-attempt deterministic report, fallback, version-fenced snapshot | report unit/repository tests fail before builder exists | `coach_conversational_report.py`, conversational repository, command/reconciliation | Task 3 command | Required: exact RED/GREEN output and counts |
| §28 / AC-24, AC-25 — exact compatibility groups, deterministic ordering/cap, named trends | progress selector/group/vector tests fail before service exists | `coach_conversational_progress.py`, repository | Task 4 command | Required: exact RED/GREEN output and counts |
| §29.5–§29.8 / AC-27 — physical transcript-derived deletion and hidden fenced rebuild | privacy deletion/rebuild tests fail before orchestrator exists | `coach_privacy.py`, repository, report/reconciliation | Task 5 command | Required: physical absence and stale-worker evidence |
| §29.9 — every-state hard delete, bounded receipt, failure/retry, worker fencing | hard-delete replay/race/expiry tests fail before service exists | privacy service/repository/reconciliation | Task 5 command and five race repeats | Required: exact race outputs and receipt inspection |
| §29.12 — snapshot-consistent JSON/Markdown, safe headers/filename, deterministic ETag, no artifact/audio | export byte/race tests fail before renderer exists | `coach_report_export.py`, repository/router | Tasks 6–7 commands | Required: byte/hash/header assertions |
| §30.4–§30.6, §35 — auth, IDOR, safe IDs/errors, bounded resources | router/security negative cases fail before routes exist | router, schemas, security tests | Tasks 7 and 11 commands | Required: no disclosure/mutation evidence |
| §31 / AC-30 — facade spans/metrics, trace-only state version, content-free diagnostics | canary/sanitizer tests fail before allowlist extensions | observability files, diagnostics, privacy tests | Task 8 command | Required: all canaries absent, safe codes present |
| §33.7, §33.10 / AC-25 — accessible named report/progress/privacy/print, safe untrusted rendering | frontend tests fail before PR4 components exist | API types, report page, conversation components | Task 9 command | Required: unit/type/build/a11y results |
| §34 / AC-29 — legacy reports/progress/video/callers unchanged | existing legacy regression protects numeric fixtures | dispatch only; legacy builder/components untouched | Tasks 7 and 13 full suites | Required: unchanged fixture results |
| §37.7, §37.11–§37.15 / AC-22–AC-30 — report/deletion/router/frontend/E2E/race coverage | new tests initially fail on missing PR4 paths | all PR4 tests | Tasks 3–11 commands | Required: focused/full counts and E2E artifact |
| §38 — complete synthetic standard profile, hard gates, metrics, manifest | benchmark tests fail on missing groups/profile fields | existing Coach benchmark harness and fixture | Tasks 10 and 13 benchmark commands | Required: run ID, manifest hash, gate summary |
| §39 PR4, §42, §45–§46 — complete production-hardening and rollout evidence | release checklist is incomplete before full gates | docs/evidence and whole PR4 diff | Task 13 commands/reviews | Required: two ordered PASS verdicts and owner acceptance status |

## Binding Security Finding Record

Every finding uses this exact record:

```text
ID and severity:
Boundary and synthetic attack precondition:
V6 section/approved gate, or optional hardening proposal:
Reproduction command and fixture ID:
Observed versus required behavior:
Confidentiality/integrity/availability/privacy impact:
Owner and disposition (fix, accepted risk, deferred proposal, false positive):
Verification artifact and residual limitation:
```

Critical/high findings block merge. Each medium requires explicit disposition. Optional proposals remain separate from the V6 binding verdict.

## PR4 Completion Record

The PR description must report:

- Scope and explicit legacy/Phase 2/export-PDF exclusions.
- Integration base SHA, PR4 head SHA, target branch, V6/design hashes, and one Alembic head.
- Completed traceability table with observed RED/GREEN outputs.
- Report/progress determinism evidence and export byte/ETag samples without candidate content.
- Deletion ownership, race, failure/retry, receipt expiry, rebuild, and cleanup evidence.
- Full backend/frontend/build/E2E counts and standard benchmark run/manifest/gate paths.
- Isolated synthetic security target statement, runtime/tool versions, findings/dispositions, leakage scan, and cleanup result.
- Documentation check and backup/restore gate disposition based on the supported release process.
- Feature-flag false/true acceptance, rollback, owner manual acceptance, and known limitations.
- Specification-compliance verdict followed by code-quality/security verdict.
- Merge readiness. Missing evidence, any unresolved binding finding, an unexecuted required standard/E2E/security gate, or owner acceptance pending means not ready for stable promotion.

## Explicit Exclusions

- No Phase 2 Candidate Intelligence persistence, findings, confidence bands, governance gateways, mentor personas, or cross-session weakness plan.
- No conversion/recalculation of legacy numeric reports or progress, no removal of legacy video/media, and no `ScoreRadar` reuse for conversational sessions.
- No persisted export entity, download lifecycle, expiry worker, server PDF, recruiter sharing, or raw-audio export/link.
- No new generic benchmark, observability SDK use in Coach services, WebSocket/WebRTC, production DAST, real candidate fixtures, or checked-in secrets/artifacts.
- No feature-flag default enablement before the full integration promotion gate and owner approval.
