---
title: Hatch Revised Product Gap Spec: UI Control Plane, Onboarding, AI Setup, Company Watchlist, Question Bank, OpenRouter, and PDF Export
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# Hatch Revised Product Gap Spec: UI Control Plane, Onboarding, AI Setup, Company Watchlist, Question Bank, OpenRouter, and PDF Export

**Repository:** https://github.com/arvindsoni2/hatch  
**Spec status:** Revised Codex implementation spec  
**Owner intent:** Hatch should become a privacy-first guided UI product that helps users continuously discover suitable roles from companies they care about, manage applications, tailor CVs, and prepare interviews without forcing CLI-first setup.

---

## 0. Decisions captured in this revision

This spec incorporates the latest product decisions:

1. **Structured CV import/review is not a gap.** Hatch already has `Upload -> Uploading -> Parsing -> Review extracted data -> Confirm save` in onboarding/settings. Reuse and regression-test it rather than rebuilding it.
2. **Add a UI-first setup/control abstraction.** User data reset, onboarding reset, AI profile selection, hardware probe, capability status, and provider setup should not be CLI-only. CLI remains a power-user/fallback path.
3. **Add Company Watchlist.** Hatch should help users continuously discover suitable roles from companies they care about.
4. **Add Question Bank.** Hatch should let users store and reuse interview answers, STAR stories, proof points, and reusable question responses.
5. **Add OpenRouter provider.** OpenRouter should be supported as a cloud AI provider alongside existing providers.
6. **Skip MCP integration for now.** Do not implement external MCP server/client integration in this spec.
7. **Add PDF export.** Hatch should support optional PDF export/preview while keeping DOCX/structured data as the source of truth.

---

## 1. Product positioning

Hatch should not become a CLI-only job-search tool. Its differentiator should be:

> **Privacy-first guided job search workspace with local-first data, optional local/cloud AI, and proactive company-based role discovery.**

The product promise should be:

> **Hatch helps you continuously discover suitable roles from companies you care about, score them against your profile, tailor your CV, track progress, and prepare for interviews.**

---

## 2. Implementation split

The full scope is bigger than one clean PR. Implement in separate PRs.

### PR 1 — P0 onboarding, reset, password, and UI control plane foundation

Scope:

- Add password setup during onboarding.
- Fix reset/new onboarding stale-data bug.
- Add explicit reset modes.
- Add UI-first setup/control plane service layer.
- Add reset preview/apply endpoints.
- Ensure existing Master CV import/review participates correctly in reset/onboarding state.

### PR 2 — AI setup, hardware probe, capabilities, and OpenRouter

Scope:

- Add AI experience choice to onboarding: Basic, Local AI, Cloud AI.
- Add hardware probe UI flow.
- Add capability registry/status model.
- Add OpenRouter provider support.
- Keep API keys host-owned; browser never asks for secrets.

### PR 3 — Company Watchlist and recurring discovery

Scope:

- Add target company/watchlist management.
- Add manual and scheduled watchlist scans.
- Add role discovery, dedupe, scoring handoff, and Today/Applications surfacing.
- Reuse existing Import from URL where possible.
- Keep advanced scraping optional and provider-based.

### PR 4 — Question Bank

Scope:

- Add reusable interview question/answer bank.
- Add STAR/proof-point tagging.
- Integrate with Interview Prep/Coach.
- Allow saving strong answers from interview prep into the bank.

### PR 5 — PDF export

Scope:

- Add optional PDF export/preview from generated CV packages.
- Keep DOCX/structured package as source of truth.
- Add clear fallback when PDF backend is unavailable.

---

## 3. Architecture principle: UI-first Setup Control Plane

### 3.1 Problem

Today, important setup operations are either CLI-based or appear as instructions such as “run `hatch probe`”. This creates friction for non-technical users and weakens content/demo quality.

### 3.2 Required architecture

Introduce a typed setup/control service layer shared by frontend, backend, CLI, and optional host agent.

```text
Frontend UI
  -> Backend API
    -> Setup Control Plane / Application Services
      -> Database state + safe allowlisted host operations
        -> Optional Hatch Host Agent for privileged local actions
```

The CLI should become a thin wrapper over the same service layer wherever possible.

### 3.3 Action categories

#### A. App-data actions

These can run through backend services and database transactions without CLI:

- Reset onboarding state.
- Reset demo/workspace data.
- Clear applications, roles, follow-ups, agent runs, LLM traces.
- Set onboarding step.
- Set AI mode: `basic | local | cloud`.
- Save selected provider metadata.
- Save capability preference.
- Save company watchlist entry.
- Save question bank entry.

