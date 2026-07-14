# Combined PR2 and PR3 Onboarding and AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver password-last onboarding and a single authoritative AI/capability setup control plane with Standard Hatch, cloud-native model routing, curated Hugging Face local-model discovery, explicit host actions, and shared onboarding/Settings readiness.

**Architecture:** Add a singleton SQL onboarding state and idempotent profile finalization, then compose it with atomic non-secret setup intent and request-time readiness under `/api/setup/*`. Keep AI engine, model routing, and optional capabilities separate; use backend-owned provider/model catalogs, curated Hugging Face discovery with a pinned fallback, and instructional host actions consumed by shared React Query hooks and components.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, httpx, SQLite, Bash/Python host CLI, Next.js/React, TypeScript, TanStack Query, Vitest, Playwright, Docker Compose.

## Global Constraints

- Deliver PR2 and PR3 on `feature/release-blocker-onboarding-ai-pr2-pr3` in one GitHub pull request with logically separated commits.
- Keep provider secrets host-managed under `${HATCH_HOME}/config/secrets.env`; never accept or return secret values through browser setup APIs.
- Keep the browser free of shell, Docker socket, arbitrary command execution, and arbitrary file-write access.
- Persist only intent and deferral timestamps; derive readiness and errors from current evidence.
- Use `none`, `local`, `cloud`, `custom`, and `not_configured` as canonical AI modes; hide `custom` from normal onboarding.
- Present persisted backend profile `core` as **Standard Hatch** in user-facing copy.
- Cloud mode uses provider-hosted primary/triage models and never enables the local llama.cpp overlay.
- Local mode requires explicit validated catalog selections before download or service activation.
- Curated Hugging Face discovery must enforce approved sources, licenses, GGUF/chat compatibility, pinned revisions, integrity metadata, and explicit selection.
- Preserve pinned Qwen defaults only in the legacy developer `docker-compose.yml`; remove fixed-model assumptions from easy-install, onboarding, shared CLI, and `docker-compose.local-ai.yml`.
- Use `apply_patch` for source edits, targeted tests during TDD, and fresh full verification before completion.

---

## File Structure

### New backend units

- `backend/app/models/onboarding.py`: singleton onboarding persistence only.
- `backend/app/services/onboarding_service.py`: onboarding migration, transitions, idempotency, and finalization orchestration.
- `backend/app/schemas/setup.py`: typed setup intent/status/action/provider/model API contracts.
- `backend/app/services/setup_intent.py`: canonical normalization and atomic field-owned intent writes.
- `backend/app/services/model_discovery.py`: curated Hugging Face query, policy filtering, ranking, caching, fallback, and verification evidence.
- `backend/app/services/provider_catalog.py`: cloud provider/model catalog and redacted validation evidence.
- `backend/app/services/setup_status.py`: request-time readiness derivation and ordered host-action construction.
- `backend/app/config/model_discovery_policy.json`: approved publishers, families, licenses, quantizations, and limits.
- `backend/app/config/provider_catalog.json`: normal onboarding cloud providers and primary/triage choices.
- `backend/alembic/versions/20260714_0001_o2p3q4r5s6t7_add_onboarding_state.py`: singleton onboarding schema and existing-install backfill.

### New frontend units

- `frontend/src/lib/setup.ts`: canonical setup types, API functions, query keys, and polling policy.
- `frontend/src/components/setup/SetupStatusPanel.tsx`: shared readiness/error presentation.
- `frontend/src/components/setup/HostActions.tsx`: ordered accessible command actions.
- `frontend/src/components/setup/AiEngineSelector.tsx`: None/Local/Cloud selection.
- `frontend/src/components/setup/ModelRoutingSelector.tsx`: local discovery or cloud provider/model routing.
- `frontend/src/components/setup/CapabilitySelector.tsx`: Standard Hatch plus advanced profiles.
- `frontend/src/components/setup/AiCapabilitiesForm.tsx`: shared composition used by onboarding and Settings.
- `frontend/src/components/setup/SetupStatusBanner.tsx`: post-onboarding pending reminder.

### Existing units to adapt

- Backend: app-lock, profile, setup router/service, reset, database/model registration, host CLI, fallback catalog, Compose files, tests.
- Frontend: app-lock gate, onboarding gate/page/draft, password/review screens, Settings AI page, API fixtures/tests.
- Documentation: README, installation, local models, CLI reference, operations, troubleshooting.

---

### Task 1: Add Authoritative Singleton Onboarding State

**Files:**
- Create: `backend/app/models/onboarding.py`
- Create: `backend/alembic/versions/20260714_0001_o2p3q4r5s6t7_add_onboarding_state.py`
- Create: `backend/app/services/onboarding_service.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/database.py`
- Test: `backend/tests/test_services/test_onboarding_service.py`
- Create: `backend/tests/test_migrations/test_onboarding_state_migration.py`

**Interfaces:**
- Produces: `OnboardingState`, `OnboardingStatus`, `OnboardingService.status()`, `mark_in_progress(step_id)`, `mark_password_configured()`, `mark_complete(finalization_id, payload_hash, profile_hash)`, and `reset_progress()`.
- Consumes: `AsyncSession`, canonical profile existence/completeness checks, and singleton row ID `1`.

- [ ] **Step 1: Write failing state-transition and migration tests**

