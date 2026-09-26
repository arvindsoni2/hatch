---
title: Hatch Runtime Architecture Pre-Coach Phase 2
document_type: architecture
status: current
implementation_status: not-applicable
applies_to: main/latest
last_verified: 2026-08-24
---

# Hatch Runtime Architecture — Pre-Coach Phase 2

**Document status:** Living architecture source of truth
**Architecture stage:** COMPLETE — ARCH-00 through ARCH-12 approved, including ARCH-06R1
**Purpose:** Establish the Hatch runtime foundation before Coach Phase 2 implementation
**Review mode:** Delta-only review; chat is not the design document
**Last consolidated:** 2026-08-18

---

## 0. How to use this document

This file is the authoritative architecture record for the pre-Coach-Phase-2 runtime work.

The conversation should contain only:

- decisions;
- requested changes;
- short delta summaries;
- unresolved questions;
- approval statements.

Detailed approved design belongs here.

### Review commands

Use short references rather than quoting large sections:

- `ARCH-07 approved`
- `ARCH-07 change item 4`
- `ARCH-09 reject option B`
- `show open decisions`
- `prepare implementation handoff`

After every 2–3 reviewed sections, produce only a compact checkpoint:

```text
Approved
Open
Changed
Risks
Next
```

### Change-control rule

A previously approved architectural decision is not silently rewritten. A material change must be recorded as:

```text
Decision ID
Previous state
New state
Reason
Affected sections
Migration consequence
```

---

# 1. Executive Decision Ledger

| ID | Decision | Status | Selected direction |
|---|---|---:|---|
| ARCH-00 | Migration strategy | **Approved** | Foundation + critical vertical slices |
| ARCH-01 | TaskSpec | **Approved** | Code-defined correctness contract + configurable operational policy overrides |
| ARCH-02 | Context Plane | **Approved** | Capability-driven dynamic context resolution with progressive disclosure |
| ARCH-03 | Intelligence Plane | **Approved** | Deterministic eligibility + evidence-based model ranking + bounded fallback |
| ARCH-04 | Evaluation & Observability | **Approved** | Runtime-native OpenTelemetry-backed tracing + layered evaluation + controlled evidence promotion |
| ARCH-05 | Control Plane | **Approved** | Centralized deterministic Hatch-native policy engine |
| ARCH-06 | Durable Workflow Kernel | **Approved + ARCH-06R1** | Relational durable-state contract; SQLite/WAL default backend, PostgreSQL designed scale-up backend; atomic claims, leases + fencing, retries, resumable approvals |
| ARCH-07 | Execution Plane / Gateway | **Approved** | Typed native capabilities behind a common Execution Gateway; MCP only as an optional adapter |
| ARCH-08 | Events / Outbox | **Approved** | SQLite transactional event log + durable outbox; at-least-once delivery with idempotent consumers |
| ARCH-09 | Runtime data model for traces/evals | **Approved — Option B** | Small durable SQLite decision/eval records + OpenTelemetry operational traces + promoted evidence store |
| ARCH-10 | Migration architecture | **Approved** | Strangler migration with LEGACY/SHADOW/NEW modes; job scoring first proof; Coach Phase 1 kernel extraction before Phase 2 |
| ARCH-11 | Testing & architecture invariants | **Approved — Option B** | Conventional test pyramid + named architecture-invariant suite + deterministic failure injection |
| ARCH-12 | Implementation phases / Coach Phase 2 boundary | **Approved — Option B** | Gated foundation + vertical proofs; Coach Phase 2 implementation unlocked only after R4 Coach-runtime gate |

---

# 2. Goal and Scope

Before implementing Coach Phase 2, Hatch will introduce a runtime foundation that accommodates:

- newer model and reasoning capabilities;
- harness/runtime evolution;
- runtime schema and context selection;
- reusable agent skills;
- task-aware model routing;
- control-plane governance;
- durable/resumable execution;
- evaluation and observability as first-class runtime concerns.

The selected target is:

> **Four Planes + TaskSpec + dynamic context + model router + Control Plane + durable Workflow Kernel.**

This is an architectural modernization, not a wholesale rewrite.

---

# 3. Target Architecture

```text
                HATCH PRODUCT
                     │
              Workflow Kernel
                     │
                Hatch Runtime
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
   CONTEXT       INTELLIGENCE    CONTROL
    PLANE           PLANE         PLANE
       │             │             │
       └─────────────┼─────────────┘
                     ▼
               EXECUTION PLANE
```

Hatch domain concepts remain visible to the product:

```text
Scout
Scorer
Tailor
Coach
```

Internally, they become workflows composed of typed tasks rather than autonomous infrastructure units.

---

# 4. Cross-Cutting Architectural Principles

These principles are binding unless explicitly superseded by a later approved decision.

## 4.1 Typed contracts over implicit prompt behavior

Runtime correctness must be represented by code-defined contracts, schemas, deterministic validators and policy—not by prompt wording alone.

## 4.2 Models propose; deterministic systems authorize

Models may reason, recommend and request actions.

Models do not:

- grant themselves permissions;
- increase their own budgets;
- bypass data-egress restrictions;
- approve external side effects;
- rewrite mandatory correctness requirements.

## 4.3 Minimum necessary context

Tasks receive only the context needed for their declared capabilities and current execution stage.

## 4.4 Durable state is authoritative

SQLite-backed workflow state is the source of truth.

In-memory task state, worker-local state or `asyncio.Task` state must never be required for recovery.

## 4.5 Leases detect; fencing protects

Leases are used to detect abandoned work.

Monotonic fencing tokens protect correctness by preventing stale workers from finalizing newer work.

## 4.6 Side effects are explicit

Preparation and commitment are distinct operations.

Examples:

```text
email.compose
email.send

application.prepare
application.submit
```

## 4.7 Evidence informs routing; evidence does not self-govern

Production evidence may influence model selection only after deterministic qualification and promotion.

No model or runtime observation automatically rewrites routing policy.

## 4.8 Framework patterns over framework dependency

Adopt useful patterns from agent/runtime frameworks without making Hatch dependent on unnecessary orchestration infrastructure.

---

