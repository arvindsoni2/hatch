# Task 13 — R6 CV Tailoring migration report

## Scope and revision

- Base / integration head: `b2659a164ee88bcbb15b35da0b38b7147aeefc8c`
  (`main`, merged R5 Job Scoring).
- Branch: `runtime/r6-cv-tailor-migration`.
- Target: `main`.
- Architecture authority: `docs/implementation-specs/active/Hatch_Architecture_Foundation_Implementation_Spec_v2.md`, SHA-256
  `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`.
- Task brief: `.superpowers/sdd/Hatch_Architecture_Foundation_Implementation_Plan_v2/task-13-brief.md`, SHA-256
  `5a4ac0993e6a6257802f9c43a342c788c380a873bb67035924f936e4bb1acf39`.
- Alembic heads: `z3a4b5c6d7e8 (head)`; no schema migration was required or added.

The mutable `progress.md` is controller-owned and was not edited by this task.

## Discovered ownership

- HTTP entry: `backend/app/routers/tailor.py`, `POST /api/tailor/generate-cv`.
- Authoritative legacy write: `backend/app/services/tailor_service.py`,
  `TailorService.generate_cv`, with `DocxCVBuilder` and `DocumentRepository`.
- CV generation and current grounding: `backend/app/services/cv_tailor.py` and
  `backend/app/services/grounding_validator.py`.
- Existing R4 bindings reused as the declared source shape:
  `runtime_bindings/context/profile.py`, `resume.py`, and `job.py`.
- Existing artifact boundary: `runtime_bindings/capabilities/registry.py` and
  `runtime/execution/adapters/artifact.py`.

## Implemented contract and migration constraints

`CV_TAILOR_V1` is `cv.tailor` version 1. Its reference-only input declares the six §21
capabilities: verified experience, achievements, skills, resume text, job requirements,
and job description. It has deterministic validators, in fixed order, for schema,
required sections, artifact contract, and source-supported candidate claims. Transient
claim allowlists are excluded from serialization, preventing raw CV evidence from entering
runtime/shadow payloads.

`TailorService.generate_cv` resolves `HATCH_RUNTIME_CV_TAILOR_MODE` once. `LEGACY`
retains the prior implementation. `SHADOW` first completes the legacy visible document,
then runs a separate evaluation-only generation; it never calls the committing artifact
adapter and failures are recorded only as a stable log code. `NEW` runs deterministic
validation before the adapter-backed artifact commit. Validation or artifact failure
withholds the document; NEW never falls back to a second legacy writer. Repair is limited
to one repair and one fallback candidate in the runtime seam.

Default remains `RuntimeMode.LEGACY`; no flag defaults, rollout decision, R5 promotion, or
production-promotion claim was changed. Rollback is setting
`HATCH_RUNTIME_CV_TAILOR_MODE=legacy` before a new request; an already-resolved request
keeps its selected writer.

## Files

- Added `backend/app/runtime_bindings/tasks/cv_tailor.py`.
- Added `backend/app/runtime_bindings/migration/cv_tailor.py`.
- Updated runtime-binding exports and `backend/app/services/tailor_service.py`.
- Added focused task, mode/rollback, grounding/provenance/long-context, and artifact tests
  under `backend/tests/runtime/test_cv_tailor_*.py`.

## TDD and verification evidence

RED was observed before implementation: the initial focused suite failed collection with
three expected missing-module imports (`tasks.cv_tailor` and `migration.cv_tailor`). A
second RED privacy test showed `source_claims` in `model_dump`; setting the field to
`exclude=True` made the test green.

```text
cd backend
python -m pytest -q --no-cov \
  tests/runtime/test_cv_tailor_task.py \
  tests/runtime/test_cv_tailor_migration.py \
  tests/runtime/test_cv_tailor_grounding.py \
  tests/runtime/test_cv_tailor_artifacts.py
17 passed in 0.13s

python -m pytest -q --no-cov \
  tests/runtime/test_cv_tailor_task.py \
  tests/runtime/test_cv_tailor_migration.py \
  tests/runtime/test_cv_tailor_grounding.py \
  tests/runtime/test_cv_tailor_artifacts.py \
  tests/test_services/test_cv_tailor.py \
  tests/test_services/test_blocking_gate.py \
  tests/test_services/test_ats_grounded_retry.py \
  tests/test_routers/test_tailor_router.py \
  tests/test_routers/test_tailor_async.py --tb=short
59 passed, 7 warnings in 2.47s

python -m py_compile app/services/tailor_service.py \
  app/runtime_bindings/tasks/cv_tailor.py \
  app/runtime_bindings/migration/cv_tailor.py
exit 0

ruff check [seven changed Python paths]
All checks passed

ruff format --check [seven changed Python paths]
The two edited existing source files would be reformatted; the five new/other
scoped files are already formatted. No unrelated whole-file formatting was
committed.

git diff --check
exit 0
```

The affected router run retains pre-existing async-job fixture warnings and background
`async_jobs` table log noise; test assertions passed. No production/shared data was used;
all added fixtures are synthetic.

## Required-case traceability

| §21 / brief case | Evidence |
| --- | --- |
| sparse evidence / required sections | `test_validator_rejects_sparse_output_without_required_sections` |
| unsupported claim | task + artifact tests reject before commit |
| conflicting candidate/job evidence | `test_conflicting_job_language_does_not_authorize_a_new_candidate_claim` |
| long context | `test_long_context_remains_reference_only_and_does_not_change_validation_order` |
| artifact failure | `test_new_artifact_failure_returns_safe_failure_without_partial_result` |
| repair/fallback | `test_repair_is_bounded_then_uses_fallback_output` |
| provenance/privacy | transient source claims excluded from serialized payloads |
| SHADOW/rollback | one-writer mode table, no SHADOW commit, LEGACY-default test |

