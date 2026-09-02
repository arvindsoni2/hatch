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

## Fix round 1 — review hardening

### RED evidence

Before the fix, the local focused RED command was:

```text
python -m pytest -q --no-cov tests/runtime/test_model_router.py \
  tests/runtime/test_evidence_promotion.py tests/runtime/test_intelligence_bounds.py
# 5 failed, 6 passed.
```

The expected failures proved absent registry-issued selection proofs, missing
context/privacy/fallback contracts, duplicate promotion acceptance, an unbounded
registry, and acceptance of long body-like metadata under an innocuous key.

### Changes

- Registry-issued HMAC-sealed selection proofs now bind model ID/version/provider;
  Control Plane and Gateway verify the proof through the issuing registry instead
  of trusting caller-provided capabilities or descriptors.
- Requirements enforce bounded context and privacy levels. Fallback IDs are bounded,
  ordered, independently eligible, and disabled for FORCE.
- Config catalog descriptors have neutral default quality/rank and a canonical
  configuration-derived version; snapshots include provider-native model name.
- Evidence activation is private to qualification, rejects duplicate observation
  IDs and invalid thresholds/versions, and validates all aggregate invariants.
- Promoted evidence now has durable lineage fields and UoW persistence/load seams;
  the additive `x1y2z3a4b5c6` migration preserves one migration head.
- Registry, fallback, observation/promotion, candidate metadata and body-like
  string bounds are enforced before durable persistence.

### GREEN evidence and remaining gates

After implementation, the local expanded selection reported `27 passed in 12.61s`:

```text
python -m pytest -q --no-cov tests/runtime/test_model_router.py \
  tests/runtime/test_evidence_promotion.py tests/runtime/test_intelligence_bounds.py \
  tests/runtime/test_policy_force_model.py \
  tests/runtime/test_execution_gateway.py::test_gateway_accepts_only_a_trusted_selected_descriptor \
  tests/runtime/test_router_candidate_snapshot.py tests/runtime/test_schema_migration.py
```

Final authoritative Python 3.12 container commands and results are recorded in the
fix-round handoff after their execution. The final selected Python 3.12 command
exited `0` after all named routing, evidence, Control, Gateway, storage, schema,
migration bootstrap, and model-discovery modules passed; the tool's output cap
truncated the terminal display after 77% of individual pass lines.

Exact final container gate:

```text
docker run --rm --entrypoint python -v <worktree>/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest -m pytest -q --no-cov \
  tests/runtime/test_model_router.py tests/runtime/test_router_candidate_snapshot.py \
  tests/runtime/test_evidence_promotion.py tests/runtime/test_intelligence_bounds.py \
  tests/runtime/test_policy_force_model.py tests/runtime/test_execution_gateway.py \
  tests/runtime/test_schema_migration.py tests/runtime/test_storage_contract.py \
  tests/test_services/test_model_discovery.py tests/test_migrations/test_database_setup.py
# exit 0; only bind-mounted pytest-cache warnings.
```

Final scoped Ruff check passed, `ruff format` reported `19 files left unchanged`,
`python /workspace/scripts/check_docs.py` reported documentation validation passed,
and both staged and post-commit `git diff --check` commands exited zero.

## Fix round 2 — trusted composition and durability-first promotion

### RED evidence

The first focused constructor-migration run reported two expected failures: the
old test setup still passed a per-call registry, and a Control Plane without its
composition-owned registry correctly denied the selected route. This proved the
raw verifier seam had been removed before the callers were migrated.

### GREEN evidence

```text
python -m pytest -q --no-cov tests/runtime/test_evidence_promotion.py \
  tests/runtime/test_policy_force_model.py tests/runtime/test_execution_gateway.py
# 32 passed in 3.08s
```

This selection covers fake verifier rejection, cross-registry proof rejection,
missing proof fail-closed behavior, and durability-first promotion (a failing
flush leaves the routing evidence snapshot unchanged). Candidate snapshots are
also revalidated at the SQLite boundary for type, finite numeric fields, bounded
counts, canonical form, and total serialized size. Promotion now accepts only a
typed `ModelEvidence`, recomputes its deterministic lineage identity, treats exact
replay as idempotent, and rejects conflicting identity reuse. Reload requires the
referenced immutable observations and recomputes the aggregate; incomplete rows
remain inactive.

Additional replay GREEN:

```text
python -m pytest -q --no-cov tests/runtime/test_evidence_promotion.py
# 5 passed in 0.09s
```

It explicitly verifies persistence failure leaves no active evidence and that
forged evidence IDs, aggregate sample tampering, missing observation lineage, and
raw promoted rows without observations all fail closed during reconstruction.

## Fix round 3 — final registry authority and durable observation replay

### RED evidence

Adding the required additive lineage migration caused the expected single-head
RED: `test_runtime_migration_has_one_head` expected `x1y2z3a4b5c6` and received
`y2z3a4b5c6d7`. This confirms the schema change is independently visible.

### GREEN evidence

```text
python -m pytest -q --no-cov tests/runtime/test_evidence_promotion.py \
  tests/runtime/test_policy_force_model.py tests/runtime/test_execution_gateway.py \
  tests/runtime/test_schema_migration.py
```

The focused run passed the promotion/replay and Control/Gateway portions before
terminal output truncation. It covers final/non-subclassable registry injection,
instance verifier monkeypatch rejection, threshold-inclusive deterministic
identity, exact `promoted` evidence type, and reconstruction solely through typed
durable evaluation-store loaders. The additive `y2z3a4b5c6d7` migration carries
minimum qualification threshold and typed routing-observation identity/aggregate
columns; generic observations remain compatible.

## Fix round 4 — exact verifier and replay values

### RED/GREEN evidence

The round began by exercising the former mutable class-authority and replay
tolerance seams. The final focused green command was:

```text
python -m pytest -q --no-cov tests/runtime/test_policy_force_model.py \
  tests/runtime/test_evidence_promotion.py
# 16 passed in 0.13s
```

`ModelRegistry` now rejects class replacement/deletion of verification authority,
and Control/Gateway capture the verified concrete closure during trusted
composition. Reload requires an exact promoted type, persisted threshold, exact
row count and ID set, and exact canonical quality value. Evidence and observations
reject float/bool integer fields; quality is canonicalized once to the storage
precision; descriptor rank, quality, and context-window inputs are finite/bounded.

## Fix round 5 — composition-field immutability

### RED/GREEN evidence

```text
python -m pytest -q --no-cov \
  tests/runtime/test_policy_force_model.py::test_control_composition_verifier_fields_are_immutable
# RED: Failed: DID NOT RAISE (before implementation)

python -m pytest -q --no-cov tests/runtime/test_policy_force_model.py \
  tests/runtime/test_evidence_promotion.py
# 17 passed in 0.09s
```

Control and Gateway now make their captured verifier and registry references
write/delete-protected after construction. Model evidence is final, and routing
requirements use the same finite canonical quality and exact integer rules as
evidence contracts.
