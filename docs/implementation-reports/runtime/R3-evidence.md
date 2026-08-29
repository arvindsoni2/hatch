# R3 typed execution gateway evidence

## Scope and immutable provenance

- Recorded R3 base: `69dc8c9` on branch `runtime/r3-control-execution`.
- Architecture SHA-256: `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36`.
- Foundation spec SHA-256: `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`.
- Coach V6 SHA-256: `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`.
- Authoritative interpreter: Python 3.12.13 in the existing local image
  `localhost/job_pilot_v2_backend:latest`.

R3 adds the provider-generic typed capability registry, adapters, and execution
gateway under `app.runtime.execution`. Product ownership remains outside the generic
runtime: `app.runtime_bindings.capabilities` supplies only `job.local_score`,
`artifact.render_cv`, and `artifact.render_cover_letter`; the generic layer supplies
only `llm.generate_structured`. No internal function is exposed through MCP. The only
R2 extension is the semantic `WorkflowStore.persist_execution_result` seam and its
SQLite implementation, which atomically fence-checks the live claim, inserts the
execution record, and durably transitions an ambiguous attempt when required.

All verification uses bounded synthetic payloads, injected local adapters, and
disposable SQLite databases. No production or shared external provider was called.

## Invariant matrix

| Invariant | Implementation boundary | Independent evidence |
| --- | --- | --- |
| `INV-EXE-001` typed registration and resolution | Immutable `CapabilityDescriptor`, duplicate-safe `CapabilityRegistry`, strict Pydantic input/output validation | `test_gateway_strictly_validates_payload_and_typed_output`, `test_gateway_rejects_adapter_output_that_violates_descriptor`, `test_only_four_initial_capabilities_are_registered` |
| `INV-EXE-002` control and approval precede side effects | Fail-closed Control Plane allowlist check followed by exact durable, payload-bound approval verification | `test_visible_capability_is_not_automatically_authorized`, all four side-effect authorization cases, inherited policy precedence/force-model cases |
| `INV-EXE-003` deadlines, cancellation, and replay advice only narrow | Minimum policy/descriptor deadline, `asyncio.timeout`, uncaught external `CancelledError`, descriptor-constrained retry advice | `test_earlier_policy_deadline_and_budgets_reach_adapter`, `test_timeout_of_commit_is_outcome_unknown_not_retryable`, `test_external_cancellation_remains_cancellation`, all idempotency cases |
| `INV-EXE-004` external result persistence is fenced and ambiguous outcomes reconcile | Adapter call occurs before the short write UoW; claim/attempt/fence/lease are checked atomically before record insertion; `OUTCOME_UNKNOWN` stores a hashed reconciliation reference and releases the claim in the same UoW | `test_lost_external_commit_becomes_outcome_unknown`, `test_gateway_rejects_result_after_claim_loss`, affected R2 fencing/reconciliation gate |
| Privacy-safe evidence and telemetry | Durable metadata contains stable codes, classifications, latency, and hashes only; telemetry is content-free, emitted after persistence, and non-fatal | `test_canaries_never_enter_records_errors_logs_or_telemetry`, `test_idempotency_key_reaches_adapter_but_only_hash_is_persisted`, `test_success_is_typed_persisted_then_reported_with_nonfatal_telemetry`, inherited runtime privacy cases |

The gateway order is resolve, Control Plane authorization, payload-bound approval
verification when required, deadline/budget establishment, adapter invocation outside
a write transaction, typed result classification, fenced durable persistence, then
non-fatal telemetry. `OUTCOME_UNKNOWN` and non-retryable side effects always return
`retry_allowed=False`; the gateway contains no blind retry loop.

## TDD evidence

The five requested gateway test modules were created before their production
imports existed. The initial authoritative RED command was:

```text
docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov \
  tests/runtime/test_execution_gateway.py \
  tests/runtime/test_side_effect_authorization.py \
  tests/runtime/test_idempotency.py \
  tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_deadlines.py \
  tests/runtime/test_policy_precedence.py \
  tests/runtime/test_policy_force_model.py tests/runtime/test_fencing.py
# Exit 2 during collection: five expected ModuleNotFoundError failures for
# app.runtime.execution.
```

The first implementation run reached `15 passed, 1 failed`; the sole failure was a
test-helper `NameError` and was corrected in test code. A later adversarial test
forged an `ALLOW` decision while retaining an effective approval requirement. Its
module-only RED run reported `1 failed, 3 passed`: expected `policy_denied`, observed
`success`. The gateway was hardened to inspect both the decision label and effective
constraints; the same module then reported `4 passed`.

