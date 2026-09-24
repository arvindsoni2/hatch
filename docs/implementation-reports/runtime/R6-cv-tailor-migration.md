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

## Verification

`python -m pytest -q --no-cov tests/runtime/test_cv_tailor_artifacts.py
tests/runtime/test_cv_tailor_migration.py tests/runtime/test_cv_tailor_task.py
tests/runtime/test_cv_tailor_grounding.py tests/test_services/test_blocking_gate.py`
passed (23 tests). The suite includes AWS-only candidate evidence rejected when
a live `CVTailor` response introduces Kubernetes, durable NEW/SHADOW lineage,
one-repair/fallback behavior, sparse/conflicting/long-context inputs, and safe
artifact failure behavior.

## Rollback and limitations

Rollback is setting `HATCH_RUNTIME_CV_TAILOR_MODE=legacy` before a new request;
already-bound attempts keep their selected mode. No migration or Alembic head
changed (`z3a4b5c6d7e8`). This implementation intentionally makes no production
promotion claim; real provider quality/cost measurements and operator rollout
approval remain separate gates.