```python
async def test_password_setup_moves_incomplete_onboarding_to_finalization_pending(db):
    service = OnboardingService(db)
    await service.mark_in_progress("review")
    state = await service.mark_password_configured()
    assert state.status == "finalization_pending"

async def test_existing_complete_profile_backfills_complete(migrated_db):
    row = migrated_db.execute("SELECT status FROM onboarding_state WHERE id = 1").fetchone()
    assert row == ("complete",)
```

- [ ] **Step 2: Run the tests and verify the missing model/service fails**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_onboarding_service.py tests/test_migrations/test_onboarding_state_migration.py --no-cov -q`

Expected: FAIL because `OnboardingState` and the migration do not exist.

- [ ] **Step 3: Add the singleton model and migration**

```python
class OnboardingState(Base):
    __tablename__ = "onboarding_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_started")
    last_completed_step: Mapped[str | None] = mapped_column(String(64))
    finalization_id: Mapped[str | None] = mapped_column(String(36))
    finalization_payload_hash: Mapped[str | None] = mapped_column(String(64))
    finalized_profile_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
```

The migration creates one row and classifies existing installations as `complete`, `in_progress`, or `not_started` from validated profile evidence; app-lock configuration alone never produces `complete`.

- [ ] **Step 4: Implement serialized transition methods**

```python
VALID_STEPS = {"welcome", "profile", "preferences", "skills", "experience", "ai-capabilities", "review", "protect-workspace"}

async def mark_in_progress(self, step_id: str) -> OnboardingState:
    if step_id not in VALID_STEPS:
        raise ValueError(f"Unknown onboarding step: {step_id}")
    row = await self.state()
    if row.status != "complete":
        row.status = "in_progress"
        row.last_completed_step = step_id
    await self._db.flush()
    return row

async def mark_password_configured(self) -> OnboardingState:
    row = await self.state()
    if row.status != "complete":
        row.status = "finalization_pending"
        row.last_completed_step = "protect-workspace"
    await self._db.flush()
    return row
```

Validate stable step IDs and legal transitions; never downgrade `complete` implicitly.

- [ ] **Step 5: Run focused tests and migration upgrade/downgrade checks**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_onboarding_service.py tests/test_migrations/test_onboarding_state_migration.py --no-cov -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/models/onboarding.py backend/app/models/__init__.py backend/app/database.py backend/app/services/onboarding_service.py backend/alembic/versions/20260714_0001_o2p3q4r5s6t7_add_onboarding_state.py backend/tests/test_services/test_onboarding_service.py backend/tests/test_migrations/test_onboarding_state_migration.py
git commit -m "feat(onboarding): add authoritative state machine"
```

### Task 2: Reconcile App-Lock Setup with Onboarding State

**Files:**
- Modify: `backend/app/services/app_lock_service.py`
- Modify: `backend/app/routers/app_lock.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routers/test_app_lock.py`
- Test: `backend/tests/test_middleware/test_app_lock_gate.py`

**Interfaces:**
- Consumes: `OnboardingService.mark_password_configured()` and `OnboardingService.status()`.
- Produces: app-lock status with authoritative `onboarding`, setup response with `unlocked` and `onboarding`, and minimum bootstrap allowlist behavior.

- [ ] **Step 1: Add failing tests for password-state reconciliation and bootstrap paths**

```python
async def test_setup_returns_finalization_pending(client):
    response = await client.post("/api/app-lock/setup", json={"password": "valid-password-1"})
    assert response.json()["onboarding"]["status"] == "finalization_pending"

async def test_locked_bootstrap_can_save_non_secret_setup_intent(client):
    response = await client.patch("/api/setup/intent", json={"ai_mode": "none"})
    assert response.status_code == 200
```

- [ ] **Step 2: Run focused tests and confirm current responses/423 behavior fail**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_routers/test_app_lock.py tests/test_middleware/test_app_lock_gate.py --no-cov -q`

Expected: FAIL because app-lock responses lack onboarding state and setup bootstrap paths are protected.

- [ ] **Step 3: Make app-lock setup and conflict responses authoritative**

```python
token = await AppLockService(db).setup(body.password)
onboarding = await OnboardingService(db).mark_password_configured()
return {"unlocked": True, "onboarding": serialize_onboarding(onboarding)}
```

On a duplicate password setup, return `409` without secrets and include the same authoritative lock/onboarding status so the frontend can reconcile.

- [ ] **Step 4: Add the narrow bootstrap middleware allowlist**

Allow only locale metadata, hardware/probe reads, provider/model catalogs, non-secret intent writes, setup status, onboarding finalization, and app-lock setup/unlock before an authenticated session. Keep profile writes and all product APIs locked.

- [ ] **Step 5: Re-run app-lock and middleware tests**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_routers/test_app_lock.py tests/test_middleware/test_app_lock_gate.py --no-cov -q`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add backend/app/services/app_lock_service.py backend/app/routers/app_lock.py backend/app/main.py backend/tests/test_routers/test_app_lock.py backend/tests/test_middleware/test_app_lock_gate.py
git commit -m "feat(onboarding): reconcile password and bootstrap state"
```

### Task 3: Add Crash-Safe Idempotent Onboarding Finalization

**Files:**
- Modify: `backend/app/services/profile_service.py`
- Modify: `backend/app/services/onboarding_service.py`
- Modify: `backend/app/routers/setup.py`
- Modify: `backend/app/services/setup_reset.py`
- Test: `backend/tests/test_routers/test_setup_onboarding.py`
- Test: `backend/tests/test_services/test_setup_reset.py`

**Interfaces:**
- Produces: `POST /api/setup/onboarding/finalize`, `POST /api/setup/onboarding/progress`, and reset behavior preserving app lock and completed onboarding when required.
- Consumes: unlocked app-lock session, `finalization_id`, complete staged profile payload, and existing profile validation.

- [ ] **Step 1: Add failing finalization/idempotency/recovery tests**

```python
async def test_finalize_same_id_and_payload_is_idempotent(unlocked_client, profile_payload):
    body = {"finalization_id": FIXED_ID, "profile": profile_payload}
    first = await unlocked_client.post("/api/setup/onboarding/finalize", json=body)
    second = await unlocked_client.post("/api/setup/onboarding/finalize", json=body)
    assert first.status_code == second.status_code == 200
    assert second.json()["onboarding"]["status"] == "complete"