# 5. ARCH-00 — Migration Strategy

**Status: Approved**

Selected strategy:

> **Foundation + critical vertical slices**

Build the complete new runtime foundation, then initially migrate:

```text
Coach
CV tailoring
Cover-letter generation
Job scoring
```

Remaining legacy AI consumers may temporarily use a thin compatibility facade over the new runtime.

## Invariants

- No full Hatch rewrite.
- No requirement that every legacy consumer migrate before Coach Phase 2.
- New Phase-2 Coach behavior should depend on the new runtime rather than duplicating workflow, policy, retry or reconciliation logic.
- Compatibility code is transitional and must not become a second permanent runtime.

---

# 6. ARCH-01 — TaskSpec

**Status: Approved**

`TaskSpec` is the code-defined correctness contract for a unit of AI/runtime work.

Representative contract:

```text
task_id
version
input_schema
output_schema
context_requirements
model_capability_requirements
risk_classification
validators
evaluation_policy
workflow_behaviour
```

Operational configuration may override preferences such as:

```text
preferred_model
provider
cost_budget
latency_budget
reasoning_budget
retry_budget
local_cloud_preference
```

Configuration cannot remove mandatory correctness or safety requirements.

## Required separation

```text
TaskSpec
  = what must be true

Runtime / user / deployment configuration
  = how Hatch prefers to achieve it
```

## Invariants

- A task is versioned.
- Inputs and outputs are schema-bound.
- Context requirements are declared, not fetched ad hoc by prompt code.
- Capability requirements are explicit.
- Validators are part of the task contract.
- Risk classification is visible to the Control Plane.
- Operational overrides cannot weaken system invariants.

---

# 7. ARCH-02 — Context Plane

**Status: Approved**

Selected direction:

> **Capability-driven dynamic context resolution**

Tasks request semantic capabilities such as:

```text
candidate.verified_experience
candidate.achievements
job.requirements
```

They do not encode storage topology such as:

```text
read table X
call service Y
```

## Core concepts

```text
ContextProvider
ContextItem
ContextPackage
ContextResolver
CapabilityRegistry
```

## Progressive disclosure

Context is resolved in stages:

```text
descriptor
    ↓
summary / index
    ↓
specific evidence
```

The same progressive-disclosure principle may be used for:

```text
evidence
skills
schemas
tools
```

## Context metadata

Every significant `ContextItem` should carry at least:

```text
provenance
freshness
sensitivity
token_estimate
confidence
```

## ContextPackage rules

- Immutable for an execution attempt.
- Built from declared task requirements.
- Minimum necessary context by default.
- Sensitive material is not included merely because it is available.
- Provenance remains traceable even when content is summarized.
- A retry/new attempt may receive a newly resolved package according to policy; the original attempt's package remains immutable.

---

# 8. ARCH-03 — Intelligence Plane

**Status: Approved**

Selected direction:

> **Deterministic eligibility + evidence-based ranking**

Static concepts such as `primary_model` and `triage_model` are replaced by model descriptors.

## ModelDescriptor

Representative capabilities:

```text
structured_output
tool_calling
context_size
reasoning_capability
local_or_cloud
latency_profile
cost_profile
hardware_requirements
privacy_characteristics
```

## Routing sequence

```text
1. Capability gate
2. Quality-floor gate
3. Control-policy gate
4. Evidence-based ranking
5. Explicit fallback chain
```

A model that fails an earlier gate is not rescued by a high ranking score later.

## Task-specific model evidence

Evidence is task-specific, for example:

```text
model X
    cv.tailor        .92
    job.score        .95
    coach.evaluate   .83
```

A model is not assigned one universal quality score.

## User control

Supported intent:

```text
AUTO
PREFER
FORCE
```

`FORCE` is still subject to:

- policy;
- mandatory capabilities;
- privacy restrictions;
- safety constraints;
- task correctness requirements.

## Initial execution strategies

```text
SINGLE_PASS
VALIDATE_AND_REPAIR
FALLBACK_ON_FAILURE
```

Repair, retry and fallback budgets are explicit and bounded.

---

# 9. ARCH-04 — Evaluation and Observability

**Status: Approved at architectural level**

Build on existing OpenTelemetry instrumentation.

Every task trace should make the runtime decision path explainable.

## Minimum trace shape

```text
context_resolution
policy_decision
routing_candidates
selected_model
execution
validation
repair_or_fallback
cost
tokens
latency
result
```

Sensitive content is not persisted by default.

## Evaluation hierarchy

```text
deterministic validation
       ↓
domain heuristics
       ↓
LLM evaluator when judgement is actually required
       ↓
human review for important ambiguity
```

The system should not use an LLM evaluator where a deterministic validator is sufficient.

## Production evidence lifecycle

```text
observed
   ↓
qualified
   ↓
promoted
   ↓
deprecated
```

Promotion requires deterministic qualification thresholds.

## Invariants

- Production observations do not automatically rewrite routing.
- Eval results are task- and version-aware.
- Model, prompt/task version, context package identity and validator outcomes are traceable.
- Privacy-sensitive content is excluded or redacted by default.
- Runtime telemetry should support both engineering diagnosis and model-quality evaluation without creating two inconsistent observability systems.

---

# 10. ARCH-05 — Control Plane

**Status: Approved**

Selected direction:

> **Centralized deterministic Hatch-native policy engine**

No OPA or Cedar dependency is required at this stage.

## Policy precedence

```text
1. System invariants
2. TaskSpec requirements
3. Security / privacy policy
4. Workflow policy
5. User configuration
6. Routing preferences
```

Lower-precedence layers cannot weaken higher-precedence requirements.

## Policy result

```text
ALLOW
DENY
REQUIRE_APPROVAL
```

plus effective runtime constraints.

## Control Plane ownership

```text
privacy / data egress
provider permissions
model permissions
tool permissions
cost budgets
token budgets
retry limits
deadlines
human approvals
audit requirements
```

## Core rule

> **Models may request actions; models cannot authorize actions.**

## Prepare vs commit

External side effects are split into preparatory and committing capabilities.

Examples:

```text
email.compose
email.send

application.prepare
application.submit
```