Final authoritative R3 gate:

```text
docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov \
  tests/runtime/test_execution_gateway.py \
  tests/runtime/test_side_effect_authorization.py \
  tests/runtime/test_idempotency.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_deadlines.py tests/runtime/test_policy_precedence.py \
  tests/runtime/test_policy_force_model.py tests/runtime/test_fencing.py
# 35 passed, 2 PytestCacheWarning warnings in 3.98s.
```

Affected R2 regression gate:

```text
docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov tests/runtime/test_fencing.py \
  tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py \
  tests/runtime/test_storage_contract.py tests/runtime/test_runtime_privacy.py
# 58 passed, 2 PytestCacheWarning warnings in 8.49s.
```

The warnings above are limited to the read-only bind mount preventing pytest cache
writes; they do not affect test execution.

## Full backend, static, documentation, and diff verification

The complete backend gate was run once with the whole worktree mounted so repository
scripts were visible and coverage redirected to a disposable writable path:

```text
docker run --rm --entrypoint python -e COVERAGE_FILE=/tmp/task8.coverage \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel:/workspace:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest -m pytest -q
# 3485 passed, 3 failed, 9 warnings in 740.44s; coverage 76.01%.
```

The failures were outside R3:

- `tests/benchmarks/test_runner.py::test_runner_ranks_gate_pass_rate_before_quality`
  received `working_tree_clean_before="not_recorded"` because Git metadata was not
  mounted into the container.
- `tests/benchmarks/test_staged_runner.py::test_two_fresh_restart_records_authorize_two_eighty_pair_runs`
  failed in the full run but passed on the immediate isolated rerun.
- `tests/test_migrations/test_database_setup.py::test_development_backend_runs_canonical_setup_before_server`
  raised `FileNotFoundError: make`; the existing backend image has no `make` binary.

The exact isolated three-test rerun reported `1 passed, 2 failed, 3 warnings in
1.44s`, with only the missing-Git-provenance assertion and missing-`make` error still
failing. This is recorded as an environment limitation, not as a green full-suite
claim. Neither failure imports or executes an R3 path.

```text
docker run --rm --entrypoint ruff \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  check --no-cache app/runtime/execution app/runtime_bindings \
  app/runtime/storage/contracts.py app/runtime/workflow/kernel.py \
  app/runtime/workflow/repository.py tests/runtime/execution_test_support.py \
  tests/runtime/test_execution_gateway.py \
  tests/runtime/test_side_effect_authorization.py \
  tests/runtime/test_idempotency.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_deadlines.py
# All checks passed!

docker run --rm --entrypoint ruff \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  format --check --no-cache app/runtime/execution app/runtime_bindings \
  tests/runtime/execution_test_support.py tests/runtime/test_execution_gateway.py \
  tests/runtime/test_side_effect_authorization.py \
  tests/runtime/test_idempotency.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_deadlines.py
# 18 files already formatted.

python scripts/check_docs.py
# Documentation validation passed.

git diff --check
# Passed with no output.
```

## Security disposition, leakage review, and rollback

The generic security boundary classes map as follows: negative authorization and
strict untrusted-data cases cover unknown/denied capabilities, malformed inputs and
outputs, missing replay keys, and invalid approvals; adversarial cases cover mutated
approval payloads and a forged inconsistent decision; replay/race cases cover keyed
execution, retry-advice narrowing, ambiguous commits, and a deterministic stale-worker
fence loss; success cases prove typed persistence followed by non-fatal telemetry;
safe-failure cases cover timeout, external cancellation, and malformed adapter
results. Tests seed raw-content, local-path, token-like idempotency,
and provider-operation canaries and prove they are absent from records, returned safe
errors, captured logs, and telemetry. A source scan also confirms generic
`app.runtime.execution` imports no product binding module.

Coach V6 command, media, deletion, and export security classes are non-applicable:
Task 8 changes no Coach route, command, media/transcript, deletion, export, or Coach
telemetry path. No Coach PDF was touched.

Rollback is code-only: revert the Task 8 commit. No migration or schema change is
introduced; R3 reuses the existing execution and workflow records. The semantic
store method can be removed with the gateway after confirming no downstream caller
has adopted it. Scoped self-review found no Critical, High, or Medium security issue.
The only release concern is the explicitly non-green full backend container gate
described above; focused R3 and affected R2 gates are green.