#### B. Host-read actions

These may run through allowlisted backend functions or optional host agent:

- Hardware probe.
- Detect Ollama, llama.cpp, LM Studio.
- Detect CPU/RAM/GPU/disk.
- Check Docker/backend services.
- Check provider secret presence.
- Test configured provider.

These must not accept arbitrary shell input from the browser.

#### C. Host-write/privileged actions

These require explicit confirmation and should use a local host agent or CLI fallback:

- Enable backend capability profile.
- Restart backend stack.
- Install local model.
- Write host secret file.
- Modify compose override.
- Factory reset volumes.

### 3.4 New endpoints

Suggested API surface:

```http
GET  /api/setup/status
GET  /api/setup/reset/preview?mode=onboarding|demo|factory
POST /api/setup/reset/apply
POST /api/setup/onboarding-step
POST /api/setup/ai-mode
POST /api/setup/provider-selection
POST /api/system/probe/run
GET  /api/system/probe/latest
GET  /api/system/capabilities
POST /api/ai/provider/test
```

### 3.5 CLI parity

Existing/new CLI commands should call the same service logic:

```bash
hatch reset onboarding --yes
hatch reset demo --yes
hatch reset factory --yes
hatch probe
hatch ai use basic
hatch ai use local --profile balanced
hatch ai use cloud --provider openrouter --model <model-slug>
hatch secrets set openrouter
```

### 3.6 Acceptance criteria

- User can reset onboarding/demo data from UI in local/dev mode.
- User can choose Basic/Local AI/Cloud AI from onboarding without CLI.
- User can run or refresh hardware probe from UI, or gets a guided fallback command.
- CLI and UI use the same service-layer rules for reset and AI profile state.
- Browser never accepts raw API keys.
- Privileged host-write actions require explicit confirmation and audit events.
- If host agent is unavailable, UI shows safe fallback CLI commands.

---

## 4. P0: Password setup during onboarding

### 4.1 Current gap

There is no dedicated onboarding screen to set a local account password.

### 4.2 New onboarding step

Route suggestion:

```text
/onboarding/password
```

Fields:

- Password.
- Confirm password.

Minimum validation:

- Minimum 10 characters.
- At least one letter.
- At least one number.
- At least one symbol or punctuation character.
- Password and confirmation must match.
- Reject common weak passwords.

UX requirements:

- Show password requirements before submit.
- Show live checklist.
- Show/hide password toggle.
- Clear error messages.
- Do not reveal account enumeration details.

Backend/security requirements:

- Store only strong password hash.
- Never log password fields.
- Reset scripts must not print secrets.
- Add tests for validation and hash storage.

Acceptance criteria:

- New local user cannot complete onboarding without valid password.
- Weak passwords are blocked with useful messages.
- Password is never stored or logged in plaintext.

---

## 5. P0: Reset/new onboarding stale-data bug

### 5.1 Current bug

After clicking “start new onboarding” and using reset scripts, old dashboard/application/agent data can still appear. This makes fresh demos and fresh installs untrustworthy.

### 5.2 Expected clean state

After clean onboarding reset or demo reset:

- `/today` must not show old roles, follow-ups, application cards, agent totals, traces, or stale actions.
- `/applications` must not show old cards.
- Settings -> Master CV must not show old parsed CV data unless reset mode explicitly preserved it.
- Agent activity panels must be empty or show explicit seeded demo data only when requested.
- Browser refresh and backend restart must not resurrect stale state.

### 5.3 Reset modes

#### Mode A — onboarding reset

Purpose: restart onboarding while preserving installed runtime config.

Deletes/resets:

- Onboarding completion flags.
- User onboarding choices.
- Workspace data created during previous onboarding/test flow.
- Jobs, roles, applications, scoring records, follow-ups, generated CV packages, interview sessions, LLM traces, agent events.
- Parsed Master CV/profile data unless explicitly preserved by `preserveProfile=true`.

Preserves:

- Installed stack.
- Host secrets.
- Provider secret files.
- Hardware probe cache only if non-user-specific and still valid.

#### Mode B — demo reset

Purpose: clean app for screenshot/content/demo capture.

Deletes/resets:

- Everything in onboarding reset.
- Demo/test data.
- LLM traces and system log sample data.
- Fake user display names unless explicitly reseeded.

Preserves:

- App installation.
- Host secrets.
- Required runtime volumes only if needed for health.

Optional flags:

```bash
--seed-demo-user
--seed-demo-data
```