A workflow may prepare a result without obtaining authority to commit it.

## Approval binding

Approval is tied to the exact payload or a deterministic payload hash.

Changing the payload invalidates the prior approval.

Approval state must be durable and resumable.

---

# 11. ARCH-06 — Durable Workflow Kernel

**Status: Approved**

Selected direction:

> **SQLite-backed durable workflow state with atomic claims, leases/fencing, retries and resumable approval states, without introducing an external workflow engine.**

Explicitly not required at this stage:

```text
Temporal
Celery
Redis
Kafka
```

## Core concepts

```text
WorkflowDefinition
WorkflowRun
WorkflowStep
TaskAttempt
ExecutionClaim
RetryPolicy
Approval
```

## Execution lifecycle

```text
PENDING
   ↓
atomic worker claim
   ↓
RUNNING
   ↓
execute TaskSpec
   ↓
conditional finalization
```

## Claims

A claim carries at least:

```text
claim_id
lease_expiry
fencing_token
```

The `fencing_token` is monotonic for the claimable unit of work.

A stale worker cannot finalize work after a newer claim has been issued.

## Correctness principle

> **Leases detect abandonment; fencing guarantees correctness.**

## Retry model

Retries create new attempts:

```text
attempt 1 → FAILED
attempt 2 → PENDING
```

The failed attempt is immutable history.

Backoff is represented durably using:

```text
not_before
```

Workers do not sleep while owning a workflow step.

## Waiting states

Waiting for any of the following consumes no worker:

```text
human approval
user input
scheduled retry
```

Resumption receives a fresh execution claim.

## External capability idempotency

Capabilities declare behavior:

```text
IDEMPOTENT
IDEMPOTENT_WITH_KEY
CHECK_BEFORE_RETRY
NON_RETRYABLE_SIDE_EFFECT
```

Ambiguous external outcomes use:

```text
OUTCOME_UNKNOWN
```

and reconciliation rather than blind retry.

## Source of truth

SQLite is authoritative.

`asyncio.Task` state, process-local queues or transient worker memory must never be required to reconstruct workflow state.

## Coach Phase 1 extraction requirement

Existing Coach Phase 1 reconciliation and fencing behavior should be extracted into this generic kernel before Coach Phase 2 introduces new durable workflows.

Late worker finalization must be conditionally fenced against the current job/attempt identity and expected pending/running state.

---

# 12. ARCH-07 — Execution Plane / Execution Gateway

**Status: Approved**

Approved direction:

> **Typed native capabilities behind a common Execution Gateway, with MCP as an optional external adapter.**

Conceptual form:

```text
Execution Gateway
      │
 ┌────┼─────────────┐
 ▼    ▼             ▼
LLM  Tool         Artifact
 │    │             │
local search        DOCX
cloud scraper       PDF
     MCP
```

Normal deterministic Python functions do **not** need to become MCP calls.

MCP is an interoperability boundary, not Hatch's internal RPC layer.

## Approved detailed contract scope

ARCH-07 defines:

1. capability descriptor/schema;
2. invocation contract;
3. authorization hook into the Control Plane;
4. idempotency declaration;
5. timeout/deadline propagation;
6. result and error taxonomy;
7. cancellation semantics;
8. side-effect classification;
9. artifact generation contract;
10. MCP adapter boundary;
11. tool discovery / progressive disclosure;
12. execution telemetry contract.

These items are now approved as the Execution Gateway contract scope.

---

# 13. ARCH-08 — Events and Durable Outbox

**Status: Approved**

Selected direction:

> **SQLite transactional event log + durable outbox, without making Hatch event-sourced and without introducing a second workflow scheduler.**

## Concept separation

```text
Runtime / Domain Event
"What happened?"

Outbox Entry
"What must be delivered because it happened?"

Workflow / Domain State
"What is true now?"
```

Workflow/domain tables remain authoritative current state. The event log is immutable history and integration/audit support, not the mechanism for reconstructing all Hatch state from scratch.

## Event contract

Durable events carry at least:

```text
event_id
event_type
event_version
aggregate_type
aggregate_id
workflow_run_id?
workflow_step_id?
task_attempt_id?
actor_type
actor_id?
occurred_at
payload
metadata
trace_id
correlation_id
causation_event_id?
sensitivity
```

## Actor vocabulary

Fixed `actor_type` allowlist:

```text
USER
SYSTEM
WORKER
MODEL
CAPABILITY
RECONCILER
```

Actor type is independent of workflow state, approval state and authorization result.

## Transactional invariant

When an event describes a durable state transition:

```text
BEGIN

UPDATE authoritative state
INSERT runtime_event
INSERT outbox_entry   # only when durable delivery is required

COMMIT
```

A durable state transition and the event describing it must not diverge after crash recovery.

## Outbox responsibility

The Workflow Kernel remains responsible for:

```text
task scheduling
claims
retries
waiting
approvals
workflow progression
```

The outbox handles durable post-commit delivery such as:

```text
telemetry / eval processing triggers
notifications
integration events
UI/server notifications
future webhook/event integration
audit export
```

It must not become a second orchestration system.

## Delivery semantics

Delivery guarantee:

> **At-least-once delivery with idempotent consumers.**

Consumers use `event_id` or an explicit idempotency key to make duplicate delivery harmless.

## Outbox lifecycle

```text
PENDING
   ↓
CLAIMED
   ↓
DELIVERED
```

Failure path:

```text
CLAIMED
   ↓
RETRY_WAIT
   ↓
PENDING
```

Exhausted/nonrecoverable:

```text
DEAD_LETTER
```

Retry timing uses persisted `not_before`.

## Claim/fencing reuse

Outbox publication reuses the Workflow Kernel concurrency vocabulary:

```text
claim_id
lease_expiry
fencing_token
```

A stale publisher cannot overwrite a newer delivery attempt.

## Delivery-attempt history

Outbox entries preserve delivery history rather than retaining only a mutable counter:

```text
OutboxEntry
    ├── DeliveryAttempt 1 FAILED
    ├── DeliveryAttempt 2 TIMEOUT
    └── DeliveryAttempt 3 DELIVERED
```

