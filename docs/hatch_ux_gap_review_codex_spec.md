# Hatch UX Gap Review & Codex Fix Spec

**Repo:** `https://github.com/arvindsoni2/hatch`
**Prepared for:** Codex implementation
**Review type:** Static source/UX review of app routes, onboarding, app-lock/password, settings screens, and reusable modal/overlay patterns.
**Review date:** 2026-07-06

---

## 1. Scope reviewed

Source-level review covered the following areas:

- First-run app lock and unlock flow
  - `frontend/src/app/unlock/page.tsx`
  - `frontend/src/components/AppLockGate.tsx`
- Onboarding flow
  - `frontend/src/app/onboarding/page.tsx`
  - `frontend/src/components/onboarding/*`
  - `frontend/src/components/OnboardingGate.tsx`
- Settings screens
  - `frontend/src/app/settings/profile/page.tsx`
  - `frontend/src/app/settings/ai/page.tsx`
  - `frontend/src/app/settings/resume/page.tsx`
  - `frontend/src/app/settings/security/page.tsx`
  - `frontend/src/app/settings/system/page.tsx`
- Common app shell and overlay patterns
  - `frontend/src/components/AppLockGate.tsx`
  - `frontend/src/components/CommandPalette.tsx`
  - `frontend/src/components/EmailPreviewModal.tsx`
  - Common components in `frontend/src/components/ui/*`
- Main product surfaces inferred from route/component structure
  - Today, Jobs, Pipeline/Stream, Applications/Tracker, Tailor/CV Studio, Coach, Interview Prep, Analytics, Calendar, Approvals, Agents.

### Review method and limitation

This review combines:

- Static inspection of every route under `frontend/src/app`.
- Static inspection of shared navigation, settings, onboarding, form, status, modal, drawer, and overlay components.
- A desktop and mobile browser check of the real app-lock screen at 1440 × 1000 and 390 × 844.
- A protected-route redirect check in a fresh browser context.

Protected screens correctly redirected to the app lock because the audit browser did not have the user's unlock credential. Pixel-level findings for protected screens therefore remain source-backed recommendations rather than authenticated screenshots. Implementation must include authenticated Playwright screenshots at 375px, 768px, 1024px, and 1440px, keyboard navigation, 200% zoom, light/dark themes, and modal focus verification.

---

## 2. Priority definitions

| Priority | Meaning | Fix expectation |
|---|---|---|
| **P0** | Security, privacy, data-loss, or blocking confusion | Fix first before wider UI polish |
| **P1** | Core onboarding/settings usability gaps that can cause wrong setup or poor trust | Fix in the same UX remediation release |
| **P2** | Cross-screen polish, accessibility consistency, empty states, visual hierarchy | Fix after P0/P1 or in follow-up PRs |
| **P3** | Nice-to-have delight/taste improvements | Backlog unless touched by nearby work |

---

## 3. Executive summary

Hatch has a strong foundation: clear product areas, local-first positioning, a design-system direction, and a privacy-conscious app-lock model. The main UX weakness is not visual styling alone; it is **missing decision support at moments where users can make high-impact choices**.

The highest-risk gaps are:

1. **Password/app-lock screens do not explain or enforce basic password rules in the UI.** First-run setup and password-change flows only show generic password fields and limited mismatch validation.
2. **Password policy must be shared between frontend and backend.** Otherwise the UI can look valid while the backend rejects it, or the backend accepts weak app-lock passwords.
3. **Onboarding stores draft data in `localStorage` while the code comment suggests personal identity fields are not persisted.** This is a privacy/trust mismatch.
4. **Onboarding validation is incomplete.** Later steps can be skipped without clear consequences, and profile quality is not summarised before save.
5. **Settings Profile is too large and mixes profile, scoring, privacy, learning, and LLM provider controls into one long page.** It needs clearer grouping, validation, and safer save/discard behaviour.
6. **System Logs exposes powerful/debug actions without enough warning, masking, confirmation, or pause controls.**
7. **Modal/overlay behaviour is inconsistent and should be centralised in a reusable accessible dialog primitive.**
8. **The app currently exposes two overlapping route and navigation families.** `/stream` and `/tracker` use the newer Hatch shell vocabulary, while `/jobs` and `/applications` retain older concepts and layouts. Users can reach different interpretations of Pipeline, Jobs, Applications, Coach, and Interview Prep.
9. **The global shell and most route components both render page titles.** This creates duplicated headings and inconsistent vertical rhythm on desktop, while mobile receives a different heading hierarchy.
10. **Visual primitives are fragmented.** The codebase mixes `HatchIcon`, Lucide, custom SVGs, `Btn`, shared `Button`, raw buttons, semantic CSS variables, hard-coded Tailwind colours, and multiple radius conventions.
11. **Onboarding behaves as a fixed overlay while the full application shell remains mounted underneath.** The shell needs to be hidden and made non-interactive during onboarding, or onboarding needs a dedicated route layout.

---

## 4. Design principles for this remediation

1. **Explain before asking.** Every high-impact field should tell the user why it matters and what good input looks like.
2. **Prevent bad input, do not merely reject it.** Use inline validation, requirement checklists, examples, and disabled action states with reasons.
3. **Make privacy visible.** Local-first is a product advantage; show what is stored locally, what may be sent to a provider, and what can be reset.
4. **Use consistent feedback.** Use the same patterns for success, warning, error, destructive confirmation, loading, empty state, and disabled state.
5. **Prefer progressive disclosure.** Settings should not feel like a configuration dump. Group advanced controls behind clear sections.
6. **Accessible by default.** All dialogs, modals, command surfaces, and forms must support keyboard, focus management, labels, descriptions, and screen-reader status messages.

---

## 5. P0 fixes

### P0-1 — App-lock password setup and change-password policy

**Affected screens**

- First-run app-lock setup: `frontend/src/app/unlock/page.tsx`
- Unlock screen: `frontend/src/app/unlock/page.tsx`
- Change password: `frontend/src/app/settings/security/page.tsx`
- API integration: `frontend/src/lib/api.ts`
- Backend password setup/change endpoints and validation layer

**Current gap**

The first-run and security password screens are too minimal. They do not show password requirements, strength guidance, recovery implications, or inline field-level validation. The change-password UI checks only whether the two new password fields match before calling the API. This creates avoidable confusion and allows weak app-lock passwords unless the backend independently rejects them.

**Required UX**

Add a reusable password policy module and UI checklist.

Recommended policy:

- Minimum 12 characters.
- Maximum 128 characters.
- Must include at least one letter and one number.
- Special characters are allowed and encouraged, but not required.
- Reject leading/trailing whitespace.
- Reject the same value as the current password during password change.
- Show clear mismatch validation for confirmation field.

Do not make the policy overly hostile. The goal is a practical local app-lock password, not an enterprise SSO password.

**Required UI content**

First-run setup copy:

> Create a local app-lock password. This protects the job-search data stored in this Hatch workspace. It is not a Hatch cloud account and there is no email recovery.

Password requirements checklist:

- At least 12 characters
- Includes a letter
- Includes a number
- Passwords match

Change-password copy:

> Choose a new local app-lock password. You will need it the next time Hatch locks. Keep it somewhere safe because Hatch does not provide email recovery.

Unlock copy:

> Enter your local app-lock password to continue.

**Implementation requirements**

- Add `frontend/src/lib/passwordPolicy.ts`.
- Add `frontend/src/components/security/PasswordRequirementList.tsx`.
- Add `frontend/src/components/security/PasswordField.tsx` with:
  - Show/hide toggle.
  - `autoComplete="new-password"` for setup/new password.
  - `autoComplete="current-password"` for unlock/current password.
  - `aria-describedby` linking fields to checklist/error text.
- Apply the same validation to:
  - First-run setup.
  - Security settings password change.
  - Backend setup/change endpoint validation.
- Disable submit until local validation passes.
- Keep API error fallback for backend validation failure.
- Show errors inline near fields, not only as a generic form-level message.
- Use `role="status"` for success messages and `role="alert"` for errors.

**Acceptance criteria**

- A weak password such as `abc123` cannot be submitted from first-run setup.
- A weak password such as `abc123` cannot be submitted from Settings → Security.
- A password with 12+ characters, at least one letter, and at least one number is accepted when confirmation matches.
- Confirmation mismatch is shown before API submission.
- User can reveal/hide password values.
- Screen-reader users can understand password rules and errors.
- Backend rejects invalid passwords even if the frontend is bypassed.

---

### P0-2 — App-lock recovery and lock-state clarity

**Affected screens**

- `frontend/src/app/unlock/page.tsx`
- `frontend/src/app/settings/security/page.tsx`
- `frontend/src/components/AppLockGate.tsx`

**Current gap**

The app explains that Hatch is locked, but it does not give enough recovery guidance or confidence about what is happening. On first run, the user may not understand the difference between a local app-lock password and a SaaS login. In Settings → Security, environment-managed password states are present, but the action model needs clearer user-facing explanation.

**Required UX**

Add a compact “How this works” panel to first-run setup and Settings → Security:

- Hatch is self-hosted/local-first.
- The app-lock password protects local workspace access.
- It is not an online account password.
- There is no email reset.
- If forgotten, recovery requires the documented local reset command/script and may affect lock state.

**Implementation requirements**

- Add a non-alarming info callout under first-run password fields.
- Add a similar callout in Settings → Security.
- In env-managed state, clearly state:
  - “Password is managed by environment configuration.”
  - “In-app password change is disabled.”
  - “Change the environment value and restart Hatch to update it.”
