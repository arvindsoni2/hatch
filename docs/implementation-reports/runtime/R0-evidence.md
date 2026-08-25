---
document_type: implementation-spec
status: active
implementation_status: complete
applies_to: main/latest
last_verified: 2026-08-24
---

# R0 Architecture Migration Baseline Evidence

## Scope

R0 records the repository and documentation baseline and adds characterization tests only. No product code, database schema, runtime flag, router, agent, or service behavior changed.

All new fixtures contain invented candidate, employer, job, CV, cover-letter, interview, and session data. They contain no copied CV, transcript, applicant, or production data.

## Git baseline

- Planning and implementation base: `ed366775d41f9e64c3ed7a1163e8f958d0ddaa2e`
- `origin/main` at branch creation: `ed366775d41f9e64c3ed7a1163e8f958d0ddaa2e`
- R0 branch: `runtime/r0-baseline-characterization`
- Isolated worktree: `.worktrees/runtime-r0-baseline-characterization`
- Documentation preflight commit: `cae40bd7bea325f3dd0dd5422f3b08071559acb7`
- Drift audit: not required because implementation began at the exact planning baseline.

The original checkout contained one unrelated untracked file, `docs/implementation-specs/active/Hatch Conversational AI Interview Coach.pdf`. It was preserved and excluded from R0.

## Authority hashes

| Authority | SHA-256 |
| --- | --- |
| Runtime architecture v8 FINAL | `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36` |
| Architecture foundation implementation spec v2 | `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0` |
| Architecture foundation implementation plan v2 | `bb09a80b78b0643e2eab65c2d7b8a72fb7c00fd767506bd31ca4d58ae67c40bb` |
| Coach Phase 1 implementation spec v6 | `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8` |

`find docs -type f -name 'Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md' -print` returned exactly:

```text
docs/architecture/Hatch_Runtime_Architecture_Pre_Coach_Phase2_v8_FINAL.md
```

## Documentation preflight

The initial `python scripts/check_docs.py` run was the known RED baseline. Before repair it reported:

- the old Architecture Foundation v1 copy used invalid `status: draft-for-review` and `implementation_status: not_started` values;
- the untracked condensed Coach v1 copy had no required front matter;
- after the supplied architecture authority was moved into its canonical location, it initially had no required front matter.

The obsolete untracked Architecture Foundation v1 and condensed Coach v1 copies were removed as directed by the approved v2 plan and Coach v6 authority. The v2 spec and plan were moved from ignored `docs/superpowers/plans/` source locations into their canonical tracked locations. The owner-approved spec metadata was set to `approval_status: approved-for-implementation`, and the supplied runtime architecture received documentation metadata without altering its architecture content.

Fresh result after repair:

```text
Documentation validation passed.
```

## Database baseline

Environment: Python `3.14.7`.

`alembic heads` returned one head:

```text
q4r5s6t7u8v9 (head)
```

`alembic current` exited successfully with no revision printed. The configured local database is therefore not stamped at a current Alembic revision. R0 did not mutate or stamp it.

## Characterized contracts

- Job scoring: deterministic local score persisted into the complete legacy `JobScore` result shape, including rationale lists and `scoring_method`.
- CV tailoring: current parser output fields, nested experience/education shape, and default validation status.
- Cover letter: current parser output fields and canonical body-derived word count, independent of a model-supplied count.
- Coach: stale answer recovery produces a no-score failure, fails the async job, and is idempotent on a second reconciliation.

The exact field-set assertions are deliberate contract locks: an additive field is treated as an observable legacy-shape change and must be reviewed explicitly.

## Verification results

New characterization suite:

```text
4 passed
```

Plan-mandated scoring group:

```text
20 passed, 1 skipped
```

Plan-mandated tailoring and cover-letter group:

```text
35 passed, 7 warnings
```

The group exited zero. Existing async router tests emitted teardown-time warnings for unawaited worker coroutines and background `async_jobs` updates after the in-memory tables had been dropped. These were reproduced without changing product code and are baseline test-harness debt, not R0 regressions.

Plan-mandated Coach group:

```text
419 passed
```

Expected negative-path logs included model connection retry messages, malformed JSON recovery errors, and a synthetic setup failure; every asserted test passed.

All pytest invocations also emitted the environment-level `RequestsDependencyWarning` for the installed `urllib3`/character-normalization dependency combination. This did not affect test outcomes.
