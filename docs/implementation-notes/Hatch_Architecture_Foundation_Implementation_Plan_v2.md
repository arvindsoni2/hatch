# Hatch architecture foundation implementation plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the typed, durable Hatch runtime foundation; prove it with job scoring; migrate CV tailoring and cover-letter generation; then move generic Coach Phase 1 execution durability into the shared kernel without changing Coach product behavior.

**Architecture:** Add a focused `backend/app/runtime/` package around immutable `TaskSpec` contracts, relational attempts and fenced claims, deterministic policy, declared context, task-aware model routing, typed execution adapters, atomic events/outbox, evaluation records, and privacy-safe telemetry. Adopt it with a strangler boundary (`LEGACY`, `SHADOW`, `NEW`) so each product slice has one authoritative runtime, and do not begin Coach extraction until the runtime and three preceding slices have passed their gates.

**Tech Stack:** Python 3.x, FastAPI, Pydantic 2.13.4, async SQLAlchemy 2.0.50, Alembic 1.18.4, SQLite/WAL with PostgreSQL-compatible store semantics, OpenTelemetry, pytest/pytest-asyncio, existing LangChain provider adapters, existing Next.js frontend only if status or migration controls need it.

**Spec:** `docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md` (approved SHA-256: `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`)

## Global Constraints

- Planning baseline is `main` at `ed366775d41f9e64c3ed7a1163e8f958d0ddaa2e`; re-run the §0.4 drift audit when implementation starts if `HEAD` differs.
- The architecture itself is formally approved through ARCH-12, including ARCH-06R1. The exact authority file must be tracked at `docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md` and its SHA-256 recorded before R1. Do not infer or reconstruct it from this plan.
- The implementation specification is a separate approval boundary. Repository lifecycle metadata uses validator-supported `status: active` / `implementation_status: partial`, but implementation must not start until the owner explicitly says `SPEC-v2 approved for implementation` and the extra `approval_status` field is `approved-for-implementation`.
- The first `python scripts/check_docs.py` run in R0 is a known RED baseline and may fail. Record the exact failures. After documentation repair, rerun it and require exit 0 before runtime code.
- Delete untracked obsolete condensed Coach v1/local old copies as tracked V6 requires. Do not relocate, track, or treat them as authority. V6 remains the sole Phase 1 product-contract authority.
- This plan is repository authority only at `docs/implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md`; `docs/superpowers/` is ignored and must not hold the canonical plan.
- Preserve SQLite/WAL, `busy_timeout=5000`, foreign keys, short-lived async sessions, and the repository-supported Alembic topology. The current migration head is `q4r5s6t7u8v9`; every runtime migration must leave exactly one head.
- No wholesale rewrite; no OpenAI Agents SDK, ADK, LangGraph migration, Temporal, Celery, Redis, Kafka, microservices, Kubernetes, or global MCP conversion.
- PostgreSQL is a semantic seam, not a deployment deliverable. Do not add a PostgreSQL driver or environment in this foundation.
- `asyncio.Task` may wake local work but is never recovery authority. Durable state must exist before scheduling, and workers use independent `AsyncSession` instances.
- Do not hold a database write transaction across an LLM, network, artifact-rendering, or external capability call.
- Models may request actions but cannot authorize them. Committing side effects require Control Plane authorization and exact payload-bound approval when policy demands it.
- All existing slice modes default to `LEGACY`; resolve mode once at entry. A `WorkflowRun` never changes runtime mid-flight, and `SHADOW` never owns visible state or committing side effects.
- `TaskSpec`, context packages, prior attempts, execution lineage, event history, outbox-attempt history, and recorded decisions are immutable/versioned records.
- Persist structured, bounded metadata. Default production capture is `METADATA_ONLY`; do not copy raw prompts, CVs, transcripts, model output, user-controlled paths, tokens, or secrets into events, decision/evaluation records, logs, metric labels, or span attributes.
- Active failure injection, race, adversarial, deletion, and privacy tests use bounded synthetic data in isolated local databases only.
- R1–R4 implement the runtime core before any product slice becomes `NEW`. Job scoring proves R2; Job Scoring, CV Tailoring, and Cover Letter must all be `NEW` before Coach extraction can pass R4.
- Coach R8 implements no Phase 2 behavior: no Candidate Intelligence entities, findings, confidence bands, governance gateways, mentor personas, or cross-session intelligence. Coach domain semantics remain in Coach modules.
- During Coach R8, the tracked V6 Phase 1 specification remains the product-contract authority. Preserve command idempotency/order, state versions, ownership, upload/media safety, worker-generation fences, evidence rules, deletion/export semantics, safe errors, privacy, and AC-01 through AC-32.
- Every task follows RED → observed expected failure → minimal GREEN → focused regression → exact-path commit. Do not stage with `git add .` or `git add -A`.
- Every PR records baseline/head, spec hashes, invariants, exact commands, exit status, pass/fail counts, migration head, artifacts, rollback mode, and limitations. Specification-compliance review precedes code-quality/security review.
- All R0-R9 PRs target `main`. Each PR begins only after its predecessor merges, from freshly fast-forwarded `main`. No long-lived integration branch.
- Generic runtime core stays product-independent. Product TaskSpecs and concrete product context/capability/migration bindings live under `backend/app/runtime_bindings/`.
- State + event + outbox atomicity uses a transaction-scoped `RuntimeUnitOfWork`; repositories bound to one UoW share one `AsyncSession` and never commit independently.
- Persisted shadow comparisons retain metadata/hashes only for 30 days. They never store raw model output or generated artifacts.
- `DEBUG_CONTENT` remains an enum but is test/local-developer only in this foundation; normal deployment configuration must reject it. Existing LLM response-preview buffering is gated by the capture policy.

---

## Delivery topology

Use ten sequential PRs. Each branch starts from freshly updated `main` after its predecessor merges; do not stack sibling branches. Suggested branch names:

```text
runtime/r0-baseline-characterization
runtime/r1-contracts-persistence-events
runtime/r2-workflow-kernel
runtime/r3-control-execution
runtime/r4-context-intelligence-evaluation
runtime/r5-job-score-migration
runtime/r6-cv-tailor-migration
runtime/r7-cover-letter-migration
runtime/r8-coach-kernel-extraction
runtime/r9-r4-verification-cleanup
```

Before opening every PR, run:

```bash
git fetch origin
git merge-base --is-ancestor "$BASE_SHA" HEAD
git log --oneline "$BASE_SHA"..HEAD
git diff --check "$BASE_SHA"..HEAD
git diff --stat "$BASE_SHA"..HEAD
```

Open the PR with base `main`. If `origin/main` moved for unrelated reasons, update/rebase and rerun the affected gate before review.

Each PR creates `docs/implementation-reports/runtime/RN-evidence.md` using this fixed evidence shape:

```markdown
| Contract / invariant | RED test and observed failure | Implementation files | Verification command | GREEN evidence |
|---|---|---|---|---|
| `INV-CTR-001` | `test_task_spec_is_frozen_and_versioned` plus mutation failure | `backend/app/runtime/contracts/task_spec.py` | focused pytest command | exit status, count, artifact |
```

For R8, add a second table with the V6 shape:

```markdown
| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
```

## File structure and ownership

The generic runtime core and product bindings are deliberately separate.

```text
backend/app/runtime/
  contracts/       IDs, enums, TaskSpec, capture policy, stable runtime errors
  storage/         semantic store protocols, RuntimeUnitOfWork, SQLite implementation
  workflow/        ORM records, repositories, claims, retries, waiting, approvals, kernel, reconciliation
  control/         policy inputs, precedence, budgets, effective constraints
  context/         generic requirement/item/package models, registry, resolver
  intelligence/    model descriptors, registry, deterministic router, evidence qualification
  execution/       generic capability descriptors, registry, gateway, provider-level adapters
  events/          event/outbox records, transactional append, publisher/claim logic
  evaluation/      durable records, validators, bounded evaluation service, evidence records
  observability/   runtime-safe attributes and wrappers around shared telemetry
  migration/       RuntimeMode only

backend/app/runtime_bindings/
  tasks/           job.score, cv.tailor, cover_letter.generate, Coach task definitions
  context/         concrete profile/resume/job/application/Coach providers
  capabilities/    product-specific local scoring/artifact/Coach capability bindings
  migration/       legacy facade + slice dispatchers/adapters
```

Dependency direction:

```text
product entrypoints
      ↓
runtime_bindings
      ↓
runtime
```

