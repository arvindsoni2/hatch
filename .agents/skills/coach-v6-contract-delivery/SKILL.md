---
name: coach-v6-contract-delivery
description: Use when planning, implementing, reviewing, or preparing evidence for a Hatch Conversational AI Interview Coach Phase 1 pull request governed by the tracked V6 specification.
---

# Coach V6 Contract Delivery

## Authority

Treat `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md` as the sole Phase 1 technical authority. Read it completely before each PR. Do not use older specs, the PDF, or Phase 2 documents to amend V6.

**Phase 2 is forbidden in every Phase 1 PR without exception.** Do not add Candidate Intelligence entities, findings, confidence bands, governance gateways, or mentor personas. A proposed “scope amendment” does not override this boundary.

Read [references/v6-pr-contract-map.md](references/v6-pr-contract-map.md) before planning or changing a PR.

## Required Delivery Loop

1. Verify the branch head, target, current integration-base commit, and V6 file before editing.
2. Create a traceability row for every changed contract using this exact shape:

   | V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
   |---|---|---|---|---|

3. Write the smallest test first and capture the expected failure. Then implement only the mapped PR contract. Use `superpowers:test-driven-development`.
4. Keep `HATCH_COACH_CONVERSATIONAL_ENABLED = false` through PR 1. Do not enable rollout before acceptance evidence exists.
5. Run mapped targeted tests, touched-layer regressions, repository checks, and the V6 gates applicable to the PR. Preserve exact commands, exit status, pass/fail counts, migration head, and artifact or manifest paths.
6. Request two reviews in order: **specification compliance first**, then **code quality** only after compliance passes. Resolve findings and rerun affected verification.
7. Merge into `feature/coach-phase1-phase2` before branching the next PR from the updated integration head. Never base a later PR on an unmerged sibling.

## Stop Conditions

Stop and report the contract, evidence, and impact when the branch materially contradicts V6, a named integration is absent, a deletion choice exceeds V6, or a required provider capability is impossible. Do not weaken, reinterpret, omit, or defer a binding contract to make a PR pass.

## Completion Record

Report: PR scope and exclusions; integration base/head/target; completed traceability table; RED/GREEN evidence; spec-review verdict; quality-review verdict; verification commands and results; known limitations; merge readiness. Missing evidence means the PR is not ready.

## Red Flags

- Phase 2 work described as future-proofing or a local amendment
- Direct or stacked target instead of the sequential integration target
- Feature flag enabled before acceptance evidence
- Tests or files named without contract mapping
- One combined review standing in for both review stages
- “Tests pass” without reproducible command output

Any red flag stops delivery until corrected.