async def test_different_id_after_completion_conflicts(unlocked_client, profile_payload):
    await unlocked_client.post("/api/setup/onboarding/finalize", json={"finalization_id": ID1, "profile": profile_payload})
    response = await unlocked_client.post("/api/setup/onboarding/finalize", json={"finalization_id": ID2, "profile": profile_payload})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "onboarding_already_complete"
```

- [ ] **Step 2: Run focused tests and verify the endpoint is absent**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_routers/test_setup_onboarding.py tests/test_services/test_setup_reset.py --no-cov -q`

Expected: FAIL with 404/missing service behavior.

- [ ] **Step 3: Add atomic profile serialization and hash helpers**

```python
def canonical_profile_bytes(data: dict[str, Any]) -> bytes:
    profile = Profile.model_validate(data)
    rendered = yaml.safe_dump(
        profile.model_dump(exclude_none=True), sort_keys=True, allow_unicode=True,
    )
    return rendered.encode("utf-8")

def profile_payload_hash(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_profile_bytes(data)).hexdigest()

def atomic_save_profile_raw(data: dict[str, Any]) -> tuple[Profile, str]:
    profile = Profile.model_validate(data)
    payload = canonical_profile_bytes(profile.model_dump(exclude_none=True))
    path = get_profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".profile.", suffix=".yaml", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return profile, hashlib.sha256(payload).hexdigest()
```

Write a same-directory temporary file, flush/fsync it, atomically replace `profile.yaml`, invalidate the profile cache, and return its SHA-256.

- [ ] **Step 4: Implement finalization orchestration and recovery rules**

Serialize singleton finalization, validate normalized setup intent without rewriting it, compare finalization ID/payload hash, repair a mismatched partial YAML only while `finalization_pending`, and mark SQL complete only after the final profile hash matches.

- [ ] **Step 5: Make onboarding reset narrow**

Exclude `onboarding_state` from generic deletion. `mode=onboarding` resets draft/progress according to the explicit contract, never deletes app-lock rows, secrets, models, jobs, or a completed onboarding record unless the endpoint is explicitly starting a new incomplete flow.

- [ ] **Step 6: Run finalization/reset tests**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_routers/test_setup_onboarding.py tests/test_services/test_setup_reset.py tests/test_routers/test_app_lock.py --no-cov -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```bash
git add backend/app/services/profile_service.py backend/app/services/onboarding_service.py backend/app/routers/setup.py backend/app/services/setup_reset.py backend/tests/test_routers/test_setup_onboarding.py backend/tests/test_services/test_setup_reset.py
git commit -m "feat(onboarding): finalize profiles idempotently"
```

### Task 4: Move Password Last and Add Frontend Recovery

**Files:**
- Modify: `frontend/src/app/onboarding/page.tsx`
- Modify: `frontend/src/components/onboarding/StepPasswordSetup.tsx`
- Modify: `frontend/src/components/onboarding/StepReview.tsx`
- Modify: `frontend/src/components/AppLockGate.tsx`
- Modify: `frontend/src/components/OnboardingGate.tsx`
- Modify: `frontend/src/lib/onboardingDraft.ts`
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/__tests__/components/AppLockGateState.test.tsx`
- Test: `frontend/src/__tests__/components/OnboardingGate.test.tsx`
- Test: `frontend/src/__tests__/components/StepPasswordSetup.test.tsx`
- Test: `frontend/src/__tests__/lib/onboardingDraft.test.ts`

**Interfaces:**
- Consumes: authoritative app-lock/onboarding responses and finalization endpoint.
- Produces: Welcome → personal steps → AI placeholder → Review → Protect Workspace → Success, plus focused finalization retry.

- [ ] **Step 1: Add failing order, session-storage, and recovery tests**

```tsx
it("places Protect Workspace after Review and never repeats it after setup", async () => {
  render(<OnboardingPage />);
  // Advance through review, assert password appears once, mock finalization failure,
  // rerender authoritative finalization_pending, then assert Retry finalization instead.
});