#### Mode C — factory reset

Purpose: dangerous full local reset.

Deletes/resets:

- Application database.
- Documents.
- Generated CVs/PDFs.
- Agent records.
- Runtime cache.

Preserves by default:

- Host secret files unless `--delete-secrets` is explicitly passed.

Requires:

- Confirmation modal or `--yes` flag.
- Data-loss warning.

### 5.4 UI cache/state requirements

After reset:

- Invalidate frontend query cache.
- Clear local/session storage keys for user/workspace/onboarding.
- Clear IndexedDB cache if used.
- Navigate to onboarding route.
- Force reload if needed to remove stale client state.

### 5.5 Acceptance criteria

- Reset preview shows exactly what will be deleted and preserved.
- Reset apply executes in one backend transaction where possible.
- After reset, `/today`, `/applications`, `/settings/master-cv`, and agent panels show clean state.
- Refresh/restart does not bring stale data back.
- Playwright test covers seed data -> reset -> reload -> no stale data.

---

## 6. Existing Master CV import/review: keep and regression-test

### 6.1 Decision

Structured CV import/review already exists and should not be listed as a new feature gap.

Existing flow:

```text
Select file -> Uploading -> Parsing -> Review extracted data -> Confirm save
```

### 6.2 Required changes

- Reuse the same component in onboarding and Settings -> Master CV.
- Ensure reset/new onboarding handles Master CV state correctly.
- Ensure parsed profile fields, proof points, generated CV packages, and current Master CV metadata do not survive clean reset unless explicitly preserved.

Acceptance criteria:

- Onboarding can invoke existing Master CV import/review flow.
- Settings -> Master CV remains the replacement/management location.
- Clean reset removes stale current Master CV metadata and parsed profile data.
- Partial reset clearly tells user what was preserved.

---

## 7. P1: AI setup and hardware probe in onboarding

### 7.1 New AI experience screen

Route suggestion:

```text
/onboarding/ai-experience
```

Cards:

#### Basic experience

Label: “Use Hatch now, set up AI later”

Explain:

- Best for trying Hatch quickly.
- Manual job tracking and CV workflows are available.
- No prompts are sent to AI provider.
- Scoring, tailoring, interview coaching, audio/video-assisted prep, and automation are limited/off.

CTA:

```text
Continue with basic setup
```

#### Local AI experience

Label: “Run AI locally”

Explain:

- Best for privacy and cost control.
- Requires local model runtime and enough hardware resources.
- Hardware probe checks CPU, RAM, GPU, disk, and installed runtimes.
- Some features may be slower depending on hardware.

CTA:

```text
Check this machine
```

#### Cloud AI provider

Label: “Use cloud AI provider”

Explain:

- Best for quality and convenience if user already has provider/API key.
- Prompts may leave the device and be processed by selected provider.
- Hatch never asks for API keys in browser; secrets are set from host CLI/agent.

CTA:

```text
Choose provider
```

### 7.2 Hardware probe screen

Routes:

```text
/onboarding/hardware-probe
/settings/ai
```

States:

- `not_run`
- `running`
- `completed`
- `failed`
- `stale`

Display:

- CPU model/cores.
- RAM total/available.
- GPU detected/not detected.
- Disk free space.
- OS/runtime environment.
- Detected runtimes: Ollama, llama.cpp, LM Studio where supported.
- Recommended model profile: `basic | balanced | large | not_recommended`.
- Feature availability: local scoring, local tailoring, interview text coaching, audio capture, video capture, browser automation, scraping.

### 7.3 Running probe

Preferred:

```http
POST /api/system/probe/run
GET  /api/system/probe/latest
```

Fallback:

- Show copyable command: `hatch probe`.
- Show `Refresh probe result` button.

Security:

- Probe must not read secrets.
- Probe must not upload data externally.
- Probe must not execute arbitrary user/browser command text.

Acceptance criteria:

- User can complete onboarding with Basic mode.
- Local AI path leads to hardware probe.
- Cloud AI path leads to provider setup.
- Selected AI mode appears later in Settings -> AI Provider.
- Local AI card updates after successful probe.
- Failed probe shows remediation.

---

## 8. P1: Capability registry

Formalize a capability registry used by onboarding, Settings -> AI, and Settings -> System.

Suggested capabilities:

```ts
type HatchCapability =
  | 'core_tracking'
  | 'cv_studio'
  | 'local_llm'
  | 'cloud_llm'
  | 'openrouter_provider'
  | 'job_import_url'
  | 'company_watchlist'
  | 'job_scraping_basic'
  | 'job_scraping_advanced'
  | 'browser_automation'
  | 'audio_capture'
  | 'video_capture'
  | 'interview_coach'
  | 'question_bank'
  | 'document_generation_docx'
  | 'document_generation_pdf'
  | 'llm_tracing'
  | 'diagnostics';
```

Each capability should include:

```ts
interface CapabilityStatus {
  id: HatchCapability;
  label: string;
  description: string;
  status: 'available' | 'unavailable' | 'needs_setup' | 'disabled' | 'error';
  installProfile: 'lightweight' | 'full' | 'experimental';
  privacyImpact: 'none' | 'local_only' | 'leaves_device';
  costImpact: 'free' | 'local_resource' | 'external_api_cost';
  requiresSecret: boolean;
  requiresProbe: boolean;
  docsCommand?: string;
  lastCheckedAt?: string;
  errorMessage?: string;
}
```

Acceptance criteria:

- Optional features in lightweight install are shown as optional/not installed, not broken.
- Settings -> System no longer shows vague “temporarily unavailable” for predictable optional capability states.
- Onboarding summary uses same capability data.
- Settings -> AI uses same provider/capability statuses.

---

## 9. P1: OpenRouter provider

### 9.1 Why

OpenRouter gives one provider integration path for many models through an OpenAI-compatible API shape. It is useful for users who want model choice without wiring every provider individually.

### 9.2 Provider id

Add provider:

```ts
type AiProviderId =
  | 'none'
  | 'local_custom'
  | 'openai'
  | 'anthropic'
  | 'google_gemini'
  | 'openrouter';
```

### 9.3 Secret handling

Do not collect OpenRouter keys in browser.

CLI/host-agent command:

```bash
hatch secrets set openrouter
```

Environment/secret key:

```text
OPENROUTER_API_KEY
```

Provider status values:

```text
not_selected
missing_secret
configured_not_tested
test_failed
ready
```

### 9.4 Model selection

Settings -> AI should allow OpenRouter model slug selection only after provider is selected.

Minimum UI fields:

- Provider: OpenRouter.
- Model slug text input or dropdown if `/models` lookup is available.
- Usage note: external API cost may apply.
- Test provider button.

Store:

```ts
interface OpenRouterConfig {
  provider: 'openrouter';
  model: string;
  temperature?: number;
  maxTokens?: number;
  status: ProviderStatus;
  lastTestedAt?: string;
}
```

### 9.5 Adapter implementation

Use the existing cloud LLM abstraction if available.

Suggested adapter behavior:

- Treat OpenRouter as an OpenAI-compatible chat-completions provider.
- Configure base URL through provider config, not hardcoded inside business logic.
- Use bearer token from host-owned secret store.
- Support model slug passthrough.
- Normalize errors into Hatch provider errors:
  - `missing_secret`
  - `invalid_secret`
  - `model_not_found`
  - `rate_limited`
  - `provider_unavailable`
  - `unknown_error`

### 9.6 Acceptance criteria

- Settings -> AI shows OpenRouter next to Gemini/OpenAI/Anthropic.
- Onboarding Cloud AI path includes OpenRouter.
- User can select OpenRouter without secret; status remains `missing_secret`.
- After secret is present, user can test provider.
- LLM call traces correctly attribute provider/model to OpenRouter.
- Cost tracking groups OpenRouter usage under provider `openrouter`.
- Browser never displays or stores the API key.

---

## 10. P1/P2: Company Watchlist

### 10.1 Product value

Current Hatch supports single-job intake:

```text
User found a role -> Import from URL/Add manually -> Hatch scores/tailors/tracks it
```

Company Watchlist adds proactive discovery:

```text
User cares about companies -> Hatch checks them repeatedly -> new relevant roles are surfaced
```

Product promise:

> Hatch helps you continuously discover suitable roles from companies you care about.

### 10.2 User stories

1. As a user, I can add a target company and careers/job-board URL.
2. As a user, I can tell Hatch what roles I want from that company.
3. As a user, I can run a manual scan now.
4. As a user, Hatch can periodically check for new roles.
5. As a user, I only want to see new, deduplicated, relevant roles.
6. As a user, I can ignore/archive roles that are not relevant.
7. As a user, I can promote a discovered role into Applications.

### 10.3 MVP scope

Add a new area:

```text
Scout -> Company Watchlist
```

or add within Applications/Scout settings as:

```text
Watched companies
```

MVP supports:

- Add company.
- Add career/job-board URL.
- Select source type.
- Manual scan.
- Optional daily schedule if a scheduler already exists.
- Dedupe discovered roles.
- Score roles using existing Scorer where possible.
- Surface relevant results in Today and Applications -> Discovered.

### 10.4 Source types

```ts
type WatchSourceType =
  | 'greenhouse'
  | 'lever'
  | 'ashby'
  | 'workable'
  | 'generic_careers_page'
  | 'manual_url_list';
```

MVP recommendation:

- First-class support for known board/listing URLs if current importer already handles them.
- Generic careers page support can use existing Import from URL/basic scraper first.
- Firecrawl/Scrapling remain optional providers, not mandatory.

### 10.5 Watchlist data model

```ts
interface CompanyWatchlistItem {
  id: string;
  userId: string;
  companyName: string;
  companyWebsite?: string;
  careersUrl: string;
  sourceType: WatchSourceType;
  status: 'active' | 'paused' | 'error';
  scanFrequency: 'manual' | 'daily' | 'weekly';
  roleKeywords?: string[];
  locationPreferences?: string[];
  remotePreference?: 'any' | 'remote' | 'hybrid' | 'onsite';
  minMatchScore?: number;
  lastScannedAt?: string;
  lastSuccessfulScanAt?: string;
  lastError?: string;
  createdAt: string;
  updatedAt: string;
}
```

```ts
interface WatchlistScanRun {
  id: string;
  watchlistItemId: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  startedAt?: string;
  completedAt?: string;
  sourceProvider: 'builtin_basic' | 'firecrawl' | 'scrapling_experimental';
  discoveredCount: number;
  newCount: number;
  duplicateCount: number;
  importedCount: number;
  errorMessage?: string;
}
```

```ts
interface DiscoveredRoleFingerprint {
  id: string;
  sourceUrl: string;
  normalizedCompany: string;
  normalizedTitle: string;
  normalizedLocation?: string;
  externalJobId?: string;
  contentHash?: string;
  firstSeenAt: string;
  lastSeenAt: string;
}
```

### 10.6 Dedupe rules

A discovered role is duplicate if any of these match:

1. Same source URL after normalization.
2. Same external job id from same provider/company.
3. Same company + normalized title + normalized location + similar posted date.
4. Same content hash where available.

### 10.7 Discovery flow

```text
Watchlist scan starts
  -> Fetch listing/careers source
  -> Extract role links/basic metadata
  -> Normalize each role
  -> Dedupe against existing jobs/applications/discovered fingerprints
  -> Import new role records as Discovered
  -> Run Scorer if AI/scoring capability available
  -> Hide/archive low-score roles if below threshold
  -> Surface relevant roles in Today
```

### 10.8 UI requirements

Company Watchlist page:

- Empty state: “Add companies you care about. Hatch will watch for new suitable roles.”
- Add company modal:
  - Company name.
  - Careers/job-board URL.
  - Role keywords.
  - Locations.
  - Remote preference.
  - Scan frequency.
  - Min match score.
- Watchlist table/cards:
  - Company.
  - Status.
  - Last scan.
  - New roles found.
  - Error state.
  - Run scan now.
  - Pause/resume.
  - Edit/delete.

Today integration:

- Show “New roles from watched companies”.
- Provide actions:
  - Review role.
  - Add to Applications.
  - Ignore.
  - Update watchlist preferences.

Applications integration:

- New roles can enter `Discovered` stage.
- Role card should show source: `Watched company` and company watchlist name.

### 10.9 Compliance and safety

- Only scan URLs explicitly added by the user.
- Show compliance note: user is responsible for respecting website terms.
- Respect robots/terms where current architecture supports it.
- Rate-limit scans.
- Do not bypass authentication/paywalls.
- Do not attempt automated application submission in this scope.

### 10.10 Acceptance criteria

- User can add a watched company with careers URL.
- User can run scan manually.
- Scan creates deduped discovered roles.
- Existing Import from URL path is reused where possible.
- Relevant roles appear in Today and/or Applications -> Discovered.
- User can pause/delete watchlist item.
- Low-level scraping failures are surfaced as actionable error states.
- Tests cover add company, scan with mocked provider, dedupe, and application promotion.

---

## 11. Scraping provider architecture

### 11.1 Why

Company Watchlist makes scraping/discovery more important, but scraping must remain optional and capability-isolated.

### 11.2 Provider interface

