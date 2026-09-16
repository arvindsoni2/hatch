# SDD ledger — plan: docs/implementation-notes/Hatch_Architecture_Foundation_Implementation_Plan_v2.md

Baseline: `fb4d6d2` (merged PR #61), branch `runtime/r2-workflow-kernel`.
Authority hashes: architecture `ef426195f1234ad5c394ca4aefd63019d7ed05321df6cbd8f14f4baddf21eb36`; spec v2 `578d6f9d0050014bde074e1ef72588733e305f46acad017f90bfb6ac95aa65a0`; Coach V6 `39b0a616a0edb564b221ac11cf53aba5160710c034b67786c8e639b1495c00b8`.
Baseline verification: `cd backend && python -m pytest -q --no-cov tests/runtime` -> 50 passed in 7.42s.
Documentation baseline: `python scripts/check_docs.py` -> exit 0, validation passed.
Migration baseline: `alembic heads` -> one head, `r5s6t7u8v9w0`; `alembic current --check-heads` was interrupted after 90 seconds without output because it blocked on the shared development database, so Task 5/6 verification must use isolated test databases and rerun the current-head check only when that shared probe is uncontended.
Security scope for R2: generic runtime workflow records only; no Coach route, command, media, transcript, deletion, export, UI, or domain finalizer is changed. V6 boundary classes are therefore non-applicable in R2. Binding generic coverage is negative state/claim/approval validation, replay/race and stale-worker fencing, contention, crash/restart, and safe atomic failure using isolated synthetic SQLite databases.

Task 1: complete (commits `ed36677..c38bf49`, merged as PR #60)
Task 2: complete (commit `f1a3937`, review clean before PR #61 merge)
Task 3: complete (commit `e7983b9`, review clean before PR #61 merge)
Task 4: complete (commits `9afa492..630006e`, review clean before PR #61 merge; CI fixes `2cea6b9..a42523d`)

## Pre-flight cross-task/interface scan

| Tasks | Producer -> consumer / shared surface | Finding |
|---|---|---|
| 1, 12 | Job-score characterization fixtures -> migration comparison | Consistent; synthetic fixture requirement is preserved. |
| 1, 13 | Tailoring characterization fixtures -> migration comparison | Consistent; no product behavior change in Task 1. |
| 1, 14 | Cover-letter characterization fixtures -> migration comparison | Consistent. |
| 1, 15 | Coach characterization/V6 baseline -> kernel extraction regression | Consistent; V6 remains binding. |
| 2, 5 | IDs/enums/WorkflowPolicy -> kernel API | Consistent; kernel must reuse semantic IDs and persisted enums. |
| 2, 6 | WaitingReason/result taxonomy -> waiting/reconciliation | Consistent. |
| 2, 7 | TaskSpec/workflow policy -> Control Plane | Consistent. |
| 2, 9 | TaskSpec context requirements -> Context Plane | Consistent. |
| 2, 10 | model requirements -> Router | Consistent. |
| 2, 11 | evaluation policy/result taxonomy -> evaluation | Consistent. |
| 2, 12 | RuntimeMode/TaskSpec -> job-score binding | Consistent; mode resolved once. |
| 2, 13 | RuntimeMode/TaskSpec -> CV binding | Consistent. |
| 2, 14 | RuntimeMode/TaskSpec -> cover-letter binding | Consistent. |
| 2, 15 | RuntimeMode -> Coach adapter | Consistent; generic contracts stay product-independent. |
| 3, 4 | shared RuntimeUnitOfWork session -> atomic event/outbox repositories | Implemented consistently in R1. |
| 3, 5 | workflow schema/store protocols -> claims/kernel | Consistent; Task 5 must extend semantic stores without repository commits. |
| 3, 6 | attempt/approval schema -> waiting/approval operations | Consistent; waiting owns no claim. |
| 3, 8 | execution records -> gateway finalization lineage | Consistent. |
| 3, 9 | context-package schema -> resolver persistence | Consistent. |
| 3, 10 | routing/evidence schema -> router persistence | Consistent. |
| 3, 11 | evaluation/lineage schema -> evaluation/OTel services | Consistent. |
| 4, 5 | transactional events/outbox -> kernel transitions | Consistent; Task 5 transitions requiring events must use one UoW. |
| 4, 6 | transactional events/outbox -> waiting/approval/reconciliation | Consistent; no post-commit dual write. |
| 4, 8 | durable execution/event records -> gateway | Consistent. |
| 4, 11 | privacy guard/outbox -> evaluation and telemetry | Consistent. |
| 5, 6 | claims/retry/kernel/repository -> waiting/approval/reconciliation | Shared files/interfaces are intentional; Task 6 extends Task 5 without reviving claims. |
| 5, 8 | claim identity/fencing -> gateway late-result guard | Consistent; INV-EXE-004 depends on Task 5. |
| 5, 11 | kernel execution -> exporter-failure test | Consistent; telemetry remains non-fatal. |
| 5, 12 | kernel/restart/retry -> job-score NEW runtime | Consistent. |
| 5, 13 | kernel/retry -> CV runtime | Consistent. |
| 5, 14 | kernel/retry -> cover-letter runtime | Consistent. |
| 5, 15 | generic claim/fence/retry -> Coach dual fencing | Consistent; Task 15 must retain Coach domain fences too. |
| 6, 8 | approvals/reconciliation -> gateway commit and OUTCOME_UNKNOWN behavior | Consistent; exact payload hash precedes commit. |
| 6, 15 | generic reconciliation -> Coach domain callback | Consistent; no blind replay. |
| 7, 8 | Control Plane decision -> gateway authorization | Consistent; visibility is not authorization. |
| 7, 10 | policy eligibility -> router gating | Consistent; FORCE cannot bypass policy. |
| 7, 11 | capture/budget constraints -> evaluation/telemetry | Consistent. |
| 7, 12 | policy -> job-score migration | Consistent. |
| 7, 13 | policy -> CV migration | Consistent. |
| 7, 14 | policy -> cover-letter migration | Consistent. |
| 7, 15 | policy -> Coach migration | Consistent; models never authorize. |
| 8, 10 | LLM gateway -> selected model descriptor | Consistent. |
| 8, 11 | execution records -> evaluation lineage/OTel | Consistent. |
| 8, 12 | capability gateway -> scoring binding | Consistent. |
| 8, 13 | artifact/LLM gateway -> CV binding | Consistent. |
| 8, 14 | artifact/LLM gateway -> cover-letter binding | Consistent. |
| 8, 15 | gateway/reconciliation -> Coach adapter | Consistent. |
| 9, 10 | ContextPackage -> model routing requirements | Consistent. |
| 9, 12 | candidate/job providers -> scoring | Consistent. |
| 9, 13 | shared candidate/job providers -> CV | Consistent. |
| 9, 14 | shared candidate/job providers -> cover letter | Consistent; no forked provider. |
| 9, 15 | Coach providers -> Coach adapter | Consistent; domain data not relocated. |
| 10, 11 | routing decision/llm_factory -> evaluation/OTel | Shared `llm_factory` edits require preserving provider construction. |
| 10, 12 | router -> scoring | Consistent. |
| 10, 13 | router -> CV | Consistent. |
| 10, 14 | router -> cover letter | Consistent. |
| 10, 15 | router -> Coach | Consistent. |
| 11, 12 | evaluation/privacy/OTel -> scoring migration evidence | Consistent. |
| 11, 13 | evaluation/privacy/OTel -> CV migration evidence | Consistent. |
| 11, 14 | evaluation/privacy/OTel -> cover-letter evidence | Consistent. |
| 11, 15 | evaluation/privacy/OTel -> Coach gate | Consistent; V6 leakage rules still bind Coach. |
| 12, 13 | Job Scoring NEW gate -> CV start; shared runtime core | Sequential gate is explicit and consistent. |
| 12, 14 | Job Scoring NEW -> R3 generation gate | Consistent. |
| 12, 15 | Job Scoring NEW -> Coach R4 prerequisite | Consistent. |
| 12, 16 | R5 evidence -> final R4 report | Consistent. |
| 13, 14 | shared `tailor_service.py`/router/context/artifact paths | Consistent; Task 14 must reuse Task 13 infrastructure. |
| 13, 15 | CV NEW -> Coach R4 prerequisite | Consistent. |
| 13, 16 | R6 evidence -> final R4 report | Consistent. |
| 14, 15 | Cover Letter NEW -> Coach R4 prerequisite | Consistent. |
| 14, 16 | R7 evidence -> final R4 report | Consistent. |
| 15, 16 | R8 evidence/legacy inventory -> final R4 report | Consistent; Task 16 is evidence-only absent separate cleanup approval. |

## Per-task internal consistency scan

| Task | Tests/files/steps agree internally? | Finding |
|---|---|---|
| 1 | Yes | Documentation RED is explicitly allowed only before repair; characterization changes no product behavior. |
| 2 | Yes | Step numbering skips 5 but commands/files are unambiguous; no implementation conflict. |
| 3 | Yes | Migration and store tests match the declared schema/UoW output. |
| 4 | Yes | Atomicity/privacy tests match the transaction-owned event/outbox API. |
| 5 | Yes | RED cases, short transactions, immutable retry, and focused gate align. |
| 6 | Yes | Waiting/approval/reconciliation tests match output APIs and extend Task 5. |
| 7 | Yes | Precedence/FORCE tests match immutable constraint folding. |
| 8 | Yes | Gateway ordering and adapters match test set; product adapters remain bindings. |
| 9 | Yes | Declared-only resolution and immutable packages match persistence contract. |
| 10 | Yes | Router stage order and promoted evidence tests match implementation. |
| 11 | Yes | Evaluation bounds, OTel failure, capture policy, and privacy tests align. |
| 12 | Mostly | Duplicate Step 5 label is editorial only; owner approval remains a real promotion gate. |
| 13 | Yes | Validation-before-commit and SHADOW no-artifact rules align. |
| 14 | Yes | Shared-provider and one-writer tests align with reuse requirement. |
| 15 | Yes | V6 traceability precedes code; generic and domain fences are both required. |
| 16 | Yes | Evidence-only baseline and separately approved cleanup rule align. |

Pre-flight verdict: no R2-blocking contradiction. Task 5 may proceed from `fb4d6d2`.

Task 5: implementation complete pending review (commit `f637490`; focused 10 passed; affected runtime regression 23 passed; full backend 3332 passed, 2 skipped; 18 pre-existing warning-only diagnostics documented). Implementer concern disposition: Task 6 intentionally owns waiting/approval/OUTCOME_UNKNOWN reconciliation, so those omissions are within scope rather than correctness gaps.

Task 5: fix round 1/5 (`c3d5f3e`) — durable retry budget, injected finalization clock, and additive migration resolved. Scoped re-review found two Important boundary gaps still open: lower `WorkflowStore.schedule_retry()` validation and contention coverage under the full supported SQLite configuration. No Critical findings; Fix Round 2 dispatched for only those two items.

Task 5: fix round 2/5 (`f7e678f`) — storage-boundary retry metadata validation and full supported SQLite contention configuration resolved. Fresh scoped review: clean; no Critical or Important findings. Independent evidence: focused runtime/storage 31 passed, migration/schema 20 passed, contention 3 passed, Ruff and `git diff --check` passed.

Task 5: complete (commits `fb4d6d2..f7e678f`, review clean). Task 6 may extend the reviewed kernel interfaces for waiting, approvals, and generic reconciliation.

Task 6: implementation complete pending review (`f614e20`; current Python 3.12 R2 gate 50 passed; full suite 3384 passed with 2 container-environment-only failures independently passing on host; Ruff/docs/single-head/canonical current-head passed).

Task 6: fix round 1/5 dispatched after review found 8 Important issues and no Critical issues: scheduler-only retry waits, approval scope/invalidation, JSON-native canonicalization, reconciler crash recovery, durable capability/idempotency binding, privacy-safe reason codes, semantic protocol conformance, and evidence/restart/rollback accuracy. ARCH-08 approval transition event atomicity is included based on the approved `approval.granted` event example; no Task 6 outbox destination is defined.

Task 6: fix round 1/5 (`eb9c4bb`) — five findings resolved; scoped review left durable-restart proof, exact backend-neutral protocol conformance, and evidence provenance unresolved.

Task 6: fix round 2/5 (`68a6570`) — reconstructed-kernel restart proof resolved; scoped review left repository return-type conformance and symbolic evidence ranges unresolved.

Task 6: fix round 3/5 (implementation `4834991`, evidence-only `bb59fe6`) — exact return-contract testing and immutable provenance resolved. Fresh scoped review: CLEAN; no Critical, Important, or Minor findings.

Task 6: complete (implementation range `f7e678f..4834991`, evidence-only follow-up `bb59fe6`; review clean). R2 release-level verification and whole-branch review may proceed.

R2 whole-branch review at `bb59fe6`: not merge-ready; 5 Important findings, no Critical findings. Release Fix Round 1 dispatched for lease-deadline enforcement, aggregate run/step lifecycle, terminal failure-code privacy validation, bounded/isolated recovery batching, corrected final evidence, and terminal ownership clearing.

R2 release fix round 1/5 (code `394bbfb`, evidence `eeeb184`): terminal privacy and ownership clearing resolved; scoped re-review left stale post-handler reconciliation time, incomplete aggregate lifecycle/rollback proof, poison-record starvation, and evidence corrections unresolved. Release Fix Round 2 dispatched with durable non-authorizing recovery-failure backoff.

R2 release fix round 2/5 (code `e9ae56c`, evidence `cf30601`): fresh post-handler clock resolved; scoped re-review left complete original-claim lifecycle assertions and recovery-deferral CAS/reclaim enforcement unresolved. Release Fix Round 3 dispatched for only those two gaps.

R2 release fix round 3/5 (code `8c53fcc`, evidence `ce9bb1c`): stale-selection/reclaim deferral CAS and bounded fairness implemented; scoped re-review found only proof gaps in exhaustive lifecycle snapshots/counts and true deferred OUTCOME_UNKNOWN alternate-claim coverage. Release Fix Round 4 dispatched as proof-only unless tests expose a defect.

R2 release fix round 1: implementation `394bbfb`, docs-only evidence `eeeb184`.
TDD RED: 20 intended failures. GREEN: runtime 148 passed; affected persistence/schema/
event/contention 22 passed; full backend 3420 passed, 2 skipped. Ruff/docs/diff passed;
sole Alembic head confirmed. Scoped re-review pending.

R2 release fix round 2/5 (implementation `e9ae56c`; evidence-only follow-up pending):
fresh injected post-handler reconciliation time, aggregate lifecycle/rollback proof,
and bounded per-record poison recovery with durable non-authorizing backoff resolved.
Independent Python 3.12 evidence: focused 126/126 passed (66 core, 56 reconciliation/
release, 4 schema); Ruff/docs/diff and canonical fresh setup/current-head passed at sole
head `u8v9w0x1y2z3`. Full container backend result was 3448 passed, 2 known
container-environment-only failures, 6 warnings; exact host rerun of those failures
passed 2/2. Final scoped review remains pending.

R2 release fix round 4 proof closure: implementation/test head `07b89df48be55b63e5958b8aefeccd431f3740ac`.
The release-contract gate passed 43 tests and the combined reconciliation/release
focused gate passed 60 tests on the available host interpreter (Python 3.14.7;
Python 3.12 is unavailable). Runtime collection reports 169 tests. A full runtime
execution was attempted but stalled in the existing approval test before producing
a reliable completion count and was interrupted; no full-suite pass is claimed.
Ruff and `git diff --check` passed. Scoped re-review remains pending.

Ruling: the ledger's historical R3/R4 entries are incomplete, but `origin/main`
contains merged PR #64 (`d20bb89`) and PR #66 (`b842957`) with the Task 9-11
implementation/evidence commits (`eb7e4b8`, `6e27db9`, `1978b26`, and repairs).
Treat Tasks 7-11 as complete and resume at Task 12. Cost if wrong: a missed
unmerged change would be detected by the fresh-main base, task review, and R5
compatibility gates before any promotion.

Task 12: dispatched from fresh merged-main base `b842957` to
`r5_task12_implementer`. Baseline: docs validation passed; Alembic sole head
`z3a4b5c6d7e8`; Python 3.12 runtime suite `364 passed` (two cache-write
warnings). Full local backend baseline was interrupted after `622 passed` by
the pre-existing offline Hugging Face model-download retry; GitHub CI passed
for the same `b842957` commit.

Task 12: fix round 1/5 dispatched after independent review found five
Important gaps: the runtime path wrapped legacy scoring rather than producing
an independent runtime result; a global claim could cross run identity;
SHADOW lineage/metrics/failure-retention/purge were incomplete; R2 benchmark
claims used fake inputs and wrong percentile calculations; and agent evidence
mocked the product boundary. No Critical findings.

Task 12: Ruling: all five round-1 findings are valid and structurally coupled
within the approved Task 12 scope. A fresh higher-capability implementer owns
the repair because the first implementer reported the combined runtime scorer,
targeted claim, scheduled purge, valid benchmark, and database integration
work as materially larger than a patch. Cost if wrong: R5 takes longer, but
the first-job-scoring architecture proof remains honest rather than promoting
a facade-only migration.

Task 12: fix round 1/5 implementation `f8a011f` completed. The re-review
confirmed independent successful NEW/SHADOW execution, exact-run claims,
shadow lineage/retention, and honest non-promotion R2 evidence, but found two
Important defects: NEW error fallback can bypass a claimed runtime attempt's
fenced lifecycle/projection, and the fenced NEW event payload can duplicate
unbounded model-generated score prose. Focused evidence completed before a
subsequent environment failure: runtime/scoring 418 passed, 1 skipped;
DB-backed integration 13 passed; retention 4 passed; real benchmark 2 passed;
non-DB contract selection 7 passed. Fresh reruns are blocked by independently
reproducible aiosqlite `:memory:` connection hangs; no full-suite pass is
claimed. The benchmark observes 3.161x p50 and 2.794x p95 latency, and live
provider/token/cost evidence is unavailable, so Gate R2 remains incomplete
and the default remains legacy.

Task 12: fix round 2/5 dispatched only for runtime-owned NEW fallback fencing
and privacy-safe NEW event payloads. These are coupled: a fallback must not
create an independently durable visible result after a runtime run starts,
and event payloads must contain only safe references/metadata rather than raw
model-generated scoring prose. No NEW promotion, push, or PR is authorized.

Task 12: fix round 2/5 implementation `b60b1b3` replaced unfenced NEW
fallback with runtime-owned recovery and moved NEW event content behind a
canonical score reference. Its final affected evidence was 482 passed, 1
skipped; a previous full-backend run reached 3688 passed, 2 skipped, 1 stale
prompt-catalog failure, which the affected suite then covered after correction.
Fresh review found two Important end-to-end gaps: an error after a committed
runtime projection can still mark the source event failed and permit a costly
public retry/new run, and the raw public event list/detail APIs have not joined
the reference read-through used by the other product readers.

Task 12: fix round 3/5 dispatched only for post-commit source-event lifecycle
reconciliation/retry idempotency and privacy-safe canonical-score read-through
in the public event list/detail APIs. The repair must prove public retry cannot
produce a duplicate runtime/model charge after a successful projection, and
must preserve the reference-shaped output vocabulary without persisting raw
model prose in event payloads. No NEW promotion, push, or PR is authorized.

Task 12: fix round 3/5 implementation `771b3f8` added fenced source-event
acknowledgement/reconciliation and public event list/detail reference
hydration. Evidence: RED 7 failed/10 passed, focused GREEN 46 passed, and full
backend 3706 passed, 2 skipped, 16 warnings, exit 0. Fresh review found one
Important pre-dispatch race: concurrent NEW scorers can both observe no run,
then each create/claim a distinct run and incur duplicate provider cost before
the later projection fence acts. The sequential retry coverage does not prove
this concurrent window closed.

Task 12: fix round 4/5 dispatched only for an atomic source-event ownership or
idempotency boundary before job-score runtime dispatch, plus true concurrent
integration proof that exactly one run/model invocation/projection is created.
The repair must retain crash/restart recovery and not introduce a generic
schema change outside the Task 12 contract unless required by durable fencing.
No NEW promotion, push, or PR is authorized.

Task 12: fix round 4/5 implementation `7057fd7` uses a stable source-derived
run identity and atomic create-or-validate binding before claim/execution, with
existing durable lease/fence recovery. Separate-process ownership/restart and
collision coverage passed 10 tests. Historical full backend evidence was 3713
passed, 2 skipped, 2 failures; both compatibility failures were corrected and
the final affected suite passed 509, 1 skipped. Fresh scoped review found no
Critical or Important issues and confirmed generic optional-run-id compatibility,
cross-job/profile binding rejection, and the stated distinction from ambiguous
in-flight provider billing. A whole-Task-12 final acceptance audit is pending;
R2 remains incomplete and legacy remains default.

Task 12: implementation complete and final acceptance review CLEAN for
`b842957..7057fd7` (SPEC: PASS, QUALITY: PASS). The implementation keeps
LEGACY default and satisfies the reference-only task contract, independent
runtime NEW/SHADOW execution, durable cross-process fencing/recovery,
metadata-only persistence with transient API read-through, shadow retention,
and prompt catalog alignment. Verification accounting is intentionally exact:
clean full backend at `771b3f8` was 3706 passed, 2 skipped; after `7057fd7`,
the previous full run was 3713 passed, 2 skipped, 2 corrected compatibility
failures and the final affected suite was 509 passed, 1 skipped. No final
full-suite pass after `7057fd7` is claimed. R2 promotion is BLOCKED: offline
latency exceeds the threshold, live same-provider/model token/cost/latency
evidence is absent, and owner approval is not granted. Do not set NEW default
or begin the next mode-gated task until this gate is satisfied.