- Improve AppLockGate loading copy from `Securing Hatch…` to a stateful message if verification is slow:
  - Initial: “Checking app lock…”
  - Delayed: “Still checking the local backend. Make sure Hatch is running.”
- Keep backend verification failure as a blocking state; do not show protected app content when lock state is unknown.

**Acceptance criteria**

- First-run app-lock page clearly says there is no cloud account/email recovery.
- Env-managed password state cannot expose an in-app change form.
- Lock-state check error includes one next action: “Check backend is running.”
- Protected content is never visible while lock state is unknown or locked.

---

### P0-3 — Onboarding localStorage privacy mismatch

**Affected files**

- `frontend/src/app/onboarding/page.tsx`
- `frontend/src/components/onboarding/*`

**Current gap**

The onboarding page persists draft state in browser `localStorage`. The source comment says not to persist personal identity fields, but the persisted payload includes the candidate object. This is a privacy/trust mismatch, especially for a local-first app handling job-search identity, preferences, locations, rates, and visa/work eligibility details.

**Required UX/product decision**

Choose one of these two approaches and implement consistently:

#### Option A — Safer default, recommended

Persist only non-sensitive progress metadata and non-identifying preferences. Do not persist candidate identity, compensation, eligibility, or location details in `localStorage`.

#### Option B — Explicit draft persistence

Persist the full draft, but show clear copy:

> Hatch saves your onboarding draft in this browser so you can continue later. This includes profile details you enter here. You can clear the draft at any time.

Also add a “Clear onboarding draft” action.

**Recommendation**

Implement Option A for now. It better matches privacy-first/local-first positioning and avoids storing unnecessary sensitive draft data in the browser.

**Implementation requirements**

- Update `ONBOARDING_STORAGE_KEY` payload shape.
- Exclude candidate identity, compensation/rates, eligibility/legal preferences, and detailed location data from localStorage.
- Clear onboarding localStorage after successful profile save.
- Add a small “Draft saved locally in this browser” or “Progress saved locally” note only if meaningful.
- Add unit test for persisted payload excluding sensitive fields.

**Acceptance criteria**

- Inspecting localStorage after entering onboarding identity details does not reveal candidate name/title/email-like identity fields if Option A is implemented.
- On successful onboarding completion, the onboarding draft is cleared.
- Copy shown to user accurately describes what is persisted.

---

### P0-4 — Central accessible dialog/modal primitive

**Affected components**

- `frontend/src/components/EmailPreviewModal.tsx`
- `frontend/src/components/CommandPalette.tsx`
- Any current/future overlay, drawer, confirmation, preview, or detail modal

**Current gap**

Dialog and overlay patterns are implemented directly in feature components. This increases the chance of inconsistent focus handling, Escape handling, backdrop behaviour, labelling, mobile layout, and destructive-action confirmation.

**Required UX**

Create one shared dialog primitive and use it for modals and confirmations.

**Implementation requirements**

Add `frontend/src/components/ui/dialog.tsx` or equivalent wrapper using the existing UI stack.

Required behaviour:

- `role="dialog"` or native dialog implementation.
- `aria-modal="true"`.
- Dialog title linked with `aria-labelledby`.
- Optional description linked with `aria-describedby`.
- Focus moves into dialog on open.
- Focus is trapped while open.
- Focus returns to triggering element on close.
- Escape closes non-destructive dialogs unless an operation is in progress.
- Close button always has accessible label.
- Backdrop click behaviour is consistent and disabled for destructive confirmations.
- Mobile uses full-screen or near-full-screen layout for dense forms.
- Footer actions always follow the order: secondary/cancel left, primary/destructive right.

**Acceptance criteria**

- Command palette, email preview, and confirmation flows pass keyboard-only use.
- `Escape` closes the command palette and non-blocking modals.
- Focus returns to the initiating control after close.
- Playwright accessibility smoke test confirms dialog labelling exists.

---

### P0-5 — System Logs safety and destructive action confirmation

**Affected screen**

- `frontend/src/app/settings/system/page.tsx`

**Current gap**

System Logs contains runtime health, LLM traces, failed events, retry actions, clear trace actions, and CSV export. This is powerful and useful, but it behaves like a normal settings page despite showing potentially sensitive debug information and destructive actions.

**Required UX**

Make System Logs feel like an advanced/admin diagnostics screen.

**Implementation requirements**

- Add an “Advanced diagnostics” header warning:
  - Logs may contain job titles, company names, prompts, model metadata, and error details.
  - Exported CSV may contain sensitive debugging context.
- Mask or truncate sensitive previews by default.
- Add “Show details” expansion for long/raw error payloads.
- Add a “Pause auto-refresh” toggle. Default remains auto-refresh if desired, but user must be able to pause it.
- Confirm before:
  - Clearing traces.
  - Retrying failed events.
  - Exporting CSV if unmasked sensitive fields are included.
- Replace `window.confirm` patterns with shared confirmation dialog.
- Add empty states with next actions:
  - “No traces yet. Run an AI-assisted action to see traces here.”
  - “No failed events. Background processing looks healthy.”

**Acceptance criteria**

- Clear traces cannot happen accidentally.
- Retry failed event cannot happen accidentally.
- User can pause auto-refresh.
- Debug previews are masked/truncated by default.
- CSV export warning appears before export when sensitive details are included.

---

## 6. P1 fixes

### P1-1 — Onboarding step validation and review-before-save

**Affected files**

- `frontend/src/app/onboarding/page.tsx`
- `frontend/src/components/onboarding/*`

**Current gap**

Onboarding has multiple meaningful steps, but validation is uneven. Earlier steps validate name/title, roles, location, and rate, while later steps can be completed without useful confirmation. Users can finish onboarding without understanding what is required, what is optional, and how choices affect recommendations.

**Required UX**

- Add clear required/optional labels per step.
- Validate every step that captures meaningful data.
- Add a final “Review your setup” step before saving.
- Add “Skip for now” only where skipping is safe and reversible.
- Explain consequences of each major setup choice.

**Step-specific fixes**

#### Welcome

- Explain what onboarding configures:
  - profile
  - target roles
  - markets/location
  - pay expectations
  - work preferences
  - AI provider
- Add time expectation: “Takes about 3–5 minutes.”

#### About You

- Required fields should have examples.
- Use inline validation.
- Avoid vague labels such as “title” if it could mean current title vs target title.

#### Market / Location

- Make remote/hybrid/on-site implications clear.
- Validate country/city combinations where possible.
- Show examples for UK-focused search.

#### Pay

- Validate min <= max.
- Show currency and rate period clearly.
- Avoid accepting `0` once user reaches completion unless explicitly “not sure yet”.

#### Eligibility

- Explain that this affects filtering and scoring but is not legal advice.
- Let user choose “Prefer not to say” where appropriate.
- Show privacy note.

#### Skills

- Dedupe skills.
- Add examples: delivery, agile, domain, technical, AI automation.
- Show minimum useful count, e.g. “Add at least 5 skills for better matching.”

#### AI Provider

- Make local/cloud trade-off explicit.
- Allow “Set up later” with clear consequence: “Hatch will still work, but AI-assisted tailoring and coaching may be limited.”

#### Success

- Show what was saved.
- Show next best action:
  - Upload Master CV.
  - Review Profile Settings.
  - Start Job Scout / Today.

**Acceptance criteria**

- User cannot finish onboarding with invalid pay range.
- User cannot finish onboarding without at least one target role unless explicitly choosing “I’ll add later”.
- Final review page summarises profile, markets, pay, eligibility, skills, and AI provider.
- Skipped items appear as warnings on final review.

---

### P1-2 — Settings information architecture cleanup

**Affected routes**

- `frontend/src/app/settings/profile/page.tsx`
- `frontend/src/app/settings/ai/page.tsx`
- `frontend/src/app/settings/resume/page.tsx`
- `frontend/src/app/settings/security/page.tsx`
- `frontend/src/app/settings/system/page.tsx`

**Current gap**

Settings are useful but feel like implementation structure rather than user mental model. Profile settings in particular mixes identity, job preferences, scoring logic, privacy, learning, and LLM provider controls.

**Required UX**

Add a consistent Settings shell:

- Left/top settings navigation.
- Page title + short purpose text.
- Last saved status.
- Unsaved changes handling.
- Consistent save/cancel/footer actions.
- Consistent section card style.

Recommended settings IA:

1. **Profile** — identity, target roles, skills, location, pay.
2. **Job Preferences** — boards, remote/hybrid, scoring preferences, thresholds.
3. **AI Provider** — local/cloud provider setup.
4. **Master CV** — upload, parse, preview, replacement.
5. **Security** — app lock, session, password.
6. **Diagnostics** — system logs, traces, exports.

If a full IA split is too large for one PR, keep current routes but add anchors/tabs inside Profile and move LLM provider controls out of Profile to AI Provider only.

**Acceptance criteria**

- User can understand each settings page purpose from its heading/description.
- AI provider is not configured in two conflicting places.
- Profile page is easier to scan via sections or anchors.
- Settings nav shows active page.

---

### P1-3 — Profile settings validation and safe save behaviour

**Affected screen**

- `frontend/src/app/settings/profile/page.tsx`

**Current gap**