`backend/app/runtime/` may not import product routers, product agents, Coach services, job/resume/application stores, or other product-domain modules. `runtime_bindings` may import both sides. Enforce this with an import-boundary test.

---

### Task 1: R0 documentation preflight and repository characterization

**Files:**
- Modify: `docs/README.md:13`
- Modify/track: `docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md`
- Obtain/track: `docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md`
- Delete if present and untracked: `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Spec_v1.md`
- Track: `docs/implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md`
- Create: `backend/tests/runtime/conftest.py`
- Create: `backend/tests/runtime/fixtures/job_score_cases.json`
- Create: `backend/tests/runtime/fixtures/tailoring_cases.json`
- Create: `backend/tests/runtime/fixtures/cover_letter_cases.json`
- Create: `backend/tests/runtime/fixtures/coach_cases.json`
- Create: `backend/tests/runtime/test_characterization_job_scoring.py`
- Create: `backend/tests/runtime/test_characterization_tailoring.py`
- Create: `backend/tests/runtime/test_characterization_cover_letter.py`
- Create: `backend/tests/runtime/test_characterization_coach.py`
- Create: `docs/implementation-reports/runtime/R0-evidence.md`

**Interfaces:**
- Consumes: current public scorer, `TailorService`, router result schemas, `AsyncJobService`, `ConversationalSessionRepository`, and Coach reconciliation behavior.
- Produces: synthetic fixtures and locked legacy result-shape assertions used by R5–R8 semantic comparison tests.

- [ ] **Step 1: Verify authority, record RED documentation baseline, and create the R0 branch**

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git status --short
sha256sum docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
python scripts/check_docs.py; printf 'docs_baseline_exit=%s
' "$?"
cd backend
alembic heads
alembic current
cd ..
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r0-baseline-characterization
git merge-base --is-ancestor origin/main HEAD
```

Expected: record exact `HEAD`; explain every pre-existing worktree item; the first documentation check may be non-zero and is recorded as the known RED baseline; `alembic heads` returns one head. If `HEAD` differs from the planning baseline, run the exact §0.4 path-limited drift audit and record material changes in `R0-evidence.md`.

Also run:

```bash
find docs -type f -name 'Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md' -print
```

Expected before R1: exactly one owner-approved, tracked architecture file is returned at `docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md` and its SHA-256 is recorded in `R0-evidence.md`. At planning time this command returned no file, so R0 must stop until the document is supplied; the implementation spec is not silently promoted to replace its declared authority.

- [ ] **Step 2: Repair documentation authority, metadata, and plan placement**

Require the implementation spec to contain:

```yaml
status: active
implementation_status: partial
approval_status: approved-for-implementation
architecture_baseline: docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md
```

The `approval_status` change is permitted only after explicit owner approval.

Delete any untracked condensed Coach v1 copy rather than moving it:

```bash
if git ls-files --error-unmatch docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Spec_v1.md >/dev/null 2>&1; then
  echo "STOP: file is tracked; inspect against V6 before deletion"
  exit 1
fi
rm -f docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Spec_v1.md
```

Track the canonical v2 plan under `docs/implementation-notes/`. Do not force-add anything under ignored `docs/superpowers/`.

After repairs:

```bash
python scripts/check_docs.py
```

Expected: exit 0.

- [ ] **Step 3: Add the active-spec link and write synthetic golden fixtures**

Add this item under `Active Implementation Work`:

```markdown
- [Architecture Foundation implementation specification v2](implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md)
```

Fixture records use invented candidate/job/session data and stable IDs such as `synthetic-job-001`; no copied CV, transcript, or real applicant data.

- [ ] **Step 4: Write characterization tests without changing product code**

Lock observable shapes, not implementation internals. For example:

```python
def test_legacy_score_result_shape(characterized_score: dict[str, object]) -> None:
    assert set(characterized_score) >= {
        "skill_match", "experience_match", "rate_match", "location_match",
        "overall_score", "reasoning", "keyword_matches", "keyword_misses",
        "fit_reasoning", "strengths", "score_gaps", "scoring_method",
    }

def test_legacy_coach_reconciliation_is_idempotent(reconcile_twice) -> None:
    first, second, snapshot = reconcile_twice
    assert first >= 0
    assert second == 0
    assert snapshot.authoritative_result_count == 1
```

- [ ] **Step 5: Run and record the baseline suites**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_characterization_job_scoring.py tests/test_agents/test_scorer_agent.py tests/test_tools/test_local_scorer.py tests/test_tools/test_semantic_scorer.py
python -m pytest -q --no-cov tests/runtime/test_characterization_tailoring.py tests/runtime/test_characterization_cover_letter.py tests/test_agents/test_tailor_agent.py tests/test_services/test_cv_tailor.py tests/test_routers/test_tailor_router.py tests/test_routers/test_tailor_async.py
python -m pytest -q --no-cov tests/runtime/test_characterization_coach.py tests/test_services/test_async_job_service.py tests/test_services/test_coach_reconciliation.py tests/test_services/test_coach_session_queue.py tests/test_routers/test_coach_conversation_router.py
cd ..
python scripts/check_docs.py
```

Expected: characterization passes or each pre-existing failure is reproduced, isolated, and recorded without being attributed to runtime work.

- [ ] **Step 6: Commit R0**

```bash
git add docs/README.md docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md docs/implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md docs/implementation-reports/runtime/R0-evidence.md backend/tests/runtime
git commit -m "test(runtime): characterize architecture migration baseline"
```

---

### Task 2: R1 immutable contracts and migration-mode boundary

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r1-contracts-persistence-events
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime/__init__.py`
- Create: `backend/app/runtime/contracts/{__init__,ids,enums,errors,task_spec}.py`
- Create: `backend/app/runtime/migration/{__init__,modes}.py`
- Modify: `backend/app/config.py:13`
- Test: `backend/tests/runtime/test_task_spec.py`
- Test: `backend/tests/runtime/test_migration_modes.py`

**Interfaces:**
- Produces: `TaskSpec[InputT, OutputT]`, semantic ID `NewType`s, `ExecutionStrategy`, `RiskClass`, `ExecutionResultCode`, `WorkflowPolicy`, `RuntimeMode`, and `resolve_runtime_mode(slice_name)`.
- Produces exact settings: `HATCH_RUNTIME_JOB_SCORE_MODE`, `HATCH_RUNTIME_CV_TAILOR_MODE`, `HATCH_RUNTIME_COVER_LETTER_MODE`, `HATCH_RUNTIME_COACH_MODE`, all defaulting to `RuntimeMode.LEGACY`.

- [ ] **Step 1: Write RED contract tests**

```python
def test_task_spec_is_frozen_and_versioned() -> None:
    spec = TaskSpec(
        task_id="test.echo", version=1, input_model=EchoInput,
        output_model=EchoOutput, context_requirements=(),
        model_requirements=ModelCapabilityRequirements(),
        risk_class=RiskClass.LOW, validators=("echo.schema.v1",),
        evaluation_policy=EvaluationPolicy(max_evaluations=0),
        execution_strategy=ExecutionStrategy.SINGLE_PASS,
        workflow_policy=WorkflowPolicy(max_attempts=1),
    )
    with pytest.raises(FrozenInstanceError):
        spec.version = 2  # type: ignore[misc]

@pytest.mark.parametrize("setting", [
    "HATCH_RUNTIME_JOB_SCORE_MODE", "HATCH_RUNTIME_CV_TAILOR_MODE",
    "HATCH_RUNTIME_COVER_LETTER_MODE", "HATCH_RUNTIME_COACH_MODE",
])
def test_existing_installations_default_to_legacy(setting: str) -> None:
    assert getattr(Settings(), setting) is RuntimeMode.LEGACY
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/runtime/test_task_spec.py tests/runtime/test_migration_modes.py`

Expected: import failure because the runtime contracts do not exist.

- [ ] **Step 3: Implement the smallest immutable public contracts**

Use semantic IDs in signatures and reject invalid task/version/validator values in `TaskSpec.__post_init__`. Keep operational preferences out of `TaskSpec`.

- [ ] **Step 4: Run GREEN and import-boundary regression**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_task_spec.py tests/runtime/test_migration_modes.py
ruff check app/runtime/contracts app/runtime/migration app/config.py tests/runtime/test_task_spec.py tests/runtime/test_migration_modes.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/runtime/__init__.py backend/app/runtime/contracts backend/app/runtime/migration backend/tests/runtime/test_task_spec.py backend/tests/runtime/test_migration_modes.py
git commit -m "feat(runtime): add immutable task and migration contracts"
```