## Event versioning

Stable event name plus explicit schema version:

```text
event_type    = approval.granted
event_version = 1
```

Consumers declare supported versions.

## Payload discipline

Events contain identifiers, state transitions, small structured facts, reason/result classifications, hashes/version identities and references.

Large or sensitive AI inputs/outputs are referenced rather than copied into events by default.

## Authorization invariant

Event subscriptions cannot become a backdoor around policy.

Consequential actions still enter:

```text
Workflow / TaskSpec
      ↓
Control Plane
      ↓
Execution Gateway
```

Events communicate facts; they do not grant authority.

## Invariants

1. State and corresponding event commit atomically.
2. Workflow/domain tables remain the source of current truth; Hatch is not event-sourced.
3. Outbox is delivery infrastructure, not a second workflow scheduler.
4. Delivery guarantee is at-least-once.
5. Consumers are idempotent.
6. Outbox claims reuse lease + fencing semantics.
7. Retries use persisted `not_before`.
8. Delivery attempts remain durable history.
9. Event schemas are explicitly versioned.
10. Sensitive/large AI content is referenced rather than copied by default.
11. Event consumers cannot bypass the Control Plane.
12. Actor vocabulary is fixed and independent of workflow/approval state.

---

# 14. ARCH-09 — Concrete Observability and Evaluation Data Model

**Status: Approved — Option B**

Selected direction:

> **Persist small structured runtime-decision and evaluation records durably, while using OpenTelemetry for rich operational traces. Workflow/runtime IDs remain authoritative correlation identities.**

## Correlation spine

```text
WorkflowRun
    ↓
WorkflowStep
    ↓
TaskAttempt
    ├── ContextPackage
    ├── PolicyDecision
    ├── RoutingDecision
    ├── ExecutionRecord(s)
    ├── ValidationResult(s)
    └── EvaluationRun(s)
              ↓
       EvidenceObservation
              ↓
       ModelEvidence
```

`workflow_run_id`, `workflow_step_id` and `task_attempt_id` are durable lineage IDs.

Each individual model/tool/artifact/reconciliation invocation receives an `execution_id`.

One TaskAttempt may contain multiple executions, for example primary → repair → fallback.

## Three data classes

```text
AUTHORITATIVE RUNTIME DATA
    what Hatch decided / did

TELEMETRY
    how execution behaved

EVALUATION EVIDENCE
    how good the result was
```

These are correlated but not conflated.

## Durable runtime-decision records

Logical records include:

```text
policy_decisions
routing_decisions
execution_records
validation_results
evaluation_runs
evidence_observations
model_evidence
```

### Policy decisions

Persist:

```text
policy_decision_id
task_attempt_id
decision
effective_constraints
policy_version
reason_codes
created_at
trace_id
```

### Routing decisions

Persist the candidate snapshot, not only the selected model:

```text
routing_decision_id
task_attempt_id
task_spec_id
task_spec_version
candidate_snapshot
selected_model_id
selected_model_version
routing_policy_version
evidence_snapshot_version
selection_reason_codes
created_at
```

### Execution records

Representative fields:

```text
execution_id
task_attempt_id
parent_execution_id?
execution_role
capability_id
capability_version
model_id?
model_version?
provider?
strategy_stage
started_at
finished_at
result_class
input_tokens?
output_tokens?
cost?
latency?
trace_id
span_id
```

Execution roles include:

```text
PRIMARY
REPAIR
FALLBACK
EVALUATOR
TOOL
ARTIFACT
RECONCILIATION
```

## Validation results

Deterministic validation results are first-class durable records:

```text
validation_result_id
task_attempt_id
execution_id
validator_id
validator_version
PASS | FAIL | WARNING
reason_codes
metrics
created_at
```

## Evaluation runs

Evaluation is represented explicitly with evaluator provenance:

```text
evaluation_run_id
subject_task_attempt_id
subject_execution_id?
evaluator_type
evaluation_spec_id
evaluation_spec_version
evaluator_model_id?
evaluator_model_version?
result
scores
reason_codes
created_at
```

Evaluator types:

```text
DETERMINISTIC
HEURISTIC
MODEL
HUMAN
```

Evaluation is bounded by `TaskSpec.evaluation_policy`; evaluator chains cannot recurse without limit.

## Evidence model

Production execution creates an `EvidenceObservation`, not an immediate routing score.

Many observations may be qualified and aggregated into `ModelEvidence`.

Lifecycle:

```text
OBSERVED
    ↓
QUALIFIED
    ↓
PROMOTED
    ↓
DEPRECATED
```

Only promoted aggregated evidence may influence routing.

Qualification may consider sample size, TaskSpec compatibility, evaluation completeness, statistical confidence, failure rate, human agreement, freshness and benchmark-vs-production source.

## Version identity

Lineage identifies everything capable of changing meaning:

```text
TaskSpec version
workflow definition version
ContextPackage identity
model + model version
provider
routing-policy version
Control Plane policy version
capability version
validator version
evaluation-spec version
instruction/template version
```

Prompt/instruction content is referenced by identity/version rather than copied into observability records by default.

## Privacy / capture levels

```text
METADATA_ONLY     # production default
REDACTED
DEBUG_CONTENT
DISABLED
```

`DEBUG_CONTENT` requires explicit enablement, short retention and sensitivity-policy enforcement.

Raw CVs, job descriptions, prompts, model outputs and personal evidence are not automatically placed in traces.

## OpenTelemetry mapping

Typical trace:

```text
workflow.run
   └── workflow.step
          └── task.attempt
                 ├── context.resolve
                 ├── policy.evaluate
                 ├── model.route
                 ├── execution.primary
                 │      └── validation
                 ├── execution.repair
                 └── evaluation
```

Spans carry durable Hatch identifiers for correlation.

OTel exporter/backend failure must not corrupt task correctness. Audit/correctness-critical facts remain durably persisted by Hatch.

## Persistence proportionality

Initially persist what is required to answer:

```text
What happened?
Why?
Which model/tool?
What context/policy/version?
Did validation pass?
Was repair/fallback used?
How long?
How many tokens?
How much did it cost?
How good was the result?
Should this evidence influence future routing?
```