```ts
type ScrapingProviderId =
  | 'builtin_basic'
  | 'firecrawl'
  | 'scrapling_experimental';

interface ScrapingProvider {
  id: ScrapingProviderId;
  label: string;
  mode: 'local' | 'external_api' | 'experimental_local';
  requiresSecret: boolean;
  requiresOptionalInstall: boolean;
  supportsSingleUrlImport: boolean;
  supportsListingDiscovery: boolean;
  supportsDynamicPages: boolean;
  supportsCrawl: boolean;
  complianceWarningRequired: boolean;
}
```

### 11.3 Firecrawl

Keep optional.

Good fit:

- Structured extraction.
- Hosted convenience.
- Reducing site-specific crawler maintenance.

Risks:

- API key required.
- External dependency/cost.
- Data leaves local machine depending on usage.

### 11.4 Scrapling

Do not add as a mandatory dependency now.

Add only:

- Design placeholder.
- Disabled experimental flag.
- Future evaluation task.

Evaluation targets:

- Greenhouse.
- Lever.
- Ashby.
- Workable.
- Generic careers page.

Acceptance criteria:

- Lightweight install has no Scrapling dependency.
- No scraping runs without explicit user action/schedule.
- Failure falls back to manual import.
- Provider diagnostics show missing install/secret clearly.

---

## 12. P2: Question Bank

### 12.1 Product value

Users repeatedly answer similar interview questions. Hatch should help them build a reusable, evidence-backed library of answers and stories.

### 12.2 New area

Add under Interview Prep:

```text
Interview Prep -> Question Bank
```

or add a dedicated tab within existing Interview Prep.

### 12.3 Question Bank item types

```ts
type QuestionBankItemType =
  | 'interview_question'
  | 'star_story'
  | 'proof_point'
  | 'company_research_note'
  | 'role_specific_answer';
```

### 12.4 Data model

```ts
interface QuestionBankItem {
  id: string;
  userId: string;
  type: QuestionBankItemType;
  question?: string;
  title: string;
  answerDraft: string;
  situation?: string;
  task?: string;
  action?: string;
  result?: string;
  skills: string[];
  tags: string[];
  seniority?: string;
  roleFamily?: string;
  linkedApplications?: string[];
  source: 'manual' | 'interview_prep' | 'cv_import' | 'ai_suggested';
  confidence: 'draft' | 'reviewed' | 'final';
  createdAt: string;
  updatedAt: string;
}
```

### 12.5 UI requirements

Question Bank page:

- Search.
- Filter by tag, skill, type, confidence, linked role/application.
- Add new answer/story.
- Edit answer.
- Duplicate/adapt for role.
- Archive/delete.

Question detail:

- Question/title.
- Answer draft.
- STAR structured fields.
- Tags/skills.
- Linked roles/applications.
- Confidence status.

Interview Prep integration:

- “Save to Question Bank” action after a coaching answer.
- “Use from Question Bank” while preparing for role.
- “Suggest relevant stories” based on job description and skill gaps.

### 12.6 AI behavior

If AI is enabled:

- Suggest improvements.
- Convert unstructured answer into STAR format.
- Map answer to relevant skills.
- Suggest likely interview questions for a target role and link existing answers.

If AI is disabled:

- Manual CRUD still works.
- User can store answers and tags without AI.

### 12.7 Acceptance criteria

- User can create, edit, search, filter, and delete Question Bank entries.
- User can save an interview prep answer to the bank.
- User can attach entries to an application/role.
- Question Bank works in Basic mode without AI.
- AI features are disabled/hidden gracefully when AI is not configured.
- Tests cover CRUD, search/filter, and Interview Prep save action.

---

## 13. P2/P3: PDF export

### 13.1 Product decision

Add PDF export now, but keep DOCX/structured package as source of truth.

### 13.2 Scope

Add PDF export for:

- Tailored CV package.
- Master CV preview if current architecture supports it.
- Cover letter if generated.

Do not make PDF generation mandatory for core workflow.

### 13.3 UX requirements

In CV Studio / generated documents:

- Primary source format remains DOCX where applicable.
- Add actions:
  - `Download DOCX`
  - `Preview PDF`
  - `Download PDF`
- If PDF backend unavailable:
  - Show “PDF export is not installed in this setup.”
  - Show setup/capability guidance.
  - Do not block DOCX generation.

### 13.4 Generation strategy

Codex should inspect current document-generation implementation and choose the lowest-risk path.

Preferred order:

1. Convert generated DOCX to PDF using an installed, allowlisted local converter if already available.
2. Generate HTML preview from the same structured CV package and render to PDF using existing browser/PDF infrastructure if available.
3. Defer server-side PDF conversion behind a capability flag if neither exists.