---

### Task 3: R1 relational runtime schema and SQLite store contract

**Files:**
- Create: `backend/app/runtime/workflow/models.py`
- Create: `backend/app/runtime/evaluation/models.py`
- Create: `backend/app/runtime/events/models.py`
- Create: `backend/app/runtime/storage/{__init__,contracts,sqlite}.py`
- Create: `backend/alembic/versions/20260820_0001_r5s6t7u8v9w0_add_runtime_foundation.py` (use `down_revision = "q4r5s6t7u8v9"`; if R0 drift changes the head, stop and rebase this filename/revision before writing the migration)
- Modify: `backend/app/models/__init__.py:1`
- Modify: `backend/app/database.py:65`
- Test: `backend/tests/runtime/test_schema_migration.py`
- Test: `backend/tests/runtime/test_storage_contract.py`

**Interfaces:**
- Produces the complete status vocabularies and schema from spec §4, including retry reason/policy identity, waiting reason, `claim_fencing_token`, `current_claim_id`, full `runtime_execution_records.parent_execution_id`, and `runtime_shadow_comparisons`.
- Produces `RuntimeUnitOfWork`, `RuntimeUnitOfWorkFactory`, `WorkflowStore`, `ApprovalStore`, `EventStore`, `OutboxStore`, `EvaluationStore`, and `ShadowComparisonStore`.
- Every repository exposed by one UoW is bound to the same `AsyncSession`/transaction and must not commit independently.

- [ ] **Step 1: Write RED schema and protocol conformance tests**

```python
async def test_retry_schema_preserves_attempt_history(store: WorkflowStore) -> None:
    run = await store.create_run(new_run())
    step = await store.create_step(new_step(run.id))
    first = await store.create_attempt(new_attempt(step.id, attempt_number=1))
    second = await store.schedule_retry(
        first.id, retry_reason="transient", retry_policy_id="default", retry_policy_version=1
    )
    assert (first.attempt_number, second.attempt_number) == (1, 2)
    assert (await store.get_attempt(first.id)).status == AttemptStatus.FAILED

async def test_uow_rolls_back_all_bound_repositories(uow_factory) -> None:
    with pytest.raises(InjectedFailure):
        async with uow_factory.transaction() as uow:
            run = await uow.workflows.create_run(new_run())
            event = await uow.events.append(run_created_event(run.id))
            await uow.outbox.enqueue(event.id, "runtime.evaluation")
            raise InjectedFailure()
    assert await count_runtime_rows() == 0

def test_runtime_migration_has_one_head(alembic_heads: list[str]) -> None:
    assert len(alembic_heads) == 1
```

- [ ] **Step 2: Run RED**

Run: `cd backend && python -m pytest -q --no-cov tests/runtime/test_schema_migration.py tests/runtime/test_storage_contract.py`

Expected: missing models/store and unchanged migration head.

- [ ] **Step 3: Implement additive ORM records and migration**

Use UUID-string IDs consistent with current models, bounded JSON columns, UTC timestamps consistent with the repository, foreign keys, and explicit uniqueness/index constraints. Keep SQLAlchemy ORM types portable; isolate SQLite conditional-update details in `storage/sqlite.py`.

- [ ] **Step 4: Verify upgrade, supported fresh install, downgrade, and one head**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_schema_migration.py tests/runtime/test_storage_contract.py tests/test_migrations/test_database_setup.py
alembic heads
alembic current --check-heads
ruff check app/runtime app/models/__init__.py ../backend/tests/runtime
```

Expected: one head; upgrade from a copy of current-head schema succeeds; fresh `Base.metadata.create_all()` plus `alembic stamp head` sees all runtime tables; downgrade removes only runtime additions; SQLite integrity and foreign-key checks pass.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions backend/app/database.py backend/app/models/__init__.py backend/app/runtime/storage backend/app/runtime/workflow/models.py backend/app/runtime/events/models.py backend/app/runtime/evaluation/models.py backend/tests/runtime/test_schema_migration.py backend/tests/runtime/test_storage_contract.py
git commit -m "feat(runtime): add durable runtime schema and store contracts"
```

---

### Task 4: R1 atomic events, outbox, and privacy guard

**Files:**
- Create: `backend/app/runtime/events/{__init__,repository,outbox}.py`
- Test: `backend/tests/runtime/test_event_atomicity.py`
- Test: `backend/tests/runtime/test_outbox_store.py`
- Test: `backend/tests/runtime/test_runtime_privacy.py`
- Create: `docs/implementation-reports/runtime/R1-evidence.md`

**Interfaces:**
- Produces `uow.events.append(event)` and `uow.outbox.enqueue(event_id, destination)` on one transaction-scoped `RuntimeUnitOfWork`; raw `AsyncSession` is not part of the public runtime contract.
- Produces `OutboxPublisher.claim_next()`, `finalize_delivery()`, and append-only `runtime_outbox_attempts`; delivery is at-least-once and consumers deduplicate by `event_id`.

- [ ] **Step 1: Write RED atomicity, duplicate-delivery, and canary tests**

```python
async def test_state_event_outbox_roll_back_together(failing_store) -> None:
    with pytest.raises(InjectedFailure):
        await failing_store.transition_with_event(fail_after="event_append")
    assert await failing_store.count_committed_state() == 0
    assert await failing_store.count_events() == 0
    assert await failing_store.count_outbox() == 0

def test_metadata_only_records_reject_sensitive_canaries(runtime_records) -> None:
    serialized = json.dumps(runtime_records)
    for canary in ("CV-CANARY", "TRANSCRIPT-CANARY", "PROMPT-CANARY", "/tmp/user-file"):
        assert canary not in serialized
```

- [ ] **Step 2: Implement transaction-owned append/enqueue and fenced publisher claims**

Support only `runtime.telemetry`, `runtime.evaluation`, and `runtime.notification`. A destination dispatches an already-authorized event; it cannot introduce a committing side effect.

- [ ] **Step 3: Run R1 gate**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_task_spec.py tests/runtime/test_migration_modes.py tests/runtime/test_schema_migration.py tests/runtime/test_storage_contract.py tests/runtime/test_event_atomicity.py tests/runtime/test_outbox_store.py tests/runtime/test_runtime_privacy.py
python -m pytest -q --no-cov tests/test_migrations/test_database_setup.py
alembic heads
```

- [ ] **Step 4: Complete evidence, request spec review then quality/security review, and commit**

```bash
git add backend/app/runtime/events backend/tests/runtime/test_event_atomicity.py backend/tests/runtime/test_outbox_store.py backend/tests/runtime/test_runtime_privacy.py docs/implementation-reports/runtime/R1-evidence.md
git commit -m "feat(events): make runtime transitions and outbox atomic"
```

---

### Task 5: R2 claims, fencing, retry, and restart-safe kernel

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r2-workflow-kernel
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime/workflow/{__init__,repository,claims,retry,kernel}.py`
- Test: `backend/tests/runtime/test_claims.py`
- Test: `backend/tests/runtime/test_fencing.py`
- Test: `backend/tests/runtime/test_retries.py`
- Test: `backend/tests/runtime/test_runtime_restart_recovery.py`
- Test: `backend/tests/runtime/test_sqlite_contention.py`

**Interfaces:**
- Produces `WorkflowKernel.start_run(spec, input_ref, domain_ref, mode)`, `claim_next(worker_id, now)`, `renew_claim(claim, now)`, `finalize(claim, result)`, and `fail_or_retry(claim, failure, now)`.
- `ExecutionClaimRecord` binds attempt ID, claim ID, fencing token, worker, and lease; `finalize` returns `False` after ownership loss and never persists the stale result.

- [ ] **Step 1: Write deterministic RED failure-injection tests**

```python
async def test_stale_finalizer_cannot_overwrite_new_owner(kernel, clock) -> None:
    claim_a = await kernel.claim_next("worker-a", clock.now())
    clock.advance_past(claim_a.lease_expires_at)
    claim_b = await kernel.reclaim(claim_a.task_attempt_id, "worker-b", clock.now())
    assert claim_b.fencing_token > claim_a.fencing_token
    assert await kernel.finalize(claim_b, success("B")) is True
    assert await kernel.finalize(claim_a, success("A")) is False
    assert (await kernel.get_attempt(claim_a.task_attempt_id)).result_ref == "B"

async def test_crash_after_claim_recovers_from_database(kernel_factory) -> None:
    first = kernel_factory(fail_after="claim_commit")
    with pytest.raises(InjectedFailure):
        await first.run_once()
    second = kernel_factory()
    assert await second.reconcile() == 1
```

