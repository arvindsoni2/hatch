# Representative local writing model selection — 18 July 2026

## Decision

**Retain the `qwen35-4b` baseline.**

No challenger passed the Stage A hard-gate qualification, so Stage B ran only
the baseline comparator and Stage C was not permitted to start. This decision
does not authorize changes to model defaults, the model catalogue, migration
notes, or rollback instructions.

## Run identity

- Run ID: `staged-20260718T092736Z-cfb10b5c`
- Suite: `representative-local-writing-v1`
- Source commit: `90b688894864e7e9990308eee5ceb9241e488bb6`
- Started: 18 July 2026 at 10:27 BST
- Completed: 18 July 2026 at 16:43 BST
- Final state: `completed`
- Selection result: `retain_baseline`

## Stage results

Stage A completed all 15 scheduled pairs: five models, three shared seeds, and
the Delivery/Project Manager case. Every model returned three responses with
successful schema parsing, but none passed a first-pass or post-repair hard
gate. The baseline advanced solely under the documented comparator override.

Stage B completed all 12 scheduled baseline pairs across the Delivery/Project
Manager, AI/Software Engineer, Sparse CV, and Sponsorship/Salary cases. All 12
responses parsed successfully, but none passed the post-repair hard gates.
Stage C was skipped because there was no qualifying challenger.

Across both stages:

- 27 of 27 scheduled pairs completed.
- Response and schema success rates were 100%.
- Unsupported candidate claims, unsupported numeric tokens, and immutable
  token mutations were all zero.
- The sparse-evidence safe-fallback rate was 100%.
- No pair was eligible for quality ranking because no pair passed every hard
  gate.

## Protected-state evidence

The profile hash was recorded and remained unchanged. The original run did not
record the SQLite database hash because absolute `sqlite+aiosqlite` URLs were
resolved incorrectly. A SQLite write-ahead log was also present, which the
original hash function did not cover. Therefore this run does not provide the
required automated before/after proof for the complete database state.

PR5 fixes both defects:

- absolute `sqlite+aiosqlite` paths resolve to the intended database;
- the protection hash covers the main database and its write-ahead log;
- staged runs refuse to start when profile or database hashes are unavailable.

The conservative `retain_baseline` outcome remains valid and makes no model or
profile change. A future decision-authorizing run must use the corrected
protection checks.

## Privacy

This record contains only aggregate counts and controlled identifiers. Fixture
prose, generated documents, raw model responses, profile/database contents,
secrets, and machine-specific paths remain excluded.

## Limitations

- Results apply only to the controlled suite and recorded local runtimes.
- Quality comparisons were unavailable because every pair failed at least one
  hard gate.
- The run cannot authorize a model change.
