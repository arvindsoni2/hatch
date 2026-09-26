---
title: Hatch Conversational Coach
document_type: architecture
status: current
implementation_status: complete
applies_to: main
last_verified: 2026-09-25
supersedes: []
superseded_by: []
---

# Conversational Coach

Conversational Coach is an opt-in Phase 1 interview experience. Existing
`legacy_v1` sessions keep their numeric report and media behavior; new
`conversational_v1` sessions use named levels, grounded evidence statuses, and
server-authoritative state transitions.

## Rollout

`HATCH_COACH_CONVERSATIONAL_ENABLED=false` is the repository default. Set it to
`true` only after the standard benchmark, isolated security gates, frontend
checks, and owner acceptance pass. Setting it back to `false` blocks new
conversational creation while preserving existing reads, privacy deletion, and
cleanup work. Rollback is therefore a configuration change, not a database
rewrite.

Phase 1 does not infer emotion, confidence, personality, culture fit, or
deception. It does not persist Phase 2 candidate-intelligence findings.

## Data and privacy

Typed and audio answers share the same transcript/evaluation contract. Audio is
owned by its attempt and defaults to `delete_after_processing`; retained audio
can be removed with the session controls. Transcript deletion physically removes
transcript-derived rows and schedules a fenced report rebuild. Hard deletion
removes the session and owned child/media data, retains only a content-free
bounded receipt, and supports a new-command retry after failure. Receipts use
the configured 30-day default (`HATCH_COACH_DELETION_RECEIPT_DAYS`).

Exports are synchronous, snapshot-consistent JSON or Markdown responses. They
never export raw audio or filesystem paths. The report page also provides a
browser print action; there is no server-side PDF or persisted export entity.

## Diagnostics and evidence

Support diagnostics expose only registered, content-free error codes and state.
Evidence references use immutable snapshots and stable IDs. Reports aggregate
accepted attempts deterministically and do not show numeric conversational
scores.

## Verification

The synthetic benchmark suite is validated and run with:

```bash
cd backend
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/conversational_v1
python -m benchmarks.coach run --suite benchmarks/coach/fixtures/conversational_v1 \
  --models configured-local --profile standard \
  --output-root /tmp/hatch-coach-pr4-standard
```

The required standard run must use an approved isolated configured model
environment. The deterministic contract smoke is useful for local contract
checks but is not a substitute for model-dependent promotion evidence.