- [ ] **Step 2: Implement claim/finalize as short conditional transactions**

Execution occurs after the claim transaction commits and before the finalize transaction begins. Each concurrent worker obtains its own `AsyncSession`; do not share one `AsyncSession` across `asyncio.gather()` tasks.

- [ ] **Step 3: Implement immutable retries and bounded SQLite contention behavior**

Retries create attempt N+1 with `not_before`, reason, and policy identity. Use injected clocks/barriers rather than sleeps in tests.

- [ ] **Step 4: Run focused GREEN**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_claims.py tests/runtime/test_fencing.py tests/runtime/test_retries.py tests/runtime/test_runtime_restart_recovery.py tests/runtime/test_sqlite_contention.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/runtime/workflow backend/tests/runtime/test_claims.py backend/tests/runtime/test_fencing.py backend/tests/runtime/test_retries.py backend/tests/runtime/test_runtime_restart_recovery.py backend/tests/runtime/test_sqlite_contention.py
git commit -m "feat(workflow): add fenced durable execution kernel"
```

---

### Task 6: R2 waiting, approvals, and generic reconciliation

**Files:**
- Create: `backend/app/runtime/workflow/{approvals,reconciliation}.py`
- Test: `backend/tests/runtime/test_waiting.py`
- Test: `backend/tests/runtime/test_approvals.py`
- Test: `backend/tests/runtime/test_reconciliation.py`
- Create: `docs/implementation-reports/runtime/R2-evidence.md`

**Interfaces:**
- Produces `canonical_payload_hash(payload, algorithm="sha256-canonical-json-v1")` using UTF-8 JSON with sorted keys and deterministic separators.
- Produces durable `wait_for(reason)`, `resume_waiting()`, `request_approval()`, `decide_approval()`, `invalidate_for_payload_change()`, and reconciliation callbacks for `OUTCOME_UNKNOWN`.

- [ ] **Step 1: Write RED waiting and exact-payload approval tests**

```python
async def test_waiting_owns_no_claim(store) -> None:
    attempt = await store.transition_waiting(reason=WaitingReason.APPROVAL)
    assert attempt.status is AttemptStatus.WAITING
    assert await store.current_claim(attempt.id) is None

async def test_approval_for_payload_a_does_not_authorize_b(approvals) -> None:
    record = await approvals.request(capability_id="artifact.publish", payload={"path": "A"})
    await approvals.approve(record.id, decided_by="synthetic-user")
    assert await approvals.is_valid(record.id, payload={"path": "A"}) is True
    assert await approvals.is_valid(record.id, payload={"path": "B"}) is False
```

- [ ] **Step 2: Implement waiting/resume and approval invalidation**

Resume creates a fresh claimable context. Never retain or revive a worker claim across approval, user-input, or retry-time waits.

- [ ] **Step 3: Implement reconciliation policy dispatch**

Expired claims advance ownership through a new fencing token. `NON_RETRYABLE_SIDE_EFFECT` is never replayed blindly; `OUTCOME_UNKNOWN` invokes a registered capability reconciliation/check-before-retry handler.

- [ ] **Step 4: Run R2 gate and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_claims.py tests/runtime/test_fencing.py tests/runtime/test_retries.py tests/runtime/test_waiting.py tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py tests/runtime/test_runtime_restart_recovery.py tests/runtime/test_sqlite_contention.py tests/runtime/test_event_atomicity.py
python -m pytest -q
git add backend/app/runtime/workflow backend/tests/runtime/test_waiting.py backend/tests/runtime/test_approvals.py backend/tests/runtime/test_reconciliation.py docs/implementation-reports/runtime/R2-evidence.md
git commit -m "feat(workflow): add durable waiting approval and reconciliation"
```

---

### Task 7: R3 deterministic Control Plane

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r3-control-execution
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime/control/{__init__,models,policy,budgets}.py`
- Test: `backend/tests/runtime/test_policy_precedence.py`
- Test: `backend/tests/runtime/test_policy_force_model.py`

**Interfaces:**
- Produces `PolicyDecision(decision, reason_codes, effective_constraints)` and `ControlPlane.evaluate(task_spec, security_policy, workflow_policy, user_config, routing_preferences)`.
- Enforces precedence: system invariants → TaskSpec → security/privacy → workflow → user configuration → routing preferences.

- [ ] **Step 1: Write RED precedence and FORCE tests**

```python
def test_user_config_cannot_weaken_system_egress_denial(control_plane) -> None:
    decision = control_plane.evaluate(system=data_egress(False), user=data_egress(True))
    assert decision.effective_constraints.data_egress is False
    assert "system.data_egress_denied" in decision.reason_codes

def test_force_model_remains_subject_to_quality_and_policy(control_plane) -> None:
    decision = control_plane.evaluate(task=requires_structured_output(), routing=force("model-x"))
    assert decision.decision == "DENY"
    assert "model.structured_output_required" in decision.reason_codes
```

- [ ] **Step 2: Implement immutable constraint folding and bounded budgets**

Represent narrowing operations explicitly; lower-precedence inputs may tighten but never widen an already constrained set/budget.

- [ ] **Step 3: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_policy_precedence.py tests/runtime/test_policy_force_model.py
git add backend/app/runtime/control backend/tests/runtime/test_policy_precedence.py backend/tests/runtime/test_policy_force_model.py
git commit -m "feat(control): enforce deterministic runtime policy precedence"
```

---

### Task 8: R3 typed Execution Gateway and minimal adapters

**Files:**
- Create: `backend/app/runtime/execution/{__init__,models,registry,gateway}.py`
- Create: `backend/app/runtime/execution/adapters/{__init__,native,llm,artifact}.py`
- Test: `backend/tests/runtime/test_execution_gateway.py`
- Test: `backend/tests/runtime/test_side_effect_authorization.py`
- Test: `backend/tests/runtime/test_idempotency.py`
- Test: `backend/tests/runtime/test_outcome_unknown.py`
- Test: `backend/tests/runtime/test_deadlines.py`
- Create: `docs/implementation-reports/runtime/R3-evidence.md`

**Interfaces:**
- Produces `CapabilityDescriptor`, `CapabilityRegistry.register/resolve`, adapters returning typed `CapabilityResult`, and `ExecutionGateway.invoke(claim, descriptor, payload, policy, approval=None)`.
- Gateway order is resolve → authorize → verify approval → establish deadline/budget → invoke outside write transaction → classify → fenced durable execution record → non-fatal telemetry.

- [ ] **Step 1: Write RED authorization/order tests with a recording fake adapter**

```python
async def test_visible_capability_is_not_automatically_authorized(gateway, recording_adapter) -> None:
    result = await gateway.invoke(capability_id="artifact.publish", policy=deny_all(), payload={})
    assert result.code is ExecutionResultCode.POLICY_DENIED
    assert recording_adapter.calls == []

async def test_lost_external_commit_becomes_outcome_unknown(gateway, lost_response_adapter) -> None:
    result = await gateway.invoke(
        capability_id="external.commit", policy=allow(), payload={"idempotency_key": "k1"}
    )
    assert result.code is ExecutionResultCode.OUTCOME_UNKNOWN
    assert result.retry_allowed is False
```

- [ ] **Step 2: Implement registry, gateway, and only four initial capabilities**

Keep provider-generic `llm.generate_structured` in the generic runtime adapter layer.
Register product-specific `job.local_score`, `artifact.render_cv`, and `artifact.render_cover_letter`
from `backend/app/runtime_bindings/capabilities/`. Do not expose internal functions through MCP.

- [ ] **Step 3: Run R3 gate and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_execution_gateway.py tests/runtime/test_side_effect_authorization.py tests/runtime/test_idempotency.py tests/runtime/test_outcome_unknown.py tests/runtime/test_deadlines.py tests/runtime/test_policy_precedence.py tests/runtime/test_policy_force_model.py tests/runtime/test_fencing.py
python -m pytest -q
git add backend/app/runtime/execution backend/tests/runtime/test_execution_gateway.py backend/tests/runtime/test_side_effect_authorization.py backend/tests/runtime/test_idempotency.py backend/tests/runtime/test_outcome_unknown.py backend/tests/runtime/test_deadlines.py docs/implementation-reports/runtime/R3-evidence.md
git commit -m "feat(execution): add policy-gated capability gateway"
```

---

### Task 9: R4 declared Context Plane and immutable packages

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r4-context-intelligence-evaluation
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime/context/{__init__,models,registry,resolver}.py`
- Create: `backend/app/runtime_bindings/context/{__init__,profile,resume,job,application,coach}.py`
- Modify: `backend/app/agents/tools/context_budgets.py`
- Modify: `backend/app/agents/tools/context_checker.py`
- Test: `backend/tests/runtime/test_context_registry.py`
- Test: `backend/tests/runtime/test_context_resolver.py`
- Test: `backend/tests/runtime/test_context_immutability.py`
- Test: `backend/tests/runtime/test_context_privacy.py`