Do not create a token-level research warehouse.

## Invariants

1. Workflow/task IDs are the durable correlation spine.
2. OTel IDs correlate to runtime records; OTel is not authoritative runtime state.
3. One TaskAttempt may contain multiple ExecutionRecords.
4. Audit/explanation-critical policy and routing decisions are durable.
5. Routing records preserve the candidate snapshot.
6. Deterministic validation results are first-class records.
7. Evaluations preserve evaluator provenance and version.
8. Production runs create observations, not automatic routing changes.
9. Only qualified/promoted aggregated evidence influences routing.
10. Evidence is TaskSpec/version aware.
11. Raw sensitive AI content is not captured by default.
12. Telemetry-export failure cannot corrupt workflow correctness.
13. Repair, fallback and reconciliation lineage is reconstructable.
14. Evaluation is bounded by TaskSpec policy.
15. Retention may differ for durable audit facts, telemetry and debug content.

---

## ARCH-06R1 — Storage Backend Evolution

**Status: Approved — Option C**

ARCH-06 is refined from a SQLite-specific kernel into a **relational durable-state contract**.

```text
Workflow Kernel
      ↓
Durable State Contract
   ┌───────────────┴───────────────┐
   ↓                               ↓
SQLite / WAL                    PostgreSQL
default/local                   scale-up
```

### Architecture rule

Durable relational semantics are architectural.

SQLite is the initial/default deployment choice.

PostgreSQL is the designed scale-up backend.

### Required durable-store semantics

```text
atomic multi-record transaction
conditional update / compare-and-set
unique constraints
monotonic fencing tokens
durable lease + not_before semantics
transactional state + event + outbox write
safe claim acquisition
schema migrations
structured payload storage
crash-safe commit / rollback
```

The Workflow Kernel depends on these semantics rather than SQLite-specific locking behavior.

### Backend-specific implementation is allowed

The abstraction is semantic, not a generic SQL framework.

Representative operations may be implemented differently per backend:

```text
SQLite
  conditional UPDATE
  short write transactions
  fencing-token checks

PostgreSQL
  row-level locking
  queue-friendly claim patterns
  fencing-token checks
```

The application-visible contract remains identical.

### Scale-up triggers

Migration to PostgreSQL is driven primarily by topology/concurrency requirements, including:

```text
multi-host workers
high availability / failover requirements
measurable sustained write contention
unacceptable claim/scheduling latency
outbox backlog caused by DB contention
```

Database size alone is not the primary trigger.

### Invariants

- SQLite remains the default easy-install backend.
- PostgreSQL is not mandatory for current Hatch deployment.
- Workflow, Control, Execution, Context, routing and evaluation logic must not depend on SQLite-only behavior.
- Backend-specific concurrency SQL may exist behind semantic store operations.
- The migration path must not require rewriting workflow semantics.

---

# 15. ARCH-10 — Migration Architecture

**Status: Approved**

Selected direction:

> **Strangler migration with one target runtime, a thin compatibility facade, slice-level LEGACY/SHADOW/NEW cutover, job scoring as the first end-to-end proof, and Coach Phase 1 kernel extraction before Coach Phase 2.**

## Target shape

```text
Legacy Hatch feature
       │
       ▼
Compatibility Facade
       │
       ▼
    TaskSpec
       │
       ▼
   New Runtime
       │
 ┌─────┼─────────────┐
Context Intelligence Control
       │
       ▼
Execution Gateway
       │
       ▼
Workflow / Durable State
```

New and migrated features call the new runtime directly. Legacy callers may temporarily reach it through the compatibility facade.

## Package ownership

Architectural ownership is divided across:

```text
runtime/contracts
runtime/workflow
runtime/control
runtime/context
runtime/intelligence
runtime/execution
runtime/events
runtime/evaluation
runtime/observability
runtime/storage
```

Exact code-package names remain implementation-level detail.

## Compatibility facade

The facade only performs contract translation:

```text
legacy input → typed TaskSpec input
new result   → legacy response contract
```

It must not duplicate routing, retry, policy, context-resolution or workflow logic.

## Execution ownership modes

Each vertical slice is configured as exactly one of:

```text
LEGACY
SHADOW
NEW
```

- `LEGACY`: old runtime authoritative.
- `SHADOW`: old runtime authoritative; new runtime observational only.
- `NEW`: new runtime authoritative.

A single request must never have two authoritative execution paths.

## Shadow-mode safety

Shadow mode is suitable for non-committing AI work such as:

```text
job scoring
CV tailoring
cover-letter generation
Coach evaluation
```

It must not duplicate committing side effects such as sending emails, submitting applications or publishing externally.

## Migration order

```text
Slice 0 — Runtime foundation
Slice 1 — Job scoring
Slice 2 — CV tailoring
Slice 3 — Cover-letter generation
Slice 4 — Coach Phase 1 runtime migration
Slice 5 — Coach Phase 2
```

### Slice 0 — Runtime foundation

Implement the minimum production-capable foundation:

```text
TaskSpec
DurableStateStore
Workflow Kernel
Control primitives
Execution Gateway
Context Resolver
Model Router
Events/outbox
ARCH-09 lineage
```

### Slice 1 — Job scoring

Job scoring is the first end-to-end proof because it exercises typed inputs/outputs, context, routing, validation, evaluation, telemetry and fallback without dangerous side effects.

Migration:

```text
LEGACY → SHADOW → NEW
```

### Slice 2 — CV tailoring

Adds richer candidate evidence, groundedness validation, context selection and artifact behavior.

### Slice 3 — Cover-letter generation

Reuses the migrated context/runtime foundations and must not create a separate parallel architecture.

### Slice 4 — Coach Phase 1 runtime migration

Extract Coach-specific async reconciliation, late-worker protection, retry processing and durable answer/report-job behavior into generic Workflow Kernel primitives.

Coach becomes a consumer of:

```text
claims
leases
fencing
attempts
retry policy
reconciliation
```

rather than retaining bespoke durability logic.

### Slice 5 — Coach Phase 2

Coach Phase 2 begins only after the generic runtime is proven and Coach Phase 1 is operating on the new foundation.