it("moves legacy non-sensitive draft fields to sessionStorage once", () => {
  migrateLegacyOnboardingDraft();
  expect(localStorage.getItem(LEGACY_ONBOARDING_STORAGE_KEY)).toBeNull();
  expect(sessionStorage.getItem(ONBOARDING_STORAGE_KEY)).toBeTruthy();
});
```

- [ ] **Step 2: Run targeted frontend tests and verify current password-first/localStorage behavior fails**

Run: `cd frontend && npm test -- --run src/__tests__/components/AppLockGateState.test.tsx src/__tests__/components/OnboardingGate.test.tsx src/__tests__/components/StepPasswordSetup.test.tsx src/__tests__/lib/onboardingDraft.test.ts`

Expected: FAIL on ordering, reconciliation, and storage assertions.

- [ ] **Step 3: Replace profile-derived routing with authoritative onboarding queries**

```ts
export const SETUP_STATUS_QUERY_KEY = ["setup-status"] as const;
// OnboardingGate redirects when setup.onboarding.status !== "complete".
// AppLockGate permits only the server-resolved bootstrap/finalization route.
```

- [ ] **Step 4: Implement password-last finalization flow**

After password setup, invalidate/refetch app-lock and setup queries, call `/api/setup/onboarding/finalize` with a stable client-generated ID, and show Success only after `complete`. On failure, retain staged session data and render Retry without returning to password.

- [ ] **Step 5: Replace new onboarding draft localStorage writes with sessionStorage**

Read each known legacy key once, retain only non-sensitive valid fields, remove the old key, and never persist password, CV content, free text, personal profile fields, or secrets in localStorage.

- [ ] **Step 6: Run focused frontend tests**

Run: `cd frontend && npm test -- --run src/__tests__/components/AppLockGateState.test.tsx src/__tests__/components/OnboardingGate.test.tsx src/__tests__/components/StepPasswordSetup.test.tsx src/__tests__/lib/onboardingDraft.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add frontend/src/app/onboarding/page.tsx frontend/src/components/onboarding/StepPasswordSetup.tsx frontend/src/components/onboarding/StepReview.tsx frontend/src/components/AppLockGate.tsx frontend/src/components/OnboardingGate.tsx frontend/src/lib/onboardingDraft.ts frontend/src/lib/api.ts frontend/src/__tests__/components/AppLockGateState.test.tsx frontend/src/__tests__/components/OnboardingGate.test.tsx frontend/src/__tests__/components/StepPasswordSetup.test.tsx frontend/src/__tests__/lib/onboardingDraft.test.ts
git commit -m "feat(onboarding): move password to finalization gate"
```

### Task 5: Add Canonical Atomic Setup Intent

**Files:**
- Create: `backend/app/schemas/setup.py`
- Create: `backend/app/services/setup_intent.py`
- Modify: `backend/app/services/ai_setup.py`
- Modify: `backend/app/routers/setup.py`
- Test: `backend/tests/test_services/test_setup_intent.py`
- Test: `backend/tests/test_routers/test_setup_router.py`

**Interfaces:**
- Produces: `SetupIntent`, `IntentPatch`, `load_setup_intent()`, `patch_setup_intent()`, canonical normalization, and `PATCH /api/setup/intent`.
- Consumes: `${HATCH_HOME}/config/ai_setup_intent.json` and legacy `experience`, `aiMode`, `ai-later`, and `advanced` fields.

- [ ] **Step 1: Write failing normalization and field-preservation tests**

```python
def test_legacy_ai_later_normalizes_to_explicit_none(tmp_config):
    write_intent({"ai_mode": "ai-later", "backend_profile": "full"})
    assert load_setup_intent().ai_mode == "none"

def test_capability_patch_preserves_cloud_models(tmp_config):
    seed_cloud_intent(primary="gpt-primary", triage="gpt-triage")
    updated = patch_setup_intent(IntentPatch(backend_profile="browser"))
    assert (updated.cloud_primary_model, updated.cloud_triage_model) == ("gpt-primary", "gpt-triage")
```

- [ ] **Step 2: Run focused tests and confirm current whole-object writes fail**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_setup_intent.py tests/test_routers/test_setup_router.py --no-cov -q`

Expected: FAIL because `none`, cloud primary/triage fields, and field-owned patching are absent.

- [ ] **Step 3: Define typed intent and patch ownership**

```python
class SetupIntent(BaseModel):
    schema_version: Literal[2] = 2
    ai_mode: Literal["not_configured", "none", "local", "cloud", "custom"]
    backend_profile: Literal["core", "browser", "local-embeddings", "full"]
    local_primary_model: str | None = None
    local_triage_model: str | None = None
    cloud_provider: str | None = None
    cloud_primary_model: str | None = None
    cloud_triage_model: str | None = None
    setup_deferred_at: datetime | None = None
```

- [ ] **Step 4: Implement locked atomic read-modify-write and aliases**

Normalize canonical fields before legacy aliases, map `ai-later` to `none`, map `advanced` to `none` while preserving explicit profile, preserve `custom`, validate mutually active routing fields, and fsync/replace the JSON file atomically.

- [ ] **Step 5: Add typed patch endpoint and retire misleading skip behavior**

`PATCH /api/setup/intent` updates only provided fields. `/skip-ai` becomes a compatibility wrapper that writes explicit `none`, not `not_configured`.

- [ ] **Step 6: Run setup intent/router tests**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_setup_intent.py tests/test_routers/test_setup_router.py --no-cov -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add backend/app/schemas/setup.py backend/app/services/setup_intent.py backend/app/services/ai_setup.py backend/app/routers/setup.py backend/tests/test_services/test_setup_intent.py backend/tests/test_routers/test_setup_router.py
git commit -m "feat(setup): add canonical atomic AI intent"
```

### Task 6: Add Curated Hugging Face Discovery and Verification Evidence

**Files:**
- Create: `backend/app/config/model_discovery_policy.json`
- Create: `backend/app/services/model_discovery.py`
- Modify: `backend/app/config/model_catalog.json`
- Modify: `backend/app/routers/setup.py`
- Test: `backend/tests/test_services/test_model_discovery.py`
- Test: `backend/tests/fixtures/huggingface_models.json`

**Interfaces:**
- Produces: `discover_models(probe, *, force=False) -> ModelDiscoveryResult`, `validated_catalog()`, `verification_status(catalog_id)`, and `GET /api/setup/models/discovery`.
- Consumes: sanitized host probe, Hugging Face `/api/models` metadata through injected `httpx.AsyncClient`, policy registry, 24-hour cache, and pinned fallback catalog.

- [ ] **Step 1: Add failing policy, ranking, cache, and fallback tests**

```python
async def test_discovery_rejects_untrusted_unpinned_and_reranker_models(hf_client, probe):
    result = await discover_models(probe, client=hf_client)
    assert all(item.publisher in APPROVED_PUBLISHERS for item in result.models)
    assert all(item.revision and item.sha256 and item.task == "text-generation" for item in result.models)