**Interfaces:**
- Produces `ContextRequirement`, `ContextItem`, `ContextPackage`, `ContextProvider`, `ContextRegistry`, and `ContextResolver.resolve(task_attempt_id, requirements, budget)`.
- Providers wrap existing profile/resume/job/application/Coach sources; they do not relocate domain data. Package persistence stores references, provenance, sensitivity, freshness, estimates, and hashes—not a second content lake.

- [ ] **Step 1: Write RED declared-only and immutability tests**

```python
async def test_resolver_never_fetches_undeclared_context(resolver, providers) -> None:
    package = await resolver.resolve("attempt-1", (ContextRequirement(capability="job.description"),))
    assert [item.capability for item in package.items] == ["job.description"]
    assert providers["candidate.resume_text"].calls == 0

async def test_retry_resolves_new_package_without_mutating_prior(resolver) -> None:
    first = await resolver.resolve("attempt-1", REQUIREMENTS)
    second = await resolver.resolve("attempt-2", REQUIREMENTS)
    assert first.id != second.id
    assert await resolver.load(first.id) == first
```

- [ ] **Step 2: Implement provider registry and deterministic budget resolution**

Initial capabilities are exactly those listed in architecture spec §9.2. Fail a required missing item with a stable code; omit an optional item with a recorded reason.

- [ ] **Step 3: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_context_registry.py tests/runtime/test_context_resolver.py tests/runtime/test_context_immutability.py tests/runtime/test_context_privacy.py
git add backend/app/runtime/context backend/app/agents/tools/context_budgets.py backend/app/agents/tools/context_checker.py backend/tests/runtime/test_context_registry.py backend/tests/runtime/test_context_resolver.py backend/tests/runtime/test_context_immutability.py backend/tests/runtime/test_context_privacy.py
git commit -m "feat(context): resolve declared immutable context packages"
```

---

### Task 10: R4 model registry, deterministic router, and evidence promotion

**Files:**
- Create: `backend/app/runtime/intelligence/{__init__,models,registry,router,evidence}.py`
- Modify: `backend/app/agents/tools/llm_factory.py:417`
- Test: `backend/tests/runtime/test_model_router.py`
- Test: `backend/tests/runtime/test_router_candidate_snapshot.py`
- Test: `backend/tests/runtime/test_evidence_promotion.py`

**Interfaces:**
- Produces `ModelDescriptor`, `ModelRegistry`, `ModelRouter.route(requirements, policy, preference)`, `EvidenceObservation`, and explicit `promote_model_evidence(observation_ids, qualification)`.
- `llm_factory` remains provider construction; descriptors wrap its current configured models instead of duplicating provider initialization.

- [ ] **Step 1: Write RED router-order and non-self-modification tests**

```python
def test_router_records_every_candidate_and_exclusion(router) -> None:
    decision = router.route(requires_structured_output(), allow_local_only(), auto())
    assert [stage.name for stage in decision.stages] == [
        "capability", "quality", "policy", "evidence", "fallback"
    ]
    assert all(candidate.excluded_reason_codes is not None for candidate in decision.candidates)

def test_observation_does_not_change_routing_until_promoted(router, observation_store) -> None:
    before = router.route(TASK, POLICY, auto()).selected_model_id
    observation_store.record(high_quality_observation("other-model"))
    assert router.route(TASK, POLICY, auto()).selected_model_id == before
```

- [ ] **Step 2: Implement descriptors from existing model/profile configuration**

`AUTO` uses normal rank, `PREFER` adds rank only for an eligible model, and `FORCE` filters to the selected model only after capability, quality, and policy gates.

- [ ] **Step 3: Run GREEN and commit**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_model_router.py tests/runtime/test_router_candidate_snapshot.py tests/runtime/test_evidence_promotion.py tests/test_services/test_model_discovery.py
git add backend/app/runtime/intelligence backend/app/agents/tools/llm_factory.py backend/tests/runtime/test_model_router.py backend/tests/runtime/test_router_candidate_snapshot.py backend/tests/runtime/test_evidence_promotion.py
git commit -m "feat(router): add explainable task-aware model routing"
```

---

### Task 11: R4 bounded evaluation and privacy-safe OTel correlation

**Files:**
- Create: `backend/app/runtime/evaluation/{__init__,validators,service,evidence}.py`
- Create: `backend/app/runtime/observability/{__init__,attributes,tracing}.py`
- Modify: `backend/app/observability/attributes.py`
- Modify: `backend/app/observability/runtime.py:151`
- Modify: `backend/app/agents/tools/llm_factory.py:61`
- Test: `backend/tests/runtime/test_evaluation_service.py`
- Test: `backend/tests/runtime/test_otel_correlation.py`
- Test: `backend/tests/runtime/test_otel_export_failure.py`
- Test: `backend/tests/runtime/test_runtime_privacy.py`
- Create: `docs/implementation-reports/runtime/R4-evidence.md`

**Interfaces:**
- Produces deterministic → heuristic → optional model evaluator → human-review ordering with hard maximum evaluations/repairs.
- Defines `CapturePolicy` with `METADATA_ONLY`, `REDACTED`, `DEBUG_CONTENT`, `DISABLED`; normal deployment config accepts only metadata/redacted/disabled and defaults to metadata-only. `DEBUG_CONTENT` is test/local-developer injection only with <=24h debug retention.
- Produces runtime span attributes `hatch.workflow_run_id`, `hatch.workflow_step_id`, `hatch.task_attempt_id`, `hatch.execution_id`, `hatch.task_id`, and `hatch.task_version`; metric sanitization rejects identifiers and content.
- Modifies the existing `llm_factory` trace ring buffer so `response_preview` is not retained under normal deployment capture modes.

- [ ] **Step 1: Write RED bounded-evaluation, lineage, exporter-failure, and canary tests**

```python
async def test_deterministic_failure_stops_unneeded_model_evaluation(service, model_evaluator) -> None:
    result = await service.evaluate(invalid_schema_output(), policy=deterministic_only())
    assert result.status == "failed"
    assert model_evaluator.calls == []

async def test_exporter_failure_does_not_change_workflow_result(kernel, failing_exporter) -> None:
    result = await kernel.execute(ECHO_TASK)
    assert result.code is ExecutionResultCode.SUCCESS
    assert failing_exporter.failures == 1
```

- [ ] **Step 2: Implement bounded evaluation and wrap the shared telemetry facade**

Do not install a second tracer provider. Span processors must not block or throw into workflow execution.
Default exception recording must not include sensitive exception messages from model/content paths; use stable codes.
Add configuration validation that rejects `HATCH_RUNTIME_CAPTURE_POLICY=debug_content` from normal deployment settings.
Canary tests must prove the current LLM trace ring buffer does not retain raw previews under metadata/redacted/disabled modes.

- [ ] **Step 3: Run Gate R1 (runtime core ready)**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime
python -m pytest -q --no-cov tests/test_observability tests/test_services/test_model_discovery.py tests/test_migrations/test_database_setup.py
python -m pytest -q
alembic heads
ruff check app/runtime app/observability app/agents/tools/llm_factory.py tests/runtime
```

Expected: every core invariant from INV-CTR-001 through INV-PRV-001 mapped to an executed test; telemetry failure is non-fatal; one migration head; no product slice migrated.

- [ ] **Step 4: Commit and obtain two ordered reviews**

```bash
git add backend/app/runtime/evaluation backend/app/runtime/observability backend/app/observability backend/tests/runtime/test_evaluation_service.py backend/tests/runtime/test_otel_correlation.py backend/tests/runtime/test_otel_export_failure.py backend/tests/runtime/test_runtime_privacy.py docs/implementation-reports/runtime/R4-evidence.md
git commit -m "feat(eval): add bounded evaluation and runtime telemetry"
```

---

### Task 12: R5 migrate Job Scoring through LEGACY, SHADOW, and NEW

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r5-job-score-migration
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime_bindings/migration/facade.py`
- Create: `backend/app/runtime_bindings/tasks/job_score.py`
- Create: `backend/app/runtime_bindings/migration/job_score.py`
- Modify: `backend/app/agents/scorer_agent.py:113`
- Test: `backend/tests/runtime/test_job_score_task.py`
- Test: `backend/tests/runtime/test_job_score_migration.py`
- Test: `backend/tests/runtime/test_job_score_restart.py`
- Test: `backend/tests/runtime/test_job_score_privacy.py`
- Test: `backend/tests/runtime/test_shadow_retention.py`
- Modify: `backend/tests/test_agents/test_scorer_agent.py`
- Create: `docs/implementation-reports/runtime/R5-job-score-migration.md`