## Domain-data migration

Prefer adaptation over mass-copying:

```text
existing domain data
      ↓
ContextProvider
      ↓
semantic context capability
```

Runtime-specific state receives new tables/records. Domain data remains owned by the domain.

## Schema migration strategy

Prefer:

```text
ADD
MIGRATE
VERIFY
RETIRE CALLER
RETIRE OLD STATE/CODE
REMOVE SCHEMA
```

Avoid destructive schema cleanup before the migrated path has passed its retirement gate.

## Migration flags

Migration mode is resolved once at the feature entry boundary rather than scattered throughout implementation code.

## Rollback rule

Migration-mode changes affect new requests only.

A durable WorkflowRun remains on the runtime that owns it until completion or reconciliation; it is never switched between legacy and new engines mid-flight.

## Runtime identity

Migrated invocations receive the new runtime identifiers even when invoked through the compatibility facade:

```text
workflow_run_id
workflow_step_id
task_attempt_id
```

## Storage seam

Application/runtime logic uses semantic store boundaries such as:

```text
WorkflowStore
EventStore
OutboxStore
EvaluationStore
```

The initial backend is SQLite/WAL; PostgreSQL remains the scale-up backend.

Vertical slices must not depend on PostgreSQL availability.

## Retirement gate

A legacy path is removed only after the migrated path demonstrates:

```text
correctness parity or improvement
required quality/eval threshold
process-restart recovery
retry/fallback correctness
acceptable latency/cost
observability completeness
no unresolved migration-critical defects
```

AI-output migration is judged by semantic correctness and quality, not byte-identical output.

## Invariants

1. There is one target runtime architecture.
2. Compatibility facade translates contracts only.
3. Each request has one authoritative execution path.
4. Shadow execution never duplicates committing side effects.
5. Job scoring is the first end-to-end migration proof.
6. Existing domain data is adapted where possible rather than mass-copied.
7. Runtime schema changes are additive before destructive cleanup.
8. Migration mode is LEGACY / SHADOW / NEW per vertical slice.
9. A running WorkflowRun never switches engines mid-flight.
10. New runtime IDs exist even behind the compatibility facade.
11. Storage backend choice does not leak into domain workflows.
12. Legacy code is removed only after explicit retirement gates.
13. Coach Phase 1 bespoke durability/reconciliation logic is extracted into the generic kernel before Coach Phase 2.
14. PostgreSQL remains a scale-up path, not a prerequisite for the migration.

---

# 16. ARCH-11 — Testing and Architecture Invariants

**Status: Approved — Option B**

Selected direction:

> **Conventional test pyramid + named architecture-invariant suite + deterministic failure injection.**

The runtime is tested not only for successful outputs but for the architectural guarantees it is intended to provide under failure, retry, concurrency and recovery.

## Test layers

```text
L1 Contract tests
L2 Component / invariant tests
L3 Durable workflow failure tests
L4 Vertical-slice integration tests
L5 Migration / shadow parity tests
```

Large end-to-end tests are not the primary proof of runtime correctness.

## Named invariant suite

Architecture promises receive stable IDs, for example:

```text
INV-WF-001  stale worker cannot finalize newer claim
INV-WF-002  retry creates a new immutable attempt
INV-CTL-001 FORCE model cannot bypass policy
INV-EVT-001 state and event commit atomically
```

These IDs may be referenced by implementation specs, tests and reviews.

## Durable-store conformance

The same semantic contract suite applies to every `DurableStateStore` backend.

```text
DurableStateStoreContractTests
    ├── SQLite
    └── PostgreSQL
```

Backend SQL may differ; externally visible workflow semantics must not.

## Workflow-kernel tests

Must directly exercise:

```text
claims
leases
fencing
attempt immutability
not_before
durable waiting
approval resume
restart recovery
reconciliation
```

Fencing tests use real persistence behavior rather than mocks alone.

## Deterministic time and identity

Lease, deadline, retry, approval-expiry and scheduling tests use injectable:

```text
Clock
ID generator
```

rather than real sleeps.

## Failure injection

Named failure points include scenarios such as:

```text
FAIL_AFTER_CLAIM_COMMIT
FAIL_AFTER_MODEL_RESULT_BEFORE_FINALIZE
FAIL_AFTER_STATE_UPDATE_BEFORE_EVENT_INSERT
FAIL_AFTER_EXTERNAL_SIDE_EFFECT_BEFORE_RESULT_PERSIST
FAIL_AFTER_OUTBOX_DELIVERY_BEFORE_ACK
```

Recovery expectations are explicit for each failure point.

## Approval tests

Verify:

```text
exact-payload binding
approval invalidation on payload change
restart durability
workflow scoping
capability scoping
```

## Control-plane tests

Verify policy precedence and that user/model preferences cannot weaken higher-level constraints.

## Context-plane tests

Verify:

```text
undeclared context is not silently fetched
minimum-necessary package
per-attempt immutability
provenance preservation
sensitivity preservation
progressive disclosure
fresh retry may resolve a new package without mutating old history
```

## Router tests

Exercise gating in order:

```text
capability
quality floor
policy
ranking
fallback
```

Durable routing records must preserve exclusion reasons and the candidate snapshot.

## Execution-gateway tests

Exercise:

```text
PURE
READ_ONLY_EXTERNAL
PREPARE_SIDE_EFFECT
COMMIT_SIDE_EFFECT
```

and all idempotency classes.

Tool visibility must not imply execution permission.

## Ambiguous external outcomes

`OUTCOME_UNKNOWN` scenarios are explicitly simulated.

Ambiguous committing side effects reconcile instead of blindly retrying.

## Event / outbox tests

Failure injection verifies state/event/outbox atomicity around transaction and publisher boundaries.

At-least-once delivery tests intentionally redeliver events and verify idempotent consumers create only one business effect.

## Observability tests

Verify runtime correlation across:

```text
workflow_run_id
workflow_step_id
task_attempt_id
execution_id
```

including primary → repair → fallback → evaluation lineage.

OTel exporter failure must not fail otherwise-correct workflow execution.

## Privacy leakage tests

