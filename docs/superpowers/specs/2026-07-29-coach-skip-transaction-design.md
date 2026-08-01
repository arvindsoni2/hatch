# Conversational Skip Transaction Design

## Context

Phase 1 V6 section 8.7 requires the transient `advancing` state to be entered
and resolved within the same backend transaction during normal command
execution. The existing typed `skip_question` command commits and returns
`advancing`, leaving reconciliation to complete an otherwise successful command.

## Approved behavior

A normal non-terminal skip atomically marks the current question `skipped`,
presents the next planned question, updates the active question and root, and
returns stable state `asking`.

A normal terminal skip atomically marks the current question `skipped`, creates
the initial report job and ownership snapshot exactly once, clears active
question ownership, and returns stable state `reporting`.

The command retains its single state-version increment, receipt replay, activity
version increment, and transactional event persistence. Replaying the same
command returns the recorded stable result without presenting another question
or creating another report job.

## Recovery boundary

Reconciliation continues to support an `advancing` value that was persisted by
an interrupted or historical transaction. Recovery tests seed that state
directly; normal command tests must not manufacture it through the API.

## Scope

The change is limited to the typed command service and its command and
reconciliation regression tests. It does not add report generation, media,
transcription, evaluation, frontend, migration, legacy skip, or Phase 2 work.

## Verification

Tests must first fail against the current behavior, then pass after the minimal
transaction correction. Coverage includes immediate stable state for both skip
paths, exact replay, event/state-version semantics, exactly-one report job, and
preserved repair of directly seeded interrupted `advancing` states. The final
gate runs focused tests, the locked PR1 suite, the full backend suite, and exact
`make ci`.