**Interfaces:**
- Produces immutable `JOB_SCORE_V1` (`task_id="job.score"`, `version=1`) with reference-based input and the existing durable score output fields.
- Produces `LegacyAIRuntimeFacade.score_job()` and a mode dispatcher that resolves once before scorer execution.

- [ ] **Step 1: Write RED TaskSpec, authority, shadow, and recovery tests**

```python
@pytest.mark.parametrize("mode,authority", [
    (RuntimeMode.LEGACY, "legacy"),
    (RuntimeMode.SHADOW, "legacy"),
    (RuntimeMode.NEW, "runtime"),
])
async def test_job_score_has_one_authoritative_writer(mode, authority, harness) -> None:
    result = await harness.score(mode=mode)
    assert result.authoritative_engine == authority
    assert await harness.visible_score_count() == 1
    assert await harness.shadow_visible_score_count() == 0
```

- [ ] **Step 2: Implement adapters around existing scoring mathematics**

Reuse local/semantic normalization and existing fallback behavior. Move model selection, retry, declared context, and evaluation ownership to the runtime; the facade only translates inputs/results.

- [ ] **Step 3: Run LEGACY compatibility and SHADOW comparison**

```bash
cd backend
HATCH_RUNTIME_JOB_SCORE_MODE=legacy python -m pytest -q --no-cov tests/test_agents/test_scorer_agent.py tests/runtime/test_job_score_migration.py
HATCH_RUNTIME_JOB_SCORE_MODE=shadow python -m pytest -q --no-cov tests/runtime/test_job_score_task.py tests/runtime/test_job_score_migration.py tests/runtime/test_job_score_restart.py tests/runtime/test_job_score_privacy.py
```

Record golden correctness, semantic differences, latency, cost, fallback/retry, routing explanation, privacy, restart, 30-day retention, and purge results in the migration report.

- [ ] **Step 4: Evaluate the exact R2 promotion gate**

Use at least 50 synthetic/sanitized labeled cases:

```text
20 strong-fit
15 borderline within ±0.10 of shortlist threshold
15 poor-fit / irrelevant
```

Required:

```text
deterministic contract/normalization pass = 100%
expected shortlist accuracy >= 92%
NEW shortlist accuracy >= legacy - 2 percentage points
legacy-vs-NEW shortlist agreement >= 95%
|overall_score NEW - legacy| <= 0.10 for >= 90% of comparable cases
p50 latency <= 1.20x legacy
p95 latency <= 1.25x legacy
mean estimated cost/success <= 1.15x legacy
p95 token usage/success <= 1.25x legacy
privacy/recovery/fencing/shadow-one-writer tests = 100%
complete backend suite = no newly introduced failures
```

Persist shadow comparison **metadata only** for 30 days: hashes, derived metrics, reason codes,
model/task versions, latency/tokens/cost and execution references. Never persist raw shadow model
text or shadow artifacts.

Required approver: repository/architecture owner `@arvindsoni2`, recorded in the R5 report or PR review.

- [ ] **Step 5: Promote only after owner-approved Gate R2 evidence, verify NEW and rollback**

```bash
cd backend
HATCH_RUNTIME_JOB_SCORE_MODE=new python -m pytest -q --no-cov tests/runtime/test_job_score_task.py tests/runtime/test_job_score_migration.py tests/runtime/test_job_score_restart.py tests/test_agents/test_scorer_agent.py
HATCH_RUNTIME_JOB_SCORE_MODE=legacy python -m pytest -q --no-cov tests/runtime/test_job_score_migration.py
python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/runtime_bindings/tasks backend/app/runtime_bindings/migration/facade.py backend/app/runtime_bindings/migration/job_score.py backend/app/agents/scorer_agent.py backend/tests/runtime/test_job_score_task.py backend/tests/runtime/test_job_score_migration.py backend/tests/runtime/test_job_score_restart.py backend/tests/runtime/test_job_score_privacy.py backend/tests/test_agents/test_scorer_agent.py docs/implementation-reports/runtime/R5-job-score-migration.md
git commit -m "refactor(scorer): migrate job scoring to durable runtime"
```

---

### Task 13: R6 migrate CV Tailoring without unsupported claims or shadow artifacts

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r6-cv-tailor-migration
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime_bindings/tasks/cv_tailor.py`
- Create: `backend/app/runtime_bindings/migration/cv_tailor.py`
- Modify: `backend/app/services/tailor_service.py:311`
- Modify: `backend/app/services/cv_tailor.py`
- Modify: `backend/app/routers/tailor.py`
- Test: `backend/tests/runtime/test_cv_tailor_task.py`
- Test: `backend/tests/runtime/test_cv_tailor_migration.py`
- Test: `backend/tests/runtime/test_cv_tailor_grounding.py`
- Test: `backend/tests/runtime/test_cv_tailor_artifacts.py`
- Modify: `backend/tests/test_services/test_cv_tailor.py`
- Create: `docs/implementation-reports/runtime/R6-cv-tailor-migration.md`

**Interfaces:**
- Produces `CV_TAILOR_V1` with the six declared candidate/job context capabilities from §21.
- Produces deterministic validators for schema, required sections, artifact contract, and source-supported candidate claims.

- [ ] **Step 1: Write RED sparse-evidence, unsupported-claim, shadow-write, and rollback tests**

```python
async def test_shadow_cv_never_overwrites_visible_artifact(harness) -> None:
    legacy = await harness.generate(mode=RuntimeMode.SHADOW)
    assert await harness.visible_artifact_hash() == legacy.artifact_hash
    assert await harness.shadow_artifact_count() == 0

async def test_unsupported_candidate_claim_fails_before_artifact_commit(harness) -> None:
    result = await harness.generate(model_output=adds_invented_employer())
    assert result.code is ExecutionResultCode.VALIDATION_FAILURE
    assert await harness.visible_artifact_count() == 0
```

- [ ] **Step 2: Implement the runtime task and evaluation-only SHADOW path**

Reuse profile/resume/job providers from R4. Use deterministic validation before model repair; bound repair/fallback; only NEW may call the committing artifact adapter.

- [ ] **Step 3: Verify modes, long context, repair/fallback, artifact failure, privacy, and rollback**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_cv_tailor_task.py tests/runtime/test_cv_tailor_migration.py tests/runtime/test_cv_tailor_grounding.py tests/runtime/test_cv_tailor_artifacts.py tests/test_services/test_cv_tailor.py tests/test_routers/test_tailor_router.py tests/test_routers/test_tailor_async.py
```

- [ ] **Step 4: Commit after Gate R6 evidence/reviews**

```bash
git add backend/app/runtime_bindings/tasks/cv_tailor.py backend/app/runtime_bindings/migration/cv_tailor.py backend/app/services/tailor_service.py backend/app/services/cv_tailor.py backend/app/routers/tailor.py backend/tests/runtime/test_cv_tailor_task.py backend/tests/runtime/test_cv_tailor_migration.py backend/tests/runtime/test_cv_tailor_grounding.py backend/tests/runtime/test_cv_tailor_artifacts.py backend/tests/test_services/test_cv_tailor.py docs/implementation-reports/runtime/R6-cv-tailor-migration.md
git commit -m "refactor(tailor): migrate CV tailoring to durable runtime"
```

---

### Task 14: R7 migrate Cover Letter and prove shared generation infrastructure

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r7-cover-letter-migration
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime_bindings/tasks/cover_letter.py`
- Create: `backend/app/runtime_bindings/migration/cover_letter.py`
- Modify: `backend/app/services/tailor_service.py:395`
- Modify: `backend/app/routers/tailor.py:235`
- Test: `backend/tests/runtime/test_cover_letter_task.py`
- Test: `backend/tests/runtime/test_cover_letter_migration.py`
- Test: `backend/tests/runtime/test_cover_letter_contract.py`
- Modify: `backend/tests/test_routers/test_tailor_router.py`
- Create: `docs/implementation-reports/runtime/R7-cover-letter-migration.md`

**Interfaces:**
- Produces `COVER_LETTER_V1` (`task_id="cover_letter.generate"`, `version=1`) and reuses the R4 candidate/job providers, router, policy, gateway, and artifact adapter.
- Preserves current length/structure and generated-document result contracts.

- [ ] **Step 1: Write RED shared-provider, validation, shadow, and one-writer tests**

```python
def test_cover_letter_reuses_registered_candidate_context(task_spec) -> None:
    assert task_spec.context_requirements == COVER_LETTER_CONTEXT_REQUIREMENTS
    assert "cover_letter.candidate_context" not in CONTEXT_REGISTRY