Capture-mode tests use sentinel content and assert sensitive content is absent from unauthorized:

```text
runtime events
OTel attributes
policy records
routing records
evaluation metadata
logs
```

Production default remains metadata/reference oriented.

## Concurrency tests

Exercise multi-worker contention for:

```text
task claims
workflow finalization
outbox publication
retry scheduling
evaluation writes
```

SQLite tests additionally measure/validate bounded contention handling such as `SQLITE_BUSY`.

The same semantic cases later run against PostgreSQL.

## Vertical-slice acceptance

### Job scoring

Exercises:

```text
TaskSpec
context
policy
routing
execution
validation
evaluation
lineage
fallback
```

### CV tailoring

Adds evidence grounding, progressive disclosure, unsupported-claim validation and artifact behavior.

### Cover letter

Adds job/candidate grounding, output constraints and reuse of shared runtime/context infrastructure.

### Coach

Adds durable processing, answer/report jobs, retries, reconciliation, late-worker completion and waiting states.

## Shadow migration tests

In `SHADOW` mode:

```text
legacy output = authoritative
new output = evaluation-only
```

Compare semantic correctness, quality, validation pass rate, latency, cost and failure rate rather than requiring byte-identical outputs.

## Golden regression datasets

Maintain curated datasets for:

```text
job scoring
CV tailoring
cover letters
Coach evaluation
```

including difficult/edge cases.

## CI tiers

```text
FAST
normal unit/contract tests

RUNTIME
DB, workflow and integration tests

DEEP
failure injection, concurrency, migration and evaluation suites
```

Exact execution cadence belongs to the implementation specification.

## Invariants

1. Architecture invariants have named executable tests.
2. Durable-store semantics are backend-neutral at the contract level.
3. Fencing is tested against real persistence.
4. Crash/restart recovery never relies on process-local state.
5. Retry creates new immutable attempts.
6. Waiting states hold no worker.
7. Approval is exact-payload bound.
8. Policy precedence cannot be weakened by user preferences.
9. Context packages remain immutable per attempt.
10. Router exclusion reasons and candidate snapshots are testable.
11. Ambiguous external outcomes reconcile rather than blindly retry.
12. State/event/outbox atomicity is failure-injection tested.
13. At-least-once consumers are tested for duplicate delivery.
14. OTel failure cannot fail correct workflow execution.
15. Privacy capture modes have automated leakage tests.
16. Lease/deadline/backoff tests use deterministic clocks.
17. SQLite contention and stale-writer behavior are tested.
18. SQLite and PostgreSQL satisfy the same durable-state semantics.
19. Shadow migration compares semantic quality, not string equality.
20. Vertical-slice gates include correctness, recovery, quality, cost/latency and observability.

---

# 17. ARCH-12 — Implementation Phases and Coach Phase 2 Boundary

**Status: Approved — Option B**

Selected direction:

> **Gated foundation + vertical proofs. Implement the production-capable core, prove it with job scoring, progressively migrate CV tailoring and cover letters, extract Coach Phase 1 durability into the generic kernel, then unlock Coach Phase 2 implementation.**

Coach Phase 2 specification work may continue earlier, but implementation remains behind the final runtime gate.

## Phase 0 — Characterize the current system

Capture migration baselines for:

```text
job scoring
CV tailoring
cover-letter generation
Coach Phase 1
existing retry/reconciliation behavior
telemetry
database schema
golden datasets
```

Exit criterion: enough characterization exists to determine whether migration breaks existing behavior or quality.

## Phase 1 — Runtime contracts + persistence spine

Implement:

```text
TaskSpec
runtime identifiers
DurableStateStore contract
SQLite/WAL backend
workflow/task persistence
runtime events
durable outbox
ARCH-09 correlation primitives
schema migrations
```

PostgreSQL receives the designed contract/conformance seam, but a production PostgreSQL backend is not required yet.

## Phase 2 — Durable Workflow Kernel

Implement:

```text
WorkflowDefinition
WorkflowRun
WorkflowStep
TaskAttempt
atomic claims
leases
fencing tokens
retry / not_before
waiting states
approval persistence
reconciliation primitives
```

Reliability behavior is implemented together with deterministic failure tests.

## Phase 3 — Control + Execution

Implement the minimum production-capable:

```text
Control Plane
Execution Gateway
ALLOW / DENY / REQUIRE_APPROVAL
policy precedence
capability authorization
side-effect classification
idempotency semantics
typed results
deadline/cancellation
OUTCOME_UNKNOWN reconciliation
```

Only capabilities required by the migration slices are needed initially.

## Phase 4 — Context + Intelligence + Evaluation

Implement:

```text
ContextResolver
CapabilityRegistry
ContextProviders
ContextPackage
ModelDescriptor
Model Router
validators
evaluation runs
evidence observations
OpenTelemetry integration
```

Scope remains driven by job scoring, CV tailoring, cover letters and Coach.

## Phase 5 — Job Scoring architecture proof

Migration:

```text
LEGACY → SHADOW → NEW
```

Job scoring is the first complete architecture acceptance slice.

It must prove:

```text
TaskSpec
Context Plane
Control Plane
Router
Execution Gateway
Workflow Kernel
validation
evaluation
events
observability
recovery
```

Promotion from SHADOW to NEW requires acceptable correctness, quality, recovery, routing explainability, privacy, latency, cost and fallback behavior.

## Phase 6 — CV Tailoring

Migration:

```text
LEGACY → SHADOW → NEW
```

This is the primary proof of richer Context Plane behavior:

```text
candidate evidence
verified experience
achievements
job requirements
progressive disclosure
grounding
unsupported-claim detection
artifact generation
```

Groundedness remains a correctness constraint.

## Phase 7 — Cover Letter

Migration:

```text
LEGACY → SHADOW → NEW
```

This slice must substantially reuse migrated candidate/job context, routing, validation and artifact/output infrastructure.

## Phase 8 — Coach Phase 1 kernel extraction

Move generic Coach durability/concurrency semantics out of Coach-specific infrastructure:

```text
async jobs
answer processing
report building
stale reconciliation
retry processing
late-worker protection
```

into generic Workflow Kernel primitives:

```text
claims
leases
fencing
attempts
retry policy
waiting
reconciliation
```

Coach-specific domain behavior remains in Coach.

## Coach Phase 2 hard entry gate

Coach Phase 2 implementation starts only when all required runtime, reliability, migration, Coach-specific and observability conditions are satisfied.

### Runtime gate

```text
✓ TaskSpec production usable
✓ relational DurableStateStore contract established
✓ SQLite backend production usable
✓ Workflow Kernel production usable
✓ Control Plane active
✓ Execution Gateway active
✓ Context Resolver active
✓ task-aware Model Router active
✓ ARCH-09 lineage active
```

### Reliability gate

```text
✓ claim / lease / fencing tests pass
✓ restart recovery passes
✓ retry-attempt immutability passes
✓ OUTCOME_UNKNOWN reconciliation works
✓ event/outbox atomicity passes
✓ approval binding passes
```

### Migration gate

```text
✓ Job Scoring = NEW
✓ CV Tailoring = NEW
✓ Cover Letter = NEW
✓ Coach Phase 1 durability/reconciliation migrated onto generic kernel
```

### Coach-specific gate

```text
✓ late-worker protection preserved or strengthened
✓ answer/report finalization fenced
✓ Coach retry policy uses generic retry semantics
✓ process restart does not depend on asyncio state
✓ existing Phase 1 acceptance tests remain green
```

### Observability gate

```text
✓ Coach workflow lineage reconstructable
✓ policy/routing decisions explainable
✓ repair/fallback lineage visible
✓ OTel failure cannot break Coach execution
✓ sensitive content not persisted by default
```

## Non-blockers for Coach Phase 2

Coach Phase 2 does not wait for:

```text
every Hatch AI feature migrated
all legacy paths removed
PostgreSQL production implementation
multi-host support
MCP everywhere
all future ContextProviders
all model/provider integrations
perfect benchmark datasets
advanced automated evidence promotion
large-scale telemetry infrastructure
microservices
```

The gate is minimum production-complete architecture proven through critical slices.

## Phase 9 — Coach Phase 2

Coach Phase 2 is implemented as typed workflows and TaskSpecs on the shared Hatch Runtime rather than creating another bespoke async/routing/evaluation subsystem.

## Formal implementation gates

```text
GATE R1
Runtime Core Ready
Phases 1–4

        ↓

GATE R2
Architecture Proven
Job Scoring = NEW

        ↓

GATE R3
Core Generation Migrated
CV Tailoring + Cover Letter = NEW

        ↓

GATE R4
Coach Runtime Ready
Coach Phase 1 on generic kernel

        ↓

COACH PHASE 2 IMPLEMENTATION
```

## Invariants

1. Architecture implementation is incremental and gated.
2. Reliability primitives ship with failure tests rather than being retrofitted later.
3. Job scoring is the first full runtime acceptance slice.
4. CV tailoring proves richer Context Plane behavior.
5. Cover-letter migration reuses shared runtime infrastructure.
6. Coach Phase 1 bespoke durability/reconciliation semantics are extracted into the generic kernel.
7. Coach Phase 2 specification work may proceed earlier; implementation remains behind R4.
8. PostgreSQL implementation is not a Coach Phase 2 prerequisite.
9. Noncritical legacy Hatch consumers do not block Coach Phase 2.
10. Every phase has objective exit criteria.
11. Migration remains rollback-capable until retirement gates pass.
12. Architecture work stops at production-complete foundations rather than expanding into speculative platform engineering.

---

# Architecture Design Closure

**Architecture status: COMPLETE**

Approved decisions:

```text
ARCH-00  Migration strategy
ARCH-01  TaskSpec
ARCH-02  Context Plane
ARCH-03  Intelligence Plane
ARCH-04  Evaluation + Observability
ARCH-05  Control Plane
ARCH-06  Durable Workflow Kernel
ARCH-06R1 Relational durable-state contract
ARCH-07  Execution Gateway
ARCH-08  Events + Durable Outbox
ARCH-09  Observability/Evaluation Data Model — Option B
ARCH-10  Strangler Migration Architecture
ARCH-11  Testing + Architecture Invariants — Option B
ARCH-12  Implementation Phases + Coach Phase 2 Boundary — Option B
```

No architecture section remains open.

The next artifact is the **Architecture Foundation Implementation Specification**.

That specification should consume this document as the authoritative architecture baseline and should not reopen approved decisions unless implementation evidence reveals a genuine blocker.

---

# 18. Explicitly Rejected for This Architecture Phase

The following are intentionally out of scope unless new evidence justifies reopening them:

```text
❌ wholesale OpenAI Agents SDK migration
❌ Google ADK migration
❌ LangGraph as core orchestration
❌ MCP-first internal architecture
❌ microservices
❌ Kubernetes
❌ Kafka
❌ Redis
❌ Temporal
❌ autonomous policy LLM
❌ self-modifying model router
❌ giant supervisor agent
```

The intent is to adopt useful architectural patterns without chasing framework dependencies.

---

# 19. Open Review Queue

**No architecture decisions remain open.**

Next workstream:

```text
Architecture Foundation Implementation Specification
```

The implementation specification should use this file as the architecture baseline and preserve the approved decision IDs for traceability.

---

# 20. Compact Checkpoint Format

After every 2–3 reviewed sections, use:

```text
APPROVED
- ARCH-xx ...
- ARCH-yy ...

OPEN
- ARCH-zz ...

CHANGED
- ...

RISKS
- ...

NEXT
- ...
```

This replaces long recap messages.

---

# 21. New-Conversation Handoff Rule

Do not move the full chat history into implementation threads.

A new thread should receive only:

1. the current version of this architecture document;
2. a compact handoff brief;
3. the latest relevant code/repository snapshot;
4. the exact phase objective.

Suggested thread boundaries:

```text
Chat A — Architecture Foundation Design
Chat B — Architecture Foundation Implementation Spec
Chat C — Architecture Foundation Implementation / Review
Chat D — Coach Phase 2 Spec
Chat E — Coach Phase 2 Implementation
```

This file, not the old conversation, is the architectural source of truth.
