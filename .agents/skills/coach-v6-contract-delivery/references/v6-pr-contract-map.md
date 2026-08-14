# V6 Phase 1 PR contract map

Use this map to select contracts; verify details in the tracked V6 file. V6 remains the sole technical authority.

## Authority and boundary

| Source | Binding rule |
|---|---|
| V6 §0.6 | V6 overrides Phase 1 v1–v5 and the condensed draft; preserve legacy readability and callers; extend completed correctness, benchmark, reconciliation, and observability work. |
| V6 §4.4 | Phase 1 outputs stay session-scoped. Do not implement Candidate Intelligence entities, findings, confidence bands, or governance gateways. |
| V6 §39.1, §46 | Do not add Candidate Intelligence or mentor personas. Phase 2 planning starts only after Phase 1 is merged and its stable release gates pass. |

## Sequential branch and PR contract

Every PR targets `feature/coach-phase1-phase2`. Create each head from the integration branch only after its predecessor merges.

| PR | Head branch | Required V6 §39 scope | Required acceptance evidence |
|---|---|---|---|
| 1 | `phase1/pr1-conversational-foundation` | Migration, experience dispatch, state/command/event persistence, attempt/question/version tables, repository transactions, command/live routes, reconciliation, legacy compatibility, deterministic evaluation stub | State machine, idempotency, migration, stale command/worker, legacy report regression |
| 2 | `phase1/pr2-capture-processing-retention` | Conversational UI shell, typed/audio capture, upload, transcript/stage processing, deadlines/retries, retention/cleanup, refresh recovery, accessible controls | Typed/audio E2E, default deletion, pause/resume, restart recovery, no live score, stale cleanup fencing |
| 3 | `phase1/pr3-evaluation-coaching-followups` | Rubric, delivery, evidence grounding, follow-up policy, coaching, transcript edit/re-evaluation, explicit acceptance, review UI, benchmark smoke | Rubric/evidence gates, prohibited inference, follow-up cap, edit race, fact-safe coaching |
| 4 | `phase1/pr4-report-privacy-hardening` | Report/progress, deletion, exports, observability, benchmark standard, security/adversarial tests, diagnostics, docs, rollout evidence | Deterministic report, deletion/rebuild, compatibility, manifests, complete regression/E2E evidence |

PR 1 must keep `HATCH_COACH_CONVERSATIONAL_ENABLED = false` (V6 §36.1). PR 1 merges before PR 2; PR 2 before PR 3; PR 3 before PR 4 (V6 §39.2).

## Contract-to-evidence routing

| V6 section | Map to tests/evidence |
|---|---|
| §37.1–§37.13 | Backend unit, service, repository, migration, concurrency, router, retention, evaluation, evidence, follow-up, and report tests |
| §37.14 | Frontend server-state recovery, conflict replay, capture, accessibility, legacy rendering, and no-live-score tests |
| §37.15 | Typed, voice/deletion, retry, follow-up, transcript race, restart, degraded-AI, and legacy E2E scenarios |
| §40 | Exact touched model, migration, schema, repository, service, router, reconciliation, frontend, and documentation files |
| §41 | Targeted/full backend, one-head migration, frontend type/unit/build/E2E, repository CI, and benchmark commands |
| §42 | Architecture, concurrency, product, AI-quality, privacy, compatibility, accessibility, and operational release gates |
| §43 | AC-01 through AC-30; every implemented criterion needs a traceability row |
| §44 | Tests must exercise mandated ORM, SQLite, deletion, model-variability, router-size, and media-recovery mitigations when touched |
| §45 | Read/inspect/baseline, RED first, bounded implementation, targeted/full verification, migration checks, and captured evidence |
| §46 | Do not claim Phase 1 complete until the full definition of done and stable release gates pass |

## Evidence shape

Maintain this table in the plan or PR evidence:

| V6 contract | Failing test and RED evidence | Implementation files | Verification command | Result/evidence |
|---|---|---|---|---|
| `§x / AC-yy — behavior` | `test_name`: expected failure and observed message | Exact repository paths | Exact reproducible command | Exit status, counts, head/hash, artifact path |

Review in two separate stages:

1. Specification compliance: validate scope, exclusions, authority, contracts, traceability, and acceptance evidence.
2. Code quality: validate correctness, maintainability, security, test quality, and repository conventions after stage 1 passes.
