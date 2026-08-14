# V6 threat and test matrix

Use this matrix after identifying the changed trust boundaries. V6 is the sole Phase 1 authority; the approved integration design adds execution gates but cannot change V6 technical contracts.

## Authority

- `docs/implementation-specs/active/Hatch_Conversational_AI_Interview_Coach_Phase1_Implementation_Spec_v6.md`
- `docs/superpowers/specs/2026-07-24-coach-phase1-phase2-integration-design.md`
- Relevant V6 sections: 9, 19, 21, 24, 29–31, 35–38, and 42–46.

Recompute document hashes for each evidence run. Do not assume the hashes recorded by an earlier run still describe the tracked files.

## Boundary matrix

| Trust boundary | V6 binding controls | Minimum negative, adversarial, and race evidence |
|---|---|---|
| Conversation commands and state | Section 9: validate the typed envelope; canonicalize and hash semantic JSON; look up `(session_id, command_id)` before version validation; return the original matching result; reject same ID/different hash; apply new mutations and result persistence atomically; reject stale `expected_state_version` with the canonical error. | Replay before and after restart; same ID with changed payload; stale and future state versions; invalid command/payload; concurrent `begin_answer`; exact attempt-limit boundary; assert one mutation/event/job and unchanged state on rejection. |
| Authentication, IDs, and object ownership | Sections 30.4 and 35: use existing authentication/lock boundaries, `_require_safe_id` patterns, parent ownership, canonical safe errors, and no internal details. This applies to session, question, attempt, upload, export, retention, and deletion routes. | Unauthenticated/unauthorized access; cross-user and cross-session question/attempt/media IDs; malformed and traversal-like IDs; IDOR enumeration; assert no data existence leak, mutation, file access, or unsafe error detail. |
| Audio upload and storage | Sections 19 and 30.5–30.6: stream to generated temporary storage, verify SHA-256 and byte size, canonicalize the upload hash, enforce MIME/size/state/ownership, never use the original filename as a path, constrain resolved paths to the Coach root, reject symlinks where supported, and delete duplicate/failed temporary data. | Hash mismatch, oversized body, unsupported/spoofed MIME, traversal filename, symlink/path escape, cross-attempt upload, duplicate matching upload, same ID/different request, concurrent upload, and temp-file cleanup. Prove no overwrite and at most one current completed upload. |
| Processing jobs and stale workers | Section 21: workers open their own database sessions; claims bind job ID, generation, source versions/hash, deadline, and claim token where applicable; retries share one absolute deadline; stale stages record no authoritative content; reconciliation is idempotent. Section 36 binds limits and snapshotted retry budgets. | Two finalizers; transcript edit/retry/deletion while an old worker runs; expired deadline/lease; wrong claim token, generation, transcript version, or audio hash; duplicate reconciliation; assert no stale authoritative mutation and exact once-only version/event effects. |
| Evidence and AI output | Sections 24, 30.1–30.3, 30.7, and 38: separate system contract, trusted metadata, and untrusted content; enforce strict schemas and application validation; validate spans, evidence IDs, source hashes, approval capabilities, and deterministic status rules; never treat absence as false or infer confidence, emotion, personality, deception, or culture fit. | Prompt injection in transcript, CV, job, Question Bank, and evidence; invented/wrong-source IDs; invalid spans/enums; authoritative conflict versus lower-trust support; draft consent boundaries; schema escape/repair exhaustion; prohibited judgement in model-authored content versus a legitimate transcript quotation. Assert invalid output never partially persists. |
| Audio retention and cleanup | Sections 21.3 and 29.1–29.4: each attempt snapshots policy; default cleanup begins after transcript commit and terminal speech analysis, independently of evaluation; deletion requires exact URI, hash, policy, state, claim, and generation predicates; explicit audio deletion keeps transcript/evaluation; terminal effects increment specified versions once. | Changed retention before finalization; stale cleanup after replacement; missing/mismatched hash/path/policy/token; already-deleted retry; failure and reconciliation repetition; cleanup concurrent with evaluation. Assert no replacement deletion, truthful failure state, and no `activity_version` increment for audio-only deletion. |
| Transcript and session deletion | Sections 29.5–29.9: physically delete transcript versions and derived evaluation/evidence/coaching data; fence workers by incrementing generation; invalidate/rebuild completed reports; hide hard-delete claims from normal reads; fence setup/attempt/report workers; delete owned media; finalize only on the full deletion claim; retain only bounded pseudonymous command receipts. | Delete during evaluation/report/setup; delete accepted, active, historical, root, and follow-up transcripts; duplicate deletion; stale delete finalizer; media-removal/database failure; expired claim and retry with new command ID; receipt expiry. Assert deleted content is absent from reads, export, progress, logs, and telemetry and stale workers cannot restore it. |
| Synchronous export | Section 29.12: require completed/fallback report, match activity and retention versions before rendering and before response commit, render from one snapshot, produce byte-identical results/ETags for identical requests, send `Cache-Control: no-store`, use a safe filename, and never include/link raw audio. | Cross-owner request; stale version at entry and response race; invalidated/building/failed report; include flag disallowed after deletion; repeated identical request; hostile title/ID content. Assert 409 without stale bytes, safe headers, deterministic bytes, and no server export artifact. |
| Errors, logs, metrics, traces, and diagnostics | Sections 29.11, 31, 35, and AC-30: derive errors from the single registry; return one safe status/retryability/message mapping; do not expose stack, prompt, provider secret, restricted evidence, or path; never log transcript/evidence/CV/prompt/model bodies or user paths; exclude IDs/content from metric labels; keep `state_version` trace-only. | Seed unique synthetic canaries in every sensitive field, force success and failures, and scan captured logs, spans, metric attributes, diagnostics, error bodies, and support output. Test the metric sanitizer and forbidden error alias. Assert canaries and raw IDs/paths are absent while stable content-free codes remain. |
| Frontend rendering and browser capture | Sections 30.1, 37.14–37.15, and 42.7: render untrusted transcript/evidence safely; server state wins after refresh; 409 refresh does not duplicate; voice is optional; capture and retention states are truthful and keyboard accessible. | Stored/reflected markup and script payloads in every rendered untrusted field; stale-tab conflict; refresh during capture/processing; microphone denial; deleted-content back navigation. Assert no execution, unsafe URL/navigation, duplicate command, false resume/deletion claim, or audio-only accessibility barrier. |
| Resource and release gates | Sections 30.6, 37–38, 42–46 and the approved integration design: enforce bounded characters, claims, excerpts, audio, duration, attempts, questions, retries, deadlines, and benchmark groups. Run security/adversarial suites with synthetic content in isolation; no unresolved critical/high finding; explicitly disposition every medium. | Exact boundary and boundary-plus-one inputs; retry/deadline exhaustion; expensive prompt/schema cases; duplicate/group amplification; dependency, secret, and static analysis; isolated seeded API scanning. Record full regression, E2E, benchmark, stale-worker, feature-flag, and compatibility results required by the touched PR. |

## Coverage selection

For every changed boundary, select at least one test from each applicable class:

- **Negative:** missing/invalid credentials, ownership, ID, state, version, type, size, hash, or contract.
- **Adversarial:** injection, schema escape, path manipulation, prohibited inference, unsafe rendering, or leakage canary.
- **Replay/race:** duplicate key, reordered response, concurrent mutation, stale worker, cleanup/deletion replacement, or source-version change.
- **Safe failure:** no partial persistence, no unauthorized disclosure, truthful stable error, bounded retry, and recoverable/idempotent cleanup.

Document why a class is not applicable; silence is not evidence.

## Finding disposition

Each finding records:

```text
ID and severity
boundary and attack precondition
V6 section / approved gate, or "optional hardening proposal"
reproduction command and synthetic fixture
observed versus required behavior
affected confidentiality, integrity, availability, or privacy property
owner and disposition: fix, accepted risk, deferred proposal, or false positive
verification artifact and residual limitation
```

Only a violated binding contract or approved repository gate contributes to the binding verdict. Optional proposals remain visible but do not masquerade as V6 blockers. Critical/high findings block promotion; every medium requires an explicit disposition under the approved integration design.