async def test_low_memory_probe_ranks_smaller_compatible_quantization_first(hf_client):
    result = await discover_models(probe(ram_gb=8, disk_gb=20), client=hf_client)
    assert result.recommended_primary.min_ram_gb <= 8
```

- [ ] **Step 2: Run discovery tests and verify service is missing**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_model_discovery.py --no-cov -q`

Expected: FAIL because the discovery service and policy do not exist.

- [ ] **Step 3: Add explicit policy and normalized model contracts**

```json
{
  "approved_publishers": ["bartowski", "unsloth"],
  "approved_licenses": ["apache-2.0", "mit", "qwen-research"],
  "formats": ["gguf"],
  "tasks": ["text-generation"],
  "quantizations": ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"],
  "cache_ttl_hours": 24
}
```

Keep the registry deliberately small; every added publisher/family requires fixtures and compatibility evidence.

- [ ] **Step 4: Implement bounded Hub query, filtering, ranking, and cache**

Use existing `httpx`, bounded result counts/timeouts, rate-limit-aware errors, revision/file metadata requests, deterministic scoring, and `${HATCH_HOME}/config/model_discovery_cache.json`. Never send personal profile data or secrets to Hugging Face.

- [ ] **Step 5: Normalize pinned fallback entries and verification manifests**

The existing Qwen entries remain fallback candidates. Add `${HATCH_HOME}/config/model_verification.json` keyed by catalog ID with revision, filename, size, mtime, checksum, and verified time; invalidate evidence on metadata mismatch.

- [ ] **Step 6: Expose discovery and catalog status through setup APIs**

Return `source=live|cache|fallback`, probe compatibility, recommended primary/triage, compatible alternatives, rejected counts/reasons, and safe retry errors. Do not return arbitrary shell fragments.

- [ ] **Step 7: Run model discovery tests**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_model_discovery.py tests/test_services/test_ai_setup.py --no-cov -q`

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```bash
git add backend/app/config/model_discovery_policy.json backend/app/config/model_catalog.json backend/app/services/model_discovery.py backend/app/routers/setup.py backend/tests/test_services/test_model_discovery.py backend/tests/fixtures/huggingface_models.json
git commit -m "feat(setup): discover curated local models"
```

### Task 7: Add Cloud Provider Catalog and Cached Validation

**Files:**
- Create: `backend/app/config/provider_catalog.json`
- Create: `backend/app/services/provider_catalog.py`
- Modify: `backend/app/routers/setup.py`
- Modify: `backend/app/routers/profile.py`
- Test: `backend/tests/test_services/test_provider_catalog.py`
- Test: `backend/tests/test_routers/test_setup_provider.py`

**Interfaces:**
- Produces: `provider_catalog()`, `validate_provider_selection()`, `test_provider_connection()`, redacted 24-hour validation evidence, `GET /api/setup/providers`, and typed `POST /api/setup/provider/test`.
- Consumes: Anthropic, OpenAI, Google GenAI, and OpenRouter host environment secrets plus selected provider primary/triage model IDs.

- [ ] **Step 1: Add failing provider routing and secret-redaction tests**

```python
async def test_cloud_selection_uses_provider_models_without_local_ids(client):
    response = await client.patch("/api/setup/intent", json={
        "ai_mode": "cloud", "cloud_provider": "openai",
        "cloud_primary_model": "provider-primary", "cloud_triage_model": "provider-triage",
    })
    intent = response.json()["intent"]
    assert intent["local_primary_model"] is None
    assert "API_KEY" not in response.text

async def test_status_poll_does_not_call_provider(provider_spy, client):
    await client.get("/api/setup/status")
    provider_spy.assert_not_called()
```

- [ ] **Step 2: Run provider tests and verify hard-coded/unsupported paths fail**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_provider_catalog.py tests/test_routers/test_setup_provider.py --no-cov -q`

Expected: FAIL because provider models are frontend/profile hard-coded and only OpenRouter has a live test.

- [ ] **Step 3: Add backend-owned provider catalog**

```json
{
  "providers": [
    {"id": "anthropic", "secret_env": "ANTHROPIC_API_KEY", "primary_model": "claude-sonnet-5", "triage_model": "claude-haiku-4-5"},
    {"id": "openai", "secret_env": "OPENAI_API_KEY", "primary_model": "gpt-5.5", "triage_model": "gpt-5.5"},
    {"id": "google_genai", "secret_env": "GOOGLE_API_KEY", "primary_model": "gemini-2.5-flash", "triage_model": "gemini-2.5-flash-lite"},
    {"id": "openrouter", "secret_env": "OPENROUTER_API_KEY", "primary_model": "anthropic/claude-sonnet-5", "triage_model": "anthropic/claude-haiku-4.5"}
  ]
}
```

Populate reviewed primary/triage model entries with stable IDs, labels, roles, and data/cost caveats; do not infer availability from frontend constants.