Do not introduce a heavyweight dependency into lightweight install without capability gating.

### 13.5 Data model

```ts
interface GeneratedDocumentAsset {
  id: string;
  applicationId?: string;
  packageId: string;
  kind: 'cv' | 'cover_letter' | 'summary';
  format: 'docx' | 'pdf' | 'html_preview';
  pathOrBlobRef: string;
  createdAt: string;
  sourceAssetId?: string;
  generationStatus: 'pending' | 'completed' | 'failed';
  errorMessage?: string;
}
```

### 13.6 Acceptance criteria

- User can generate/download PDF for a completed CV package when PDF capability is available.
- If PDF generation fails, DOCX remains available.
- PDF output uses the same content as the approved/generated CV package.
- Generated PDF assets are cleaned during demo/factory reset.
- Tests cover successful PDF generation with mocked converter and unavailable capability state.

---

## 14. Data model summary

Add or update these entities as needed:

```text
users
onboarding_state
hardware_probe_results
capability_status
ai_provider_configs
company_watchlist_items
watchlist_scan_runs
discovered_role_fingerprints
question_bank_items
generated_document_assets
setup_audit_events
```

### `setup_audit_events`

Track sensitive setup/control actions:

```ts
interface SetupAuditEvent {
  id: string;
  userId?: string;
  action:
    | 'reset_previewed'
    | 'reset_applied'
    | 'ai_mode_changed'
    | 'provider_selected'
    | 'provider_tested'
    | 'hardware_probe_started'
    | 'hardware_probe_completed'
    | 'host_action_requested'
    | 'host_action_completed';
  status: 'success' | 'failed';
  metadataJson?: string;
  createdAt: string;
}
```

Never include secrets in audit metadata.

---

## 15. API summary

```http
# Setup/control plane
GET  /api/setup/status
GET  /api/setup/reset/preview
POST /api/setup/reset/apply
POST /api/setup/ai-mode
POST /api/setup/provider-selection

# Onboarding
GET  /api/onboarding/state
POST /api/onboarding/password
POST /api/onboarding/step

# System/capabilities
POST /api/system/probe/run
GET  /api/system/probe/latest
GET  /api/system/capabilities

# AI providers
GET  /api/ai/providers
POST /api/ai/provider/test
GET  /api/ai/openrouter/models        # optional if implemented safely

# Company Watchlist
GET  /api/watchlist/companies
POST /api/watchlist/companies
PATCH /api/watchlist/companies/:id
DELETE /api/watchlist/companies/:id
POST /api/watchlist/companies/:id/scan
GET  /api/watchlist/scans/:id

# Question Bank
GET  /api/question-bank
POST /api/question-bank
GET  /api/question-bank/:id
PATCH /api/question-bank/:id
DELETE /api/question-bank/:id
POST /api/question-bank/from-interview-answer

# PDF export
POST /api/documents/:packageId/export/pdf
GET  /api/documents/assets/:assetId
```

---

## 16. Frontend summary

Add/update components:

```text
PasswordSetupStep
PasswordRequirementChecklist
AIExperienceStep
HardwareProbeStep
CapabilitySummaryPanel
ProviderSetupCommandCard
ResetPreviewModal
ResetSuccessEmptyState
CompanyWatchlistPage
CompanyWatchlistForm
WatchlistScanStatusCard
DiscoveredFromWatchlistPanel
QuestionBankPage
QuestionBankItemEditor
QuestionBankFilters
SaveToQuestionBankButton
PdfExportButton
PdfUnavailableNotice
```

UX copy rules:

- Avoid saying “temporarily unavailable” for optional features that are not installed/configured.
- Distinguish `not installed`, `missing secret`, `not tested`, `failed`, and `ready`.
- Use plain language around privacy/cost trade-offs.
- For scraping/watchlist, clearly communicate that Hatch checks only user-added sources.

---

## 17. Testing requirements

### Unit tests

- Password validation.
- Password hashing path.
- Reset deletion/preservation rules.
- Capability status mapping.
- Hardware probe parser/recommendation logic.
- OpenRouter provider config/status mapping.
- Watchlist dedupe/fingerprint logic.
- Question Bank validation/search filtering.
- PDF capability status and export-state mapping.

### Integration tests

- Complete onboarding with Basic mode.
- Complete onboarding with Cloud mode + OpenRouter missing secret.
- Complete onboarding with Local mode + mocked hardware probe.
- Seed data -> reset -> all stale data removed.
- Add watched company -> mocked scan -> discovered roles created.
- Duplicate watchlist scan -> no duplicate applications/roles.
- Save interview answer to Question Bank.
- Export PDF with mocked converter.

