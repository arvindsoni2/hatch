# Combined PR2 and PR3 Onboarding and AI Design

**Date:** 2026-07-14

**Branch:** `feature/release-blocker-onboarding-ai-pr2-pr3`

**Source specification:** `/home/asoni/Downloads/Assignment/HatchCV/docs/Hatch_Release_Blocker_Installer_Onboarding_AI_Spec_v3.md`

**Delivery:** One combined GitHub pull request with logically separated PR2 and PR3 commits

## Purpose

Implement the specification's password-sequencing and actionable AI onboarding work as one coherent change. PR2 establishes authoritative onboarding and finalization state. PR3 extends the existing `/api/setup/*` control plane with independent AI and capability intent, derived readiness, safe host actions, and a shared onboarding and Settings experience.

The combined implementation must preserve the browser/host security boundary, remain usable without generative AI, and safely normalize existing installations.

## Decisions

- Extend the existing `/api/setup/*` API family. Do not create a replacement control plane.
- Deliver PR2 and PR3 on one branch and in one pull request.
- Keep commits logically separated by PR2 backend, PR2 frontend, PR3 backend/CLI, PR3 frontend, and verification/documentation responsibilities.
- Support Anthropic, OpenAI, Google GenAI, and OpenRouter in normal cloud onboarding.
- Preserve additional CLI/developer provider aliases for compatibility, but do not expose unsupported providers in normal onboarding.
- Use explicit cloud connection tests. Setup-status polling reads cached validation evidence and never makes billable provider calls.
- Cache successful cloud validation for 24 hours. Provider, model, or secret changes invalidate it immediately; observed runtime failures override it.
- Verify local model checksums during installation. Reuse a verification manifest during status polling and rehash only when relevant file metadata changes.
- Keep `custom` as a compatibility-only AI mode. Preserve and round-trip it without offering it during normal onboarding.
- Allow onboarding to complete while AI or optional capabilities remain pending.

## Architecture

### Authoritative setup service

The existing setup router remains the public control plane. A focused setup-status service composes one response from:

- database-backed onboarding state;
- persisted non-secret setup intent;
- the canonical hardware probe;
- local model catalog, verification evidence, and service health;
- cloud provider catalog, secret-presence status, and cached validation evidence;
- selected and active backend capability profiles;
- current structured setup/runtime errors.

The router owns request validation and HTTP responses. Services own state transitions, normalization, readiness derivation, catalog validation, and host-action construction. Frontend components do not recreate readiness or shell-command rules.

### Storage ownership

The singleton onboarding record is database-backed and authoritative for first-run routing and finalization. The canonical personal profile remains `profile.yaml`. Non-secret AI and capability intent remains under `${HATCH_HOME}/config` and is written atomically.

Persisted setup intent contains semantic equivalents of:

- `ai_mode`: `not_configured`, `none`, `local`, `cloud`, or `custom`;
- selected backend profile;
- selected primary and optional triage local-model catalog IDs;
- selected cloud provider and model IDs;
- nullable `setup_deferred_at`.

Readiness, errors, active state, and pending actions are derived evidence and are not persisted as authoritative intent.

## PR2: Onboarding and Password Finalization

### State model

Add one singleton onboarding-state row with:

- `status`: `not_started`, `in_progress`, `finalization_pending`, or `complete`;
- stable last-completed-step identifier;
- finalization identifier and payload hash required for idempotency;
- timestamps and recovery metadata required by the source specification.

The migration derives an initial state from existing profile/onboarding evidence. A configured app lock alone does not imply completed onboarding. Completed existing installations must not be forced through onboarding again.

### First-run and finalization flow

1. Welcome is always the first new-install screen.
2. Personal profile, market, preferences, skills, and experience answers remain in React memory and `sessionStorage` before password setup.
3. Non-secret AI/capability intent may be saved through the bootstrap setup API before password setup.
4. Review validates staged personal data and setup intent.
5. Protect Workspace creates the password and unlocked session, then moves onboarding to `finalization_pending`.
6. The frontend immediately reconciles shared app-lock and setup queries.
7. The authenticated finalization endpoint receives the staged payload and client-generated finalization ID.
8. Finalization writes the canonical profile safely, records its hash, and commits onboarding `complete` according to the crash-recovery contract.
9. Success renders only after the server confirms completion.

