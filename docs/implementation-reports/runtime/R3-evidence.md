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
only `llm.generate_structured`. No internal function is exposed through MCP. The R2
extensions are the semantic `WorkflowStore.begin_execution_intent` and
`persist_execution_result` seams, their SQLite implementations, and the additive
execution-intent migration. The first commits a fenced metadata-only binding before
adapter work; the second atomically fence-checks the live claim, inserts the execution
record, and either closes replay-safe intent, retains unsafe disposition until fenced
task finalization, or transitions an ambiguous outcome for reconciliation.

All verification uses bounded synthetic payloads, injected local adapters, and
disposable SQLite databases. No production or shared external provider was called.

## Invariant matrix

| Invariant | Implementation boundary | Independent evidence |
| --- | --- | --- |
| `INV-EXE-001` typed registration and resolution | Immutable `CapabilityDescriptor`, duplicate-safe `CapabilityRegistry`, strict Pydantic input/output validation | `test_gateway_strictly_validates_payload_and_typed_output`, `test_gateway_rejects_adapter_output_that_violates_descriptor`, `test_only_four_initial_capabilities_are_registered` |
| `INV-EXE-002` control and approval precede side effects | Fail-closed capability, egress, and concrete routing authorization followed by exact durable approval verification against the effective typed payload | `test_visible_capability_is_not_automatically_authorized`, LLM denied/omitted routing cases, forced-route approval cases, side-effect authorization cases, inherited policy precedence/force-model cases |
| `INV-EXE-003` deadlines, cancellation, and replay advice only narrow | Minimum policy/descriptor deadline, executor-backed synchronous handlers, `asyncio.timeout`, uncaught external `CancelledError`, descriptor-constrained retry advice | `test_earlier_policy_deadline_and_budgets_reach_adapter`, timeout/cancellation cases, synchronous native/artifact cases, all idempotency cases |
| `INV-EXE-004` external work and result persistence are fenced; ambiguous outcomes reconcile | A short pre-invocation UoW commits capability/version/side-effect/idempotency/hash binding and closes before adapter work; a second fenced UoW inserts the result, closing replay-safe intent but retaining unsafe disposition until atomic task finalization; expired unsafe disposition becomes `OUTCOME_UNKNOWN` without replay | `test_fenced_intent_is_committed_before_adapter_invocation`, pre- and post-persistence crash/restart cases, safe replay control, lost-claim cases, affected R2 fencing/reconciliation gate |
| Privacy-safe evidence and telemetry | Durable metadata contains stable codes, classifications, latency, and hashes only; telemetry is content-free, emitted after persistence, and non-fatal | `test_canaries_never_enter_records_errors_logs_or_telemetry`, `test_idempotency_key_reaches_adapter_but_only_hash_is_persisted`, `test_success_is_typed_persisted_then_reported_with_nonfatal_telemetry`, inherited runtime privacy cases |

The gateway order is resolve, Control Plane authorization, exact effective-payload
approval verification when required, deadline/budget establishment, fenced durable
intent, adapter invocation outside a write transaction, typed result classification,
fenced durable persistence, then non-fatal telemetry. `OUTCOME_UNKNOWN` and
non-retryable side effects always return `retry_allowed=False`; the gateway contains
no blind retry loop.

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
has adopted it. The initial scoped self-review did not identify the boundary gaps
subsequently reported and resolved in review fix round 1 below. The remaining release
concern is the explicitly non-green full backend container gate; focused R3 and
affected R2 gates are green.

## Review fix round 1: effective-constraint and ambiguity hardening

Fix base: `0ec7b133d787c4de2bfe52a6b12c16beaaa8d829`. This evidence accompanies
the fix commit and therefore does not self-reference its own commit SHA.

The review identified four related boundary gaps. The fix makes egress and routing
relevance explicit in `CapabilityDescriptor`; `READ_ONLY_EXTERNAL` also implies
egress without relying on a second flag. The generic structured-generation adapter
now accepts bounded stable model/provider routing fields. Before approval or
invocation, the gateway enforces `data_egress`, supplied model/provider selections
against their allowlists, and forced-model equality. It injects the authorized forced
model into the typed payload and passes effective egress, model/provider allowlists,
and selected routing in `CapabilityInvocationContext`. That round did not reject an
omitted selection under a non-empty allowlist; review fix round 2 closes that gap.