Profile Settings provides many powerful controls but lacks enough validation and guardrails. Numeric fields can create invalid combinations, tag inputs may accept duplicates, and destructive reset uses a browser confirm instead of app-native confirmation.

**Required validation**

Add a shared profile validation schema, ideally with Zod or existing project validation style.

Validate:

- Target roles: at least one non-empty role unless intentionally skipped.
- Skills: dedupe case-insensitively.
- Locations: no empty city/country rows.
- Compensation: minimum <= maximum, numeric values only, currency required.
- Scoring weights: accepted range and either sum to expected total or clearly explain independent weighting.
- Thresholds: min/max valid range and min <= max where applicable.
- Job boards: valid known values.
- LLM provider: valid known value and not duplicated with AI settings.

**Required UX**

- Show field-level errors.
- Show section-level error count in sticky save bar.
- Disable Save when validation fails and tell the user why.
- Replace `window.confirm` with shared confirmation dialog for reset learning.
- Add unsaved changes guard on route change / page unload.
- Save button should show loading, success, and error states.
- Discard should ask for confirmation when there are dirty changes.

**Acceptance criteria**

- Invalid pay range cannot be saved.
- Duplicate skills are merged or rejected with a helpful message.
- Reset learning uses app-native confirmation.
- Navigating away with unsaved changes warns the user.
- Save errors remain visible until fixed or dismissed.

---

### P1-4 — AI Provider setup clarity

**Affected screen**

- `frontend/src/app/settings/ai/page.tsx`

**Current gap**

The AI setup page has valuable functionality but uses too much implementation-level copy. Users need clearer choices: use Hatch without AI, use local AI, or use cloud provider. They also need to know what data may leave the machine.

**Required UX**

Reframe the page around three clear choices:

1. **Use Hatch now, set up AI later**
   - Best for trying the app.
   - AI tailoring/coaching may be limited.
2. **Run AI locally**
   - Best for privacy and cost control.
   - Requires local model runtime and compatible model.
3. **Use cloud AI provider**
   - Best for quality/convenience.
   - Prompts may be sent to provider.
   - Requires secret setup.

**Implementation requirements**

- Add “Current setup” summary at the top.
- Add provider cards with:
  - Best for.
  - Privacy impact.
  - Setup required.
  - Status: ready / missing secret / not installed / unknown.
- Add copy-to-clipboard for generated CLI commands, e.g. secret setup commands.
- Add “Test provider” action if backend supports it; otherwise add a clear “Not tested yet” status.
- Show hardware/model detection results in plain language:
  - “Detected RAM: X GB”
  - “Recommended local model tier: small/medium”
  - “Selected models: N”
- Avoid raw backend error text where possible. Convert to friendly messages with details expandable.

**Acceptance criteria**

- A new user can safely choose “set up later” and know what happens next.
- User can distinguish local vs cloud privacy trade-offs.
- Missing secret/provider states are visible before save.
- CLI commands can be copied.

---

### P1-5 — Master CV upload and parse flow

**Affected screen**

- `frontend/src/app/settings/resume/page.tsx`

**Current gap**

The Master CV screen communicates the right idea, but upload constraints and replacement implications are not enforced or explained strongly enough. The UI says max 10 MB, but client-side checks appear focused on file extension only.

**Required UX**

- Enforce file size client-side and backend-side.
- Enforce allowed MIME/types in addition to extension.
- Explain what happens to the uploaded CV:
  - stored locally
  - parsed into structured profile fields
  - used for tailoring/coaching/matching
- If replacing an existing CV, show confirmation:
  - “This will replace your current Master CV data after you confirm the parsed preview.”
- Add a clear multi-step flow:
  1. Select file
  2. Uploading
  3. Parsing
  4. Review extracted data
  5. Confirm save
- In preview, show warnings near affected fields, not only as a list.
- Add “Upload a different file” and “Cancel” actions during preview.
- Avoid overpromising with “never invents content”; use “Hatch will only save what it can extract or what you confirm.”

**Acceptance criteria**

- Files over 10 MB are rejected before upload with a helpful message.
- Unsupported file types are rejected before upload.
- Replacing an existing CV requires explicit confirmation.
- User can cancel or upload a different file after parse preview.
- Parse warnings are visible next to relevant extracted data.

---

### P1-6 — Email Preview modal send safety

**Affected component**

- `frontend/src/components/EmailPreviewModal.tsx`

**Current gap**

The email preview flow contains high-impact actions: regenerate, skip, open mail client, and send directly. It needs stronger send safety, validation, preview clarity, and dialog accessibility.

**Required UX**

- Use shared dialog primitive.
- Validate recipient email format, not only presence.
- Show “Send Directly” as a high-emphasis action only when SMTP is configured and ready.
- If SMTP status is unknown, disable direct send and explain why.
- Require confirmation before direct send, or add a pre-send review state:
  - recipient
  - subject
  - body preview
- Add unsaved body-change warning before regenerate/skip/close if edits exist.
- Make HTML preview safer and visually clear:
  - state that preview is sandboxed
  - provide plain text fallback
- Show success after send/open action.

**Acceptance criteria**

- Invalid recipient email cannot be sent.
- Direct send cannot happen accidentally.
- Closing/regenerating with unsaved edits asks for confirmation.
- Modal is keyboard accessible and returns focus after close.

---

## 7. P2 fixes

### P2-1 — Cross-screen empty states and first-use guidance

**Affected screens**

- Today
- Jobs
- Pipeline/Stream
- Applications/Tracker
- Tailor/CV Studio
- Coach
- Interview Prep
- Analytics
- Calendar
- Approvals
- Agents

**Current gap**

The app has many surfaces. For a new user, blank or low-data states can feel like the product is not working.

**Required UX**

Each major screen should have:

- One-line purpose statement.
- Empty state with one recommended next action.
- Secondary action to settings/help if setup is incomplete.
- Loading skeleton where data fetch can take time.
- Error state with retry and diagnostics link.

**Examples**

Today:

> No actions yet. Start by uploading your Master CV or running Job Scout.

Applications:

> No applications tracked yet. Save a job or create your first application pack.

Interview Prep:

> Add an upcoming interview or choose an application to generate prep questions.

Analytics:

> Analytics will appear after you track applications and outcomes.

**Acceptance criteria**

- Every primary route has loading, empty, error, and content states.
- Empty states include exactly one primary CTA and one secondary link where useful.

---

### P2-2 — Form component consistency

**Affected areas**

- Onboarding forms
- Settings forms
- Email preview form
- Filters and drawers

**Current gap**

Form inputs use repeated class strings and inconsistent helper/error text patterns. This makes screens feel less polished and increases accessibility risk.

**Required UX**

Create or extend shared form components:

- `FormField`
- `TextInput`
- `PasswordField`
- `NumberInput`
- `SelectField`
- `TagInput`
- `InlineError`
- `HelperText`
- `SectionCard`
- `SettingsSaveBar`

Each field should support:

- Label
- Optional/required indicator
- Helper text
- Error text
- `aria-invalid`
- `aria-describedby`
- Disabled reason where relevant

**Acceptance criteria**

- New password, profile, onboarding, and email fields use shared field patterns.
- Error styling and helper text are visually consistent.

---

### P2-3 — Command palette polish

**Affected component**

- `frontend/src/components/CommandPalette.tsx`

**Current gap**

The command palette is useful but can become more helpful and accessible.

**Required UX**

- Use shared dialog/popover primitive or ensure equivalent focus management.
- Add search input placeholder such as “Search screens and actions…”
- Include recent actions or most-used routes if trivial to implement.
- Add route aliases:
  - “CV” → CV Studio / Master CV
  - “resume” → Master CV
  - “settings” → Profile Settings
  - “logs” → Diagnostics
- Hide or label advanced actions such as System Logs as “Advanced”.
- Ensure keyboard hints are accurate on Windows/Linux (`Ctrl+K`) and Mac (`⌘K`).

**Acceptance criteria**

- Ctrl+K opens command palette on Linux/Windows.
- Search aliases return expected actions.
- Focus is trapped and returned correctly.

---

### P2-4 — Main navigation naming consistency

**Affected files**

- Shell/nav components
- Command palette
- Route labels
- Empty states

**Current gap**

Some areas use multiple names for similar concepts, e.g. Applications vs Tracker, Pipeline vs Stream, Master CV vs CV Studio vs Tailor. This creates avoidable cognitive load.

**Required UX**

Standardise labels:

- **Today** — daily dashboard
- **Jobs** — discovered/saved jobs
- **Applications** — application tracker
- **CV Studio** — tailoring and application pack creation
- **Interview Prep** — interview materials
- **Coach** — practice sessions
- **Analytics** — progress metrics
- **Settings** — configuration
- **Diagnostics** — system logs and traces

Use route names internally if needed, but user-facing labels should be consistent.

**Acceptance criteria**

- Nav, command palette, page headings, and empty states use the same names.
- “System Logs” is nested under or renamed “Diagnostics” in user-facing navigation.

---

### P2-5 — Responsive/dense screen treatment

**Affected screens**

- System Logs
- Applications/Kanban
- Analytics tables/charts
- Settings Profile
- Email Preview modal

**Current gap**

Dense screens and tables likely degrade on mobile or smaller laptop screens unless explicitly handled.

**Required UX**

- Tables become cards below a defined breakpoint.
- Settings forms use one-column layout on small screens.
- Modals become full-screen sheets on mobile.
- Sticky footers do not cover content.
- Primary actions remain visible without horizontal scrolling.

