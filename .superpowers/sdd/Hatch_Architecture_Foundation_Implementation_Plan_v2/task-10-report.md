# Task 10 — R4 Model Routing Evidence

## Scope and authority

- Baseline reviewed: `7779df4`.
- Implemented: metadata-only `ModelDescriptor` registry, deterministic five-stage
  router, durable candidate snapshots, and explicit evidence promotion.
- Binding invariants: `INV-RTR-001`, `INV-RTR-002`, `INV-RTR-003`, plus the R3
  `INV-CTL-003` and execution authorization regression boundary.
- Authorities read: Task 10 brief; the R4 Model registry/router/evidence sections
  of the active implementation plan/specification; and the Architecture v8
  routing/evidence/durable-decision sections.

## Implementation

- `ModelRegistry.from_configured_models()` uses the profile catalog exposed by
  `llm_factory.configured_model_catalog()`. It does not construct a LangChain
  client or make a provider/network call. Stable Hatch `model_id` and provider-native
  `model_name` remain separate.
- `ModelRouter` evaluates gates in fixed order: capability, quality, policy,
  evidence, fallback. Every configured candidate receives eligibility, stable
  exclusion codes, rank components, and final rank in the decision snapshot.
- `AUTO` ranks eligible candidates; `PREFER` boosts only an eligible matching
  descriptor; `FORCE` selects only an eligible matching descriptor after all
  mandatory gates.
- `RoutingPreferences.model_capabilities` remains compatibility-only and does not
  prove a capability. `ControlPlane` accepts an explicit trusted capability handoff,
  and `ExecutionGateway` accepts a selected trusted descriptor, keeping arbitrary
  payload model/provider values from becoming authorization.
- Observations are immutable and inactive. Only
  `promote_model_evidence(observation_ids, qualification)` creates routing-active,
  bounded aggregate evidence.
- The additive Alembic revision `w0x1y2z3a4b5` adds explicit routing decision
  snapshot/task/model/evidence fields; no structured snapshot is placed in
  `reason_codes_json`.

## TDD record

1. Initial router/evidence/snapshot tests were added before the package existed.
   Authoritative initial RED: `ModuleNotFoundError: app.runtime.intelligence`
   during collection for all three Task 10 modules.
2. Trusted Control Plane handoff test RED: `TypeError: ControlPlane.evaluate()`
   did not accept `trusted_model_capabilities`.
3. Execution Gateway descriptor handoff test RED: `TypeError:
   ExecutionGateway.invoke()` did not accept `model_descriptor`.
4. Minimal implementation produced the GREEN results below. The added tests name
   the removed/incorrect production behavior they catch rather than checking mocks.

## Verification

All test invocations used the local, isolated Python 3.12 backend container with
synthetic fixtures only. No provider client or external model service was invoked.

| Gate | Result |
| --- | --- |
| Task 10 focused + model discovery | `10 passed, 2 warnings` (initial GREEN) |
| Final Task 10 focused + schema migration | `16 passed, 2 warnings in 18.06s` |
| Affected R3 Control/Execution/migration regression selection | Exit `0`; full selection passed. Terminal output was capped after 72% of named passing cases; the final focused schema/migration rerun independently completed `16 passed`. |
| Ruff check (`--no-cache`, scoped Task 10 paths) | `All checks passed!` |
| Ruff format check (`--no-cache`, scoped Task 10 paths) | `17 files already formatted` |
| Documentation validation | `Documentation validation passed.` |
| `git diff --check` | Exit `0`, no output (run before report creation; repeated in final handoff gate) |

The two pytest warnings are the known bind-mounted `.pytest_cache` permission
warnings in the non-root container user; they do not expose application data or
affect results.

## Security and privacy disposition

- Scope: model routing, policy/execution capability handoff, routing/evidence
  persistence. No Coach command, media, transcript, deletion, export, or telemetry
  path is modified.
- Durable routing metadata is restricted to stable IDs, versions, provider IDs,
  rank/exclusion metadata, and evidence snapshot identity. It contains no prompts,
  CV/job/transcript content, model outputs, secrets, tokens, or user-controlled
  paths.
- No binding security finding remains from the implemented scope. The existing
  metadata-only persistence guard is used for candidate snapshots and metrics.

## Limitations

- The persistent evaluation store exposes a minimal `record_model_evidence` seam;
  application orchestration that loads observations and invokes promotion is outside
  Task 10's router contract.
- The authoritative comprehensive backend suite is controller-owned and was not run
  in this task. The required focused Task 10, model-discovery, R3 Control/Execution,
  and migration selections were run.