async def test_shadow_cover_letter_has_no_visible_document(harness) -> None:
    result = await harness.generate(mode=RuntimeMode.SHADOW)
    assert result.authoritative_engine == "legacy"
    assert await harness.visible_document_count() == 1
```

- [ ] **Step 2: Implement mode dispatch and bounded validation/repair**

Do not duplicate candidate-context or routing logic. The legacy facade translates current `GeneratedDocumentRead`; runtime owns retries and evaluation.

- [ ] **Step 3: Run Gate R3**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_cover_letter_task.py tests/runtime/test_cover_letter_migration.py tests/runtime/test_cover_letter_contract.py tests/runtime/test_cv_tailor_migration.py tests/runtime/test_job_score_migration.py tests/test_routers/test_tailor_router.py tests/test_routers/test_tailor_async.py
python -m pytest -q
```

Expected report state: Job Scoring, CV Tailoring, and Cover Letter each verified in NEW; shared context/router/control/execution used; legacy rollback remains executable; no bespoke slice retry/router remains authoritative.

- [ ] **Step 4: Commit**

```bash
git add backend/app/runtime_bindings/tasks/cover_letter.py backend/app/runtime_bindings/migration/cover_letter.py backend/app/services/tailor_service.py backend/app/routers/tailor.py backend/tests/runtime/test_cover_letter_task.py backend/tests/runtime/test_cover_letter_migration.py backend/tests/runtime/test_cover_letter_contract.py backend/tests/test_routers/test_tailor_router.py docs/implementation-reports/runtime/R7-cover-letter-migration.md
git commit -m "refactor(tailor): migrate cover letters to shared runtime"
```

---

### Task 15: R8 extract generic Coach execution durability, preserving V6

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r8-coach-kernel-extraction
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `backend/app/runtime_bindings/migration/coach.py`
- Modify: `backend/app/services/async_job_service.py:36`
- Modify: `backend/app/services/coach_session_queue.py`
- Modify: `backend/app/services/coach_reconciliation.py:1561`
- Modify: `backend/app/repositories/conversational_session_repository.py:786`
- Modify: `backend/app/services/coach_attempt_pipeline.py`
- Modify: `backend/app/routers/coach.py`
- Test: `backend/tests/runtime/test_coach_kernel_adapter.py`
- Test: `backend/tests/runtime/test_coach_fencing.py`
- Test: `backend/tests/runtime/test_coach_restart.py`
- Test: `backend/tests/runtime/test_coach_mode_ownership.py`
- Modify: `backend/tests/test_services/test_async_job_service.py`
- Modify: `backend/tests/test_services/test_coach_reconciliation.py`
- Modify: relevant existing V6 acceptance/security tests selected by the traceability table
- Create: `docs/implementation-reports/runtime/R8-coach-kernel-extraction.md`

**Interfaces:**
- Produces `LegacyCoachRuntimeAdapter` and Coach runtime-mode dispatch.
- Maps existing job/session claim identity to `ExecutionClaim`, expiry to lease expiry, late completion guards to claim+fencing finalization, retry to a new `TaskAttempt`, and stale recovery to kernel reconciliation plus a Coach-owned domain transition.
- Keeps transcription, answer evaluation, rubric, session question state, report aggregation, retention/deletion/export behavior, and diagnostic schemas in Coach modules.

- [ ] **Step 1: Build the R8 V6 traceability map before code**

At minimum map generic extraction changes to V6 §§9, 21, 29, 30, 31, 35–38, 42–46 and AC-02/03/04/08/11/27/28/29/30/31. Record omitted negative/adversarial/replay/safe-failure classes with a concrete non-applicability reason.

- [ ] **Step 2: Write RED late-answer, late-report, retry, restart, and idempotent-recovery tests**

```python
async def test_late_coach_answer_worker_cannot_overwrite_newer_result(harness) -> None:
    old, new = await harness.two_answer_claims()
    assert await harness.finalize(new, result="new") is True
    assert await harness.finalize(old, result="old") is False
    assert await harness.authoritative_answer() == "new"

async def test_coach_restart_requires_no_asyncio_task_registry(harness) -> None:
    run_id = await harness.queue_answer_without_local_wakeup()
    harness.drop_process_objects()
    assert await harness.new_kernel().reconcile(run_id) == 1
```

- [ ] **Step 3: Implement the adapter with dual fencing**

Create the durable runtime run/step/attempt before any local wake-up. Finalization must match the generic claim/fencing token and the existing Coach processing generation/job/source/version/hash predicates. Do not weaken V6 domain fences merely because the generic fence passes.

- [ ] **Step 4: Route retries and reconciliation through the kernel**

Preserve existing safe conditional SQL and idempotent domain transitions. `AsyncJobService.run()` may remain as a compatibility wake-up, but recovery and finalization authority come from durable kernel records. Open a new session in every worker/reconciler.

- [ ] **Step 5: Run focused runtime plus binding Coach tests**

```bash
cd backend
python -m pytest -q --no-cov tests/runtime/test_coach_kernel_adapter.py tests/runtime/test_coach_fencing.py tests/runtime/test_coach_restart.py tests/runtime/test_coach_mode_ownership.py tests/test_services/test_async_job_service.py tests/test_services/test_coach_reconciliation.py tests/test_services/test_coach_session_queue.py tests/test_services/test_coach_attempt_pipeline.py
python -m pytest -q --no-cov tests/test_services/test_coach_conversation_commands.py tests/test_repositories/test_conversational_session_repository.py tests/test_routers/test_coach_conversation_router.py tests/test_observability/test_coach_runtime.py tests/test_observability/test_coach_failure_isolation.py
```

- [ ] **Step 6: Run V6 acceptance/security/restart/benchmark gates in isolated synthetic environments**

```bash
cd backend
python -m pytest -q --no-cov tests/benchmarks/coach/test_conversational_acceptance_smoke.py tests/benchmarks/coach/test_conversational_contract_smoke.py tests/benchmarks/coach/test_e2e_session.py tests/benchmarks/coach/test_observability.py
python -m pytest -q --no-cov tests/test_services/test_coach_retention.py tests/test_services/test_coach_media_storage.py tests/test_services/test_coach_evidence_grounder.py tests/test_routers/test_coach_conversation_capture.py
```

Scan captured errors/logs/spans/metrics for synthetic canaries and confirm deleted/transcript/evidence/media content is absent. Critical/high findings block merge; every medium receives an explicit owner/disposition.

- [ ] **Step 7: Verify LEGACY rollback, SHADOW no-commit rule, NEW ownership, and feature compatibility**

```bash
cd backend
HATCH_RUNTIME_COACH_MODE=legacy python -m pytest -q --no-cov tests/runtime/test_coach_mode_ownership.py tests/test_services/test_coach_reconciliation.py
HATCH_RUNTIME_COACH_MODE=shadow python -m pytest -q --no-cov tests/runtime/test_coach_mode_ownership.py
HATCH_RUNTIME_COACH_MODE=new python -m pytest -q --no-cov tests/runtime/test_coach_kernel_adapter.py tests/runtime/test_coach_fencing.py tests/runtime/test_coach_restart.py tests/runtime/test_coach_mode_ownership.py
```

- [ ] **Step 8: Run complete backend promotion suite**

```bash
cd backend
python -m pytest -q
```

Any newly introduced failure blocks R4.

- [ ] **Step 9: Obtain specification-compliance review, then code-quality/security review, and commit**

```bash
git add backend/app/runtime_bindings/migration/coach.py backend/app/services/async_job_service.py backend/app/services/coach_session_queue.py backend/app/services/coach_reconciliation.py backend/app/repositories/conversational_session_repository.py backend/app/services/coach_attempt_pipeline.py backend/app/routers/coach.py backend/tests/runtime/test_coach_kernel_adapter.py backend/tests/runtime/test_coach_fencing.py backend/tests/runtime/test_coach_restart.py backend/tests/runtime/test_coach_mode_ownership.py backend/tests/test_services/test_async_job_service.py backend/tests/test_services/test_coach_reconciliation.py docs/implementation-reports/runtime/R8-coach-kernel-extraction.md
git commit -m "refactor(coach): move execution durability to runtime kernel"
```