## Limitations and gate status

The current application has no pre-composed CV-specific durable workflow-kernel,
control-plane/router, or execution-gateway composition analogous to R5's Job Scoring
factory. This task establishes the versioned contract and artifact-adapter migration seam,
but does not persist a CV workflow run/lineage or independently invoke the generic gateway.
That integration must be completed before any NEW-mode promotion can be considered. The
complete backend suite, live-model quality/cost measurements, and owner approval were not
run/obtained here. These limitations block promotion; they do not change the default
LEGACY behavior or rollback availability.

## Review fix round 1 — corrected implementation evidence

The preceding limitation paragraph described the pre-review implementation and is
superseded for the stated runtime composition: R6 now uses the generic durable kernel,
declared R4 `ProfileYamlContextProvider`, `ResumeContextProvider`, and
`JobPostingContextProvider`, Control Plane, `ModelRouter`, fenced
`ExecutionGateway`, and durable workflow/attempt/execution/evaluation stores. The old
local callback dispatcher and its seam-only tests were removed. This is still not a
production-promotion claim.

### Eight review findings, repair and evidence

1. **Grounding:** validation now requires a product-owned statement allowlist for every
   summary and achievement; it no longer accepts positional provenance IDs or output
   `source_claims`. `test_live_cv_tailor_kubernetes_claim_is_withheld_against_aws_only_master`
   runs `CVTailor` with AWS-only source evidence and withholds invented Kubernetes.
2. **Generic runtime composition:** `DurableCVTailorRuntime` starts/claims a durable
   run, resolves declared context, persists Control Plane and router decisions, and
   invokes generation/artifact capabilities through the gateway. The DB-backed NEW test
   proves run, attempt, generation, and artifact execution lineage.
3. **Entry routing:** `generate_cv` is the sole CV writer boundary. `generate_all` (and
   therefore TailorAgent/UI) plus `stream_progress` bind mode at entry and delegate to
   it. SHADOW retains one legacy visible CV and does not invoke its artifact capability;
   NEW has no legacy writer fallback.
4. **Metadata-only sinks:** NEW and SHADOW tailoring parameters are reduced to hashes,
   counts, IDs, metrics, and reason codes; runtime output result hashes likewise contain
   only artifact reference/byte and section counts. Canonical CV prose remains in the
   DOCX artifact.
5. **Order and bounded recovery:** generation is followed by deterministic schema,
   required-section, artifact-contract, and source-support validation before the artifact
   gateway. Exactly one repair and then a safe fallback candidate are allowed; validation
   failure withholds the artifact.
6. **Rendered artifact validation:** NEW renders to staging, verifies concrete path,
   SHA-256, byte count and document XML sections, then binds only those metadata values
   to the product projection before publication.
7. **Lifecycle/failure:** staging paths include attempt-unique entropy, promotion uses a
   no-overwrite link, staging is discarded on failure, and gateway ambiguous commit
   outcomes are withheld/reconciled rather than retried as a second writer.
8. **Live tests:** callback-loop migration tests were replaced by DB-backed durable
   NEW/SHADOW mode tests. Focused test modules cover context lineage, policy/router and
   artifact executions, sparse/conflicting/long evidence, privacy serialization,
   repair/fallback, artifact failure, and LEGACY rollback.

### Fix-round TDD/systematic-debugging record

RED: removing the old dispatcher caused its seam test module to fail collection. It was
replaced with DB-backed run/attempt/execution tests. RED: gateway artifact-handler
exception classified as `OUTCOME_UNKNOWN` rather than a fabricated permanent failure;
the test now asserts the safer reconciliation state and no output. RED: changing legacy
metadata serialization broke the existing legacy compatibility expectation; metadata-only
serialization is restricted to NEW/SHADOW and the LEGACY format remains unchanged.

GREEN verification after the repair:

```text
cd backend
python -m pytest -q --no-cov \
  tests/runtime/test_cv_tailor_artifacts.py \
  tests/runtime/test_cv_tailor_migration.py \
  tests/runtime/test_cv_tailor_task.py \
  tests/runtime/test_cv_tailor_grounding.py \
  tests/test_services/test_blocking_gate.py
23 passed in 1.69s

ruff check app/runtime_bindings/migration/cv_tailor.py \
  app/runtime_bindings/tasks/cv_tailor.py \
  app/runtime_bindings/migration/__init__.py \
  app/services/docx_cv_builder.py app/services/tailor_service.py \
  tests/runtime/test_cv_tailor_artifacts.py \
  tests/runtime/test_cv_tailor_migration.py \
  tests/runtime/test_cv_tailor_grounding.py
All checks passed

python -m pytest -q --no-cov \
  tests/test_services/test_cv_tailor.py \
  tests/test_services/test_ats_grounded_retry.py \
  tests/test_routers/test_tailor_router.py \
  tests/test_routers/test_tailor_async.py
37 passed, 6 warnings in 2.26s
```

The affected router fixture run retains existing async-job table/background coroutine
warnings; assertions passed and R6 does not modify that async-job fixture infrastructure.

Alembic remains at `z3a4b5c6d7e8`; no migration was added. The default and rollback
remain `LEGACY` / `HATCH_RUNTIME_CV_TAILOR_MODE=legacy`. Remaining limitation: full
provider-backed quality/cost and operational rollout evidence is intentionally out of
scope, so R5/R6 production promotion remains separately blocked.