At ambiguous commit boundaries, adapter exceptions and malformed/unvalidated success
responses now classify as non-retryable `OUTCOME_UNKNOWN`, receive only a
gateway-owned SHA-256 reconciliation reference, and use the inherited atomic fenced
persistence transition. For every other result class, any adapter-supplied
reconciliation reference is discarded. Approval-required payloads are checked by
the canonical approval algorithm before verification; hashing and verification
failures return bounded typed failures and cannot reach the adapter. External
`CancelledError` remains outside all `except Exception` handlers.

### Strict TDD record

The first review-fix RED command was:

```text
docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov tests/runtime/test_execution_gateway.py \
  tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_side_effect_authorization.py
# 15 failed, 13 passed, 3 warnings in 4.35s.
```

The intended failures independently observed: allowed LLM egress returned success;
disallowed model/provider and forced-model cases did not return policy denial;
authorized routing was absent from the adapter handoff; raised and malformed commit
responses returned permanent/validation failure; raw provider references survived
seven non-unknown result classes; and oversized canonical approval material escaped
as `ValueError`. The direct `OUTCOME_UNKNOWN` reference case already passed because
the original gateway replaced that one class.

After the first implementation pass the same command reported `28 passed, 2 warnings
in 3.64s`. Mutation review then added a separate fail-closed descriptor test. After
correcting a test-call typo, its intended RED was:

```text
python -m pytest -q --no-cov \
  tests/runtime/test_execution_gateway.py::test_external_side_effect_class_fails_closed_on_egress_denial
# 1 failed, 3 warnings in 0.53s: expected policy_denied, observed success.
```

The production mutation caught was removing/omitting the separate egress flag from a
descriptor already classified `READ_ONLY_EXTERNAL`. The final authorization logic
derives egress relevance from either declaration.

### Final fix-round verification

```text
# Exact R3 gate (same container wrapper and mount as above)
python -m pytest -q --no-cov \
  tests/runtime/test_execution_gateway.py \
  tests/runtime/test_side_effect_authorization.py \
  tests/runtime/test_idempotency.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_deadlines.py tests/runtime/test_policy_precedence.py \
  tests/runtime/test_policy_force_model.py tests/runtime/test_fencing.py
# 52 passed, 2 warnings in 4.57s.

python -m pytest -q --no-cov tests/runtime/test_fencing.py \
  tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py \
  tests/runtime/test_storage_contract.py tests/runtime/test_runtime_privacy.py
# 58 passed, 2 warnings in 6.82s.

ruff check --no-cache app/runtime/execution \
  tests/runtime/test_execution_gateway.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_side_effect_authorization.py
# All checks passed!

ruff format --check --no-cache app/runtime/execution \
  tests/runtime/test_execution_gateway.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_side_effect_authorization.py
# 11 files already formatted.
```

The complete backend gate was rerun with the whole worktree mounted:

```text
docker run --rm --entrypoint python \
  -e COVERAGE_FILE=/tmp/task8-fix1.coverage \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel:/workspace:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest -m pytest -q
# 3503 passed, 2 failed, 9 warnings in 536.50s; coverage 76.07%.
```

This full suite is not green. The two failures are unchanged environment limitations:
the benchmark manifest recorded `working_tree_clean_before="not_recorded"` because
Git metadata was not mounted, and the development setup test raised
`FileNotFoundError` because the backend image has no `make`. The formerly intermittent
staged-runner test passed in this complete run. No R3 path failed.

Fix-round security mapping adds explicit integration coverage for denied egress,
disallowed model and provider, forced-model mismatch, authorized routing handoff,
raised and malformed commit ambiguity, all eight result classes with raw
reference/path/token canaries across result, attempt, execution metadata, logs, and
telemetry, and canonical approval oversize rejection. Coach V6 command, media,
deletion, and export classes remain non-applicable because no Coach path changed.

## Review fix round 2: concrete routing and effective approval material

Fix base: `d784a33e2a0c3869e3e082633831d79c43179049`. This evidence accompanies
the round-2 fix commit and therefore does not self-reference its own commit SHA.

The prior evidence's broad routing statement was incomplete: explicit mismatches
were rejected, but an omitted `model_id` or `provider` under a non-empty allowlist
remained unresolved and could be selected inside an arbitrary handler. The gateway
now fails closed with bounded `model_selection_required` or
`provider_selection_required` before approval or invocation. A policy-forced model
is the only omitted model that is concretely injected by this boundary.

Approval-required invocation now derives canonical approval material from the
post-routing typed payload using `model_dump(mode="json", exclude_unset=True)`. Thus
gateway-injected routing is included, caller input that omits the injected model no
longer authorizes execution, and an approval for the exact effective payload does.
The effective representation retains explicitly supplied fields and gateway updates
without adding unrelated schema defaults. Serialization/canonicalization failure
still returns the bounded `invalid_approval_payload` typed result.

