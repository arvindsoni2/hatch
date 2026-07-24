# Coach Phase 1 and Phase 2 integration-branch design

**Status:** Approved in conversation on 24 July 2026

**Scope:** Establish the long-lived integration branch, Phase 1 pull-request stack, testing and security gates, and reusable execution skills. Phase 2 remains backlog-only until its own specification is supplied, audited, and approved.

## Goal

Deliver the conversational Interview Coach Phase 1 contract through four reviewable pull requests while keeping remote `main` unchanged. Retain the integration branch for joint automated and owner-led testing, then add Phase 2 to the same branch only after a separate readiness gate.

## Source authority

The tracked `Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md` is the sole Phase 1 implementation authority. The local PDF and condensed Phase 1 v1 Markdown file are design evidence only. When those sources differ, v6 wins.

Graphify analysis of the two design-evidence files identified five central dependency boundaries:

- deterministic orchestration and state authority;
- answer capture and processing;
- evidence-grounded evaluation and coaching;
- recovery, privacy and observability;
- API, command and security contracts.

The older Markdown describes three pull requests. V6 Section 39 requires four sequential pull requests, so the four-PR contract is binding.

## Approaches considered

### Stacked pull requests into one integration branch

Create one long-lived remote integration branch and four sequential child branches. Each child pull request targets the integration branch. Merge each pull request before creating the next child from the updated integration head.

This approach is selected because it preserves V6 migration and contract ordering, keeps every review cumulative and testable, and leaves `main` unchanged.

### Direct commits to the integration branch

This reduces Git operations but removes isolated review gates and makes rejection or revision of one workstream harder. It is not selected.

### Independent pull requests from `main`

This permits parallel development but repeats conflicts across migrations, schemas and shared Coach contracts. It also lacks one cumulative test target. It is not selected.

## Branch topology

The persistent branch is:

```text
feature/coach-phase1-phase2
```

Phase 1 uses these sequential branches and pull-request targets:

| Pull request | Head branch | Base branch |
|---|---|---|
| PR 1 | `phase1/pr1-conversational-foundation` | `feature/coach-phase1-phase2` |
| PR 2 | `phase1/pr2-capture-processing-retention` | `feature/coach-phase1-phase2` after PR 1 |
| PR 3 | `phase1/pr3-evaluation-coaching-followups` | `feature/coach-phase1-phase2` after PR 2 |
| PR 4 | `phase1/pr4-report-privacy-hardening` | `feature/coach-phase1-phase2` after PR 3 |

Every pull request includes only its delta from the current integration head. A later branch must not be based on an unmerged sibling branch.

Remote `main` receives no Phase 1 or Phase 2 implementation merge until the final promotion decision. The two documentation-preflight commits already present in the local ancestry travel with the integration branch instead of being pushed directly to `main`.

## Phase 1 pull-request boundaries

### PR 1: Conversational foundation and persistence

Implement the V6 migration, experience-version dispatch, state machine, command and event persistence, question and attempt extensions, version tables, repository transactions, command/live endpoints, reconciliation, legacy compatibility, and disabled-by-default feature flag. Use deterministic test doubles rather than final model evaluation.

### PR 2: Capture, processing and retention

Implement the conversational shell, typed and MediaRecorder capture, silence prompts, uploads, transcript versions, observable speech metrics, stage processing, retry and timeout budgets, retention cleanup, refresh recovery, and accessible capture controls.

### PR 3: Evaluation, evidence, coaching and follow-ups

Implement named rubric evaluation, delivery policy, immutable evidence grounding, follow-up policy, coaching enrichment, transcript editing and reevaluation, explicit attempt acceptance, answer review, and benchmark smoke profiles.

### PR 4: Report, progress, privacy and production hardening

Implement deterministic report generation, report UI, compatibility-grouped progress, audio/transcript/session deletion, synchronous exports, observability, support diagnostics, full benchmark coverage, security and adversarial testing, documentation, and controlled rollout evidence.

## Review and merge rules

Each pull request must:

1. start from the current integration head;
2. map every changed V6 contract to tests and files;
3. contain no Phase 2 persistence or persona behavior;
4. pass its focused test and security gate;
5. receive specification-compliance and code-quality reviews;
6. merge into the integration branch before the next pull request begins.

Failed gates block the merge. Fixes stay on the affected pull-request branch. Cross-cutting changes discovered later use a dedicated fix branch targeting the integration branch and identify the affected contract and regression suite.

## Test strategy

### Baseline gate

Before application changes, verify the isolated worktree with repository-supported dependencies and record:

- `python scripts/check_docs.py`;
- backend focused and full test baselines;
- frontend unit tests, type check and build;
- Playwright environment availability;
- Alembic head and upgrade baseline;
- `make ci` or the repository's current authoritative equivalent.

If a baseline fails, diagnose it before implementation. Do not attribute an existing failure to Phase 1.

### PR 1 gate

Require migration upgrade and rollback tests, state-transition and allowed-command parity, idempotency replay, monotonic attempt allocation, stale ownership fencing, reconciliation, concurrency races, route schemas, and legacy report regression.

### PR 2 gate

Require typed and audio integration tests, upload identity and hash validation, media ownership checks, pause/resume and refresh recovery, retry/deadline behavior, cleanup races, default deletion, retained-audio behavior, accessibility, and browser E2E.

### PR 3 gate

Require structured-output validation and repair, transcript-span integrity, evidence trust levels, prompt-injection resistance, prohibited inference rejection, follow-up budgets, coaching fact preservation, transcript-edit races, model-route failure handling, and contract/acceptance benchmark smoke profiles.

### PR 4 gate

Require report and progress determinism, export safety, authorization and insecure direct object reference tests, command replay, deletion races, privacy receipt expiry, telemetry redaction, full backend/frontend/E2E suites, standard benchmark profile, and backup/restore smoke when supported by the release process.

### Integration promotion gate

Promotion to `main` remains blocked until:

- all automated gates pass from the integration head;
- no unresolved critical or high-severity security finding remains;
- every medium finding has an explicit disposition;
- synthetic-data penetration testing passes in an isolated environment;
- the owner completes manual acceptance testing;
- the final evidence bundle records commands, versions, results and known limitations.

## Security design

Treat audio, transcripts, evidence text, model output, identifiers and file metadata as untrusted input. Security testing covers:

- authentication, authorization and object ownership on every new route;
- command replay, version conflicts and idempotency-key collisions;
- upload type, size, hash, path and ownership validation;
- prompt injection and structured-output escape attempts;
- stored and reflected UI injection through transcript or evidence content;
- denial-of-service boundaries for duration, size, retries and group counts;
- deletion fencing, stale workers and partial media removal;
- PII, prompt, transcript, evidence and path leakage in logs or telemetry;
- dependency, secret and static-analysis findings;
- dynamic API scanning against an isolated seeded instance.

Never run active penetration tests against production or an external shared environment. Use synthetic candidates, jobs, transcripts and media.

## Skill strategy

Use these existing skills at their trigger points:

- Graphify for design-evidence and dependency maps;
- Superpowers brainstorming and plan writing before implementation;
- Superpowers worktrees for isolation;
- Superpowers test-driven development for every behavior change;
- Superpowers systematic debugging for failures;
- Superpowers subagent-driven development or plan execution for approved tasks;
- Superpowers code-review and verification workflows at every merge gate;
- Design Taste for the conversational frontend direction;
- Web Design Guidelines for accessibility and UX audit;
- React and Next.js best practices for performance and component boundaries;
- Context7 for current framework, library, SDK and CLI documentation.

Create and test two repository-local skills before application implementation:

1. `coach-v6-contract-delivery`: use when planning, implementing or reviewing a V6 Coach pull request; enforce authority, Phase 2 exclusion, contract-to-test traceability and sequential merge evidence.
2. `ai-interview-security-testing`: use when changing AI interview APIs, audio/transcript processing, evidence grounding, deletion, export or telemetry; enforce the threat model and isolated security evidence.

Create both skills with pressure-scenario tests following the skill-writing TDD workflow. Keep exact V6 mappings in references so the main skill instructions remain concise.

## Phase 2 boundary

The integration branch reserves future Phase 2 work, but Phase 1 pull requests must not add Candidate Intelligence tables, findings, confidence bands, mentor personas or governance gateways. Before Phase 2 starts:

1. supply and track its authoritative specification;
2. audit the specification and repository baseline;
3. define a separate pull-request topology and security model;
4. verify Phase 1's stable release gates;
5. branch Phase 2 work from the tested integration head.

The archived JobPilot v3 Phase 2 documents do not authorize Candidate Intelligence or Interview Mentor implementation.

## Graphify artifact policy

The exploratory graph currently lives outside the repository under `/tmp/hatch-coach-graphify.o82TVU/graphify-out/`. The implementation plan may copy a curated graph report into the integration branch only if it materially improves contract traceability. Generated HTML and caches remain untracked unless reviewers request them.

## Completion of this design phase

After owner review, create detailed task plans for the four Phase 1 pull requests, create and test the two repository-local skills, publish the integration branch, and run the isolated baseline gate. Application implementation begins only after those artifacts are reviewed.
