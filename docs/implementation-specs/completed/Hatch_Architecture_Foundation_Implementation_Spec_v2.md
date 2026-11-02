---
title: Hatch Architecture Foundation Implementation Specification v2
document_type: implementation-spec
status: active
implementation_status: partial
applies_to: main/latest
architecture_baseline: docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md
last_verified: 2026-08-24
target_repository: https://github.com/arvindsoni2/hatch
approval_status: approved-for-implementation
---

# Hatch architecture foundation implementation specification v2.0

> **For agentic workers:** implement this specification task-by-task with TDD. Do not reopen approved architecture decisions unless repository evidence makes an approved contract impossible or unsafe. Record any such blocker before changing the architecture.

**Goal:** Implement the approved Hatch runtime foundation, prove it through job scoring, migrate CV tailoring and cover-letter generation, extract Coach Phase 1 durability/reconciliation into the generic kernel, and satisfy the R4 gate before Coach Phase 2 implementation.

**Architecture:** Four planes around a typed `TaskSpec`, a deterministic Control Plane, dynamic Context Plane, evidence-aware Intelligence Plane, typed Execution Gateway, relational durable Workflow Kernel, transactional event/outbox model, and runtime-native evaluation/observability. Migration uses a strangler pattern with per-slice `LEGACY`, `SHADOW`, and `NEW` modes.

**Tech stack:** Python 3.x, FastAPI, Pydantic v2, async SQLAlchemy, Alembic, SQLite/WAL initially, PostgreSQL-compatible durable-store semantics, OpenTelemetry, pytest, existing Hatch frontend/Next.js only where migration controls or status UI require it.

**Architecture source of truth:** `docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md`

**Canonical repository path for this specification:**

```text
docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md
```

---

# 0. Document control and implementation baseline

## 0.0 Approval and authority state

The architecture design is formally approved through `ARCH-12`, including `ARCH-06R1`. The approved authority is:

```text
docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md
```

The implementation specification has a separate approval state. Repository front matter uses
`status: active` and `implementation_status: partial` because those are validator-supported
document lifecycle values; they do **not** themselves authorize implementation.

Before any runtime implementation code, the owner must explicitly approve this document with:

```text
SPEC-v2 approved for implementation
```

After that approval, change only the extra metadata field:

```yaml
approval_status: approved-for-implementation
```

No architecture decision is reopened by that metadata change.

R0 must copy the exact approved architecture file into the repository, record its SHA-256 in
`R0-evidence.md`, and verify that the file's decision ledger says `ARCH-00` through `ARCH-12`
are approved. Do not reconstruct that authority from this implementation specification or plan.


## 0.1 Architecture authority

This specification implements the approved architecture decisions:

```text
ARCH-00   Foundation + critical vertical slices
ARCH-01   TaskSpec
ARCH-02   Context Plane
ARCH-03   Intelligence Plane
ARCH-04   Evaluation + Observability
ARCH-05   Control Plane
ARCH-06   Durable Workflow Kernel
ARCH-06R1 Relational durable-state contract
ARCH-07   Execution Gateway
ARCH-08   Events + Durable Outbox
ARCH-09   Durable decision/eval records + OpenTelemetry
ARCH-10   Strangler migration
ARCH-11   Named invariant suite + deterministic failure injection
ARCH-12   Gated implementation + Coach Phase 2 R4 boundary
```

If implementation pressure conflicts with one of these decisions, the implementer must stop that affected task and report:

```text
architecture decision
repository evidence
why the contract is blocked
minimum viable alternative
migration consequence
```

Do not silently weaken an invariant.

## 0.2 Repository baseline verified during specification preparation

The repository was inspected on `main` on 20 August 2026.

Latest observed `main` commit:

```text
ed366775d41f9e64c3ed7a1163e8f958d0ddaa2e
```

Commit message:

```text
Merge pull request #59 from arvindsoni2/feature/coach-phase1-phase2

feat(coach): promote Phase 1 conversational interview coach
```

This commit is a **design-evidence baseline**, not a permanently pinned implementation SHA.