### Strict TDD record

The production changes that the new tests catch are (1) removing the missing-route
branches so an adapter can choose after authorization, and (2) passing `raw_payload`
instead of the post-routing effective payload to canonical approval verification.
Literal allowlists, route identifiers, and expected reason codes were derived in the
tests independently of gateway helpers.

Exact RED command:

```text
docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov tests/runtime/test_execution_gateway.py \
  -k 'omitted_restricted_routing or approval_for_effective_forced_route or approval_for_pre_routing_payload'
# 4 failed, 12 deselected, 3 warnings in 0.84s.
```

Both omitted-selection cases observed `SUCCESS` instead of `POLICY_DENIED`; approval
for the effective forced route observed `approval_invalid`; and approval for the
pre-routing payload observed `SUCCESS`. These were the intended behavioral failures,
not collection errors or test typos.

The same command after the minimal production change reported
`4 passed, 12 deselected, 2 warnings in 0.77s`.

### Required final gates

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
# 56 passed, 2 warnings in 5.15s.

docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov tests/runtime/test_fencing.py \
  tests/runtime/test_approvals.py tests/runtime/test_reconciliation.py \
  tests/runtime/test_storage_contract.py tests/runtime/test_runtime_privacy.py
# 58 passed, 2 warnings in 6.64s.

docker run --rm --entrypoint ruff \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  check --no-cache app/runtime/execution \
  tests/runtime/test_execution_gateway.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_side_effect_authorization.py
# All checks passed!

docker run --rm --entrypoint ruff \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  format --check --no-cache app/runtime/execution \
  tests/runtime/test_execution_gateway.py tests/runtime/test_outcome_unknown.py \
  tests/runtime/test_side_effect_authorization.py
# 11 files already formatted.
```

Per the round-2 assignment, the full backend suite was not rerun; the controller owns
the expensive final whole-branch gate. The latest completed full-suite evidence
remains the round-1 `3503 passed, 2 failed` environment-limited run above and is not
overstated as green.

Security disposition: omitted restrictive routing is now a negative authorization
case; forced-route positive/negative approval tests prove exact effective-payload
binding; no payload, path, token, model output, or provider-operation content is added
to errors, persistence, logs, or telemetry. Existing privacy, ambiguity, fencing,
cancellation, and reconciliation coverage remains green. Coach V6 command, media,
deletion, and export classes remain non-applicable because no Coach path changed.

## Final controller verification

After Task 8's clean fix-round re-review, the controller reran the complete backend
suite in the authoritative Python 3.12.13 image. Root-cause tracing corrected the
earlier environment diagnosis: the image lacked the `git` executable itself, rather
than merely lacking mounted Git metadata; it also lacked `make`. The repository was
mounted at its exact host path, the worktree was declared a Git safe directory, and
the host read-only `git` and `make` binaries were mounted into the disposable test
container. The two formerly failing canaries passed together before the full run.

```text
docker run --rm --entrypoint python \
  -e COVERAGE_FILE=/tmp/r3-final.coverage \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0=/home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2:/home/asoni/Downloads/Assignment/Job_Pilot_v2:Z \
  -v /usr/bin/git:/usr/bin/git:ro -v /usr/bin/make:/usr/bin/make:ro \
  -w /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend \
  localhost/job_pilot_v2_backend:latest -m pytest -q