**Acceptance criteria**

- Playwright screenshots at desktop, tablet, and mobile widths show no clipped primary actions.
- System Logs is usable on mobile as cards or horizontal scroll with clear affordance.

---

## 8. P3 taste and delight improvements

### P3-1 — Setup checklist on Today

Add a small checklist for new users:

- Complete profile
- Upload Master CV
- Choose AI setup
- Start Job Scout
- Track first application

Dismiss when complete.

### P3-2 — Trust badges and microcopy

Add small, consistent badges:

- Local-only
- Cloud provider
- Needs setup
- Advanced
- Beta

### P3-3 — Better success moments

After completing onboarding, CV upload, AI setup, or password change, show a brief success state that includes the next useful action.

---

## 8A. Comprehensive screen, modal, and design consistency review

### 8A-1. Design read and target system

**Design read:** Preserve-mode redesign of a trust-first job-search product for daily professional use, with a restrained modern SaaS language built on the existing Hatch semantic tokens.

| Dial | Target | Reason |
|---|---:|---|
| Design variance | 4/10 | Predictable structure is more valuable than expressive composition in a workflow product |
| Motion intensity | 3/10 | Motion should communicate feedback and state change, not decorate dashboards |
| Visual density | 6/10 | The product contains real operational data, but primary actions still need breathing room |

Hatch should continue using its owned Tailwind and CSS-variable system. Do not add another full design system. Radix Dialog is already installed and is the correct accessible foundation for dialogs, sheets, confirmations, and the command palette wrapper.

The intended personality remains: calm, competent, local-first, evidence-led, and non-gamified. Preserve the teal accent and dark-first identity, but make both themes first-class rather than relying on global catch-all overrides.

### 8A-2. New priority findings missing from the first review

#### P1 — Consolidate duplicate route families and product vocabulary

**Evidence**

- Primary Hatch navigation uses `/today`, `/stream`, `/tracker`, `/tailor`, and `/prep`.
- Older routes remain active at `/jobs`, `/applications`, `/coach`, and related detail pages.
- `/stream` is labelled “Pipeline”, while `/applications` also renders “Pipeline”.
- `/tracker` is labelled “Applications”, while the command palette also links to `/tracker` as “Applications”.
- The command palette exposes both “Coach” and “Interview Prep” as separate top-level destinations without explaining the difference.
- The dormant `Sidebar` and `BottomNav` components define a third navigation vocabulary.

**Recommendation**

Choose one canonical user journey and document the route relationship before visual polish:

| Canonical label | Canonical route | Treatment of overlapping route |
|---|---|---|
| Today | `/today` | Keep |
| Jobs | `/jobs` | Keep as searchable job inventory |
| Pipeline | `/stream` | Keep as discovery-to-application flow |
| Applications | `/tracker` | Keep as real-world application tracker |
| CV Studio | `/tailor` | Keep |
| Interview Prep | `/prep` | Keep as generated interview material |
| Coach | `/coach` | Keep only if it remains a distinct live-practice product |
| Analytics | `/analytics` | Keep as secondary navigation |
| Settings | `/settings/*` | Keep as account/workspace configuration |
| Diagnostics | `/settings/system` | Rename user-facing “System Logs” to “Diagnostics” |

Do not delete routes silently. Add redirects only after usage, deep links, tests, and route ownership are confirmed. Remove or archive unused `Sidebar` and `BottomNav` implementations once the active shell is established.

**Acceptance criteria**

- Every route has one unique purpose statement.
- Nav, top bar, page heading, command palette, empty states, and breadcrumbs use the same label.
- No two visible routes present themselves as “Pipeline” or “Applications”.
- Legacy navigation components cannot accidentally be reintroduced.

#### P1 — Establish one page-header contract

**Evidence**

- `HatchTopBarSlot` renders a desktop page title for nearly every route.
- Most routes also render their own `<h1>`, including Today, Pipeline, Applications, Interview Prep, Jobs, Analytics, Calendar, Agents, Coach, Settings, and Diagnostics.
- Desktop therefore receives a top-bar title plus a second page title, while mobile hides the top bar and depends on the route `<h1>`.
- Several detail routes inherit generic top-bar labels such as “Coach” or “Applications” even when the page content is a report, story, job, or approval detail.

**Recommendation**

Adopt one explicit contract:

- Desktop shell top bar owns global search and utilities, not the document `<h1>`.
- Each route owns exactly one semantic `<h1>` inside content.
- The top bar may show a compact breadcrumb or section label, but must not duplicate the route title.
- Detail routes use breadcrumb + object title, for example `Applications / Senior Delivery Lead`.
- Mobile keeps the same content heading hierarchy as desktop.

**Acceptance criteria**

- Exactly one `<h1>` exists per route.
- Heading levels remain sequential in every content state.
- Route title does not appear twice above the first action.
- Screen-reader landmarks contain one top-level `main` and one page heading.

#### P1 — Give onboarding a dedicated, isolated layout

**Evidence**

- `AppLockGate` mounts the Hatch sidebar, mobile bar, top bar, install prompt, and command palette around all routes except `/unlock`.
- `/onboarding` renders as `fixed inset-0`, visually covering that shell.
- The covered shell remains in the DOM and can remain reachable to keyboard or assistive technology unless explicitly made inert.
- `OnboardingGate` can also mount onboarding over protected content.

**Recommendation**

Use a dedicated onboarding layout outside the application shell. If the overlay architecture is retained temporarily:

- Apply `inert` and `aria-hidden="true"` to the underlying shell.
- Disable command palette and global shortcuts.
- Prevent background scroll.
- Return focus to a meaningful destination after completion.
- Use `min-height: 100dvh`, safe-area padding, and a persistent mobile action region that does not cover fields.

Do not style onboarding as a modal. It is a full workflow with its own progress, navigation, validation, and recovery model.

#### P1 — Consolidate visual primitives before screen-by-screen polish

**Evidence**

- Icons come from Lucide, the custom `HatchIcon` SVG path map, and isolated custom SVG charts/spinners.
- Buttons use `components/ui/button.tsx`, `components/hatch/Btn.tsx`, and many raw `<button>` implementations.
- Components use semantic variables alongside hard-coded `slate`, `indigo`, `blue`, `red`, `green`, and `amber` utilities.
- Radius usage mixes `--radius-*`, undefined `--r-card`/`--r-field` fallbacks, Tailwind `rounded-*`, pills, and inline pixel values.
- `globals.css` contains broad dark-mode catch-all overrides, indicating components are not natively tokenised.
- Typography loads Inter through `next/font`, defines Inter again in CSS, imports Newsreader globally, and uses Newsreader only for isolated onboarding progress numerals.

**Recommendation**

Create a short design-system consolidation PR before broad page redesign:

1. Select Lucide as the single product icon family because it is already the dominant installed dependency. Migrate `HatchIcon` mappings to Lucide equivalents, then remove the hand-rolled path map. Keep custom SVG only for data visualisations that cannot be represented as icons.
2. Standardise icon stroke at 2px, with 1.75px allowed only for dense 16px icons. Every icon-only control must be at least 44 × 44px and have an accessible name.
3. Use one `Button` API with primary, secondary, ghost, and destructive variants. Absorb `Btn` behaviour into it and remove raw visual button styling from feature screens.
4. Define one shape rule:
   - Fields: 8px.
   - Buttons: 8px.
   - Cards/dialogs: 12px.
   - Status badges/toggles only: full pill.
5. Use semantic tokens in components. Remove the global dark-mode utility remapping once migrated.
6. Keep Inter/system sans for the product UI and Roboto Mono for aligned data. Remove Newsreader from product workflow screens unless a clearly documented brand role is approved.
7. Keep one teal accent. Agent colours and semantic success/warning/danger colours may vary only when they communicate real meaning.

#### P1 — Replace every bespoke overlay with dialog, sheet, or non-modal popover primitives

The initial P0-4 recommendation remains correct but the affected inventory is larger than first listed.

| Surface | Current pattern | Required primitive |
|---|---|---|
| Command palette | Custom fixed overlay around `cmdk` | Radix Dialog + cmdk |
| Email preview | Custom fixed overlay | Dialog desktop, full-screen sheet mobile |
| Job URL import | Custom fixed overlay | Dialog |
| Add application | Custom dialog markup | Dialog |
| Review queue | Custom responsive overlay | Dialog/sheet with protected in-progress close state |
| Application detail | Custom right drawer | Sheet |
| Coach consent | Custom fixed dialog | Alert Dialog or non-dismissible Dialog |
| Coach session launcher | Custom fixed overlay | Dialog |
| Interview Prep launcher | Custom fixed overlay | Dialog |
| Destructive stage changes | `window.confirm` | Alert Dialog |
| Prep deletion and errors | `confirm`/`alert` | Alert Dialog + inline/toast feedback |
| Profile learning reset | `window.confirm` | Alert Dialog |
| Notification and user menus | Custom popovers | Radix Popover/Dropdown Menu semantics |

Every primitive must define initial focus, focus trap, focus return, Escape policy, backdrop policy, scroll lock, mobile safe area, `overscroll-behavior: contain`, busy-state close protection, and action ordering.

### 8A-3. Cross-screen shell and navigation review

