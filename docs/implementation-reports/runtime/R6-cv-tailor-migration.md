# R6 CV Tailor Runtime Migration

## Scope

R6 migrates CV-tailoring execution behind `cv.tailor` v1 while retaining
`LEGACY` as the default. It does not promote R5 or change any production flag.

## Runtime path

Every non-legacy CV entry binds the runtime mode once. `generate_cv` is the
single writer boundary; package/UI (`generate_all` and TailorAgent) and SSE
delegate through it. `SHADOW` creates exactly one visible legacy CV and runs a
durable, evaluation-only runtime attempt. `NEW` owns the visible CV and does
not invoke a legacy fallback writer.

The durable attempt records the workflow run, attempt, R4 profile/resume/job
context package, control-plane decision, model-router decision, generation
execution, deterministic validation, and (only in NEW) the artifact execution.
The gateway fences both capability executions and carries an idempotency key
derived from the task attempt.

The gateway-only generation invocation includes the router-authorized model and provider;
cloud selections require Control Plane egress authorization. Artifact conflict cleanup is
ownership-safe: a losing attempt never deletes a peer's final file.

The `cv_publications` journal binds the runtime attempt and owner fence to immutable
staging/final paths, hashes, section metadata, and the eventual product projection.
Artifact execution retains its ambiguous side-effect intent until a fenced receipt
verifier confirms the staged artifact; only then may ATS evaluation begin. Cancellation,
partial rendering, and ambiguous finalization preserve ownership boundaries and allow a
restarted worker to reconcile without repeating model or render calls. Runtime package
replay reuses the committed cover-letter document for the same delivery identity.

## Safety controls

- Candidate support is statement-level: every rendered summary and achievement
  must exactly match a product-owned master-CV statement allowlist. Model
  provenance labels and empty `source_claims` do not authorize a claim.
- Deterministic schema, required-section, artifact-contract, and support checks
  run before ATS/model evaluation, evaluator repair/fallback, and rendering. Repair is bounded
  to one attempt; an invalid result is withheld.
- NEW rendering uses attempt-unique immutable staging paths. The staged DOCX
  has path/hash/size/section checks before projection and is published by a
  non-overwriting atomic link. Failures discard staging; ambiguous gateway
  outcomes remain withheld for reconciliation instead of retrying a writer.
- Runtime product records store hashes/counts/reason codes rather than CV text,
  claim text, prompt dumps, or source content. Canonical prose is retained only
  in the approved generated document artifact.
- Cancellation joins the renderer before deleting its owned staging path, and final
  publication is never overwritten or removed by a losing peer.

## Verification

`python -m pytest -q --no-cov tests/runtime/test_cv_tailor_task.py
tests/runtime/test_cv_tailor_migration.py tests/runtime/test_cv_tailor_grounding.py
tests/runtime/test_cv_tailor_artifacts.py tests/runtime/test_cv_tailor_lifecycle.py
tests/runtime/test_execution_receipt.py tests/test_services/test_cv_tailor.py
tests/test_routers/test_tailor_router.py tests/test_routers/test_tailor_async.py`
passed (60 tests, 7 pre-existing async-job fixture warnings). The suite includes
AWS-only candidate evidence rejected when a live `CVTailor` response introduces
Kubernetes, durable NEW/SHADOW lineage, one-repair/fallback behavior,
sparse/conflicting/long-context inputs, safe artifact failure behavior,
cancellation/reconciliation, lease renewal, HTTP history/download, and package replay.

`alembic heads` reports one head: `a4b5c6d7e8f9`. Ruff and changed-path compilation
pass. An isolated CLI upgrade/downgrade/re-upgrade probe stalled in the existing Alembic
path without output and was interrupted; its temporary database was removed and no
shared database was changed. Migration regression tests pass, but no CLI upgrade claim
is made from this environment.

## Rollback and limitations

Rollback is setting `HATCH_RUNTIME_CV_TAILOR_MODE=legacy` before a new request;
already-bound attempts keep their selected mode. The additive `cv_publications` migration
is at Alembic head `a4b5c6d7e8f9`. This implementation intentionally makes no production
promotion claim; real provider quality/cost measurements and operator rollout approval
remain separate gates, and LEGACY remains the default.
