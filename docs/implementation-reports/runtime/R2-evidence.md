# R2 workflow-kernel evidence

## Scope and provenance

- Baseline: `fb4d6d2` (the R1 merge).
- R2 implementation commits: `f637490..4834991`; release-hardening implementation
  commit: `394bbfb`.
- This evidence is a docs-only follow-up; it intentionally does not self-reference
  its own commit ID.
- Architecture SHA-256: `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36`.
- Foundation spec SHA-256: `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`.
- Coach V6 SHA-256: `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`.

All active tests use disposable, file-backed SQLite databases with synthetic IDs,
metadata references, and result references only. No Coach product boundary was
changed by R2.

## Release hardening covered

- Every execution or reconciliation worker mutation verifies the durable active
  claim, attempt identity, fencing token, and `lease_expires_at > now`. Exact-expiry
  and just-after-expiry tests cover renewal, finalization, waiting, unknown-outcome,
  terminal failure, retry, and reconciliation confirmed/not-found/return paths.
- Workflow step and run state are derived atomically from attempts in the same UoW:
  claim/run, wait/resume, retry, terminal failure, success, normal expired recovery,
  and ambiguous-outcome reconciliation preserve coherent aggregates.
- Terminal failure codes are bounded stable identifiers at the lowest repository
  boundary; boolean, whitespace, long, path, prompt, transcript/CV, and model-output
  canaries reject without changing the claim, attempt, step, or run.
- Recovery has a validated `batch_size` (default 25, maximum 100), pages expired
  claims deterministically, and commits each recovered claim in a short transaction.
  A later injected record failure does not roll back an earlier recovered claim.
- All terminal attempt transitions clear `current_claim_id`, including success and
  the failed predecessor of a scheduled retry.

## TDD and verification evidence

```text
# Release hardening RED before implementation
python -m pytest -q tests/runtime/test_release_contract.py
# 20 failed for the intended missing expiry, aggregate, failure-code, and bounded-
# recovery protections (coverage threshold also reported because this was a focused run).

# Focused GREEN after implementation
python -m pytest -q --no-cov [release-contract, claims, fencing, retries, waiting,
# reconciliation, storage-contract]
# 61 passed in 9.24s before final exact-after-expiry and partial-isolation additions.

# Final runtime gate (host Python 3.14.7; python3.12 is unavailable on this host)
python -m pytest -q --no-cov tests/runtime
# 148 passed in 31.33s; requests/urllib3 compatibility warning only.

# Affected persistence, migration, event, and contention regression
python -m pytest -q --no-cov [storage-contract, schema-migration, event-atomicity,
# sqlite-contention]
# 22 passed in 11.94s; same host dependency warning only.

# Required composite backend gate
python -m pytest -q
# 3420 passed, 2 skipped, 127 warnings in 440.22s; coverage 77.96%.
# The prior approved composite provenance gate recorded 3402 passed plus one host
# provenance test passed; this release rerun adds the release-contract cases and
# therefore reports 3420 rather than reusing the stale 3384 result.

python -m ruff check app/runtime/workflow tests/runtime/test_release_contract.py \
  tests/runtime/test_claims.py tests/runtime/test_fencing.py \
  tests/runtime/workflow_test_support.py
# All checks passed.

python scripts/check_docs.py
git diff --check
# Documentation validation passed; diff check passed.

alembic heads
# sole head: t7u8v9w0x1y2.
```

`python3.12` is not installed in this host environment. The full suite above ran
under the available Python 3.14.7 interpreter. An isolated `alembic current
--check-heads` attempt with a disposable SQLite URL blocked without output and was
interrupted; no schema state was changed. The sole-head check and the repository's
existing migration tests pass. The supported canonical bootstrap/current-head result
from the prior R2 gate remains recorded in its implementation history.

The full suite's warnings are existing negative-path log output (temporary SQLite
fixtures, deliberate provider connection failures, and Coach recovery tests) plus the
requests/urllib3 dependency compatibility warning. They are not failures and contain
no test fixture secrets or candidate content.

## Security disposition and rollback

R2 changes generic workflow records only. Coach routes, commands, media, transcripts,
deletion, exports, UI sinks, telemetry, and domain finalizers are out of scope and
untouched. Applicable generic controls are covered by stable-code input rejection,
replay/race and stale-worker fencing, expiry-bound ownership, bounded recovery,
isolated synthetic fixtures, and atomic rollback assertions.

Rollback is code-first: revert the R2 implementation range after confirming no active
workflow claims require recovery. No new migration was introduced by release hardening;
the existing R2 migration remains additive. Review disposition: pending scoped
re-review of the release hardening changes.