- [ ] **Step 4: Implement explicit provider tests and cached evidence**

Test the selected primary model with a minimal request, redact response/error bodies, store provider/model/config plus non-returned secret fingerprint and timestamp, expire after 24 hours, and invalidate on any selection or secret fingerprint change. Setup status reads evidence only.

- [ ] **Step 5: Route legacy profile connection testing through the catalog**

Remove the inline `model_map` in `backend/app/routers/profile.py`; keep the endpoint as a compatibility adapter that never accepts a browser secret and returns the host command when configuration is missing.

- [ ] **Step 6: Run provider tests**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_provider_catalog.py tests/test_routers/test_setup_provider.py tests/test_routers/test_profile_router.py --no-cov -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add backend/app/config/provider_catalog.json backend/app/services/provider_catalog.py backend/app/routers/setup.py backend/app/routers/profile.py backend/tests/test_services/test_provider_catalog.py backend/tests/test_routers/test_setup_provider.py backend/tests/test_routers/test_profile_router.py
git commit -m "feat(setup): add cloud model routing catalog"
```

### Task 8: Derive Authoritative Readiness and Ordered Host Actions

**Files:**
- Create: `backend/app/services/setup_status.py`
- Modify: `backend/app/routers/setup.py`
- Modify: `backend/app/services/backend_capabilities.py`
- Test: `backend/tests/test_services/test_setup_status.py`
- Test: `backend/tests/test_routers/test_setup_router.py`

**Interfaces:**
- Produces: `build_setup_status(db) -> SetupStatus`, stable structured errors, selected/active capability distinction, and ordered `HostAction` values.
- Consumes: onboarding state, canonical intent, probe/discovery/verification evidence, provider validation, capability/service health, and runtime state.

- [ ] **Step 1: Add failing readiness precedence and action-order tests**

```python
async def test_local_selection_without_models_is_pending_not_ready(status_context):
    status = await build_setup_status(status_context.local_without_files())
    assert status.overall_status == "pending_host_action"
    assert [a.id for a in status.next_actions] == ["models.install", "ai.apply"]

async def test_cloud_ready_never_requires_local_overlay(status_context):
    status = await build_setup_status(status_context.validated_cloud())
    assert status.overall_status == "ready"
    assert status.local_ai.status == "not_selected"
```

- [ ] **Step 2: Run status tests and verify current configured-equals-healthy logic fails**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_setup_status.py tests/test_routers/test_setup_router.py --no-cov -q`

Expected: FAIL because current status hard-codes onboarding complete and treats selections/secrets as healthy.

- [ ] **Step 3: Implement typed request-time derivation**

Apply precedence `error` → `not_configured` → `pending_host_action` → `ready`. Derive local states from probe, selected/verified files, applied routing, and service health; cloud states from provider/model selection, secret presence, validation evidence, and runtime; capabilities from selected profile, active profile, dependencies, and service health.

- [ ] **Step 4: Build safe ordered actions**

```python
HostAction(id="probe.run", order=10, command="hatch probe", blocking=True)
HostAction(id="capabilities.enable", order=20, command=f"hatch capabilities enable {profile}", blocking=True)
HostAction(id="models.install", order=30, command="hatch models install " + " ".join(validated_ids), blocking=True)
HostAction(id="secret.set", order=30, command=f"hatch secrets set {provider}", blocking=True)
HostAction(id="ai.apply", order=40, command="hatch apply-ai-config --restart", blocking=True)
```

Only validated IDs reach commands; never append `--yes` or return arbitrary command output.

- [ ] **Step 5: Replace `/api/setup/status` with the normalized response**

Include PR2 onboarding, canonical mode, selected/active profiles, subsystem states, catalogs/recommendations, actions, and nullable structured `last_error`. Preserve compatibility adapters only where existing consumers require them.

- [ ] **Step 6: Run status/router tests**

Run: `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_services/test_setup_status.py tests/test_routers/test_setup_router.py tests/test_routers/test_system_capabilities.py --no-cov -q`

Expected: PASS.

- [ ] **Step 7: Commit Task 8**

```bash
git add backend/app/services/setup_status.py backend/app/routers/setup.py backend/app/services/backend_capabilities.py backend/tests/test_services/test_setup_status.py backend/tests/test_routers/test_setup_router.py backend/tests/test_routers/test_system_capabilities.py
git commit -m "feat(setup): derive readiness and host actions"
```

### Task 9: Make Host CLI and Easy Compose Selection-Driven

**Files:**
- Modify: `scripts/hatch_cli.py`
- Modify: `scripts/fetch_models.sh`
- Modify: `scripts/verify_runtime.sh`
- Modify: `docker-compose.local-ai.yml`
- Preserve: `docker-compose.yml`
- Test: `scripts/tests/test_hatch_cli.py`
- Test: `scripts/tests/test_linux_installer.sh`
- Test: `backend/tests/test_services/test_ai_setup.py`

**Interfaces:**
- Consumes: validated live cache/fallback catalog schemas and canonical intent.
- Produces: selection-driven model install/apply, verification manifest, explicit Compose model filenames, and legacy wrapper behavior without defaults.

- [ ] **Step 1: Add failing CLI/shell/Compose guard tests**

```python
def test_fetch_models_without_ids_does_not_download(repo_root):
    result = run(["bash", "scripts/fetch_models.sh"], check=False)
    assert result.returncode == 2
    assert "hatch models" in result.stderr

def test_easy_local_compose_has_no_fixed_qwen_fallback(repo_root):
    text = (repo_root / "docker-compose.local-ai.yml").read_text()
    assert ":-Qwen" not in text
```