Retries with the same finalization ID and payload are idempotent. Conflicting finalization attempts return the specified conflict response and never overwrite a completed onboarding record.

### Recovery and reconciliation

If password setup succeeds but profile finalization fails, the app remains unlocked and routes to a focused finalization recovery state. It does not show the password form again. App-lock setup, app-lock gate, onboarding status, and profile readiness use shared invalidation/refetch behavior after every state-changing request.

The explicit start-new-onboarding flow clears only the specified draft/progress data and preserves the app lock, user records, models, secrets, and completed state where required by the reset contract.

## PR3: AI and Capability Onboarding

### Independent dimensions

The UI and persistence model treat these as independent choices:

1. Generative AI: None, Local, or Cloud.
2. Backend capability profile: Core, Browser, Local Embeddings, or Full capabilities.

`not_configured` means no explicit choice. `none` means the user explicitly selected no generative AI. Legacy `ai-later` normalizes to `none`; legacy `advanced` is an input alias for `none` plus an explicitly selected capability profile. Selecting Full never changes the AI mode.

### Intent writes

Setup-intent endpoints perform atomic read-modify-write operations and update only fields owned by the operation. Model selection preserves provider and capability fields. Provider selection preserves local-model and capability fields. Capability selection preserves AI/provider/model fields. CLI commands follow the same ownership rules.

Idempotency is based on the normalized resulting intent. Repeating the same request has no additional effect.

### Hardware and local models

The backend classifies the host-generated probe as available, missing, stale, invalid, or error. A probe older than 30 days is stale. The browser displays backend recommendations and never encodes RAM or model thresholds.

The local-model catalog supplies display metadata, roles, compatibility, sizes, memory guidance, checksums, installed state, selected state, and service readiness. The backend preselects recommendations but the user may choose another compatible catalog entry.

Model installation verifies the expected checksum and writes a non-secret verification manifest containing the catalog ID, filename, size, modification metadata, checksum, and verification time. Status requests trust this evidence only while the file metadata still matches; otherwise verification becomes pending until a controlled recheck recalculates the checksum.

### Cloud providers

The backend owns the normal onboarding provider catalog for Anthropic, OpenAI, Google GenAI, and OpenRouter, including supported model choices and host-secret commands. The frontend renders this catalog instead of hard-coding providers or models.

The browser never accepts a provider secret. It displays `hatch secrets set <provider>` from the backend. An explicit connection-test request uses the host-owned secret and returns redacted structured status. Successful evidence is cached for 24 hours and keyed to provider, model, configuration, and a non-returned secret fingerprint. Status polling only reads that evidence. Configuration changes, secret changes, expiry, or observed runtime failures invalidate readiness.

### Capabilities and ordered host actions

Setup intent records the selected capability profile while runtime inspection reports the active profile and required service health. A mismatch yields an explicit `hatch capabilities enable <profile>` or disable action.

The backend returns validated actions in dependency order:

1. `hatch probe` when required;
2. capability activation when selected and active profiles differ;
3. explicit model installation or provider-secret setup;
4. `hatch apply-ai-config --restart` when configuration must be applied;
5. manual readiness recheck where appropriate.

Commands use validated catalog/provider/profile identifiers, remain interactive, and never append `--yes`. Host actions are instructional objects only; no API executes them.

### Derived readiness

Every setup-status response derives subsystem and overall state from current evidence. Precedence is:

1. `error` for a current blocking setup/runtime failure;
2. `not_configured` when a mandatory explicit selection is absent;
3. `pending_host_action` when intent exists but required work or health checks remain incomplete;
4. `ready` only when selected intent matches the active healthy runtime.