# 3509 passed, 8 warnings in 609.51s; coverage 76.11%; exit 0.
```

This supersedes the earlier environment-limited full-suite results. No production or
shared external provider was called, no migration was added by R3, and the unrelated
Coach PDF remained untouched.

After the formatter-only commit `8e05aa7`, the focused R3 gate passed `56/56` and
Ruff reported all 24 R3 files formatted. A second complete backend run at that code
head reported `3508 passed, 1 failed, 9 warnings in 621.19s`; the sole failure was the
pre-existing timing-sensitive
`test_two_fresh_restart_records_authorize_two_eighty_pair_runs`, whose synthetic
`now + 2 seconds` restart timestamp lost its ordering race against the later stage
boundary during the long full-suite process. The exact test passed immediately in
isolation (`1 passed in 0.73s`). It also passed in the preceding complete `3509`
green run, and it imports no R3 path. Therefore the final evidence is a green R3 gate,
a green complete backend run before a formatting-only change, and a final-head
composite result with one reproducible-as-isolation-green out-of-scope timing flake;
it is not represented as a second green complete run.

## Final architecture/security integration fix

Fix base: `536690c`. This section supersedes the earlier statement that R3 added no
migration: final review required an additive migration so ambiguous pre-invocation
intent survives process failure. Migration `v9w0x1y2z3a4` adds only
`side_effect_class` and `execution_intent_active` to task attempts; downgrade and
re-upgrade are tested against a disposable SQLite database.

The gateway now commits a short fenced intent UoW after exact effective-payload
approval and deadline setup, and before invoking any adapter. The transaction binds
capability/version, side-effect class, idempotency class, and a gateway-owned SHA-256
reference; it is closed before external work. Result persistence requires that exact
active binding. At fix base `b6196d7`, result persistence then cleared the binding for
every non-ambiguous result. Recovery maps expired active preparation, commit,
artifact, check-before-retry, or non-retryable intent to `OUTCOME_UNKNOWN`; ordinary
safe abandoned work remains replayable. The injected crash, cancellation, and
post-effect persistence-failure tests in that wave covered failures before a result
was durably inserted. They did not prove the separate crash window after a successful
unsafe result commit and before task finalization; the round-4/5 evidence below
supersedes that no-blind-replay overclaim.

Non-FORCE required model capabilities now deny until Task 10 provides trusted model
evidence; routing-supplied claims do not satisfy them. Synchronous native and artifact
handlers run through the executor so the event loop and deadline remain effective;
artifact work that can outlive cancellation is protected by the durable intent and
classified conservatively. Gateway extras are rejected even for an input model that
would ignore them, keyed registrations require a typed key field, and the adapter
context, approval hash, persistence hash, and intent all derive from the same
post-routing typed key. Capture policy exposes exactly `METADATA_ONLY`, `REDACTED`,
`DEBUG_CONTENT`, and `DISABLED` and folds only toward less capture.

Final-fix strict RED observations, captured before production edits, were behavioral:

- durable intent/restart module: `4 failed, 3 warnings in 1.17s` (no pre-intent was
  visible and expired crash/cancel/persistence-failure work recovered `PENDING`);
- canonical capture test: `1 failed, 3 warnings in 0.17s` (legacy enum shape);
- non-FORCE capability end-to-end test: `1 failed, 3 warnings in 0.76s` (policy
  incorrectly allowed routing-supplied claims);
- exact key/extras/registration tests: `3 failed, 3 deselected, 3 warnings in 0.86s`;
- synchronous deadline tests: `2 failed, 3 deselected, 3 warnings in 1.44s`;
- reference/numeric boundary module: `7 failed, 3 warnings in 0.21s`;
- prepare malformed/timeout selection: `2 failed, 18 deselected, 3 warnings in
  0.71s`; artifact malformed selection: `1 failed, 3 warnings in 0.52s`;
- migration head/model/column selection: `3 failed, 2 deselected, 3 warnings in
  2.25s`.

Authoritative final-fix gates in Python 3.12.13:

```text
# Focused R3: gateway, intent, side effects, keys, ambiguity, deadlines,
# precedence/force-model, schemas, fencing, and migration.
# 85 passed, 2 PytestCacheWarning warnings in 24.73s.

# Affected R2: reconciliation, restart recovery, fencing, storage, privacy,
# approvals, and migration.
# 64 passed, 2 PytestCacheWarning warnings in 24.84s.

docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov tests/runtime
# 249 passed, 2 PytestCacheWarning warnings in 44.84s.
```

The warnings are solely cache-write warnings on the bind mount. Per assignment, the
controller owns the final complete backend rerun; this section makes no new whole-
backend green claim. No production/shared external call was made. Synthetic raw
payload, token, path, provider-reference, and content canaries remain absent from
records, typed errors, logs, and telemetry. Only stable codes and gateway hashes are
durable. Coach V6 command, media, deletion, and export classes remain non-applicable:
this wave changes no Coach path. The inherited staged-runner timestamp flake was not
modified.

Rollback is one revert of the final-fix commit followed by Alembic downgrade to
`u8v9w0x1y2z3`; the migration is additive and contains no content data.

Final scoped static verification reported `All checks passed!`, Ruff format reported
`25 files already formatted`, `python scripts/check_docs.py` reported
`Documentation validation passed.`, and `git diff --check` exited 0 with no output.

## Review fix round 4/5: post-persist unsafe disposition

Fix base: `b6196d709ed07288acf13d23aa6958fea522b436`. This evidence accompanies
the fix commit and therefore does not self-reference its own SHA. No schema or
migration change was required.

The existing `execution_intent_active` field now remains true after a successfully
persisted unsafe result when either the side-effect class is prepare, commit, or
artifact, or the idempotency class is check-before-retry or non-retryable. The exact
fenced `WorkflowKernel.finalize()` transition clears that disposition atomically with
task success. If the claim expires first, both direct reclaim and ordinary lease
recovery prevent a replacement invocation: recovery moves the attempt to
`OUTCOME_UNKNOWN`, where the reconciliation workflow owns the next decision. The
compare-and-swap predicates preserve stale-claim and fencing behavior. Pure,
idempotent work closes its intent after result persistence and remains ordinarily
replayable after a crash, so conservative recovery does not over-block safe work.
Adapter work remains outside both short database write units of work.

The gateway now creates one privacy-safe `sha256.` correlation handle and supplies
that exact value to `CapabilityInvocationContext.correlation_handle`, the durable
intent's existing reconciliation reference, execution-result metadata, and the
reconciliation handler input. A synthetic committing adapter records an effect by
that handle; after constructing a restarted kernel, its reconciliation handler finds
and confirms the effect using the same value. The durable snapshot is independently
checked to exclude the raw idempotency key, provider-operation canary, content, and
path. No production or shared external provider was called.

The strict behavioral RED selection injected failure immediately after the real
`persist_execution_result()` transaction returned successfully and before caller
task finalization. It named the mutations where unsafe result persistence cleared the
disposition and where the adapter lacked the gateway handle:

```text
# Post-persist unsafe/safe/correlation selection before production edits.
# 5 failed, 1 passed, 4 deselected, 3 warnings in 1.13s.
```

The three unsafe variants (commit/check-before-retry, pure/non-retryable, and
artifact/idempotent-with-key), the atomic-finalization case, and the restarted
correlation lookup failed for the intended behavioral reasons. The pure/idempotent
replay control already passed. After the minimal production change:

```text
# Same focused selection.
# 6 passed, 4 deselected, 2 warnings in 1.25s.

# Full intent, reconciliation, and fencing modules.
# 29 passed, 2 warnings in 4.49s.

# Focused R3 gate: gateway, intent, side effects, idempotency, ambiguity,
# deadlines, policy precedence/force, capability schemas, fencing, migration.
# 91 passed, 2 warnings in 21.67s.

# Affected R2 recovery, restart, fencing, storage, privacy, approvals, migration.
# 64 passed, 2 warnings in 20.59s.

docker run --rm --entrypoint python \
  -v /home/asoni/Downloads/Assignment/Job_Pilot_v2/.worktrees/runtime-r2-workflow-kernel/backend:/workspace/backend:Z \
  -w /workspace/backend localhost/job_pilot_v2_backend:latest \
  -m pytest -q --no-cov tests/runtime
# 255 passed, 2 warnings in 37.25s.
```

The warnings are only bind-mounted pytest-cache write warnings. Scoped Ruff format
reported `1 file reformatted, 3 files left unchanged`; Ruff check reported
`All checks passed!`, and the subsequent format check reported
`4 files already formatted`. Documentation validation passed and `git diff --check`
returned no output. The controller owns the complete backend run; it was not run in
this fix round. The inherited staged-runner timestamp flake was not modified.

This closes the remaining scoped Critical finding: a durable successful unsafe
result can no longer become ordinarily claimable before atomic task finalization,
and reconciliation has the same opaque handle the adapter used. Approval hashes,
post-routing idempotency binding, metadata-only persistence, and all earlier security
constraints remain unchanged. Rollback is one revert of this schema-neutral commit.

## Final controller release verification

The controller reran the complete backend suite at the reviewed R3 head
`1af429e9987faa39cd36e85864571c13983e1a3b` in the authoritative Python 3.12.13
container. The repository was mounted at its exact worktree path with host `git` and
`make`, and the worktree was declared a Git safe directory, matching the diagnosed
environment required by provenance and migration tests:

```text
# Complete backend suite at the reviewed head.
# 3540 passed, 8 warnings in 545.80s (0:09:05).
# Required coverage 58%; measured coverage 76.14%.
# Exit code 0.

# Ruff check over all 32 changed Python files.
# All checks passed!

# Ruff format --check over all 32 changed Python files.
# 32 files already formatted.

# python scripts/check_docs.py
# Documentation validation passed.

# git diff --check 826da3c8564f9ff53d71065289618410d638be4d..HEAD
# Exit code 0; no output.

# alembic heads
# v9w0x1y2z3a4 (head)
```

The warnings do not represent test failures. The previously observed inherited
staged-runner timestamp flake did not recur in this final run. Together with the clean
narrow scoped review, the complete suite closes the R3 implementation and verification
gate. No external provider or production/shared service was invoked.