| Surface | Finding | Recommendation |
|---|---|---|
| Desktop sidebar | Five primary items are clear, but “Your agents” is persistent supporting content and competes with navigation | Collapse agent capability into a secondary status link or show live status only when it is actionable |
| Mobile navigation | Five labels fit narrowly; “Interview Prep” is likely to crowd at 320-390px and 200% zoom | Use shorter visible label “Prep” only if the page title remains “Interview Prep”; test 320px and text zoom |
| Top bar search | “Search roles…” appears on settings, security, diagnostics, and coach pages | Hide global search where irrelevant or relabel as global “Search jobs…” with results destination made explicit |
| User menu | Navigation is implemented as buttons calling `router.push` | Use links for navigation so open-in-new-tab and browser semantics work |
| Theme controls | Theme exists in both mobile bar and user menu with separate state implementations | Centralise theme state and expose one control per breakpoint |
| Notifications | Bell has a custom dropdown, hard-coded colours, and locale-dependent time text | Use popover semantics, semantic status tokens, `Intl.DateTimeFormat`, and a labelled empty state |
| Page container | Route-specific widths range from `max-w-2xl` to `max-w-[1400px]` without a documented template | Define narrow form, standard content, and wide data page templates |
| Landmarks | `AppLockGate` owns `<main>` while several route files also render `<main>` | Prevent nested main landmarks; shell owns one main and route roots use sections/divs |
| Skip navigation | No skip link is present | Add “Skip to main content” as the first focusable control |

### 8A-4. Main-screen review

| Screen | Current strengths | Main gaps | Recommendation |
|---|---|---|---|
| Today | Clear next-action concept, ready queue, activity evidence | Two page-heading treatments, several small text sizes, agent totals can dominate first use, some empty states have no direct setup action | Keep one H1; prioritise setup blocker or next action; use 12px minimum metadata; add one primary CTA in empty state |
| Jobs | Mature filtering and contextual empty states | Uses older light/indigo visual vocabulary and “Inbox” heading while shell says “Jobs” | Rename H1 to Jobs; tokenise controls and cards; preserve query state in URL; keep archive/rescore actions subordinate |
| Pipeline `/stream` | Clear stage filters and desktop/mobile layouts | Fixed desktop grid columns risk clipping; stage filters are local state; empty state only suggests another stage | Put stage in query string; allow table columns to contract; add “View all jobs” secondary action |
| Applications `/tracker` | Purposeful drag workflow and mobile horizontal lanes | Confirmation uses browser dialog; add form is bespoke; drag-forward button language says “Drag” for a click action; lane scrolling lacks a strong affordance | Shared dialogs; label click action “Move to …”; add visible lane pagination/scroll cue only when overflow exists; provide keyboard move menu |
| Legacy Applications `/applications` | Existing Kanban feature coverage | H1 says Pipeline, duplicating `/stream`; visual system is legacy | Decide whether it redirects, becomes a distinct legacy admin view, or is removed after migration |
| CV Studio | Clear analyse/generate/review sequence | Numbered headings, mixed raw buttons and shared components, loading uses generic spinners, long page can lose action context | Use named stages without decorative numbering; skeleton/inline progress matching final panels; sticky action summary only while relevant |
| Interview Prep `/prep` | Useful session list and generated material | Uses browser alerts/confirms; launcher is bespoke; title/company metadata uses decorative middle dots; delete icon target needs verification | Shared dialog/toast patterns; one metadata separator max; 44px destructive target; expose retry errors inline |
| Coach | Distinct practice functionality exists | Naming relationship to Interview Prep is unclear; light slate styling and launcher differ from `/prep`; modal is bespoke | Add purpose text explaining live practice vs prepared material; share session-launcher dialog and tokens |
| Analytics | Rich evidence and cost/quality visibility | Six-up metric density, repeated cards, hard-coded chart/status colours, likely mobile overload | Group into Outcomes, Match Quality, AI Usage, and Reliability; 2-column tablet/1-column mobile; semantic chart palette; informative empty states |
| Calendar | Simple structure | Legacy light-only classes, generic spinner, no clear empty action | Tokenise; add “Add interview” or “Open Applications” empty CTA; use skeleton matching calendar |
| Agents | Operational visibility | Dense 4-card and 2-column dashboard, animated spinners, blue/slate legacy palette, status can imply activity without timestamp | Show last updated and actual state; reserve animation for confirmed running work; tokenise and reduce repeated cards |
| Approvals | Clear human-in-the-loop concept | Legacy icon/colour treatment, loading spinner, actions need consistent destructive hierarchy | Use shared action footer and semantic statuses; distinguish approve from irreversible reject; add no-pending next action |
| Job/Application/Approval details | Detailed evidence is available | Generic top-bar labels, inconsistent back navigation, mixed drawers/pages, hard-coded colours | Use one detail-page template with breadcrumb, title, metadata, action rail, and consistent back behavior |
| Coach session/report/stories | Deep feature coverage | Several pages are light-theme-specific and use independent typography, forms, cards, and loaders | Treat Coach as one sub-system with shared shell, page template, form fields, score treatment, and report hierarchy |

### 8A-5. Settings-screen review

All settings routes need a persistent settings sub-navigation on desktop and a compact select/tabs pattern on mobile. The user menu is an entry point, not sufficient settings navigation.

Recommended order:

1. Profile
2. Job Preferences
3. AI Provider
4. Master CV
5. Security
6. Diagnostics

| Settings screen | Findings | Recommendation |
|---|---|---|
| Profile | Long page mixes identity, locale, location, target roles, boards, compensation, skills, scoring, Coach privacy, outcome learning, and LLM provider; three-column compensation grid is fragile on mobile; sticky save bar becomes invisible rather than unmounted | Split Job Preferences from Profile; remove duplicate LLM provider section; use anchors only as interim; use one-column mobile grids; preserve layout space only when save bar is visible; add dirty-navigation guard |
| AI Provider | Choice framing is improved, but provider cards and local model controls use mixed amber/token styling; status and save intent need stronger separation | Keep “later/local/cloud” choice model; use selectable cards with radio semantics; show current effective routing; distinguish “Save choice” from “Install/apply/restart”; provide copy buttons for commands |
| Master CV | Parse preview and warnings are valuable; upload zone uses legacy brand colours; uppercase micro-headings are overused; summary grids may compress badly | Use a five-state upload stepper; tokenise upload and warning states; use sentence-case section headings; stack preview definition lists at mobile; require replacement confirmation |
| Security | Clear two-section structure, but password inputs lack shared policy/show controls; no recovery panel; form controls use outline removal and low-level styling | Implement P0 password components; add local-account explanation and reset guidance; use inline field errors and announced success; verify 16px mobile inputs |
| Diagnostics | Strong operational data, but page lacks advanced/sensitive framing; tables and hard-coded status colours are dense; no pause; retry/clear/export safety is incomplete | Rename to Diagnostics; add privacy warning, pause, masking, details disclosure, confirmation, and responsive card/table views; show last refresh time |

Settings shell acceptance criteria:

- Active page is always visible.
- One page title and one purpose sentence.
- Consistent section spacing and card treatment.
- Save/discard placement is identical.
- Dirty, saving, saved, validation error, and API error states use the same components.
- Destructive actions live in a clearly separated danger region.
- Mobile content is never hidden behind a sticky footer or bottom navigation.

### 8A-6. Form, control, and feedback review

1. Replace repeated field class strings with a shared field composition API.
2. Every control requires persistent label, helper/error association, `name`, suitable `autocomplete`, correct `type`/`inputMode`, and `aria-invalid` when needed.
3. Do not disable a submit action merely because a field is incomplete before the user attempts submission. Keep it enabled until request start, then focus and explain the first invalid field on submit. The exception is a multi-step “Next” action where requirements are already visible and live.
4. Replace `transition-all` with explicit property transitions.
5. Keep placeholders as examples, never labels, and use ellipsis characters consistently.
6. Tag inputs must deduplicate case-insensitively and expose removal as a 44px target at mobile.
7. Toggles need `role="switch"` with `aria-checked`, not `aria-pressed`.
8. Async errors must include the next action. Success uses polite live regions; errors use alerts only when immediate interruption is necessary.
9. Skeletons should match the final layout. Reserve spinners for compact button-level activity.
10. Add route-leave and browser-close protection for dirty onboarding, profile, email, CV preview, and story editing states.

### 8A-7. Visual language and copy review

#### Colour and theme

- Use semantic variables directly in every component.
- Remove hard-coded indigo as a second pseudo-accent.
- Do not use success green for a high score unless success is the actual meaning.
- Test all status combinations in light and dark modes.
- Update `theme-color` with the active theme rather than keeping one fixed teal value.
- Remove catch-all dark-mode remapping after component migration because it can silently alter unrelated utilities.

#### Type and hierarchy

- Keep Inter/system sans as the product face for consistency with the existing design-system document.
- Use Roboto Mono only for aligned counts, timestamps, IDs, and metrics.
- Retire isolated Newsreader use from onboarding progress unless Hatch adopts it as an approved brand display face.
- Use sentence case throughout.
- Keep 12px as the minimum non-essential label and 16px for mobile form inputs.
- Use balanced wrapping for page and empty-state headings.

#### Iconography

- Use Lucide consistently because it is already installed and dominant.
- Keep one stroke weight within each control group.
- Replace text glyph close buttons such as `✕` and multiplication-sign tag removals with the standard close icon.
- Decorative icons need `aria-hidden="true"`.
- Agent identity requires icon + agent name; colour alone is insufficient.
- Reserve dots for real status only. Remove decorative dots from section labels and save bars.

#### Shape and elevation