`none` can be ready when its selected capability profile is active and healthy. A saved local selection, present cloud secret, or selected capability profile alone is never sufficient.

Structured errors identify the subsystem, stable code, safe message, and retryability. They contain no secrets, stack traces, or arbitrary command output. The response retains useful last-known display data while the current subsystem and overall status reflect the error.

## API Shape

`GET /api/setup/status` becomes the normalized authoritative response defined by the source specification. It includes the PR2 onboarding object, canonical AI mode, selected and active profiles, derived overall status, probe state, local and cloud state, capability state, ordered next actions, and nullable structured error.

Existing `/api/setup/*` endpoints may be adapted or consolidated behind typed request models. Existing consumers receive a coordinated migration rather than a parallel response family. `/api/system/capabilities` may remain a read-only diagnostic compatibility endpoint, but it is not authoritative for onboarding.

Pre-password access is restricted to the minimum bootstrap operations defined by PR2. Personal profile persistence and protected operations still require the unlocked authenticated session.

## Frontend Experience

### Onboarding

The AI & Capabilities stage contains two internal sections:

1. Choose generative AI: None, Local, or Cloud.
2. Choose capabilities: Core, Browser, Local Embeddings, or Full capabilities.

Conditional panels show hardware, recommendations, model/provider choices, privacy and resource implications, selected versus active status, and ordered host actions. Option cards are keyboard accessible; selection and status never rely on color alone.

While pending, the primary action checks setup and the secondary action finishes setup later. Finishing later stores the timestamp, explains unavailable features, and continues to Review and Protect Workspace. The timestamp clears when setup becomes ready or the user changes setup intent.

After onboarding, a dismissible status banner links to Settings. Banner dismissal is session-scoped; the persistent AI & Capabilities Settings entry always remains available.

### Settings continuity

Onboarding and Settings share:

- canonical API and TypeScript types;
- provider and model catalogs;
- setup-status query and polling hook;
- option labels and implications;
- readiness and error components;
- ordered host-action and copy-command components.

Polling runs every five seconds while pending and visible, backs off to fifteen seconds after two minutes, stops on Ready/Error/unmount/hidden state, prevents overlap, and preserves prior content during transient failures.

## Security

- The browser receives no shell, Docker socket, arbitrary file-write, or command-execution access.
- Provider secrets remain under host CLI ownership and are never returned by setup APIs.
- Stored secret fingerprints are non-returned invalidation evidence, not authentication material.
- Host-action commands are constructed only from validated identifiers.
- Pre-password bootstrap access excludes personal profile persistence and protected application APIs.
- Existing developer-stack compatibility remains intact without weakening easy-install boundaries.

## Testing

### Backend and migration tests

Cover onboarding migration/state transitions, password-finalization idempotency and recovery, bootstrap authorization, reset preservation, canonical AI normalization, independent capability intent, atomic field preservation, probe states, model evidence, cloud secret redaction and cached validation, selected/active capability status, action ordering, readiness precedence, and structured errors.

### Frontend tests

Cover password-last sequencing, shared query reconciliation, recovery after finalization failure, all normal AI and capability choices, hidden `custom`, explicit None, probe/model/provider panels, selected versus active state, polling/backoff, finish-later behavior, accessibility, and Settings continuity.

### End-to-end tests

Run the PR2 first-run, retry, existing-user, and reset matrix plus all ten PR3 scenarios from the source specification. Verify that pending setup never blocks password/finalization and is never mislabeled Ready.

### Regression and release gates

Run backend tests, frontend unit/component tests, installer and host-CLI tests, Playwright onboarding flows, documentation validators, standalone easy-install Compose validation, security-boundary checks, and the repository CI workflow. Record any unrelated baseline lint findings separately from changed-slice failures.

## Delivery Boundaries

This work does not add browser-controlled host execution, browser secret entry, automatic model downloads, a new model-serving architecture, or unrelated onboarding redesign. It adapts the existing setup APIs and UI patterns only as required to make the combined PR2 and PR3 contract correct and maintainable.