Before implementation begins, Codex must run:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git status --short
python scripts/check_docs.py
```

The **first** documentation check is a baseline observation. If the known preflight documentation
errors are present, record the non-zero result as expected RED evidence; do not pretend it passed.
R0 repairs the documentation authority/metadata issues, deletes untracked obsolete Coach copies,
and then reruns `python scripts/check_docs.py`. Only the **post-repair** check must exit 0.

Required result before R1:

- implementation specification has explicit owner approval;
- approved architecture authority is tracked at the canonical path and its SHA-256 is recorded;
- working tree scope is understood and unrelated changes are not staged;
- post-repair documentation check passes;
- implementation summary records the exact full `HEAD`;
- if `HEAD` differs from the design-evidence baseline, perform the drift checks in §0.4.

## 0.3 Existing repository seams verified

The current repository already contains useful migration seams:

```text
backend/app/database.py
backend/app/services/agent_orchestrator.py
backend/app/services/async_job_service.py
backend/app/services/coach_reconciliation.py
backend/app/agents/scorer_agent.py
backend/app/agents/tailor_agent.py
backend/app/agents/tools/event_bus.py
backend/app/agents/tools/llm_factory.py
backend/app/agents/tools/context_budgets.py
backend/app/agents/tools/context_checker.py
backend/app/observability/*
backend/app/models/*
backend/app/repositories/*
backend/alembic/versions/*
backend/tests/*
```

The current design has:

- async SQLAlchemy with SQLite WAL, `busy_timeout`, foreign keys, and short-lived sessions;
- an in-process `AgentOrchestrator` using APScheduler and a supervisor `asyncio.Task`;
- a `ScorerAgent` that selects current triage/primary models directly through `llm_factory`;
- a legacy event bus;
- `AsyncJobService` with persisted job state but fire-and-forget `asyncio.create_task`;
- extensive Coach reconciliation code with conditional SQL updates and recovery semantics;
- existing OpenTelemetry support.

The new runtime must **extract and reuse useful semantics**, not wrap these legacy mechanisms as permanent second-class runtimes.

## 0.4 Mandatory drift check

If implementation `HEAD` differs from the baseline above, inspect at minimum:

```bash
git log --oneline ed366775..HEAD -- \
  backend/app/database.py \
  backend/app/services/agent_orchestrator.py \
  backend/app/services/async_job_service.py \
  backend/app/services/coach_reconciliation.py \
  backend/app/agents/scorer_agent.py \
  backend/app/agents/tailor_agent.py \
  backend/app/agents/tools \
  backend/app/observability \
  backend/app/models \
  backend/app/repositories \
  backend/alembic/versions \
  backend/tests
```

Record material drift before starting PR R1.

A change is material if it affects:

```text
database/session semantics
async job ownership
claim/retry/reconciliation behavior
model selection
context construction
event publication
OpenTelemetry
job scoring
CV/cover-letter generation
Coach answer/report processing
```

## 0.5 Documentation placement

Before implementation code:

1. place this specification at its canonical active path;
2. add it to `docs/README.md` under active implementation work;
3. preserve the final architecture document under the appropriate design/architecture documentation location;
4. run `python scripts/check_docs.py`;
5. commit the documentation-only preflight separately.

---

# 1. Global implementation constraints

These constraints apply to every PR and every task.

## 1.1 Architecture constraints

- No wholesale rewrite.
- No OpenAI Agents SDK/ADK/LangGraph migration.
- No Temporal, Celery, Redis, Kafka, microservices, or Kubernetes.
- MCP remains an optional adapter, not Hatch's internal RPC mechanism.
- SQLite/WAL remains the default backend.
- PostgreSQL compatibility is designed through semantic store contracts; production PostgreSQL support is not required before Coach Phase 2.
- Models may request actions; models never authorize them.
- External committing side effects remain separated from preparation.
- Production observations never directly self-modify routing behavior.
- `asyncio.Task` state is never authoritative for recovery.

## 1.2 Engineering constraints

- TDD for each new invariant and behavior.
- Prefer additive migrations.
- No destructive legacy schema cleanup before slice retirement.
- Preserve existing public API behavior unless the migration mode intentionally changes ownership.
- Avoid generic repository abstractions unrelated to durable-runtime semantics.
- No broad refactor of unrelated agents.
- Keep runtime files focused; split by responsibility.
- Add dependencies only when repository-native libraries cannot satisfy an approved contract.
- All persistent timestamps use one repository-consistent UTC convention.
- JSON payload columns remain bounded and structured; raw prompts/CVs/model outputs are not duplicated into telemetry/event tables by default.

## 1.3 Migration modes

Canonical enum:

```python
class RuntimeMode(str, Enum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    NEW = "new"
```

Required initial configuration keys:

```text
HATCH_RUNTIME_JOB_SCORE_MODE
HATCH_RUNTIME_CV_TAILOR_MODE
HATCH_RUNTIME_COVER_LETTER_MODE
HATCH_RUNTIME_COACH_MODE
```

Default for all existing installations:

```text
LEGACY
```

Mode is resolved once at the slice entry boundary.

A running new-runtime `WorkflowRun` never changes engine mid-flight.

## 1.4 Naming convention

Runtime-owned public identifiers use stable strings:

```text
task_id
workflow_definition_id
capability_id
validator_id
evaluation_spec_id
model_id
```

Each has an explicit version where semantic behavior can change.

Database IDs should follow existing Hatch ID conventions unless a reviewed reason requires otherwise.

---

# 1.4 Implementation decisions resolved after Codex review

The following implementation decisions are now binding and do not require further inference:

1. **Coach condensed v1:** delete any untracked local condensed Phase 1 v1 copy. Do not relocate,
   track, or treat it as authority. The tracked V6 Phase 1 implementation specification remains
   authoritative for Coach Phase 1.
2. **PR topology:** all R0-R9 pull requests target `main`. Each branch starts only after its
   predecessor merges, from freshly fast-forwarded `main`. No long-lived integration branch.
3. **Plan tracking:** the implementation plan is tracked at
   `docs/implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md`;
   do not use the ignored `docs/superpowers/` location as repository authority.
4. **Product bindings:** generic runtime remains product-independent. Product `TaskSpec`
   definitions and concrete product context/capability/migration bindings live under
   `backend/app/runtime_bindings/`.
5. **Shadow retention:** structured shadow comparison metadata is retained for 30 days.
   Persisted shadow comparisons never contain raw model-generated text or artifacts.
6. **Capture policy:** `DEBUG_CONTENT` remains an architectural enum value but is test/local
   developer-only in this foundation. Normal deployment configuration cannot enable it.
7. **R2 promotion:** objective quality, latency, cost, reliability, privacy and owner-approval
   thresholds in §20 are mandatory before Job Scoring becomes `NEW`.

---

# 2. Target code structure

The generic runtime core is product-independent:

```text
backend/app/runtime/
    __init__.py

    contracts/
        __init__.py
        ids.py
        task_spec.py
        enums.py
        errors.py
        capture.py

    storage/
        __init__.py
        contracts.py
        uow.py
        sqlite.py

    workflow/
        __init__.py
        models.py
        repository.py
        kernel.py
        claims.py
        retry.py
        approvals.py
        reconciliation.py

    control/
        __init__.py
        models.py
        policy.py
        budgets.py

    context/
        __init__.py
        models.py
        registry.py
        resolver.py

    intelligence/
        __init__.py
        models.py
        registry.py
        router.py
        evidence.py

    execution/
        __init__.py
        models.py
        registry.py
        gateway.py
        adapters/
            __init__.py
            llm.py
            native.py
            artifact.py

    events/
        __init__.py
        models.py
        repository.py
        outbox.py

    evaluation/
        __init__.py
        models.py
        validators.py
        service.py
        evidence.py

    observability/
        __init__.py
        tracing.py
        attributes.py

    migration/
        __init__.py
        modes.py
```

Product bindings live outside the runtime core:

```text
backend/app/runtime_bindings/
    __init__.py

    tasks/
        __init__.py
        job_score.py
        cv_tailor.py
        cover_letter.py
        coach.py

    context/
        __init__.py
        profile.py
        resume.py
        job.py
        application.py
        coach.py

    capabilities/
        __init__.py
        job_score.py
        artifacts.py
        coach.py

    migration/
        __init__.py
        facade.py
        job_score.py
        cv_tailor.py
        cover_letter.py
        coach.py
```

Dependency direction:

```text
product routers/services/agents
        ↓
runtime_bindings
        ↓
runtime public contracts/services
```

Rules:

- `backend/app/runtime/` must not import `backend/app/routers`, product agents, Coach services,
  resume stores, job models, or other product-domain modules.
- `runtime_bindings` may import both runtime contracts and existing product/infrastructure code.
- generic execution adapters may depend on provider/infrastructure libraries but not product domains;
  product-specific capabilities belong in `runtime_bindings/capabilities`.
- generic context resolver/registry never imports concrete product providers;
  product providers register from `runtime_bindings/context`.
- product TaskSpecs are composed in `runtime_bindings/tasks`, never under `runtime/tasks`.
- enforce these rules with an import-boundary test.

---

# 3. Core contract definitions

## 3.1 Runtime identifiers

Create typed aliases/wrappers for:

```text
WorkflowRunId
WorkflowStepId
TaskAttemptId
ExecutionId
PolicyDecisionId
RoutingDecisionId
ContextPackageId
EventId
OutboxEntryId
ApprovalId
```

The implementation may use UUID strings internally, but public function signatures must not accept arbitrary mixed identifiers without semantic naming.

## 3.2 TaskSpec

Required immutable contract:

```python
@dataclass(frozen=True)
class TaskSpec(Generic[InputT, OutputT]):
    task_id: str
    version: int
    input_model: type[InputT]
    output_model: type[OutputT]
    context_requirements: tuple[ContextRequirement, ...]
    model_requirements: ModelCapabilityRequirements
    risk_class: RiskClass
    validators: tuple[str, ...]
    evaluation_policy: EvaluationPolicy
    execution_strategy: ExecutionStrategy
    workflow_policy: WorkflowPolicy
```

Initial `ExecutionStrategy` values:

```text
SINGLE_PASS
VALIDATE_AND_REPAIR
FALLBACK_ON_FAILURE
```

Operational preferences are passed separately as runtime policy/configuration; they do not mutate `TaskSpec`.

## 3.3 Common result taxonomy

Canonical execution result codes:

```text
SUCCESS
VALIDATION_FAILURE
POLICY_DENIED
TIMEOUT
CANCELLED
TRANSIENT_FAILURE
PERMANENT_FAILURE
OUTCOME_UNKNOWN
```

These are persisted as strings/enums and may be mapped to product-specific error contracts at the facade boundary.

---

# 4. Durable-state schema

Implement through additive Alembic migrations and SQLAlchemy models.

All status values below are canonical persisted values for v1 runtime schema.

## 4.1 Status vocabularies

```text
WorkflowRunStatus:
PENDING | RUNNING | WAITING | COMPLETED | FAILED | CANCELLED

WorkflowStepStatus:
PENDING | RUNNING | WAITING | COMPLETED | FAILED | CANCELLED

TaskAttemptStatus:
PENDING | RUNNING | WAITING | SUCCEEDED | FAILED | CANCELLED | OUTCOME_UNKNOWN

ExecutionClaimStatus:
ACTIVE | RELEASED | EXPIRED | SUPERSEDED

WaitingReason:
APPROVAL | USER_INPUT | RETRY_TIME
```

A retry with a future `not_before` creates a new attempt in `WAITING/RETRY_TIME`.
A due-retry promotion transaction moves it to `PENDING`; workers never sleep for durable backoff.

## 4.2 `runtime_workflow_runs`

```text
id
workflow_definition_id
workflow_definition_version
domain_type
domain_id nullable
status
runtime_mode
created_at
updated_at
completed_at nullable
input_ref_json nullable
result_ref_json nullable
failure_code nullable
trace_id nullable
```

## 4.3 `runtime_workflow_steps`

```text
id
workflow_run_id FK
step_key
step_order
task_id
task_version
status
waiting_reason nullable
created_at
updated_at
completed_at nullable
failure_code nullable
```

Unique:

```text
(workflow_run_id, step_key)
```

## 4.4 `runtime_task_attempts`

```text
id
workflow_step_id FK
attempt_number
prior_attempt_id nullable
status
waiting_reason nullable
not_before nullable
retry_reason nullable
retry_policy_id nullable
retry_policy_version nullable
claim_fencing_token BIGINT NOT NULL DEFAULT 0
current_claim_id nullable
context_package_id nullable
result_ref_json nullable
failure_code nullable
started_at nullable
finished_at nullable
created_at
updated_at
```

Unique:

```text
(workflow_step_id, attempt_number)
```

Retry rules:

- prior attempt remains terminal immutable history;
- attempt N+1 points to N via `prior_attempt_id`;
- retry policy identity and reason are stored on N+1;
- retry wait is durable via `WAITING/RETRY_TIME` plus `not_before`.

## 4.5 `runtime_execution_claims`

Use `id` as the canonical `claim_id`.

```text
id
task_attempt_id FK
fencing_token BIGINT
claimed_by
claimed_at
lease_expires_at
released_at nullable
status
```

Unique:

```text
(task_attempt_id, fencing_token)
```

Fencing allocation contract:

1. in one write transaction, verify the attempt is claimable;
2. atomically increment `runtime_task_attempts.claim_fencing_token`;
3. create the new claim with the returned token;
4. set `current_claim_id` to the new claim;
5. mark any previously ACTIVE claim for the same attempt `SUPERSEDED`;
6. commit.

Finalization must condition on:

```text
task_attempt_id
TaskAttemptStatus.RUNNING
current_claim_id
claim_fencing_token
ExecutionClaimStatus.ACTIVE
```

A zero-row conditional finalization means ownership was lost; the result is discarded.

## 4.6 `runtime_approvals`

```text
id
workflow_run_id FK
workflow_step_id nullable
task_attempt_id nullable
capability_id
payload_hash
payload_hash_algorithm
status
requested_at
decided_at nullable
decided_by nullable
expires_at nullable
decision_reason nullable
```

Statuses:

```text
PENDING | APPROVED | DENIED | EXPIRED | INVALIDATED
```

## 4.7 `runtime_events`

```text
id
event_type
event_version
aggregate_type
aggregate_id
workflow_run_id nullable
workflow_step_id nullable
task_attempt_id nullable
actor_type
actor_id nullable
occurred_at
payload_json
metadata_json nullable
trace_id nullable
correlation_id nullable
causation_event_id nullable
sensitivity
```

Actor values:

```text
USER | SYSTEM | WORKER | MODEL | CAPABILITY | RECONCILER
```

## 4.8 `runtime_outbox`

```text
id
event_id FK
destination
status
not_before
claim_id nullable
fencing_token BIGINT NOT NULL DEFAULT 0
lease_expires_at nullable
delivered_at nullable
created_at
updated_at
```

Statuses:

```text
PENDING | CLAIMED | RETRY_WAIT | DELIVERED | DEAD_LETTER
```

## 4.9 `runtime_outbox_attempts`

```text
id
outbox_entry_id FK
attempt_number
started_at
finished_at nullable
result
error_code nullable
error_detail nullable
```

Unique:

```text
(outbox_entry_id, attempt_number)
```

Delivery attempt history is append-only.

## 4.10 ARCH-09 decision and evaluation tables

Create:

```text
runtime_policy_decisions
runtime_routing_decisions
runtime_execution_records
runtime_validation_results
runtime_evaluation_runs
runtime_evidence_observations
runtime_model_evidence
```

`runtime_execution_records` has this minimum schema:

```text
id                         # execution_id
task_attempt_id FK
parent_execution_id nullable FK -> runtime_execution_records.id
execution_role
capability_id
capability_version
model_id nullable
model_version nullable
provider nullable
strategy_stage nullable
started_at
finished_at nullable
result_class
input_tokens nullable
output_tokens nullable
cost_usd nullable
latency_ms nullable
trace_id nullable
span_id nullable
metadata_json nullable
```

Execution roles:

```text
PRIMARY | REPAIR | FALLBACK | EVALUATOR | TOOL | ARTIFACT | RECONCILIATION
```

## 4.11 Context package persistence

```text
runtime_context_packages
    id
    task_attempt_id
    package_version
    content_hash
    token_estimate
    sensitivity_max
    resolved_at
    items_json
```

Persist references/metadata rather than a second raw-content lake.

## 4.12 Shadow comparison records

Create:

```text
runtime_shadow_comparisons
    id
    slice_name
    domain_type
    domain_id_hash
    legacy_execution_ref nullable
    runtime_execution_id nullable
    legacy_result_hash
    runtime_result_hash
    comparison_status
    metrics_json
    created_at
    expires_at
```

Rules:

- `expires_at = created_at + 30 days`;
- purge expired records at startup and by a daily best-effort maintenance job;
- no raw legacy output, raw runtime model output, CV text, job-description text, prompt,
  transcript, or generated artifact may be stored in this table;
- compare in memory and persist only derived metrics, stable reason codes, hashes and references;
- `DEBUG_CONTENT` does not weaken this shadow-table rule.

---

# 5. Durable store and unit-of-work contract

## 5.1 Runtime unit of work

State/event/outbox atomicity is implemented through one explicit transaction-scoped repository family.

```python
class RuntimeUnitOfWork(Protocol):
    workflows: WorkflowStore
    approvals: ApprovalStore
    events: EventStore
    outbox: OutboxStore
    evaluations: EvaluationStore
    shadow: ShadowComparisonStore

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

class RuntimeUnitOfWorkFactory(Protocol):
    def transaction(self) -> AsyncContextManager[RuntimeUnitOfWork]: ...
```

Repository objects exposed by one UoW are bound to the **same `AsyncSession` and transaction**.
Repositories never call `commit()` internally.

Usage:

```python
async with uow_factory.transaction() as uow:
    await uow.workflows.transition(...)
    event = await uow.events.append(...)
    await uow.outbox.enqueue(event.id, destination="runtime.evaluation")
    await uow.commit()
```

If any operation raises before commit, the context manager rolls back the whole transaction.

Long-running LLM/network/artifact calls are never made inside a runtime UoW transaction:

```text
UoW claim transaction
    ↓ commit/close
external/model execution
    ↓
new UoW finalization + event/outbox transaction
```

## 5.2 Public semantic store operations

```python
class WorkflowStore(Protocol):
    async def create_run(...) -> WorkflowRunRecord: ...
    async def create_step(...) -> WorkflowStepRecord: ...
    async def create_attempt(...) -> TaskAttemptRecord: ...
    async def claim_attempt(...) -> ExecutionClaimRecord | None: ...
    async def renew_claim(...) -> bool: ...
    async def finalize_attempt(...) -> bool: ...
    async def schedule_retry(...) -> TaskAttemptRecord: ...
    async def promote_due_retries(...) -> int: ...
    async def transition_waiting(...) -> bool: ...
    async def resume_waiting(...) -> TaskAttemptRecord: ...

class ApprovalStore(Protocol):
    async def request(...) -> ApprovalRecord: ...
    async def decide(...) -> bool: ...
    async def invalidate_for_payload_change(...) -> int: ...

class EventStore(Protocol):
    async def append(...) -> RuntimeEventRecord: ...

class OutboxStore(Protocol):
    async def enqueue(...) -> OutboxEntryRecord: ...
    async def claim_next(...) -> OutboxClaim | None: ...
    async def finalize_delivery(...) -> bool: ...

class EvaluationStore(Protocol):
    async def record_policy_decision(...) -> PolicyDecisionRecord: ...
    async def record_routing_decision(...) -> RoutingDecisionRecord: ...
    async def record_execution(...) -> ExecutionRecord: ...
    async def record_validation(...) -> ValidationResultRecord: ...
    async def record_evaluation(...) -> EvaluationRunRecord: ...
    async def record_observation(...) -> EvidenceObservationRecord: ...

class ShadowComparisonStore(Protocol):
    async def record(...) -> ShadowComparisonRecord: ...
    async def purge_expired(...) -> int: ...
```

## 5.3 SQLite implementation

Use existing async SQLAlchemy and SQLite WAL configuration.

SQLite-specific code may use short transactions, conditional `UPDATE`, `RETURNING` where
supported, unique constraints, busy-timeout behavior and fencing comparisons.

Do not hold a write transaction across an LLM/network/artifact call.

## 5.4 PostgreSQL seam

Production PostgreSQL is not required in this foundation.

Required now:

- public store/UoW semantics contain no SQLite-only contract;
- conformance tests are backend-parameterizable;
- ORM types avoid gratuitous SQLite-only behavior;
- future PostgreSQL implementation can use row locks/`SKIP LOCKED` without changing workflow APIs.

---

# 6. Workflow Kernel

## 6.1 Claim algorithm

A worker may execute a task only after a successful durable claim.

Required flow:

```text
PENDING attempt
    ↓
atomic claim
    ↓
RUNNING with claim + fencing token
    ↓
execute outside write transaction
    ↓
conditional finalization
```

Finalization condition includes:

```text
attempt id
expected attempt state
current claim id
current fencing token
```

If rowcount is zero, the worker lost ownership and must discard its late result.

## 6.2 Lease behavior

Lease expiry identifies potentially abandoned work.

Lease expiry alone does not authorize an old worker to finalize.

A reconciler/new claimant advances ownership through a new fencing token.

## 6.3 Retry behavior

Retry creates:

```text
attempt N = terminal history
attempt N+1 = PENDING
```

Persist:

```text
not_before
retry_reason
retry_policy_id/version
```

Workers never `sleep()` to implement durable backoff.

## 6.4 Waiting

Supported waiting reasons:

```text
APPROVAL
USER_INPUT
RETRY_TIME
```

Waiting owns no worker claim.

Resume always creates/acquires a fresh claimable execution context.

## 6.5 Reconciliation

Generic reconciler responsibilities:

- expire abandoned claims;
- preserve fencing;
- classify retryable/terminal cases;
- transition `OUTCOME_UNKNOWN` to capability-specific reconciliation;
- create a new attempt only when policy permits;
- never blindly replay `NON_RETRYABLE_SIDE_EFFECT`.

---

# 7. Control Plane

## 7.1 Policy precedence

Implement exactly:

```text
1. System invariants
2. TaskSpec requirements
3. Security/privacy policy
4. Workflow policy
5. User configuration
6. Routing preferences
```

## 7.2 Result model

```python
class PolicyDecision(BaseModel):
    decision: Literal["ALLOW", "DENY", "REQUIRE_APPROVAL"]
    reason_codes: list[str]
    effective_constraints: EffectiveConstraints
```

`EffectiveConstraints` initially includes:

```text
allowed_providers
allowed_models
allowed_capabilities
max_cost
max_input_tokens
max_output_tokens
deadline
max_retries
max_repairs
data_egress
approval_required
audit_level
capture_policy
```

## 7.3 Approval hash

Use deterministic canonical serialization of the committing capability payload and hash that representation.

The hash algorithm must be explicit and versioned.

Suggested initial value:

```text
sha256(canonical_json(payload))
```

Canonical JSON must use deterministic key ordering and encoding.

---

# 8. Execution Gateway

## 8.1 Capability descriptor

```python
class CapabilityDescriptor(BaseModel):
    capability_id: str
    version: int
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    side_effect_class: SideEffectClass
    idempotency_class: IdempotencyClass
    required_permissions: tuple[str, ...]
    default_timeout_seconds: float | None
```

Side-effect classes:

```text
PURE
READ_ONLY_EXTERNAL
PREPARE_SIDE_EFFECT
COMMIT_SIDE_EFFECT
ARTIFACT_GENERATION
```

Idempotency classes:

```text
IDEMPOTENT
IDEMPOTENT_WITH_KEY
CHECK_BEFORE_RETRY
NON_RETRYABLE_SIDE_EFFECT
```

## 8.2 Gateway order

```text
resolve capability
    ↓
Control Plane authorization
    ↓
approval verification if required
    ↓
deadline/budget setup
    ↓
invoke adapter
    ↓
typed result classification
    ↓
durable execution record
    ↓
telemetry
```

Tool exposure to a model never equals execution authorization.

## 8.3 Initial adapters

Implement only what current slices need:

```text
NativeCapabilityAdapter
LLMCapabilityAdapter
ArtifactCapabilityAdapter
```

Create `MCPAdapter` interface/stub only if useful for type stability; no MCP migration is required.

---

# 9. Context Plane

## 9.1 Core models

```python
class ContextRequirement(BaseModel):
    capability: str
    required: bool = True
    max_tokens: int | None = None
    freshness_policy: str | None = None

class ContextItem(BaseModel):
    capability: str
    provider_id: str
    source_ref: str
    descriptor: str
    summary: str | None
    provenance: dict
    freshness: datetime | None
    sensitivity: str
    token_estimate: int
    confidence: float | None
    content_hash: str

class ContextPackage(BaseModel):
    id: str
    task_attempt_id: str
    items: tuple[ContextItem, ...]
    total_token_estimate: int
    content_hash: str
```

## 9.2 Initial capabilities

For migration slices, define at least:

```text
candidate.profile_summary
candidate.verified_experience
candidate.achievements
candidate.skills
candidate.resume_text

job.summary
job.requirements
job.description

application.current_cv
application.current_cover_letter

coach.session_context
coach.question_context
coach.transcript
```

Do not build a complete ontology before a slice needs it.

## 9.3 Initial providers

Wrap existing sources behind providers rather than moving domain data:

```text
ProfileYamlContextProvider
ResumeContextProvider
JobPostingContextProvider
ApplicationContextProvider
CoachContextProvider
```

Progressive disclosure may initially be implemented with descriptors/summaries plus an explicit evidence-resolution call.

## 9.4 Immutability

After a `ContextPackage` is bound to a `TaskAttempt`, no in-place mutation is allowed.

A retry may resolve a new package and receives a new package ID/hash.

---

# 10. Intelligence Plane

## 10.1 ModelDescriptor

Wrap current `llm_factory` configuration into descriptors.

Initial fields:

```text
model_id
provider
model_name
structured_output
tool_calling
context_window
reasoning_class
local_or_cloud
estimated_latency_class
estimated_cost_class
hardware_requirements
privacy_characteristics
enabled
```

## 10.2 Router pipeline

Implement in this order:

```text
capability eligibility
quality floor
Control Plane eligibility
evidence ranking
explicit fallback chain
```

Every candidate is recorded with:

```text
eligible
excluded_reason_codes
rank_components
final_rank
```

## 10.3 AUTO / PREFER / FORCE

```text
AUTO   normal ranking
PREFER rank preferred eligible model higher
FORCE  restrict to selected model only if still eligible
```

`FORCE` cannot bypass capability/policy/quality requirements.

## 10.4 Evidence

Initial evidence may seed from current benchmark/static qualification data.

Production executions create `EvidenceObservation`.

Only an explicit qualification/promotion operation creates routing-active `ModelEvidence`.

No automatic online self-modification.

---

# 11. Evaluation and observability

## 11.1 Deterministic-first evaluation

Evaluation order:

```text
deterministic validator
domain heuristic
model evaluator only when needed
human review when required
```

## 11.2 Execution lineage

Persist:

```text
PRIMARY
REPAIR
FALLBACK
EVALUATOR
TOOL
ARTIFACT
RECONCILIATION
```

with `parent_execution_id` where applicable.

## 11.3 OpenTelemetry

Wrap existing Hatch OpenTelemetry rather than replacing it.

Required durable IDs on spans when available:

```text
hatch.workflow_run_id
hatch.workflow_step_id
hatch.task_attempt_id
hatch.execution_id
hatch.task_id
hatch.task_version
```

OTel exporter failure must not fail workflow correctness.

## 11.4 Capture policy

Canonical enum values remain:

```text
METADATA_ONLY
REDACTED
DEBUG_CONTENT
DISABLED
```

Implementation configuration:

```text
HATCH_RUNTIME_CAPTURE_POLICY=metadata_only
```

Allowed normal-deployment values in this foundation:

```text
metadata_only
redacted
disabled
```

`DEBUG_CONTENT` is **test/local-developer only** for this foundation. It is not accepted from the
normal deployment environment/configuration path. Tests may inject it directly through a
test-only capture-policy factory. Production/default startup must reject an environment request
for `debug_content` with a stable configuration error.

Required behavior:

- `METADATA_ONLY` is default;
- `REDACTED` permits only explicitly allowlisted safe fields;
- `DISABLED` emits only correctness/audit records that cannot be disabled;
- `DEBUG_CONTENT` never weakens event/shadow-table prohibitions and has a maximum 24-hour
  test/local retention if a debug sink persists content;
- credentials/secrets are never capturable in any mode.

Existing `llm_factory` response-preview buffering must be changed so raw response previews are
not retained under `METADATA_ONLY`, `REDACTED`, or `DISABLED`. Privacy tests must place canaries
in model output and prove the ring buffer, logs, spans and durable records do not retain them.

Add sentinel tests proving sensitive content does not leak into runtime event payloads, OTel
attributes, routing/policy records, evaluation metadata, shadow records, logs or the LLM trace buffer.

---

# 12. Events and outbox

## 12.1 Transaction rule

When a durable state transition requires an event:

```text
BEGIN
state change
runtime_event append
outbox enqueue if needed
COMMIT
```

No dual-write after commit.

## 12.2 Delivery

Guarantee:

```text
at-least-once
```

Consumers must deduplicate via `event_id` or explicit idempotency key.

## 12.3 Initial outbox destinations

Do not over-generalize.

Support only destinations currently needed for runtime operation, e.g.:

```text
runtime.telemetry
runtime.evaluation
runtime.notification
```

A destination is not permission to perform a hidden committing side effect.

---

# 13. Legacy compatibility facade

Create a thin migration facade.

Suggested API:

```python
class LegacyAIRuntimeFacade:
    async def score_job(...) -> LegacyScoreResult: ...
    async def tailor_cv(...) -> LegacyTailorResult: ...
    async def generate_cover_letter(...) -> LegacyCoverLetterResult: ...
```

The facade may:

- translate legacy inputs;
- invoke TaskSpecs/workflows;
- translate results back.

The facade may not:

- choose models itself;
- run retries;
- fetch undeclared context;
- authorize tools;
- manage claims;
- duplicate evaluation logic.

Coach migration may use a separate `LegacyCoachRuntimeAdapter` if its interface is materially different.

---

# 14. Phase and PR plan

Do not implement the full foundation in one PR.

All R0-R9 pull requests target `main`; there is **no long-lived integration branch**.
Each PR branch is created only after its predecessor merges.

Before each PR:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
BASE_SHA="$(git rev-parse HEAD)"
git switch -c <approved-branch-name>
git merge-base --is-ancestor origin/main HEAD
```

Before opening each PR:

```bash
git fetch origin
git merge-base --is-ancestor "$BASE_SHA" HEAD
git log --oneline "$BASE_SHA"..HEAD
git diff --check "$BASE_SHA"..HEAD
git diff --stat "$BASE_SHA"..HEAD
```

PR base is always `main`. If `origin/main` moved because an unrelated PR merged, rebase/update
the branch and rerun affected tests before review. Do not start the next runtime PR until the
current one has merged.

The tracked implementation plan lives at:

```text
docs/implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md
```

Recommended PR sequence:

```text
PR R0  Baseline + specification + characterization
PR R1  Runtime contracts + durable schema/store + event/outbox primitives
PR R2  Workflow Kernel + claims/fencing/retry/waiting/approval
PR R3  Control Plane + Execution Gateway
PR R4  Context + Intelligence + Evaluation/OTel integration
PR R5  Job Scoring LEGACY/SHADOW/NEW migration
PR R6  CV Tailoring migration
PR R7  Cover-Letter migration
PR R8  Coach Phase 1 kernel extraction/migration
PR R9  R4 gate verification + legacy cleanup eligible at this point only
```

A PR may be split further if its review surface becomes too large.

Never merge R5 before R1–R4 gates pass.

---

# 15. PR R0 — Baseline and characterization

## Files

Modify/create:

```text
docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md
docs/README.md

backend/tests/runtime/fixtures/
backend/tests/runtime/test_characterization_job_scoring.py
backend/tests/runtime/test_characterization_tailoring.py
backend/tests/runtime/test_characterization_cover_letter.py
backend/tests/runtime/test_characterization_coach.py
```

Do not change product behavior.

## Required work

- Capture exact baseline commit.
- Verify `approval_status: approved-for-implementation` before code changes.
- Obtain the exact approved architecture authority file and track it at the canonical architecture path.
- Record the architecture SHA-256 in R0 evidence.
- Run `python scripts/check_docs.py` once **before** repair and record known documentation failures as RED baseline evidence.
- Delete untracked obsolete condensed Coach v1/local historical copies as required by tracked Coach V6; do not relocate or track them.
- Repair implementation-spec metadata/links and plan placement.
- Run `python scripts/check_docs.py` again and require exit 0.
- Track the v2 plan under `docs/implementation-notes/`, not ignored `docs/superpowers/`.
- Run current targeted backend tests for scorer, Tailor/CV, cover letter, async jobs and Coach reconciliation.
- Establish golden fixtures using synthetic/non-personal data.
- Characterize current API/result shapes.
- Record unrelated baseline failures separately; do not “fix” them in R0.
- Verify tracked Coach V6 remains the sole Phase 1 product-contract authority.

## R0 exit gate

```text
✓ spec tracked
✓ docs check passes
✓ exact implementation SHA recorded
✓ targeted baseline tests recorded
✓ golden synthetic fixtures added
✓ no product behavior changed
```

---

# 16. PR R1 — Contracts, persistence, events and outbox

## Files

Create core `backend/app/runtime/contracts/*`, `runtime/storage/*`, `runtime/events/*`.

Create SQLAlchemy models either under:

```text
backend/app/runtime/workflow/models.py
backend/app/runtime/events/models.py
backend/app/runtime/evaluation/models.py
```

or repository-standard `backend/app/models/runtime_*.py`.

Choose one convention during R1 and use it consistently.

Modify:

```text
backend/app/database.py
backend/app/models/__init__.py if applicable
backend/alembic/versions/*
```

Tests:

```text
backend/tests/runtime/test_task_spec.py
backend/tests/runtime/test_storage_contract.py
backend/tests/runtime/test_event_atomicity.py
backend/tests/runtime/test_outbox_store.py
backend/tests/runtime/test_schema_migration.py
```

## R1 invariant IDs

```text
INV-CTR-001 TaskSpec is immutable/versioned
INV-DB-001  state+event commit atomically
INV-DB-002  retry history schema cannot collapse attempts
INV-EVT-001 outbox item cannot exist for rolled-back event
INV-EVT-002 delivery attempt history is append-only
INV-PRV-001 metadata-only records reject/avoid raw sensitive payloads
```

## R1 exit gate = partial R1 architecture gate

- migrations upgrade from current `main` database;
- no second Alembic head;
- SQLite WAL behavior preserved;
- schema downgrade works where project migration policy requires it;
- storage semantic tests pass;
- event/outbox transactional tests pass;
- app startup remains healthy.

---

# 17. PR R2 — Workflow Kernel

## Files

Create:

```text
runtime/workflow/kernel.py
runtime/workflow/repository.py
runtime/workflow/claims.py
runtime/workflow/retry.py
runtime/workflow/approvals.py
runtime/workflow/reconciliation.py
```

Tests:

```text
test_claims.py
test_fencing.py
test_retries.py
test_waiting.py
test_approvals.py
test_reconciliation.py
test_runtime_restart_recovery.py
test_sqlite_contention.py
```

## Required failure points

Add a test-only failure-injection mechanism, not production behavior flags:

```text
FAIL_AFTER_CLAIM_COMMIT
FAIL_AFTER_EXECUTION_BEFORE_FINALIZE
FAIL_AFTER_STATE_CHANGE_BEFORE_EVENT
```

## Critical tests

### INV-WF-001 stale finalizer

1. Worker A claims token 10.
2. Lease expires.
3. Worker B claims token 11.
4. B finalizes.
5. A finalization returns false/no-op.
6. persisted result remains B.

### INV-WF-002 retry immutability

Failed attempt 1 remains terminal; retry creates attempt 2.

### INV-WF-003 restart recovery

Create pending/running/waiting records, dispose process-level objects, reconstruct only from DB, and resume correctly.

### INV-WF-004 no-worker waiting

No active in-memory task is required for approval/retry wait.

### INV-APP-001 payload binding

Approval for payload hash A does not authorize B.

## R2 exit gate

Focused R2 tests must pass, then run:

```bash
cd backend
python -m pytest -q
```

Promotion is blocked by any newly introduced full-suite failure.

```text
✓ fencing
✓ retry immutability
✓ not_before
✓ waiting
✓ approval durability
✓ restart recovery
✓ SQLite contention path
✓ complete backend suite green or pre-existing failures explicitly unchanged and owner-dispositioned
```

---

# 18. PR R3 — Control Plane and Execution Gateway

## Files

Create `runtime/control/*`, `runtime/execution/*`.

Tests:

```text
test_policy_precedence.py
test_policy_force_model.py
test_execution_gateway.py
test_side_effect_authorization.py
test_idempotency.py
test_outcome_unknown.py
test_deadlines.py
```

## Required invariant IDs

```text
INV-CTL-001 system invariant beats user config
INV-CTL-002 TaskSpec capability requirement cannot be removed
INV-CTL-003 FORCE cannot bypass policy
INV-EXE-001 visible capability != authorized capability
INV-EXE-002 commit capability verifies approval when required
INV-EXE-003 OUTCOME_UNKNOWN does not blind-retry
INV-EXE-004 stale claim cannot persist a late capability result
```

## Initial native/LLM capabilities

Register only capabilities needed by subsequent slices.

Examples:

```text
llm.generate_structured
job.local_score
artifact.render_cv
artifact.render_cover_letter
```

Do not expose internal functions through MCP.

## R3 exit gate

Focused Control/Execution tests pass with no product slice migrated yet, then run:

```bash
cd backend
python -m pytest -q
```

R3 does not pass with a newly introduced full-suite regression.

---

# 19. PR R4 — Context, router, evaluation and OTel correlation

## Files

Create:

```text
runtime/context/*
runtime/intelligence/*
runtime/evaluation/*
runtime/observability/*
```

Modify/wrap:

```text
backend/app/agents/tools/llm_factory.py
backend/app/agents/tools/context_budgets.py
backend/app/agents/tools/context_checker.py
backend/app/observability/*
```

Do not remove legacy behavior yet.

## Model registry bootstrap

Create descriptors from current configured providers/models.

Do not hard-code one universal “best model”.

## Initial context providers

Concrete product providers live under `backend/app/runtime_bindings/context/` and register with
the generic runtime registry. Implement only providers needed by R5-R8.

## Tests

```text
test_context_registry.py
test_context_resolver.py
test_context_immutability.py
test_context_privacy.py
test_model_router.py
test_router_candidate_snapshot.py
test_evaluation_service.py
test_evidence_promotion.py
test_otel_correlation.py
test_otel_export_failure.py
```

## Invariants

```text
INV-CTX-001 undeclared context is not fetched
INV-CTX-002 package immutable per attempt
INV-CTX-003 provenance/sensitivity preserved
INV-RTR-001 gating order is deterministic
INV-RTR-002 candidate snapshot persists
INV-RTR-003 unpromoted observation cannot affect routing
INV-EVL-001 evaluation is bounded
INV-OBS-001 OTel failure does not fail workflow
INV-OBS-002 durable IDs correlate every execution
```

## Gate R1 — Runtime Core Ready

R1 is passed only after PRs R1-R4 pass together.

Before recording Gate R1 PASS, run:

```bash
cd backend
python -m pytest -q
```

No newly introduced full-suite failure is allowed.

Required proof:

```text
TaskSpec usable
SQLite durable store usable
Workflow Kernel usable
Control Plane usable
Execution Gateway usable
Context Resolver usable
task-aware Router usable
decision/eval lineage usable
events/outbox usable
OTel correlation usable
core invariant suite green
```

---

# 20. PR R5 — Job Scoring migration

This is the first full architecture proof.

## Existing path

Current scoring behavior resides primarily in:

```text
backend/app/agents/scorer_agent.py
backend/app/agents/tools/local_scorer.py
backend/app/agents/tools/semantic_scorer.py
backend/app/agents/tools/llm_factory.py
backend/app/agents/tools/event_bus.py
```

Do not rewrite scoring mathematics unnecessarily.

## New TaskSpec

Create:

```text
task_id = job.score
version = 1
```

Input must identify the job and candidate/profile context by reference, not embed arbitrary storage assumptions.

Output mirrors current durable score semantics:

```text
skill_match
experience_match
rate_match
location_match
overall_score
reasoning
keyword_matches
keyword_misses
fit_reasoning
strengths
score_gaps
scoring_method
```

Keep deterministic normalization/weighting behavior where currently correct.

## Context requirements

```text
candidate.profile_summary
candidate.resume_text
job.description
job.requirements
```

## Execution strategy

Suggested:

```text
FALLBACK_ON_FAILURE
```

with deterministic/local fallback where existing product behavior already supports it.

## Migration boundary

Resolve mode before entering scorer execution:

```text
LEGACY
  current ScorerAgent

SHADOW
  current result authoritative
  new runtime evaluates same job
  no duplicate durable JobScore ownership

NEW
  new runtime authoritative
```

Shadow new-runtime results go into migration/evaluation records, not the user-visible authoritative score table unless explicitly modeled as shadow snapshots.

## Tests

- golden score cases;
- normalization;
- policy exclusion;
- local fallback;
- structured-output failure;
- model timeout;
- context missing;
- shadow duplicate prevention;
- semantic comparison between legacy/new;
- restart/retry;
- OTel lineage.

## Gate R2 — Architecture Proven

### Benchmark population

Use a minimum of **50 synthetic or explicitly sanitized labeled cases**:

```text
20 clear strong-fit cases
15 borderline cases within ±0.10 of the configured shortlist threshold
15 poor-fit / irrelevant cases
```

The fixture set records expected shortlist classification and stable scenario labels. No personal
candidate data is required for this gate.

### Quality thresholds

All must pass:

```text
deterministic output/schema/normalization validators = 100% pass
expected shortlist classification accuracy >= 92%
NEW shortlist accuracy >= legacy accuracy - 2 percentage points
legacy-vs-NEW shortlist decision agreement >= 95%
absolute overall_score delta <= 0.10 for >= 90% of comparable cases
no critical/high privacy or correctness regression
```

Any case outside the score-delta tolerance is listed in the R2 report with reason codes.
The owner may accept a deliberate semantic improvement only by explicitly adjudicating that case;
adjudicated exceptions do not waive validator/privacy requirements.

### Latency thresholds

Run legacy and NEW against the same 20-case performance subset, same machine, provider/model,
warm-up policy and concurrency.

```text
NEW p50 end-to-end latency <= 1.20 × legacy p50
NEW p95 end-to-end latency <= 1.25 × legacy p95
```

If a remote provider has a transient incident, rerun both modes together; do not compare runs from
different provider conditions.

### Cost thresholds

Using the same benchmark population/model/provider:

```text
mean estimated cost per successful scored job <= 1.15 × legacy
p95 total token usage per successful scored job <= 1.25 × legacy
```

### Reliability and full-suite thresholds

```text
restart/recovery/fencing/fallback tests = 100% pass
shadow produces exactly one authoritative visible score
privacy canary suite = 100% pass
complete backend test suite has no newly introduced failure
```

### Approval

The required R2 approver is the Hatch repository/architecture owner, GitHub `@arvindsoni2`.
Promotion to `HATCH_RUNTIME_JOB_SCORE_MODE=new` requires explicit approval recorded in
`R5-job-score-migration.md` or the PR review.

Only after all thresholds and owner approval may Job Scoring become `NEW`.

---

# 21. PR R6 — CV Tailoring migration

## Existing paths to re-check

At implementation baseline identify exact Tailor/CV service ownership, including:

```text
backend/app/agents/tailor_agent.py
backend/app/services/*cv*
backend/app/services/ats_optimiser.py
backend/app/services/resume_store.py
artifact/template generation paths
```

Do not guess paths if current main has moved ownership.

## TaskSpec

```text
task_id = cv.tailor
version = 1
```

Context:

```text
candidate.verified_experience
candidate.achievements
candidate.skills
candidate.resume_text
job.requirements
job.description
```

Mandatory correctness:

```text
no unsupported candidate claims
schema/contract valid
required sections present
artifact contract valid
```

Use deterministic validators before model evaluators.

## Migration

```text
LEGACY → SHADOW → NEW
```

Shadow artifact generation must not overwrite user-visible legacy artifacts.

Use separate shadow artifact storage or evaluation-only structured output.

## Required tests

- sparse candidate evidence;
- unsupported claim attempt;
- conflicting candidate/job evidence;
- long resume/context budget;
- artifact failure;
- repair then fallback;
- context provenance;
- privacy capture;
- migration rollback.

---

# 22. PR R7 — Cover-letter migration

## TaskSpec

```text
task_id = cover_letter.generate
version = 1
```

Reuse CV/job context providers and routing infrastructure.

Required deterministic validators include existing product limits, especially the repository's cover-letter length/structure contracts where still current.

Do not fork a second candidate-context implementation.

## Migration

```text
LEGACY → SHADOW → NEW
```

## Gate R3 — Core Generation Migrated

Before R3 PASS, run the complete backend suite:

```bash
cd backend
python -m pytest -q
```

R3 passes when:

```text
Job Scoring = NEW
CV Tailoring = NEW
Cover Letter = NEW

shared Context Plane is used
shared Router is used
shared Control/Execution paths are used
no slice owns bespoke retries/routing
migration rollback remains available
```

---

# 23. PR R8 — Coach Phase 1 kernel extraction

This PR is not a Coach Phase 2 feature PR.

Its purpose is to remove generic durability/concurrency semantics from Coach-specific ownership.

## Existing paths to inspect first

```text
backend/app/services/async_job_service.py
backend/app/services/coach_reconciliation.py
backend/app/services/coach_session_queue.py
backend/app/repositories/conversational_session_repository.py
backend/app/repositories/session_repository.py
backend/app/models/async_job.py
backend/app/models/coach_session.py
backend/app/routers/coach.py
backend/tests/*coach*
```

Current Coach contains valuable conditional updates and reconciliation semantics. Preserve their behavior while transferring generic responsibility.

## Extraction mapping

### Existing `AsyncJobService.run`

Current fire-and-forget `asyncio.create_task` must no longer be required for durable recovery.

Allowed transitional behavior:

- API request may schedule a local worker wake-up;
- durable workflow/attempt exists before wake-up;
- if no process-local task is created, another worker/reconciler can still resume it.

### Existing answer/report reconciliation

Map to generic kernel:

```text
job/session claim identity
    → ExecutionClaim

claim expiry
    → lease expiry

late completion guards
    → fencing-token finalization

retry processing
    → new TaskAttempt + RetryPolicy

stale recovery
    → generic reconciliation callback + Coach-specific domain transition
```

### Coach-specific behavior remains domain-owned

Examples:

```text
transcription semantics
answer evaluation
rubric construction
session question state
report aggregation
Coach diagnostic payloads
```

Do not move these into `runtime/`.

## Compatibility strategy

`HATCH_RUNTIME_COACH_MODE`:

```text
LEGACY
    current Coach runtime

SHADOW
    only for safe preparation/evaluation segments
    no duplicate domain commits

NEW
    generic kernel owns durability/retry/reconciliation
```

Because Coach already contains durable domain tables, this migration may use adapters rather than immediate domain-table replacement.

The goal is generic ownership of execution semantics, not unnecessary data copying.

## Mandatory Coach invariant tests

```text
INV-COACH-001 late answer worker cannot overwrite reconciled/newer result
INV-COACH-002 late report worker cannot overwrite reconciled/newer result
INV-COACH-003 retry creates generic new attempt
INV-COACH-004 restart requires no asyncio task state
INV-COACH-005 stale claim recovery is idempotent
INV-COACH-006 Phase 1 acceptance behavior preserved
```

Late finalization must be fenced using the new generic claim identity plus existing domain ownership conditions where required.

## Gate R4 — Coach Runtime Ready

Before R4 PASS, run the complete backend suite plus the binding Coach V6 acceptance/security
suites named in the implementation plan. R4 cannot pass with a new full-suite regression.

R4 passes only when all are true:

### Runtime

```text
✓ R1–R3 passed
✓ Coach uses generic Workflow Kernel for durable execution semantics
```

### Reliability

```text
✓ claim/lease/fencing suite green
✓ restart recovery green
✓ retry immutability green
✓ event/outbox atomicity green
✓ OUTCOME_UNKNOWN path green where applicable
✓ approval binding green
```

### Migration

```text
✓ Job Scoring = NEW
✓ CV Tailoring = NEW
✓ Cover Letter = NEW
✓ Coach Phase 1 durability/reconciliation on generic kernel
```

### Coach

```text
✓ answer finalization fenced
✓ report finalization fenced
✓ retry budget/policy explicit
✓ no recovery dependency on asyncio.Task
✓ existing Phase 1 acceptance tests green
```

### Observability

```text
✓ workflow lineage reconstructable
✓ model routing explainable
✓ repair/fallback lineage visible
✓ OTel failure non-fatal
✓ raw sensitive content not captured by default
```

Only after written R4 approval may Coach Phase 2 implementation begin.

---

# 24. PR R9 — Gate verification and eligible cleanup

This PR is intentionally small.

Do not remove all legacy infrastructure merely because R4 passed.

Eligible cleanup:

- dead compatibility code for slices permanently retired;
- old model-selection code no longer referenced by NEW slices;
- duplicate retry/reconciliation code now replaced by kernel;
- stale migration flags only after owner approves retirement.

Do not remove:

- legacy support still required by non-migrated consumers;
- old schema still needed by historical data;
- compatibility facade used by remaining callers.

Produce:

```text
docs/implementation-reports/Hatch_Architecture_Foundation_R4_Report.md
```

Report:

```text
baseline SHA
PR SHAs
migration modes
invariant suite result
golden-set result
latency/cost comparison
known residual risks
legacy paths remaining
PostgreSQL trigger metrics/status
Coach Phase 2 gate = PASS/FAIL
```

---

# 25. Canonical architecture invariant registry

The canonical registry contains **36** binding invariant IDs. No PR-local invariant may exist
outside this table without first updating the registry.

| ID | Invariant | Named minimum test |
|---|---|---|
| INV-CTR-001 | TaskSpec correctness contract is immutable/versioned | `test_task_spec_is_frozen_and_versioned` |
| INV-DB-001 | Durable state transition and required event/outbox work commit atomically | `test_state_event_outbox_roll_back_together` |
| INV-DB-002 | Retry history cannot collapse/rewrite prior attempts | `test_retry_schema_preserves_attempt_history` |
| INV-WF-001 | Stale worker cannot finalize after newer fencing token | `test_stale_finalizer_cannot_overwrite_new_owner` |
| INV-WF-002 | Retry creates a new immutable attempt | `test_retry_creates_new_attempt` |
| INV-WF-003 | Recovery does not require process-local state | `test_crash_after_claim_recovers_from_database` |
| INV-WF-004 | Waiting states hold no worker claim | `test_waiting_owns_no_claim` |
| INV-APP-001 | Approval is bound to exact payload hash | `test_approval_for_payload_a_does_not_authorize_b` |
| INV-CTL-001 | Higher-precedence policy cannot be weakened | `test_user_config_cannot_weaken_system_egress_denial` |
| INV-CTL-002 | TaskSpec mandatory requirements cannot be removed | `test_task_requirement_survives_user_override` |
| INV-CTL-003 | FORCE cannot bypass capability/quality/policy gates | `test_force_model_remains_subject_to_quality_and_policy` |
| INV-CTX-001 | Undeclared context is not silently fetched | `test_resolver_never_fetches_undeclared_context` |
| INV-CTX-002 | ContextPackage is immutable per attempt | `test_retry_resolves_new_package_without_mutating_prior` |
| INV-CTX-003 | Provenance/sensitivity survive resolution | `test_context_metadata_survives_resolution` |
| INV-RTR-001 | Router gates run in approved deterministic order | `test_router_stage_order_is_fixed` |
| INV-RTR-002 | Candidate snapshot/exclusion reasons are persisted | `test_router_records_every_candidate_and_exclusion` |
| INV-RTR-003 | Unpromoted observations cannot alter routing | `test_observation_does_not_change_routing_until_promoted` |
| INV-EXE-001 | Tool visibility does not grant execution authorization | `test_visible_capability_is_not_automatically_authorized` |
| INV-EXE-002 | Committing side effect respects approval policy | `test_commit_capability_requires_valid_approval` |
| INV-EXE-003 | OUTCOME_UNKNOWN reconciles instead of blind retry | `test_lost_external_commit_becomes_outcome_unknown` |
| INV-EXE-004 | Stale claim cannot persist a late capability result | `test_gateway_rejects_result_after_claim_loss` |
| INV-EVT-001 | Event/outbox crash boundaries remain consistent | `test_state_event_outbox_roll_back_together` |
| INV-EVT-002 | Duplicate at-least-once delivery is harmless and attempts remain history | `test_duplicate_delivery_is_idempotent` |
| INV-EVL-001 | Evaluation chain is bounded | `test_deterministic_failure_stops_unneeded_model_evaluation` |
| INV-OBS-001 | OTel failure does not fail correct workflow | `test_exporter_failure_does_not_change_workflow_result` |
| INV-OBS-002 | Durable execution lineage is reconstructable | `test_primary_repair_fallback_lineage_reconstructs` |
| INV-PRV-001 | Metadata-only capture does not leak raw sensitive content | `test_metadata_only_records_reject_sensitive_canaries` |
| INV-MIG-001 | A request has exactly one authoritative runtime | `test_slice_has_one_authoritative_writer` |
| INV-MIG-002 | SHADOW cannot duplicate visible/committing effects | `test_shadow_has_no_visible_or_commit_side_effect` |
| INV-MIG-003 | Running WorkflowRun does not switch engines | `test_mode_change_does_not_move_running_workflow` |
| INV-COACH-001 | Late Coach answer completion is fenced | `test_late_coach_answer_worker_cannot_overwrite_newer_result` |
| INV-COACH-002 | Late Coach report completion is fenced | `test_late_coach_report_worker_cannot_overwrite_newer_result` |
| INV-COACH-003 | Coach retry creates a generic new TaskAttempt | `test_coach_retry_creates_generic_new_attempt` |
| INV-COACH-004 | Coach restart needs no asyncio task registry | `test_coach_restart_requires_no_asyncio_task_registry` |
| INV-COACH-005 | Coach stale-claim recovery is idempotent | `test_coach_stale_claim_recovery_is_idempotent` |
| INV-COACH-006 | Coach Phase 1 acceptance behavior remains compatible | `test_coach_v6_acceptance_regression_gate` |

Every implementation PR identifies the subset it introduces/proves. R9 reports all 36.

---

# 26. Failure-injection matrix

Tests must simulate at least:

| Failure point | Expected recovery |
|---|---|
| crash after claim commit | lease expires; new claimant obtains newer token |
| late old worker finalizes | conditional finalize fails |
| execution succeeds, process crashes before finalization | retry/reconciliation follows idempotency policy |
| state update before event insert | transaction rollback leaves neither committed |
| commit completes before publisher sees outbox | outbox remains pending and later delivers |
| outbox consumer succeeds, publisher crashes before ACK | duplicate delivery; consumer idempotency prevents duplicate effect |
| external commit response lost | `OUTCOME_UNKNOWN`; reconcile/check-before-retry |
| OTel exporter unavailable | durable execution continues; telemetry export degrades |
| approval payload mutated | old approval invalidated |
| SQLite write contention | bounded retry/busy handling; no duplicate claim |

Do not use nondeterministic long sleeps to create these races.

---

# 27. Test commands

Implementers must adapt exact filenames to repository conventions, but every PR summary records commands and results.

Minimum backend gates:

```bash
python scripts/check_docs.py

cd backend
pytest -q
```

Focused runtime examples:

```bash
pytest -q tests/runtime/test_storage_contract.py
pytest -q tests/runtime/test_fencing.py
pytest -q tests/runtime/test_policy_precedence.py
pytest -q tests/runtime/test_model_router.py
pytest -q tests/runtime/test_event_atomicity.py
pytest -q tests/runtime/test_otel_export_failure.py
```

Before R2/R3/R4 promotion, run the complete backend test suite and all relevant existing slice/Coach tests.

If the repository uses additional lint/type commands at implementation time, Codex must discover and run them rather than inventing replacements.

---

# 28. Commit and review discipline

Each task follows:

```text
write failing test
run and observe expected failure
implement minimum behavior
run focused test
run affected suite
commit bounded change
```

Never use:

```bash
git add .
git add -A
```

Stage exact paths.

Suggested commit prefixes:

```text
test(runtime):
feat(runtime):
feat(workflow):
feat(control):
feat(context):
feat(router):
feat(execution):
feat(events):
feat(eval):
refactor(scorer):
refactor(tailor):
refactor(coach):
docs(runtime):
```

Each PR description must include:

```text
architecture decisions implemented
invariant IDs
new migrations
migration-mode behavior
tests
failure-injection cases
rollback path
known risks
```

---

# 28.1 Shadow retention and capture enforcement

`runtime_shadow_comparisons` is metadata-only and expires after 30 days.

A best-effort maintenance routine runs at application startup and daily while the process is up:

```python
await shadow_store.purge_expired(now=clock.now())
```

Failure to purge must be observable but must not fail product workflows. The next startup retries.

Persisted shadow records may contain:

```text
execution/reference IDs
model/task/version IDs
result hashes
validator/evaluation metrics
latency/token/cost metrics
reason codes
```

They may **not** contain raw model-generated content or generated artifacts.

The existing in-memory LLM `response_preview` behavior is included in `INV-PRV-001`; under normal
deployment capture modes it must be empty/not retained.

---

# 29. Non-goals

This specification does not implement:

```text
PostgreSQL production deployment
multi-host workers
high availability
Kafka/Redis/Temporal
framework migration
global MCP conversion
self-modifying router
LLM policy authorization
all Hatch AI consumers
Coach Phase 2 product features
```

These remain outside the R4 foundation gate.

---

# 30. Open implementation details that do not require architecture reopening

Codex may choose repository-consistent details for:

```text
exact SQLAlchemy model file placement
UUID helper implementation
exact Alembic revision IDs
test fixture filenames
internal Pydantic helper names
logging helper names
```

provided all public semantics and invariants in this specification remain intact.

Material changes to:

```text
claim/fencing semantics
policy precedence
migration ownership
event atomicity
approval binding
router gates
context immutability
Coach Phase 2 R4 boundary
```

require explicit architecture review.

---

# 31. Definition of Architecture Foundation Complete

The Architecture Foundation is complete only when:

```text
GATE R1 = PASS
GATE R2 = PASS
GATE R3 = PASS
GATE R4 = PASS
```

and the R4 implementation report is committed.

Completion means:

```text
Job Scoring        NEW
CV Tailoring       NEW
Cover Letter       NEW
Coach Phase 1      generic kernel owns durability/recovery semantics
```

It does **not** require all legacy Hatch AI consumers to be migrated.

At this point the architecture foundation becomes the implementation baseline for the separate:

```text
Hatch Coach Phase 2 Implementation Specification
```

---

# 32. Suggested first implementation task

Do **not** start by creating every runtime file.

Start with R0 and the first R1 contract slice:

```text
1. Commit this specification/documentation preflight.
2. Record current main SHA and baseline tests.
3. Add TaskSpec/enums/ID contracts with failing tests.
4. Add the first additive runtime persistence migration.
5. Add WorkflowStore semantic contract tests.
6. Implement SQLite store until those tests pass.
7. Add state+event atomicity tests before adding Workflow Kernel logic.
```

This keeps the first review small and proves that the architecture can be expressed cleanly in the existing Hatch codebase before proceeding to claims/fencing.
