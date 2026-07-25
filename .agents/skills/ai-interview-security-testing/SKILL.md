---
name: ai-interview-security-testing
description: Use when planning, implementing, reviewing, or verifying changes to AI interview APIs, audio or transcript handling, evidence grounding, command state, deletion, export, errors, diagnostics, logging, metrics, or telemetry.
---

# AI Interview Security Testing

## Purpose

Produce contract-grounded security tests and reproducible evidence for AI interview trust boundaries. Treat candidate content, model output, IDs, filenames, and metadata as untrusted.

## Safety boundary

Run active tests only in an isolated local or ephemeral environment using synthetic candidates, jobs, transcripts, evidence, and media. Never aim DAST, fuzzing, exploit probes, load, or destructive tests at production, shared external environments, or real-user data.

Do not enable body logging, expose secrets/tokens, or capture transcript, evidence, CV, prompt/model bodies, user-controlled paths, or raw media in evidence. Passive production review is limited to authorized, production-safe configuration or already-redacted aggregates.

## Workflow

1. Read tracked V6, the approved integration design, and [the threat matrix](references/threat-and-test-matrix.md) for every touched boundary. Record repository revision and document hashes.
2. Inspect changed routes, workers, storage, UI sinks, deletion/export paths, and observability. Map each boundary to V6 sections and acceptance/release gates.
3. Label controls `V6 binding` or `optional hardening`. Generic advice is not a blocker. Keep extra scanners, retention regimes, and infrastructure controls as proposals unless V6 or approved repository policy requires them.
4. Write tests first. For each applicable boundary, cover negative authorization/input, adversarial content, idempotency/replay, stale-worker/concurrency, success, and safe failure. Explain omitted classes.
5. Run the smallest focused set, then required regression, E2E, benchmark, and security gates. Use bounded synthetic inputs and clean up artifacts.
6. Inspect evidence for leakage. Redact secrets and identifiers while preserving reproducible commands, versions, assertions, and failures.

## Required test mapping

For touched boundaries, prove:

- canonical command/upload hashes, duplicate lookup order, idempotency conflicts, and stale `state_version` rejection;
- parent ownership/safe IDs for sessions, questions, attempts, media, exports, and deletion;
- processing generation, job/claim token, transcript, activity, and retention version fences;
- exact path/hash/policy media ownership and protection from stale replacement deletion;
- strict schemas, evidence ID/source trust, prompt injection, and prohibited-inference rejection;
- physical derived-content deletion, hidden hard-delete state, worker fencing, bounded pseudonymous receipts, and idempotent reconciliation;
- export version rechecks, stable bytes/ETags, `no-store`, safe filenames, and content exclusions;
- registry-derived safe errors and redacted logs/telemetry, including trace-only versus metric-safe attributes.

## Evidence and disposition

Return:

```text
scope, boundaries, V6 sections, and gate/acceptance IDs
repository revision and spec/design hashes
isolated-environment and synthetic-fixture statement
commands, tool/runtime versions, cases, expected/actual results, artifacts
leakage review and cleanup result
findings: severity, binding/proposal class, evidence, owner, disposition
limitations and unexecuted gates
```

Critical/high findings block merge; every medium needs explicit disposition. Separate optional proposals from the binding verdict. Never claim a gate passed without captured output.

## Stop conditions

Stop when the target may contain real data, ownership is unclear, testing could affect shared services, credentials require unsafe handling, or deletion exceeds V6. Report the blocked test and required isolated substitute.