---

### Task 16: R9 full R4 verification, evidence report, and cleanup eligibility decision

**PR start gate:**
```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c runtime/r9-r4-verification-cleanup
git merge-base --is-ancestor origin/main HEAD
```

PR base: `main`. Do not start this branch until the predecessor PR has merged.


**Files:**
- Create: `docs/implementation-reports/Hatch_Architecture_Foundation_R4_Report.md`
- Modify: no runtime/product code in the baseline R9 plan; cleanup candidates are inventoried for a separately reviewed bounded plan after explicit owner approval.
- Test: affected existing tests plus complete backend suite.

**Interfaces:**
- Produces the final gate verdict, residual-risk list, retained legacy-path inventory, and explicit `Coach Phase 2 gate = PASS` or `FAIL`.
- Removes no historical schema and no compatibility facade still used by a caller or rollback mode.

- [ ] **Step 1: Recompute baseline, authority hashes, PR SHAs, migration head, and mode state**

```bash
git rev-parse HEAD
git log --oneline --decorate -20
sha256sum docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md
cd backend && alembic heads && alembic current --check-heads
```

- [ ] **Step 2: Run the complete repository verification matrix**

```bash
python scripts/check_docs.py
cd backend
python -m pytest -q
ruff check app/ tests/
alembic heads
cd ../frontend
npm run type-check
npm test -- --run
npm run build
cd ..
make ci
```

Record exact exit status/counts and artifact paths. If the full suite is too long for one CI job, preserve the same test set in named shards and record every shard; do not replace it with sampling.

- [ ] **Step 3: Prove all four gates and every invariant**

The final report contains:

```text
baseline SHA and PR SHAs
architecture/V6 hashes
Gates R1, R2, R3, R4 with evidence links
all invariant IDs with test names
migration modes and rollback results
golden/semantic comparison results
latency/cost comparison
failure-injection matrix results
privacy leakage scan and cleanup result
Coach V6 acceptance/security/benchmark verdict
known residual risks and owners
legacy paths remaining and why
PostgreSQL trigger metrics/status
Coach Phase 2 gate = PASS or FAIL
```

- [ ] **Step 4: Identify cleanup candidates with read-only evidence**

```bash
rg -n "LegacyAIRuntimeFacade|LegacyCoachRuntimeAdapter|HATCH_RUNTIME_.*_MODE|AsyncJobService\.run|EventBus|retry|reconcile" backend/app backend/tests
python scripts/dead_code_check.py
```

Delete only code approved for retirement and proven unused by NEW slices and required rollback/legacy callers. Keep legacy schemas needed for historical data.

- [ ] **Step 5: Record the cleanup decision without deleting compatibility code**

The R4 report classifies every candidate as `retain`, `eligible for a separately approved cleanup plan`, or `not actually dead`. This plan deliberately performs no deletion because exact safe paths depend on post-R8 call-site evidence and owner approval; a later cleanup request must name those files and their rollback consequences.

- [ ] **Step 6: Commit the final evidence report**

```bash
git add docs/implementation-reports/Hatch_Architecture_Foundation_R4_Report.md
git commit -m "docs(runtime): record architecture foundation R4 evidence"
```

---

## Final self-review and handoff gates

Before declaring the foundation complete:

- [ ] Every architecture requirement in §§0–32 maps to a task, invariant test, or explicit non-goal.
- [ ] All 36 binding architecture invariants have executed evidence; INV-DB-002 and INV-MIG-001/002/003 are included even though they are not repeated in every PR gate list.
- [ ] All ten failure-injection rows have deterministic tests with no long sleeps.
- [ ] Runtime imports obey the allowed dependency direction and no product router is imported by `backend/app/runtime/`.
- [ ] `alembic heads` returns one head and supported upgrade/fresh-install/downgrade paths are evidenced.
- [ ] Each mode resolves once; SHADOW makes no committing side effect; running workflows never switch engines.
- [ ] Each worker uses its own session and no write transaction spans an LLM/network/artifact call.
- [ ] Sensitive canaries are absent from events, outbox records, logs, traces, metrics, policy/routing/evaluation metadata, errors, diagnostics, and evidence artifacts.
- [ ] Job Scoring, CV Tailoring, and Cover Letter are verified in NEW with rollback evidence.
- [ ] Coach generic durability is kernel-owned while V6 product/domain contracts and AC-01–AC-32 remain green.
- [ ] Specification-compliance and code-quality/security reviews are recorded separately for every PR.
- [ ] The R4 report says PASS only when Gates R1–R4 all have captured evidence; otherwise it says FAIL and lists the blocking contract, evidence, owner, and next action.

## Invariant-to-task coverage index

This index contains all 36 canonical invariant IDs from spec v2.

| Invariant | Proved in task/test |
|---|---|
| `INV-CTR-001` | Task 2 — `test_task_spec.py` |
| `INV-DB-001` | Task 4 — `test_event_atomicity.py` |
| `INV-DB-002` | Task 3 — `test_storage_contract.py` proves retry rows cannot collapse prior attempts |
| `INV-WF-001` | Task 5 — `test_fencing.py` |
| `INV-WF-002` | Task 5 — `test_retries.py` |
| `INV-WF-003` | Task 5 — `test_runtime_restart_recovery.py` |
| `INV-WF-004` | Task 6 — `test_waiting.py` |
| `INV-APP-001` | Task 6 — `test_approvals.py` |
| `INV-CTL-001` | Task 7 — `test_policy_precedence.py` |
| `INV-CTL-002` | Task 7 — `test_policy_precedence.py` |
| `INV-CTL-003` | Tasks 7 and 10 — `test_policy_force_model.py`, `test_model_router.py` |
| `INV-CTX-001` | Task 9 — `test_context_resolver.py` |
| `INV-CTX-002` | Task 9 — `test_context_immutability.py` |
| `INV-CTX-003` | Task 9 — `test_context_privacy.py` |
| `INV-RTR-001` | Task 10 — `test_model_router.py` |
| `INV-RTR-002` | Task 10 — `test_router_candidate_snapshot.py` |
| `INV-RTR-003` | Task 10 — `test_evidence_promotion.py` |
| `INV-EXE-001` | Task 8 — `test_execution_gateway.py` |
| `INV-EXE-002` | Task 8 — `test_side_effect_authorization.py` |
| `INV-EXE-003` | Task 8 — `test_outcome_unknown.py` |
| `INV-EXE-004` | Tasks 5 and 8 — `test_fencing.py`, `test_execution_gateway.py` |
| `INV-EVT-001` | Task 4 — `test_event_atomicity.py` |
| `INV-EVT-002` | Task 4 — `test_outbox_store.py` proves both append-only delivery attempts (§16) and harmless duplicate delivery (§25) |
| `INV-EVL-001` | Task 11 — `test_evaluation_service.py` |
| `INV-OBS-001` | Task 11 — `test_otel_export_failure.py` |
| `INV-OBS-002` | Task 11 — `test_otel_correlation.py` |
| `INV-PRV-001` | Tasks 4, 9, and 11 — runtime/event/context/telemetry canary tests |
| `INV-MIG-001` | Tasks 12–15 — each `test_*_migration.py` / Coach ownership test |
| `INV-MIG-002` | Tasks 12–15 — shadow no-visible-write/no-commit tests |
| `INV-MIG-003` | Tasks 2 and 12–15 — mode snapshot plus mid-flight configuration-change tests |
| `INV-COACH-001` | Task 15 — `test_coach_fencing.py` answer finalizer case |
| `INV-COACH-002` | Task 15 — `test_coach_fencing.py` report finalizer case |
| `INV-COACH-003` | Task 15 — `test_coach_retry_creates_generic_new_attempt` |
| `INV-COACH-004` | Task 15 — `test_coach_restart_requires_no_asyncio_task_registry` |
| `INV-COACH-005` | Task 15 — `test_coach_stale_claim_recovery_is_idempotent` |
| `INV-COACH-006` | Task 15 — `test_coach_v6_acceptance_regression_gate` |

The architecture spec uses `INV-EVT-002` for two compatible obligations in §§16 and 25; Task 4 must test both. It also introduces `INV-DB-002` and `INV-EXE-004` in PR-specific sections even though the compact §25 registry omits them; this plan treats both as binding rather than silently dropping them.