- [ ] **Step 2: Run targeted CLI/installer tests and confirm hard-coded paths fail**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest scripts/tests/test_hatch_cli.py backend/tests/test_services/test_ai_setup.py --no-cov -q && bash scripts/tests/test_linux_installer.sh`

Expected: FAIL on new no-default assertions.

- [ ] **Step 3: Make catalog lookup merge validated live cache and pinned fallback**

Reject expired/unvalidated live entries, preserve unrelated intent fields, download to `.part`, verify checksum, atomically rename, and update verification evidence. `hatch models install` without IDs lists candidates and exits without downloading.

- [ ] **Step 4: Convert `fetch_models.sh` and runtime verification**

The wrapper forwards explicit IDs to `hatch models install`; with no IDs it prints discovery/list guidance and exits usage code `2`. Runtime verification reads selected intent/manifest instead of a Qwen filename.

- [ ] **Step 5: Remove easy-local Compose filename fallbacks**

Use required-variable expansion such as `${HATCH_PRIMARY_MODEL_FILE:?Select and apply a primary local model first}` and enable the triage profile only when a selected triage ID exists. Keep `docker-compose.yml` unchanged except for a clear developer-default comment if needed.

- [ ] **Step 6: Verify read-modify-write preservation and Compose variants**

Run: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest scripts/tests/test_hatch_cli.py backend/tests/test_services/test_ai_setup.py --no-cov -q && bash scripts/tests/test_linux_installer.sh && docker compose -f docker-compose.easy.yml config --quiet`

Expected: PASS; local overlay validation uses explicit fixture environment variables.

- [ ] **Step 7: Commit Task 9**

```bash
git add scripts/hatch_cli.py scripts/fetch_models.sh scripts/verify_runtime.sh docker-compose.local-ai.yml scripts/tests/test_hatch_cli.py scripts/tests/test_linux_installer.sh backend/tests/test_services/test_ai_setup.py
git commit -m "feat(models): make local runtime selection driven"
```

### Task 10: Build Shared AI and Capabilities Frontend

**Files:**
- Create: `frontend/src/lib/setup.ts`
- Create: `frontend/src/components/setup/SetupStatusPanel.tsx`
- Create: `frontend/src/components/setup/HostActions.tsx`
- Create: `frontend/src/components/setup/AiEngineSelector.tsx`
- Create: `frontend/src/components/setup/ModelRoutingSelector.tsx`
- Create: `frontend/src/components/setup/CapabilitySelector.tsx`
- Create: `frontend/src/components/setup/AiCapabilitiesForm.tsx`
- Create: `frontend/src/components/setup/SetupStatusBanner.tsx`
- Modify: `frontend/src/app/onboarding/page.tsx`
- Modify: `frontend/src/app/settings/ai/page.tsx`
- Modify: `frontend/src/components/AppLockGate.tsx`
- Remove/replace: `frontend/src/components/onboarding/StepExperienceChoice.tsx`
- Remove/replace: `frontend/src/components/onboarding/StepAIProvider.tsx`
- Test: `frontend/src/__tests__/components/AiCapabilitiesForm.test.tsx`
- Test: `frontend/src/__tests__/components/SetupStatusPanel.test.tsx`
- Test: `frontend/src/__tests__/components/SettingsAIPage.test.tsx`

**Interfaces:**
- Consumes: normalized setup status, provider/discovery catalogs, intent patch endpoint, provider test endpoint, and host actions.
- Produces: one shared form for onboarding/Settings, Standard Hatch labels, accessible command copying, polling/backoff, and pending banner.

- [ ] **Step 1: Add failing shared-component and polling tests**

```tsx
it("routes cloud models without rendering local discovery", async () => {
  render(<AiCapabilitiesForm context="onboarding" />);
  await user.click(screen.getByRole("radio", { name: "Cloud" }));
  expect(await screen.findByLabelText("Primary cloud model")).toBeVisible();
  expect(screen.queryByText("Hugging Face recommendations")).not.toBeInTheDocument();
});

it("labels core as Standard Hatch and discloses advanced capabilities", async () => {
  expect(screen.getByRole("radio", { name: "Standard Hatch" })).toBeChecked();
  await user.click(screen.getByRole("button", { name: "Advanced capabilities" }));
  expect(screen.getByRole("radio", { name: "Full capabilities" })).toBeVisible();
});
```

- [ ] **Step 2: Run focused frontend tests and confirm old coupled UI fails**

Run: `cd frontend && npm test -- --run src/__tests__/components/AiCapabilitiesForm.test.tsx src/__tests__/components/SetupStatusPanel.test.tsx src/__tests__/components/SettingsAIPage.test.tsx`

Expected: FAIL because shared setup units do not exist.

- [ ] **Step 3: Implement canonical API types and non-overlapping polling**

```ts
export const useSetupStatus = ({ visible }: { visible: boolean }) => useQuery({
  queryKey: SETUP_STATUS_QUERY_KEY,
  queryFn: getSetupStatus,
  refetchInterval: (query) => nextSetupPollInterval(query.state.data, visible),
  refetchIntervalInBackground: false,
});
```

Use five seconds while pending, fifteen seconds after two minutes, and stop on ready/error/hidden/unmounted. Preserve previous data on transient failures and provide manual Check again.

- [ ] **Step 4: Build accessible shared selectors and host actions**