- Cards/dialogs: 12px.
- Inputs/buttons: 8px.
- Pills: status, compact filters, tags, and toggles only.
- Avoid shadows on dark surfaces. Use border and surface contrast.
- Do not wrap every metric in a card; use grouped regions and dividers for dense analytics.

#### Copy and naming

- Replace duplicate labels according to the canonical route map.
- Use specific outcome labels: “Save Profile”, “Install Models”, “Apply AI Configuration”, “Send Email”.
- Replace raw implementation errors with a plain summary and expandable technical detail.
- Remove decorative numbering from user-facing headings where the actual task name is sufficient.
- Avoid em-dash and en-dash separators in user-facing UI; use sentences, commas, line breaks, or regular hyphens.
- Limit middle-dot separators to one per metadata line.

### 8A-8. Responsive and accessibility verification matrix

Test each screen at 375px, 768px, 1024px, and 1440px, in light and dark themes.

| Check | Required outcome |
|---|---|
| Keyboard | Every action reachable; visible focus; logical order; no shell focus behind onboarding/dialogs |
| Dialogs | Focus enters, stays inside, and returns; Escape policy is consistent; background is inert |
| Zoom | 200% text zoom produces no horizontal page scroll and no clipped primary action |
| Mobile navigation | Labels do not overlap; safe-area inset is reserved; final content is not covered |
| Tables/Kanban | Usable card or scroll model with an explicit affordance; keyboard alternative to drag |
| Forms | 16px inputs; labels persist; errors are associated and first error receives focus |
| Themes | Text, borders, controls, charts, focus rings, and native inputs pass contrast in both modes |
| Motion | Reduced-motion removes non-essential animation; running status remains understandable without motion |
| Loading | Layout-shaped skeleton or compact labelled progress; no unexplained full-page spinner |
| Empty/error | One primary next action, optional secondary help/settings link, retry where recoverable |
| Content stress | Long job/company names, long errors, empty strings, 99+ counts, and translated text do not break layout |
| Landmarks | One main landmark, one H1, skip link, correct heading sequence |

### 8A-9. Recommended delivery sequence

Deliver the remediation through the small pull requests (PRs) defined in section 9. Each PR must leave the application deployable, include tests for its changed behaviour, and avoid opportunistic work from a later PR.

Do not begin with cosmetic per-page edits. Without the foundation and route decisions, visual work will be duplicated and inconsistencies will return.


## 9. Implementation PR plan

This plan favours reviewable contracts over one large visual rewrite. Implement and merge PRs in order unless a PR explicitly allows parallel work. Start each PR from the latest merged target branch.

### 9.1 PR status ledger

Update this table in the same commit that completes each PR. Record the branch, final commit, validation results, and any deferred work in the PR handoff. Because `docs/*` is ignored in this repository, use `git add -f docs/hatch_ux_gap_review_codex_spec.md` when this file changes.

| PR | Scope | Depends on | Status | Branch / commit | Handoff notes |
|---|---|---|---|---|---|
| PR 1 | Product vocabulary and route contract | None | Merged | `ux/01-route-contract` / `033ed49` | Merged as GitHub PR #5 |
| PR 2 | Shared page and control foundation | PR 1 | Merged | `ux/02-ui-foundation` / `e8bebd7` | Merged as GitHub PR #6 |
| PR 3 | Accessible overlay primitives | PR 2 | Merged | `ux/03-overlay-primitives` / `3e3533a` | Merged as GitHub PR #7 |
| PR 4 | App-lock security and recovery | PR 2, PR 3 | In progress | `ux/04-app-lock-security` / `82db518` | Implementation validated; PR review and merge pending |
| PR 5 | Onboarding privacy and flow | PR 2, PR 3 | Not started | `ux/05-onboarding` | |
| PR 6 | Settings shell and Profile | PR 2, PR 3 | Not started | `ux/06-settings-profile` | |
| PR 7 | AI Provider, Master CV, and Diagnostics | PR 6 | Not started | `ux/07-settings-tools` | |
| PR 8 | Core job-search screens | PR 1 to PR 3 | Not started | `ux/08-core-screens` | |
| PR 9 | Prep, Coach, and secondary screens | PR 1 to PR 3 | Not started | `ux/09-secondary-screens` | |
| PR 10 | Cross-app verification and cleanup | PR 4 to PR 9 | Not started | `ux/10-verification-cleanup` | |

Allowed status values are `Not started`, `In progress`, `Blocked`, and `Merged`. Do not mark a PR `Merged` until its remote PR has merged.

### 9.2 Rules for every PR

Each PR must satisfy these rules:

1. Change only its listed scope and the tests or documentation needed to prove that scope.
2. Keep routes and stored data backward compatible unless the PR documents a migration or redirect.
3. Run targeted tests during development, then run frontend type-checking, relevant unit/component tests, and `git diff --check` before review.
4. Add Playwright coverage when the PR changes a user journey, focus behaviour, navigation, or responsive layout.
5. Include light and dark screenshots at 375px and 1440px for each changed visual surface.
6. Record skipped checks, known failures, and pre-existing warnings in the PR description.
7. Update the status ledger and the PR handoff before ending the implementation session.
8. Stop after opening or preparing the current PR. Do not begin the next PR in the same branch.

Use this PR description structure:

```text
## Goal
State the user-visible outcome.

## Scope
List the screens, components, routes, and backend endpoints changed.

## Deliberately excluded
List work reserved for later PRs.

## Validation
List each command and its result. Link visual evidence when applicable.

## Resume handoff
Record the final commit, unresolved items, relevant decisions, and the next PR.
```

### 9.3 PR 1: Lock product vocabulary and route ownership

**Goal:** Establish one canonical name and owner for every overlapping route before changing shared UI.

**Approved route contract:**

| Capability | Canonical route | Canonical label | Purpose |
|---|---|---|---|
| Job discovery | `/jobs` | Jobs | Review discovered roles and choose which opportunities to pursue |
| Automated preparation | `/stream` | Pipeline | Monitor roles while Hatch scores, tailors, and prepares them |
| Application tracking | `/tracker` | Applications | Track submitted and active applications through each outcome |
| Preparation library | `/prep` | Interview Prep | Create preparation plans and review interview sessions |
| Live practice | `/coach` | Interview Coach | Practise interviews and manage reusable interview stories |

**Migration rule:** `/applications` is a retired duplicate of the Applications Kanban experience. Redirect it to `/tracker` and preserve all query keys, repeated values, empty values, and encoded values. Keep backend `/api/applications` routes unchanged. Existing `/stream`, `/tracker`, `/prep`, and `/coach` bookmarks remain valid.

**Included:**

- Decide the canonical purpose and label for Jobs, Pipeline, Applications, Interview Prep, and Coach
- Define redirects or retirement rules for `/stream`, `/tracker`, `/applications`, `/prep`, and `/coach`
- Align route labels in desktop navigation, mobile navigation, command palette, breadcrumbs, and page metadata
- Add route-contract tests for canonical destinations and redirects
- Record migration notes for bookmarks and internal links

**Excluded:**

- Page restyling
- Dialog migration
- Settings restructuring
- Removal of legacy components that still have consumers

**Acceptance criteria:**

- Each capability has one name across every navigation surface
- Every retained route has a distinct documented purpose
- Every retired route redirects without losing meaningful query parameters
- Direct URL navigation and browser back/forward behaviour pass

This PR is a decision gate. Do not start PR 2 until route ownership has review approval.

**PR 1 resume handoff:**

- The route contract lives in `frontend/product-routes.json`; frontend components consume it through `frontend/src/lib/product-routes.ts`
- Next.js redirects `/applications` to `/tracker` before React renders and preserves the complete query string
- Navigation, command palette, top bar, internal links, and per-route metadata use the canonical labels
- Validation passed: 388 Vitest tests, TypeScript type-check, production build, route-contract Playwright test, and diff whitespace checks
- Visual checks cover navigation, command palette, and Interview Coach at 375px and 1440px in light and dark themes
- Existing warnings remain in `AnswerTimer`, `OnboardingPrimitives`, React test `act(...)` handling, and the FaceCapture test environment
- Visual review found a pre-existing mobile Interview Coach empty-state overflow; defer it to PR 9
- Do not start PR 2 until PR 1 has review approval and is marked `Merged`

### 9.4 PR 2: Establish the shared page and control foundation

**Goal:** Give later screen migrations one stable visual and semantic contract.

**Included:**

- Establish one page-header owner and remove duplicate H1 rendering
- Ensure the application shell owns one `main` landmark and provides a skip link
- Consolidate Button, form-field, icon, page-container, section-card, and status treatments
- Adopt Lucide as the application icon family
- Lock semantic colour, typography, radius, spacing, focus, and motion tokens
- Add component examples or tests for supported variants

**Excluded:**

- Broad per-screen conversion
- Overlay implementation
- Route retirement
- Settings information architecture

**Acceptance criteria:**

- Shared examples render in light and dark themes
- Button and field states cover default, hover, focus, disabled, loading, error, and destructive use
- Pages can render one H1 and one `main` without route-specific exceptions
- New shared controls meet the 44px mobile target and visible-focus requirements

**PR 2 resume handoff:**