### Playwright tests

1. Fresh install -> onboarding appears.
2. Password screen blocks weak password.
3. Basic AI mode -> onboarding completes -> Today empty state.
4. Seed data -> reset from UI -> reload -> no old data.
5. Settings -> AI -> select OpenRouter -> missing secret visible.
6. Settings -> AI -> mocked provider test -> ready state visible.
7. Company Watchlist -> add company -> run scan -> new roles appear.
8. Interview Prep -> save answer -> appears in Question Bank.
9. CV Studio -> completed package -> PDF export button behavior.

---

## 18. Migration/backward compatibility

- Existing users without password hash should be routed to a one-time “Secure your local account” screen.
- Existing completed onboarding should not be forced through full onboarding unless reset is requested.
- Existing provider settings should map into new `ai_mode` and provider config tables.
- Existing Master CV data remains for existing users unless they run reset.
- Existing generated documents remain accessible; new PDF assets attach to existing package records.
- Existing applications can be linked to Watchlist later if source/company matches, but do not auto-link without safe migration.

---

## 19. Security and privacy requirements

- Browser must never collect or display API keys.
- Host secrets remain host-owned.
- Hardware probe must not read secrets.
- Watchlist scans must only run against user-added URLs.
- PDF export must not upload documents externally unless user explicitly selected a cloud export provider in future scope.
- Reset must warn before deleting user data.
- Audit setup/reset/provider/probe actions without logging secrets.

---

## 20. Out of scope

Do not implement in this spec:

- External MCP integration.
- Autonomous browser-based job application submission.
- Scrapling as a required dependency.
- Forced cloud provider setup.
- Full multi-user enterprise auth.
- Paid hosted sync.

---

## 21. Codex implementation prompt

```text
Implement the revised Hatch product gap spec in docs/Hatch_Revised_Product_Gaps_Control_Plane_Watchlist_QBank_OpenRouter_PDF_Spec.md.

Use separate PRs where possible:

PR 1:
- Add UI-first setup/control service layer.
- Add password setup to onboarding.
- Fix reset/new onboarding stale data.
- Add reset preview/apply UI and backend endpoints.
- Ensure Master CV/profile/application/generated document/agent/trace data is cleaned according to reset mode.

PR 2:
- Add AI experience choice to onboarding.
- Add hardware probe UI flow and capability registry.
- Add OpenRouter as a cloud AI provider with host-owned secrets.
- Keep API keys out of browser.

PR 3:
- Add Company Watchlist for proactive role discovery from user-added company/careers URLs.
- Add manual scan and scheduled scan where existing scheduler supports it.
- Reuse existing Import from URL/scoring pipeline.
- Add dedupe and Today/Applications surfacing.
- Keep Firecrawl optional and Scrapling experimental/disabled.

PR 4:
- Add Question Bank under Interview Prep.
- Support reusable questions, STAR stories, proof points, tags, search/filter, and save-from-interview-prep.
- Work in Basic mode without AI.

PR 5:
- Add optional PDF export/preview for generated CV packages.
- Keep DOCX/structured document package as source of truth.
- Gate PDF generation behind capability status and show graceful fallback if unavailable.

Do not implement MCP integration. Do not implement autonomous job application submission. Do not require Scrapling or PDF conversion tooling in lightweight install without capability gating. Add unit, integration, and Playwright tests for all changed flows.
```

---

## 22. Priority summary

| Priority | Item | Reason |
|---|---|---|
| P0 | Reset/new onboarding stale data bug | Blocks trustworthy demos and first-run UX |
| P0 | Password setup screen | Basic onboarding/security completeness |
| P0 | UI-first setup/control plane | Removes CLI-only friction for core setup operations |
| P1 | AI setup in onboarding | Core product decision is currently buried |
| P1 | Hardware probe guided flow | Local AI path is confusing without it |
| P1 | Capability registry | Prevents optional features looking broken |
| P1 | OpenRouter provider | Adds broad model access through one provider integration |
| P1/P2 | Company Watchlist | Makes Scout proactive and supports product promise |
| P2 | Question Bank | Strengthens Interview Prep and reusable personal evidence |
| P2/P3 | PDF export | Improves user/demo value while keeping DOCX source of truth |
| P2/P3 | Scraping provider abstraction | Needed for scalable Watchlist discovery |
| Deferred | MCP integration | Useful later, skipped for now |
| Deferred | Scrapling dependency | Evaluate later; do not add to lightweight install now |
```