Render None/Local/Cloud; conditionally render curated local or provider-hosted model routing; default capabilities to Standard Hatch with progressive advanced disclosure; distinguish selected versus active; include text+icon statuses and labelled copy buttons.

- [ ] **Step 5: Integrate onboarding and Settings**

Onboarding persists non-secret intent before Review, permits Finish setup later, keeps password last, and summarizes pending versus active state. Settings uses the same form and resumes the same intent/status. Remove frontend-owned provider and model constants.

- [ ] **Step 6: Add post-onboarding pending banner**

Show when onboarding is complete and status is pending/error; dismissal is session-scoped; Settings remains reachable. Mount it in the unlocked shell without blocking navigation.

- [ ] **Step 7: Run focused and full frontend tests**

Run: `cd frontend && npm test -- --run src/__tests__/components/AiCapabilitiesForm.test.tsx src/__tests__/components/SetupStatusPanel.test.tsx src/__tests__/components/SettingsAIPage.test.tsx src/__tests__/components/AppLockGateState.test.tsx`

Expected: PASS.

- [ ] **Step 8: Commit Task 10**

```bash
git add frontend/src/lib/setup.ts frontend/src/components/setup frontend/src/app/onboarding/page.tsx frontend/src/app/settings/ai/page.tsx frontend/src/components/AppLockGate.tsx frontend/src/components/onboarding/StepExperienceChoice.tsx frontend/src/components/onboarding/StepAIProvider.tsx frontend/src/__tests__/components/AiCapabilitiesForm.test.tsx frontend/src/__tests__/components/SetupStatusPanel.test.tsx frontend/src/__tests__/components/SettingsAIPage.test.tsx
git commit -m "feat(setup): share onboarding and AI capabilities UI"
```

### Task 11: Add End-to-End Matrix, Documentation, and Release Verification

**Files:**
- Modify: `frontend/e2e/onboarding.spec.ts`
- Modify: `frontend/e2e/app-lock.spec.ts`
- Modify: `frontend/e2e/settings.spec.ts`
- Modify: `frontend/e2e/fixtures.ts`
- Modify: `README.md`
- Modify: `docs/getting-started/INSTALLATION.md`
- Modify: `docs/operations/LOCAL_MODELS.md`
- Modify: `docs/operations/CLI_REFERENCE.md`
- Modify: `docs/operations/OPERATIONS.md`
- Modify: `docs/getting-started/TROUBLESHOOTING.md`
- Test: `frontend/src/__tests__/codebase/model-selection-contract.test.ts`

**Interfaces:**
- Consumes: all completed PR2/PR3 backend, CLI, and frontend contracts.
- Produces: acceptance evidence, no-hardcoded-model guard, accurate docs, and final CI-ready branch.

- [ ] **Step 1: Add failing codebase and Playwright acceptance coverage**

```ts
it("keeps fixed model downloads out of beginner paths", () => {
  for (const file of EASY_INSTALL_FILES) {
    expect(readFileSync(file, "utf8")).not.toMatch(/huggingface\.co\/.*Qwen|:-Qwen/);
  }
});
```

Add PR2 scenarios for new install, finalization retry, configured lock/incomplete onboarding, completed onboarding/no lock, and start-new-onboarding. Add PR3 scenarios for None+Standard, Local ready, Local+Full pending→ready, Cloud secret pending, Cloud+Full, missing/stale probe, finish later, reload/resume, and Settings continuity.

- [ ] **Step 2: Run targeted acceptance tests and verify documentation/fixtures are stale**

Run: `cd frontend && npm test -- --run src/__tests__/codebase/model-selection-contract.test.ts && npx playwright test e2e/onboarding.spec.ts e2e/app-lock.spec.ts e2e/settings.spec.ts`

Expected: FAIL until fixtures and final flows match the new contract.

- [ ] **Step 3: Update fixtures and user documentation**

Document Standard Hatch, separate cloud/local model routing, host-managed secrets, curated discovery and fallback, explicit selection commands, pending state, developer-stack exception, recovery commands, network/rate-limit failure behavior, and no automatic model downloads.

- [ ] **Step 4: Run documentation and Compose contract checks**

Run: `python scripts/check_docs.py && python scripts/check_readme_contract.py && docker compose -f docker-compose.easy.yml config --quiet`

Expected: PASS.

- [ ] **Step 5: Run full backend, frontend, installer, and E2E verification**

Run:

```bash
cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest --no-cov -q
cd ../frontend && npm test -- --run
npm run build
npx playwright test e2e/onboarding.spec.ts e2e/app-lock.spec.ts e2e/settings.spec.ts
cd .. && bash scripts/tests/test_linux_installer.sh
UV_CACHE_DIR=/tmp/uv-cache uv run pytest scripts/tests/test_hatch_cli.py --no-cov -q
make audit-scripts
git diff --check
```

Expected: all commands exit `0`; report unrelated repository-wide lint baseline separately if `make ci` still encounters existing findings.

- [ ] **Step 6: Commit Task 11**

```bash
git add frontend/e2e frontend/src/__tests__/codebase/model-selection-contract.test.ts README.md docs/getting-started/INSTALLATION.md docs/operations/LOCAL_MODELS.md docs/operations/CLI_REFERENCE.md docs/operations/OPERATIONS.md docs/getting-started/TROUBLESHOOTING.md
git commit -m "test: verify combined onboarding and AI remediation"
```

- [ ] **Step 7: Run final branch review before push**

Compare the complete branch against the approved design and source specification, review security-sensitive diffs, confirm the worktree is clean after commits, and only then push/open the combined pull request.