- Shared primitives now include Button, Input, FormField, Icon, PageContainer, PageHeader, SectionCard, and StatusBadge
- Semantic radius, focus, motion, control-height, and foreground-on-status tokens live in `frontend/src/app/globals.css`; legacy radius names remain as compatibility aliases
- Lucide renders every Hatch string icon through a compatibility adapter; no hand-drawn paths remain in `HatchIcon`
- The route owns its H1, while the desktop top bar contains utility context only
- `AppLockGate` owns the single runtime `main` landmark and the first content control is a skip link
- Route-level nested `main` elements were replaced without changing their layout classes
- The old `Btn` API delegates to the shared Button while later screen PRs migrate call sites
- Newsreader was removed; onboarding inherits the approved sans type family
- Validation passed: 394 Vitest tests, TypeScript type-check, production build, four Playwright landmark/skip-link tests, and diff whitespace checks
- Visual checks cover Today and Jobs at 375px and 1440px in light and dark themes
- Existing build warnings remain in `AnswerTimer` and `OnboardingPrimitives`; existing test warnings remain in asynchronous component tests and FaceCapture
- Keep the dark-mode catch-all compatibility layer until later screen migrations replace hard-coded utilities
- Do not start PR 3 until PR 2 has review approval and is marked `Merged`

### 9.5 PR 3: Add accessible overlay primitives

**Goal:** Replace fragmented modal mechanics with tested Dialog, Alert Dialog, Sheet, and Popover contracts.

**Included:**

- Add shared overlay wrappers with title, description, action, close, and size APIs
- Implement focus entry, focus trap, focus return, Escape policy, scroll lock, and inert background behaviour
- Migrate command palette, notifications, user menu, job import, application detail, review overlay, consent gate, email preview, and session launcher
- Replace browser confirmation calls in migrated surfaces
- Add component and Playwright keyboard tests

**Excluded:**

- Password-policy changes
- Onboarding validation
- Settings content restructuring
- Visual redesign of content inside an overlay beyond shared spacing and actions

**Acceptance criteria:**

- Every migrated overlay has an accessible name and description where required
- Nested overlay behaviour is either supported and tested or prevented by design
- Keyboard focus returns to the invoking control
- Destructive confirmation requires an explicit labelled action

Split this PR if migration exceeds the review limit: PR 3A adds and proves primitives on one low-risk surface; PR 3B migrates the remaining inventory without changing the API.

**PR 3 resume handoff:**

- Shared Radix-backed Dialog, Alert Dialog, Sheet, and Popover wrappers now own naming, close controls, responsive sizing, focus trapping and return, Escape/outside-click policy, scroll locking, and inert backgrounds
- Busy review, import, email, consent, and session-generation flows prevent accidental dismissal while work is in progress
- Command palette, notification bell, user menu, job URL import, application detail, review queue, consent gate, email preview, Coach and Prep launchers, add-application flow, stage movement, Prep deletion, and Profile learning reset use the shared contracts
- Browser `confirm` and `alert` calls in migrated surfaces were replaced by labelled Alert Dialogs or inline recoverable notices
- Nested sheet/dialog behaviour is explicitly covered: closing the child restores focus inside the still-active parent
- Validation passed: 400 Vitest tests, TypeScript type-check, production build, one Playwright Escape/focus-return test, and diff whitespace checks
- Visual checks cover the shared user-menu popover at 375px and 1440px in light and dark themes
- Existing build warnings remain in `AnswerTimer` and `OnboardingPrimitives`; existing test warnings remain in asynchronous component tests and FaceCapture
- Do not start PR 4 until PR 3 has review approval and is marked `Merged`

### 9.6 PR 4: Harden app-lock security and recovery

**Goal:** Make password setup, unlock, change, and recovery behaviour consistent across frontend and backend.

**Included:**

- Add one shared password-policy definition with frontend and backend parity
- Add password reveal controls and a live requirement checklist
- Apply policy to first-run setup and Security settings
- Clarify local lock state, failed attempts, recovery, and reset consequences
- Add inline validation and announced success/error states
- Test setup, unlock, change-password, mismatch, weak-password, and recovery paths

**Excluded:**

- Onboarding data persistence
- Other Settings pages
- General form migration outside app-lock flows

**Acceptance criteria:**

- Backend endpoints reject every password the frontend rejects
- Existing valid installations continue to unlock
- Recovery copy states which local data is preserved or removed
- No secret or password enters logs, analytics, browser persistence, or error detail

**PR 4 resume handoff:**

- The backend owns one app-lock password policy and publishes it through lock status: 12-128 characters, at least one letter and number, and no leading or trailing whitespace
- First-run setup and Security settings validate against the published policy, show live requirements, support reveal/hide, link errors to fields, and keep submit disabled until valid
- Unlock remains backward compatible with existing shorter passwords; the stronger policy applies only to setup and password change
- Password changes reject reuse of the current password, clear other sessions, and announce inline success or errors without persisting or logging secrets
- First-run, unlock, environment-managed, failed-attempt, slow-backend, and verification-error states now explain the local security boundary and keep protected content hidden
- Recovery guidance documents `bash scripts/reset-app-lock.sh`, states that the password and sessions are removed, and confirms jobs, profile, CVs, and application data are preserved
- Validation passed: 18 focused backend tests, focused backend Ruff checks, 414 frontend Vitest tests, TypeScript type-check, production build, two Playwright app-lock tests, and diff whitespace checks
- Visual checks cover first-run setup and Security settings at 375px and 1440px in light and dark themes
- Existing build warnings remain in `AnswerTimer` and `OnboardingPrimitives`; existing test warnings remain in asynchronous component tests and FaceCapture
- The repository-wide backend lint command still reports pre-existing errors in unrelated services and tests; all PR 4 backend files pass Ruff
- Do not start PR 5 until PR 4 has review approval and is marked `Merged`

### 9.7 PR 5: Isolate onboarding and protect draft data

**Goal:** Make onboarding a private, keyboard-complete flow with explicit review before save.

**Included:**

- Render onboarding in a dedicated layout that makes the application shell inert or unmounted
- Remove sensitive fields from browser persistence, or implement the approved explicit-persistence option
- Add field and step validation for every onboarding step
- Add review-before-save, skipped-field warnings, save progress, failure recovery, and success transition
- Add dirty-navigation protection
- Test keyboard completion, refresh behaviour, mobile layout, and persistence exclusions

**Excluded:**

- App-lock policy
- Profile page restructuring
- Core-screen setup checklist

**Acceptance criteria:**

- Assistive technology cannot reach the app shell during onboarding
- Stored drafts match the privacy copy exactly
- A failed final save preserves safe user input and offers retry
- Completion creates no duplicate records after retry

### 9.8 PR 6: Add the Settings shell and split Profile

**Goal:** Give Settings predictable navigation, form behaviour, and ownership boundaries.

**Included:**

- Add persistent desktop and mobile Settings navigation
- Split identity/profile content from Job Preferences
- Add shared section cards, field composition, save bar, dirty state, save/error feedback, and route-leave protection
- Remove duplicate AI Provider controls from Profile
- Apply responsive compensation, skills, target-role, and preference layouts
- Test active navigation, validation, dirty state, save, discard, and mobile footer clearance

**Excluded:**

- AI Provider workflow changes
- Master CV workflow changes
- Diagnostics safety changes
- Application-wide form migration

**Acceptance criteria:**

- Every Settings page has one title, one purpose sentence, and visible active navigation
- Profile and Job Preferences save only their owned fields
- Validation focuses the first invalid field
- Sticky actions never cover content or mobile navigation

### 9.9 PR 7: Clarify AI Provider, Master CV, and Diagnostics

**Goal:** Make advanced Settings actions explicit, safe, and consistent with the shell from PR 6.

**Included:**

- Separate AI choice, save, install, apply, restart, and effective-routing states
- Add a five-state Master CV upload, parse, preview, confirm, and failure flow
- Require confirmation before replacing the current Master CV
- Rename System Logs to Diagnostics and add privacy framing, masking, pause, export, retry, and clear confirmation
- Add responsive table/card treatments for diagnostic data
- Test file constraints, replacement, command copy, masking, pause, export, retry, and destructive confirmation

**Excluded:**

- Changes to model-selection algorithms
- Host-secret collection in the browser
- Backend logging expansion
- Core-screen visual polish

**Acceptance criteria:**

- AI actions state whether they save configuration or alter runtime state
- Master CV failure never discards the current accepted CV
- Diagnostics masks sensitive values by default
- Clear and export actions identify their scope before execution

### 9.10 PR 8: Align the core job-search screens

**Goal:** Apply the approved foundation to the daily job-search journey.

**Included:**

- Migrate Today, Jobs, Pipeline, Applications, and CV Studio
- Standardise page headers, action hierarchy, filters, loading, empty, error, and success states
- Preserve filter state in URLs where specified
- Add keyboard alternatives for moving applications
- Add Today setup checklist and trust/status copy only when backed by real state
- Test route labels, filters, empty actions, application movement, and responsive layouts

**Excluded:**

- Prep and Coach
- Analytics and operational screens
- New job-search features or scoring changes

**Acceptance criteria:**

- Each screen uses the canonical vocabulary from PR 1
- Each empty or recoverable error state offers a relevant next action
- Dense layouts work at 375px, 768px, 1024px, and 1440px
- Status animation appears only for confirmed active work

Split this PR by journey if the diff becomes difficult to review: PR 8A covers Today and Jobs; PR 8B covers Pipeline and Applications; PR 8C covers CV Studio. Keep the listed order.

### 9.11 PR 9: Align Prep, Coach, and secondary screens

**Goal:** Complete visual and behavioural consistency outside the core job-search journey.

**Included:**

- Clarify the relationship between Interview Prep and Coach
- Migrate Prep, Coach session/report/stories, Analytics, Calendar, Agents, Approvals, and detail views
- Apply shared loading, empty, error, metadata, status, action, and responsive patterns
- Add timestamps and evidence to operational agent states
- Test destructive actions, retries, long-content stress, and mobile density

**Excluded:**

- New coaching, analytics, calendar, or agent capabilities
- Changes to scoring or approval policy
- Cleanup reserved for PR 10

**Acceptance criteria:**

- Prep and Coach explain their distinct purposes
- Detail routes share breadcrumb, title, metadata, action, and back-navigation patterns
- Operational states distinguish running, idle, stale, failed, and unknown
- Charts and statuses use semantic colours in both themes

Split this PR by subsystem if needed: PR 9A covers Prep and Coach; PR 9B covers Analytics and Calendar; PR 9C covers Agents, Approvals, and details.

### 9.12 PR 10: Verify the complete experience and retire legacy UI

**Goal:** Prove the integrated remediation and remove only the code made obsolete by merged migrations.

**Included:**

- Run the authenticated visual regression matrix from section 11
- Add or finish keyboard, accessibility, reduced-motion, 200% zoom, and content-stress coverage
- Verify one H1 and one `main` per protected route
- Remove confirmed-unused legacy navigation, icon, button, overlay, and style code
- Resolve temporary compatibility adapters introduced by earlier PRs
- Update final documentation and status ledger

**Excluded:**

- New product features
- Cosmetic changes without a failed acceptance check
- Refactors unrelated to migrated UI

**Acceptance criteria:**

- All section 11 checks pass, or the PR documents a bounded follow-up with owner and reason
- No retired component has a runtime or test import
- No browser `alert` or `confirm` remains in user-facing flows
- The production build completes without new warnings
- Every ledger entry records its merged commit and handoff

### 9.13 Resume protocol

When a Codex session starts or resumes:

1. Read this specification and the latest remote PR state.
2. Inspect the status ledger.
3. Confirm the branch contains only the active PR scope.
4. Read the active PR description and its `Resume handoff`.
5. Run the smallest relevant validation before editing.
6. Continue the first `In progress` PR. If none exists, start the first `Not started` PR whose dependencies are `Merged`.
7. Update the ledger and handoff before the session ends, even when the PR remains incomplete.

If token budget becomes constrained, stop after a coherent commit. Record the exact failing test, unfinished file, next edit, and command needed to resume. Do not mix work from the next PR into the emergency handoff commit.

---

## 10. Suggested file changes

### New files

- `frontend/src/lib/passwordPolicy.ts`
- `frontend/src/lib/profileValidation.ts`
- `frontend/src/components/security/PasswordField.tsx`
- `frontend/src/components/security/PasswordRequirementList.tsx`
- `frontend/src/components/ui/dialog.tsx`
- `frontend/src/components/ui/confirm-dialog.tsx`
- `frontend/src/components/settings/SettingsShell.tsx`
- `frontend/src/components/settings/SettingsSaveBar.tsx`
- `frontend/src/components/settings/SectionCard.tsx`
- `frontend/src/components/ui/sheet.tsx`
- `frontend/src/components/ui/alert-dialog.tsx`
- `frontend/src/components/ui/popover.tsx`
- `frontend/src/components/ui/form-field.tsx`
- `frontend/src/components/ui/settings-nav.tsx`

### Modify

- `frontend/src/app/unlock/page.tsx`
- `frontend/src/app/onboarding/page.tsx`
- `frontend/src/components/OnboardingGate.tsx`
- `frontend/src/components/AppLockGate.tsx`
- `frontend/src/app/settings/profile/page.tsx`
- `frontend/src/app/settings/ai/page.tsx`
- `frontend/src/app/settings/resume/page.tsx`
- `frontend/src/app/settings/security/page.tsx`
- `frontend/src/app/settings/system/page.tsx`
- `frontend/src/components/CommandPalette.tsx`
- `frontend/src/components/EmailPreviewModal.tsx`
- `frontend/src/components/jobs/JobUrlImportModal.tsx`
- `frontend/src/components/ApplicationDetail.tsx`
- `frontend/src/components/coach/ConsentGate.tsx`
- `frontend/src/components/hatch/ReviewOverlay.tsx`
- `frontend/src/components/hatch/screens/TrackerScreen.tsx`
- `frontend/src/components/hatch/HatchTopBar.tsx`
- `frontend/src/components/hatch/HatchTopBarSlot.tsx`
- `frontend/src/components/hatch/HatchNav.tsx`
- `frontend/src/components/hatch/HatchSidebar.tsx`
- `frontend/src/components/hatch/UserMenu.tsx`
- `frontend/src/components/NotificationBell.tsx`
- `frontend/src/components/ThemeToggle.tsx`
- Existing nav/shell components where user-facing route names are displayed.

### Retire after migration

- `frontend/src/components/hatch/HatchIcon.tsx`
- `frontend/src/components/hatch/Btn.tsx`
- `frontend/src/components/Sidebar.tsx` if confirmed unused.
- `frontend/src/components/BottomNav.tsx` if confirmed unused.

### Backend files

Codex should locate the backend app-lock setup/change endpoints and add equivalent password validation. Do not rely on frontend validation only.

---

## 11. Test plan

### Unit tests

Add tests for:

- Password policy validation.
- Password checklist state.
- Profile validation schema.
- Onboarding localStorage persistence excluding sensitive fields.
- File upload validation for extension, MIME, and size.

### Component tests

Add tests for:

- Password field reveal/hide.
- Requirement checklist updates as user types.
- Confirm dialog focus and action behaviour.
- Tag input dedupe.
- Settings save bar dirty/clean states.

### Playwright tests

Add or update E2E tests for:

1. First-run app-lock setup rejects weak passwords and accepts valid passwords.
2. Unlock screen can unlock with configured password.
3. Security settings password change rejects weak passwords and mismatch.
4. Onboarding cannot finish with invalid pay range.
5. Onboarding final review shows skipped warnings.
6. Master CV upload rejects files over 10 MB.
7. Email Preview modal traps focus and validates recipient email.
8. System Logs clear traces requires confirmation.
9. Command palette opens with Ctrl+K, navigates, and returns focus after close.
10. Mobile viewport checks for Settings Profile, System Logs, and Email Preview modal.
11. Every protected route renders exactly one `<h1>` and one `main` landmark.
12. Onboarding makes the underlying app shell inert and unreachable.
13. Canonical route labels match sidebar, mobile navigation, top bar/breadcrumb, command palette, and page heading.
14. Settings navigation keeps the active item visible at desktop and mobile widths.
15. All dialogs, sheets, menus, and popovers return focus to their trigger.
16. Applications can be moved between stages using keyboard controls without drag.

### Visual regression matrix

Capture authenticated screenshots for:

- Today, Jobs, Pipeline, Applications, CV Studio, Interview Prep, and Coach.
- Analytics, Calendar, Agents, and Approvals.
- Profile, Job Preferences, AI Provider, Master CV, Security, and Diagnostics.
- Unlock, first-run password setup, every onboarding step, review, and success.
- Command palette, notifications, user menu, job import, application detail, review queue, email preview, consent, session launcher, and destructive confirmation.

Required combinations:

- 375px dark.
- 375px light.
- 768px dark.
- 1024px light.
- 1440px dark.
- One 200% text-zoom run for each page template.

### Accessibility checks

At minimum:

- All dialogs have accessible names.
- All form inputs have labels.
- All inline errors are linked to inputs.
- Keyboard-only user can complete onboarding and password change.
- Status messages are announced.

---

## 12. Done definition

This UX remediation is done when:

- P0 issues are fully fixed and tested.
- P1 issues are either fixed or explicitly split into separate follow-up tickets with no security/privacy ambiguity remaining.
- Password policy is enforced on both frontend and backend.
- Onboarding localStorage behaviour matches user-facing copy.
- Dialog/modal pattern is centralised and accessible.
- Settings screens have consistent save, error, destructive confirmation, and helper-text patterns.
- Major screens have empty/loading/error states.
- Playwright smoke tests pass for desktop and mobile widths.

---

## 13. Codex prompt

Use the following prompt with Codex:

```text
You are working in the Hatch repository.

Implement the UX remediation spec in docs/hatch_ux_gap_review_codex_spec.md.

Implement only the first eligible PR in the section 9 status ledger. A PR is eligible when all its dependencies are marked Merged. If one PR is already In progress, resume it instead of starting another.

Requirements:
- Keep Hatch local-first/privacy-first positioning clear in copy.
- Enforce password policy on both frontend and backend.
- Do not rely on frontend-only validation for security decisions.
- Do not introduce new paid SaaS dependencies.
- Use existing design tokens/components where possible.
- Replace browser confirm dialogs with shared app-native confirmation dialog.
- Add/update unit, component, and Playwright tests listed in the spec.
- Avoid broad unrelated refactors.
- Keep later PR work out of the active branch.
- Run the active PR's acceptance checks and the shared per-PR checks.
- Update the status ledger and Resume handoff before ending the session.
- Stop after opening or preparing the active PR. Do not start the next PR.

Before coding, inspect the latest remote state, active branch, status ledger, and relevant frontend/backend paths. If the active PR contains a decision gate, document the decision and obtain review approval before starting its dependent PR.
```
