---
title: Hatch — Security, UX/Feature & Hardcoding Audit
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

# Hatch — Security, UX/Feature & Hardcoding Audit

**Date:** 2026-06-10 (rev 2 — added Part 4: default local LLM model refresh)
**Repo:** https://github.com/arvindsoni2/hatch (commit `4d208ab`)
**Author:** Audit pass for Arvind Soni
**Status:** Ready for Claude Code implementation
**Scope:** (1) Security audit, (2) UX/feature review + trend-based refinement, (3) hardcoding removal, (4) default local LLM models for CPU-only consumer hardware

---

## How to use this spec

Four parts, each independently shippable. **Do Part 1 (security) first** — several items are
load-bearing for a self-hosted app that may be reachable beyond localhost. Part 4 (model defaults)
is small and can be slotted in anywhere after Part 1. Each task follows the
repo's TDD convention: write the test first, watch it fail, implement, watch it pass. Commit
messages and exit criteria are given per task. Open questions are flagged, not assumed away.

**Guardrail that must not regress:** `test_no_autonomous_submission` and the "no autonomous submission — ever"
principle are sacrosanct. Nothing in this spec touches the assisted-apply boundary.

---

# Part 1 — Security Audit

## Threat model note (read first)

Hatch ships bound to `127.0.0.1` in both `docker-compose.yml` and the systemd unit, and is documented
as single-user self-hosted. That is the mitigating control for most findings below. **But** two things
make the "localhost-only" assumption fragile:

1. Users put this behind a reverse proxy / tailscale / port-forward to reach it from a phone (the PWA
   and `submit-audio` endpoint strongly imply mobile use). The moment that happens, every endpoint is
   exposed with **zero authentication**.
2. CORS is set to `allow_credentials=True` with localhost origins, so a malicious page open in the
   same browser can drive the whole API via the user's machine.

The findings are ranked assuming a realistic deployment, not the ideal one.

---

### SEC-1 — [CRITICAL] No authentication on any endpoint

**Finding:** No router has any auth dependency. `grep` for `Depends(...auth)`, `verify_token`,
`Authorization` returns nothing. Every endpoint — including `PUT /api/v2/settings/env` (writes API
keys to disk), `/api/debug/llm-traces` (leaks prompt/response content), profile read/write, and all
document downloads — is open to anyone who can reach the port.

**Why it matters:** The single most damaging endpoint is `PUT /api/v2/settings/env`: an unauthenticated
caller can overwrite the user's LLM provider key and redirect spend, or read `GET /api/v2/settings/env/status`
to enumerate which providers are configured. Combined with the CORS finding (SEC-2), a drive-by webpage
can hit these.

**Fix — opt-in shared-secret middleware (keeps localhost UX frictionless):**

- [ ] Add `HATCH_AUTH_TOKEN: str = ""` to `config.py`. When empty (default), auth is **disabled** —
      preserves the zero-config localhost experience.
- [ ] Add an `AuthMiddleware` (Starlette `BaseHTTPMiddleware`) in `main.py` that, **only when the token
      is non-empty**, requires `Authorization: Bearer <token>` on every `/api/*` route except
      `/api/health`. Reject with 401 otherwise.
- [ ] Exempt `OPTIONS` (CORS preflight) and `/docs`, `/openapi.json` in non-debug? No — gate `/docs`
      too when a token is set.
- [ ] Frontend: read token from `process.env.HATCH_AUTH_TOKEN` server-side and inject it into the
      Next.js rewrite/proxy layer so the browser never holds it. Document the env var in
      `.env.example` and README "Exposing beyond localhost" section.
- [ ] Test (`backend/tests/test_middleware/test_auth.py`):
  - token unset → request without header returns 200 (default behaviour preserved)
  - token set + no header → 401
  - token set + correct bearer → 200
  - `/api/health` always reachable

**Commit:** `feat(security): optional bearer-token auth middleware for non-localhost deploys`

**Open question:** Bearer token vs. signed-cookie session. Bearer is simpler for a single-user PWA and
avoids CSRF entirely if we also tighten CORS (SEC-2). Recommending bearer. Flag if you want sessions.

---

### SEC-2 — [HIGH] CORS allows credentials with overly trusting defaults

**Finding (`main.py`):** `allow_credentials=True` with `allow_methods` including all mutating verbs.
Origins default to localhost (good), but `allow_credentials=True` + a permissive origin list is the
classic combination that lets a logged-in browser context be driven cross-origin. There is currently
no auth, so "credentials" is moot today — but once SEC-1 lands, this becomes the CSRF surface.

**Fix:**

- [ ] Since the API will use a bearer token (not cookies) once SEC-1 lands, set
      `allow_credentials=False`. Bearer tokens in an `Authorization` header are not auto-sent
      cross-origin, which closes CSRF without extra machinery.
- [ ] Keep the explicit origin allowlist from `ALLOWED_ORIGINS`. Never fall back to `["*"]`.
- [ ] Add a startup `logger.warning` if `ALLOWED_ORIGINS` contains `*` or if the bind appears
      non-loopback while `HATCH_AUTH_TOKEN` is empty.
- [ ] Test: assert the configured middleware has `allow_credentials=False` and that a wildcard origin
      env value is rejected/warned.

**Commit:** `fix(security): drop credentialed CORS in favour of bearer auth; warn on unsafe config`

---

### SEC-3 — [HIGH] Path traversal in `POST /sessions/{session_id}/submit-audio`

**Finding (`routers/coach.py` ~L275):**

```python
suffix = Path(audio.filename or "answer.webm").suffix or ".audio"
recordings_dir = Path(os.getenv("DATA_DIR", "./data")) / "recordings" / session_id
audio_path = recordings_dir / f"{question_id}{suffix}"
audio_path.write_bytes(audio_bytes)
```

`session_id` (path param) and `question_id` (form field) are attacker-controlled and flow directly
into a filesystem path. A `question_id` of `../../config/master_profile` or a crafted `session_id`
escapes the recordings directory and writes arbitrary files inside the container (overwriting
`profile.yaml`, the SQLite DB, or `api_keys.env`). The `suffix` is also taken from the uploaded
filename. The CV/CL docx builders already do `startswith(expected_parent)` traversal checks — this
endpoint does not.

**Fix:**

- [ ] Validate `session_id` and `question_id` against a strict allowlist regex (e.g. `^[A-Za-z0-9_-]+$`)
      before any path construction; 400 on mismatch. These IDs are server-generated UUIDs/slugs, so this
      is non-breaking.
- [ ] Derive `suffix` from the **content-type** (map `audio/webm`→`.webm`, `audio/wav`→`.wav`,
      `audio/mp4`→`.m4a`, default `.audio`) rather than the user filename.
- [ ] After building `audio_path`, resolve it and assert
      `audio_path.resolve().is_relative_to(recordings_dir.resolve())` — mirror the docx builder pattern.
- [ ] Test (`test_coach_router.py`): `question_id="../../etc/x"` and `session_id="../foo"` both return
      400 and write nothing outside `data/recordings/`.

**Commit:** `fix(security): prevent path traversal in coach submit-audio upload`

---

### SEC-4 — [HIGH] PII committed to the repository

**Finding:** `backend/app/config/master_profile.yaml` is tracked by git and contains the user's real
name, location, day-rate band (£550–700/day, outside IR35), employer-specific proof points
(Northern Powergrid £500K savings, Natoora), and domain history. `.gitignore` now exists (an earlier
spec's finding) but this file predates it and remains committed. Anyone cloning the public repo gets
the maintainer's full professional profile and rate expectations.

**Fix:**

- [ ] Rename the tracked file to `master_profile.example.yaml` with **placeholder** values
      ("Your Name", "Your City", generic skills).
- [ ] `config/__init__.py` `load_master_profile()` should load `master_profile.yaml` if present, else
      fall back to the example. Add `master_profile.yaml` to `.gitignore`.
- [ ] `git rm --cached backend/app/config/master_profile.yaml` and document in the commit that existing
      forks should rotate/scrub. (Note: history still contains it — call this out so the user can decide
      whether a history rewrite is worth it for a portfolio repo.)
- [ ] Test: app boots with only the example file present.

**Commit:** `fix(security): de-PII master profile; ship example template, gitignore real profile`

---

### SEC-5 — [MEDIUM] Debug endpoints leak LLM content and are unauthenticated

**Finding:** `/api/debug/llm-traces` returns the last 100 LLM calls including response previews; it is
always mounted (`main.py` includes `debug_router` unconditionally) regardless of `LOG_LEVEL`. Prompts
in this app contain the full CV and job descriptions — i.e. PII.

**Fix:**

- [ ] Mount `debug_router` only when `LOG_LEVEL == "DEBUG"` (same gate already used for `/redoc`).
- [ ] Ensure trace previews are length-capped and never include raw API keys.
- [ ] Test: with `LOG_LEVEL=INFO`, `GET /api/debug/llm-traces` returns 404.

**Commit:** `fix(security): gate debug LLM-trace endpoints behind DEBUG log level`

---

### SEC-6 — [MEDIUM] No Content-Security-Policy; inline bootstrap script

**Finding:** `SecurityHeadersMiddleware` sets `X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy` — good — but no `Content-Security-Policy` and no `Strict-Transport-Security`. The
root layout injects an inline `<script dangerouslySetInnerHTML>` for the theme flash-prevention trick,
which any future CSP must accommodate (via nonce or hash).

**Fix:**

- [ ] Add a `Content-Security-Policy` to the middleware: `default-src 'self'`,
      `connect-src 'self'` (+ the API origin), `img-src 'self' data:`, `style-src 'self' 'unsafe-inline'`
      (Tailwind), and a **nonce** for the single inline theme script rather than `'unsafe-inline'` on
      `script-src`.
- [ ] Refactor the layout theme script to use a Next.js nonce (or move to a hashed external script) so
      `script-src` can stay strict.
- [ ] Add `Strict-Transport-Security` only when served over HTTPS (behind the documented reverse proxy).
- [ ] Test: response carries a CSP header; the inline script's nonce matches.

**Commit:** `feat(security): add nonce-based CSP and HSTS headers`

**Open question:** CSP on Next.js with inline theme bootstrap is fiddly. If the nonce path is too
invasive this pass, ship a report-only CSP first (`Content-Security-Policy-Report-Only`) to validate
without breaking, then enforce. Recommending report-only → enforce in two steps.

---

### SEC-7 — [MEDIUM] No request-size / rate limits on public-ish mutating endpoints

**Finding:** LLM calls have a token-bucket limiter, but HTTP endpoints have none. `submit-audio` caps
at 50 MB but other upload/generate endpoints (tailor, profile writes) have no per-IP throttle. On a
non-localhost deploy this is a cheap DoS / cost-amplification vector (every scrape/score/tailor call
can burn paid LLM tokens).

**Fix:**

- [ ] Add `slowapi` (or a minimal in-process token bucket keyed by client host) and apply a sane
      default limit to mutating `/api/*` routes (e.g. 60/min), with generous limits since this is
      single-user.
- [ ] Make the limit configurable (`RATE_LIMIT_PER_MINUTE`, default high) and **disabled when
      `HATCH_AUTH_TOKEN` is empty** to preserve localhost dev ergonomics.
- [ ] Test: exceeding the limit returns 429.

**Commit:** `feat(security): optional per-client rate limiting on mutating endpoints`

---

### SEC-8 — [LOW] `api_keys.env` written world-readable

**Finding (`routers/settings.py`):** `_write_env_key` writes `data/api_keys.env` with default
permissions. On a shared host other users could read provider keys.

**Fix:**

- [ ] After writing, `os.chmod(_API_KEYS_FILE, 0o600)`.
- [ ] Create the parent `data/` dir with `0o700` if creating it.
- [ ] Test: file mode is `0600` after a key write.

**Commit:** `fix(security): restrict api_keys.env to owner-only permissions`

---

### SEC-9 — [LOW] Deferred dependency CVEs (tracking only)

**Finding:** `cve-report-2026-06-02.md` lists 32 backend + 14 frontend CVEs requiring major-version
bumps (langgraph 1.x, transformers 5.x, next 15.x). `requirements.txt` shows `next` already at
`14.2.35` (the patched line per the memory note), so the critical Next RCE is addressed. The remaining
items are major migrations.

**Fix (no code this pass — plan only):**

- [ ] Confirm `next` is `>=14.2.35` in `frontend/package.json` (currently `14.2.35` ✔).
- [ ] Open tracking issues for the langgraph 1.x and transformers 5.x migrations; do not attempt in
      this audit pass — they are breaking and out of scope.

**Commit:** `docs(security): refresh CVE tracking notes post-audit`

---

# Part 2 — UX / Feature Review & Trend-Based Refinement

The feature set is genuinely strong: Scout→Score→Tailor→Coach pipeline, ghost-job detection, assisted
apply with paste-maps, multimodal coach with consent-gated face analysis, PWA with offline indicator,
error boundaries per route, theme toggle. The consent gate (`ConsentGate.tsx`) already handles the
EU AI Act surface for emotion/face analysis — good. The refinements below are about polish and
catching up to current product patterns, not missing capability.

### UX-1 — [HIGH] Adopt a data-fetching/caching layer (TanStack Query)

**Finding:** Components fetch with raw `fetch()` inside `useEffect` (≈10 occurrences in `app/`, plus
component-level fetches). No caching, deduplication, background refetch, or optimistic updates. For a
dashboard that polls async jobs (the 202+poll pattern) this means manual polling loops, refetch
waterfalls, and stale UI after mutations.

**Refinement:**

- [ ] Add `@tanstack/react-query`. Wrap the app in a `QueryClientProvider`.
- [ ] Migrate the async-job polling (`/api/async-jobs/{id}`) to a `useQuery` with `refetchInterval`
      that stops when status is terminal — replaces hand-rolled polling.
- [ ] Migrate Today/Tracker/Jobs list fetches to queries with sensible `staleTime`.
- [ ] Use `useMutation` + query invalidation for approve/mark-applied so the funnel updates without a
      full reload (and add optimistic update for "Mark as applied" — instant feedback, rollback on error).
- [ ] Tests (Vitest + RTL): a mutation invalidates and refetches the affected list; polling stops on
      terminal status.

**Commit:** `feat(ui): adopt TanStack Query for caching, polling and optimistic mutations`

### UX-2 — [MEDIUM] Command palette (⌘K) for power-user navigation

**Finding:** Navigation is sidebar + bottom-nav only. For a daily-driver cockpit with Today/Tracker/
Jobs/Coach/Prep/Settings, a command palette is now table stakes (Linear, Vercel, Raycast pattern) and
suits the "review in <1 hour" power-user framing.

**Refinement:**

- [ ] Add `cmdk`. Bind ⌘K / Ctrl-K to open a palette with: jump-to-page, "trigger scout scrape",
      "open next item needing approval", "toggle theme", "search jobs".
- [ ] Ensure full keyboard operability and `aria` roles (ties into UX-4).
- [ ] Test: ⌘K opens; selecting an action routes/triggers correctly.

**Commit:** `feat(ui): add ⌘K command palette for navigation and quick actions`

### UX-3 — [MEDIUM] Skeleton loading states instead of spinners/blank

**Finding:** Only ~7 files reference skeleton/`animate-pulse`/`isLoading`. Most async views likely
flash empty or spin. Current best practice is content-shaped skeletons that match final layout to
reduce perceived latency — especially valuable here given the deliberately slow local-Ollama path
with "slow processing" UX messaging.

**Refinement:**

- [ ] Add reusable `<Skeleton>` primitives (card, row, radar-chart placeholder).
- [ ] Apply to Today cards, Tracker kanban, Jobs table, Coach evaluation/feedback while loading.
- [ ] For the long local-model coach jobs, pair the skeleton with the existing slow-processing copy so
      the wait is explained, not just animated.
- [ ] Test: a loading state renders skeletons; resolved state renders content.

**Commit:** `feat(ui): content-shaped skeleton loaders across async views`

### UX-4 — [MEDIUM] Accessibility hardening

**Finding:** Only ~19 files use `aria-*`. For an app with modals (consent gate, email preview), a
kanban with drag, radar charts, and audio/video capture, this is thin. Likely gaps: focus traps in
modals, keyboard DnD alternative for the kanban, chart text alternatives, live regions for the
async-job status changes.

**Refinement:**

- [ ] Audit modals (`ConsentGate`, `EmailPreviewModal`, approval overlay) for focus trap + Escape +
      `aria-modal`/labelledby (consent gate already has `aria-labelledby` — extend the pattern).
- [ ] Provide a keyboard-accessible way to move kanban cards between columns (buttons or menu), not
      drag-only.
- [ ] Add `aria-live="polite"` region announcing async-job transitions ("Prep ready", "Application
      prepared").
- [ ] Give `ScoreRadar` an accessible text summary of the dimensions.
- [ ] Test: modal focus is trapped and returns on close; live region announces status change.

**Commit:** `feat(a11y): focus traps, keyboard kanban, live regions, chart alt-text`

### UX-5 — [LOW] Onboarding & empty states as guided first-run

**Finding:** There's an `OnboardingGate` and `EmptyState` component, but the first-run story for a
brand-new clone (no profile, no jobs scored — which also intersects the known Phase-0 supervisor
ordering bug) deserves an explicit "you have 0 jobs because no scrape has run yet — run your first
scrape" affordance rather than a generic empty state.

**Refinement:**

- [ ] Differentiate empty states by cause: "no profile yet" → onboarding CTA; "profile set, no scrape
      yet" → "Run first scrape" button; "scraped but nothing scored" → link to scoring status (and
      surface the Phase-0 fix once landed).
- [ ] Test: each empty-state branch renders the right CTA.

**Commit:** `feat(ui): cause-specific empty states for first-run guidance`

### UX-6 — [LOW] Settings: show provider tier + cost transparency

**Finding:** `llm_factory.py` has a per-model cost table and there's a `CostTrackingCallback`. The
settings AI page knows free vs paid tier. Surfacing a running "estimated spend this week" and a clear
free-vs-paid badge per provider reinforces the cost-conscious, local-first ethos as a visible product
value, not just an internal default.

**Refinement:**

- [ ] Add a small "spend this period" readout on the AI settings page sourced from `CostTracking`.
- [ ] Badge each configured provider free/paid (data already in `_FREE_TIER_PROVIDERS`).
- [ ] Test: spend widget renders from mocked cost rows.

**Commit:** `feat(ui): surface LLM spend and free/paid tier on settings`

---

# Part 3 — Hardcoding Removal

The app advertises multi-locale support (`locales/*.yaml` for UK/India/Dubai/Ireland) but several
locale-specific values are hardcoded, which directly undercuts that selling point. These are the
highest-value de-hardcoding targets.

### HC-1 — [HIGH] Currency symbol hardcoded to `£` throughout the frontend

**Finding:** `JobCard.tsx`, `JobTable.tsx`, `FilterPanel.tsx` and coach `StoryEditor.tsx` hardcode
`£`. For an India/Dubai/Ireland user this is simply wrong (₹ / AED / €). The locale system exists but
the currency glyph never flows to the UI.

**Fix:**

- [ ] Add a `currency` field (symbol + ISO code) to the locale pack schema and to the profile/locale
      API response (UK→£/GBP, India→₹/INR, Dubai→AED, Ireland→€/EUR).
- [ ] Create a `formatRate(min, max, currency)` helper in `frontend/src/lib` and replace every
      hardcoded `£...toLocaleString()` with it. Prefer `Intl.NumberFormat(locale, {style:'currency'})`.
- [ ] Replace hardcoded placeholder strings ("Min rate (£/day)") with the active currency.
- [ ] Test (Vitest): `formatRate` renders ₹/AED/€/£ correctly per locale; JobCard shows the profile's
      currency.

**Commit:** `fix(i18n): drive currency symbol from locale instead of hardcoded £`

### HC-2 — [HIGH] User-specific proof points hardcoded as UI placeholder text

**Finding:** `coach/StoryEditor.tsx` placeholders read "£500K Mobile Platform at Northern Powergrid"
and "Delivered £500K savings by modernising a legacy mobile platform" — the maintainer's actual career
achievements baked into shipped UI. Wrong for any other user and a PII/portfolio leak.

**Fix:**

- [ ] Replace with generic, instructive placeholders ("e.g. Cut onboarding time 40% at [Company]",
      "Describe the result — quantify with %, £/$/₹, or time saved").
- [ ] Keep currency-neutral or use the locale currency from HC-1.
- [ ] Test: placeholders contain no real employer names.

**Commit:** `fix: remove maintainer-specific examples from Story editor placeholders`

### HC-3 — [MEDIUM] Hardcoded model name in cost-tracking default

**Finding:** `llm_factory.py` docstring/usage and at least one `CostTrackingCallback(... model="gemini-2.5-flash")`
hardcode a specific model, and `settings.py` route-level `_PROVIDER_MODELS` pins exact model strings
(`claude-opus-4-7`, etc.) that will drift. The provider-agnostic `init_chat_model` design is
undermined when the cost callback assumes a model.

**Fix:**

- [ ] Ensure `CostTrackingCallback` always receives the **actual** model in use (from profile/config),
      never a literal default. Audit each instantiation.
- [ ] Move `_PROVIDER_MODELS` and the cost table to a single config/data source (e.g. a
      `models.yaml` or the locale/profile layer) so adding a model doesn't require editing two Python
      files. At minimum, add a comment + test that flags drift.
- [ ] Test: cost rows record the model that actually served the request, not a hardcoded one.

**Commit:** `refactor(llm): stop hardcoding model names in cost tracking; centralise model catalog`

### HC-4 — [MEDIUM] Voice/locale defaults hardcoded to `en_GB`

**Finding:** `tts_service.py` (`voice="en_GB-alan-medium"`) and `perception_factory.py` default to
`en_GB`. `schemas/profile.py` defaults `voice="en_GB-default"`. For non-UK locales the TTS voice and
ASR language assumptions are wrong.

**Fix:**

- [ ] Derive the default voice and ASR language hint from the active locale pack (add `coach.voice`
      and `coach.asr_language` keys per locale, mirroring the existing `coach.fillers` pattern).
- [ ] `tts_service`/`perception_factory` read from locale/profile, falling back to `en_GB` only if the
      locale omits it.
- [ ] Test: a non-UK locale yields its configured voice/language; UK still defaults to alan-medium.

**Commit:** `fix(i18n): source TTS voice and ASR language from locale, not hardcoded en_GB`

### HC-5 — [LOW] Hardcoded SMTP/digest defaults assume Gmail + London

**Finding (`config.py`):** `SMTP_HOST="smtp.gmail.com"`, `DIGEST_TIMEZONE="Europe/London"`,
`DIGEST_TIME="07:00"`. These are env-overridable (acceptable), but Gmail + London as defaults bias the
out-of-box experience to one user.

**Fix:**

- [ ] Leave `SMTP_HOST` empty by default (force explicit config; digest disabled if unset) rather than
      defaulting to Gmail.
- [ ] Default `DIGEST_TIMEZONE` from the active locale pack where available, else `UTC`.
- [ ] Test: digest service no-ops gracefully when SMTP unconfigured.

**Commit:** `fix(config): remove user-biased SMTP/timezone defaults`

### HC-6 — [LOW] Priority keywords / rate defaults are one user's preferences

**Finding (`config.py`):** `PRIORITY_KEYWORDS="solutions architect,cloud architect"` and
`PRIORITY_MIN_RATE=500` are the maintainer's job-search preferences as code defaults.

**Fix:**

- [ ] Default `PRIORITY_KEYWORDS=""` and source priorities from the profile/master profile, not a
      shipped default. `PRIORITY_MIN_RATE` → derive from profile rate band.
- [ ] Test: empty defaults don't break scoring; profile values take effect.

**Commit:** `fix(config): move priority keywords/rate from code defaults to profile`

---

# Part 4 — Default Local LLM Models (CPU-only consumer hardware)

## Rationale (read first)

Current Ollama defaults are `phi3:mini` (referenced in `routers/profile.py` and error copy) and
`gemma4:e2b` (referenced throughout `llm_factory.py` / `cv_tailor.py` tuning paths). Reference
hardware class: 4-core/8-thread U-series laptop CPU (e.g. i7-10610U), 8–32 GB dual-channel DDR4,
no usable GPU. CPU decode is memory-bandwidth bound: ~12–18 tok/s for a 2B Q4 model, ~6–10 tok/s
for 4B, ~2–3 tok/s for a dense 14B. Decode cost tracks **active** params, so small-active MoE
models (gemma4:26b-a4b ≈ 3.8B active, qwen3:30b-a3b ≈ 3B active) run at ~4B-dense speed with far
better quality — viable on 16–32 GB machines.

**Decision:**
- Triage default stays **`gemma4:e2b`** (edge-optimised, right size for relevance pre-filtering).
- Primary default moves **`phi3:mini` → `qwen3:4b`** (~2.6 GB Q4; two generations newer; markedly
  stronger instruction-following / structured-output at the same footprint — roughly matches
  Qwen2.5-7B on benchmarks; 32K native context comfortably fits CV+JD prompts). Phi-4 was
  considered and rejected as a default: 14B dense is too slow on this CPU class and its 16K
  context is tight for tailoring prompts.
- Document an **upgrade tier** for 16–32 GB machines: `gemma4:26b-a4b` or `qwen3:30b-a3b`
  (MoE). Prefill is heavier on MoE — fine for the 202+poll async pattern, worth a doc note.
- **Pending empirical test (do not assume away):** Coach rubric quality on `qwen3:4b` vs the MoE
  upgrade tier. Benchmarks favour qwen3:4b, but long-form rubric output is exactly where 4B models
  diverge from benchmark scores. This replaces the earlier phi-4/gemma/qwen candidate list.

| Tier | RAM | triage_model | primary_model |
|---|---|---|---|
| Default | 8–16 GB | `gemma4:e2b` | `qwen3:4b` |
| Recommended | 16 GB | `gemma4:e2b` | `gemma4:26b-a4b` (Q4) |
| Comfortable | 32 GB | `qwen3:4b` | `gemma4:26b-a4b` or `qwen3:30b-a3b` |

### LLM-1 — [HIGH] Replace phi3:mini defaults with qwen3:4b

**Finding:** `routers/profile.py:115` `model_map["ollama"] = "phi3:mini"` (used by
`/test-connection`); `llm_factory.py:274` error copy says `ollama pull phi3:mini`;
`tests/test_tools/test_llm_factory.py` and `tests/test_services/test_job_classifier.py` pin
`phi3:mini` in fixtures.

**Fix:**

- [ ] Test first: update `test_profile_router.py` connection-test expectation to `qwen3:4b` for
      provider `ollama`; watch fail.
- [ ] `routers/profile.py` model_map: `"ollama": "qwen3:4b"`.
- [ ] `llm_factory.py` `_detect_ollama_model` error message: recommend
      `ollama pull qwen3:4b` (primary) and `ollama pull gemma4:e2b` (triage).
- [ ] Sweep remaining `phi3` references in tests/fixtures; update or parametrise.
- [ ] Test: all llm_factory + profile router tests pass with new names; no `phi3` grep hits
      outside CHANGELOG/specs.

**Commit:** `feat(llm): replace phi3:mini with qwen3:4b as Ollama default primary model`

### LLM-2 — [HIGH] Model-aware thinking-mode handling (qwen3 thinks by default)

**Finding:** `_maybe_add_think_token()` prepends `<|think|>` for Ollama when `llm.reasoning=True`
— a **gemma4** convention. Qwen3 is the opposite: thinking is **on by default** and must be
disabled (`think=False` via ChatOllama / `/no_think`), or every triage and scoring call silently
burns thinking tokens at CPU speed.

**Fix:**

- [ ] Make think handling model-aware in `llm_factory.py`: for Ollama model names matching
      `qwen3*`, pass `think=llm_cfg.reasoning` (i.e. explicitly **off** unless `reasoning=True`);
      for `gemma4*`, keep the `<|think|>` prepend behaviour. Centralise in one helper.
- [ ] Default policy: triage + scoring always non-thinking; Coach rubric generation may opt in
      via `llm.reasoning=True` (document in profile schema comment — field exists at
      `schemas/profile.py:140`, widen its docstring beyond gemma4).
- [ ] Test: building a `qwen3:4b` model with `reasoning=False` passes `think=False`; gemma4 path
      unchanged; non-Ollama providers receive neither.

**Commit:** `fix(llm): disable qwen3 thinking mode by default; model-aware reasoning flags`

### LLM-3 — [MEDIUM] Onboarding wizard: recommended Ollama defaults + RAM-tier hint

**Finding:** `StepAIProvider.tsx` Ollama `triageDefault`/`primaryDefault` are empty strings; the
picker only lists whatever `ollama list` returns, and the empty state says "pull a model" with no
specific recommendation. New users get no steer toward known-good models.

**Fix:**

- [ ] Empty state: show copy-pasteable `ollama pull qwen3:4b && ollama pull gemma4:e2b` with a
      one-line "recommended for CPU-only machines" note.
- [ ] When the live model list contains a recommended model, pre-select it (preference order:
      primary `qwen3:30b-a3b` > `gemma4:26b-a4b` > `qwen3:4b`; triage `gemma4:e2b` > smallest
      available) instead of arbitrary first-item. Apply the same ordering to
      `_detect_ollama_model()` in the backend so auto-detect and wizard agree.
- [ ] Optional RAM tier hint: backend exposes total RAM (psutil already available via perception
      deps? if not, read `/proc/meminfo` — no new dependency) on the existing system/health
      endpoint; wizard shows "your machine (32 GB) can run the upgrade tier" with the table above.
      Keep it a hint, never an auto-switch.
- [ ] Test (Vitest): empty state renders pull command; recommended model pre-selected when
      present. (pytest): `_detect_ollama_model` prefers recommended names over list order.

**Commit:** `feat(onboarding): recommend CPU-tier Ollama models and pre-select known-good defaults`

### LLM-4 — [MEDIUM] Ship a local-first example profile + docs table

**Finding:** `examples/` has UK/US/EU profiles, all configured with cloud providers
(`claude-haiku…`/`claude-sonnet…`). There is no example showing the flagship "free, local,
CPU-only" configuration, despite it being the product's headline default.

**Fix:**

- [ ] Add `examples/profile_local_free.yaml`: `provider: ollama`, `triage_model: gemma4:e2b`,
      `primary_model: qwen3:4b`, `base_url: http://host.containers.internal:11434`,
      `track_costs: false`, `reasoning: false` — with comments explaining the RAM-tier table and
      MoE upgrade path (incl. the prefill-latency caveat).
- [ ] README "Choosing local models" section: paste the tier table; note `num_ctx` tuning already
      handled in `llm_factory.py` for long-context prompts.
- [ ] Test: example YAML parses against `schemas/profile.py` (add to the existing example-profile
      validation test if present, else create one).

**Commit:** `docs(llm): add local-first example profile and CPU model tier guidance`

### LLM-5 — [LOW] Tiny-model heuristics: recognise qwen3:4b correctly

**Finding:** `_TINY_MODEL_PATTERNS = ("e2b", ":1b", ":3b", "mini", "lite", "nano")` drives the
"consider upgrading for document generation" warning. `qwen3:4b` does not match (correct — it
should be allowed as primary), but verify no other heuristic (e.g. `cv_tailor.py`'s
gemma4:e2b 512-token attention workaround) misfires or fails to fire for qwen3 models.

**Fix:**

- [ ] Audit `cv_tailor.py` / `claude_client.py` model-name conditionals for gemma4-specific
      branches; ensure qwen3 takes the generic path and produces valid output via
      `get_json_model()` (`format=json` already wired).
- [ ] Add `:0.6b`, `:1.7b` to tiny patterns (qwen3's small variants) so a user picking those as
      primary still gets the upgrade warning.
- [ ] Test: `qwen3:4b` is not flagged tiny; `qwen3:1.7b` is.

**Commit:** `fix(llm): extend tiny-model heuristics for qwen3 family`

---

## Suggested execution order

1. **SEC-3** (path traversal — concrete RCE-adjacent bug, smallest blast radius to fix)
2. **SEC-4 + HC-2** (PII removal — repo is public)
3. **SEC-1 + SEC-2** (auth + CORS — do together, they interlock)
4. **SEC-5, SEC-8** (quick wins)
5. **LLM-1 + LLM-2** (model default swap + thinking-mode fix — do together; LLM-2 guards LLM-1's
   CPU latency)
6. **HC-1, HC-4** (locale correctness — restores a headline feature claim)
7. **SEC-6, SEC-7** (CSP, rate limiting — report-only CSP first)
8. **LLM-3, LLM-4, LLM-5** (wizard defaults, docs, heuristics)
9. **HC-3, HC-5, HC-6** (config hygiene)
10. **UX-1 → UX-6** (polish; UX-1 unblocks the rest)
11. **SEC-9** (track major-version migrations separately — out of scope here)

## Out of scope / explicitly not touched

- The assisted-apply "no autonomous submission" boundary and its test — untouched.
- Phase-0 pipeline bugs (supervisor ordering, keyword scorer) — pre-existing, tracked elsewhere;
  UX-5 references them but does not fix them.
- langgraph 1.x / transformers 5.x major migrations (SEC-9) — breaking, separate effort.
- The Coach rubric-quality empirical test (qwen3:4b vs MoE tier) — Part 4 documents it as the
  decision gate, but running it is a separate hands-on session, not a Claude Code task.

## Open questions to resolve before/while implementing

1. **Auth model** — bearer token (recommended) vs. session cookie? Affects SEC-1/SEC-2.
2. **CSP rollout** — report-only first then enforce (recommended), or straight to enforce with nonce?
3. **Git history scrub** — given the public portfolio repo, do you want a history rewrite to remove the
   PII profile from past commits, or is removing it going forward acceptable? (SEC-4)
4. **Model catalog source** — new `models.yaml`, or fold into the existing profile/locale layer? (HC-3)
5. **RAM detection** (LLM-3) — `/proc/meminfo` read (zero deps, Linux-only inside the container — fine
   for Docker deploys) vs adding `psutil` to core requirements. Recommending `/proc/meminfo` with a
   graceful "unknown" fallback.
6. **Triage swap on 32 GB tier** — table suggests `qwen3:4b` as triage when the primary is MoE; is the
   extra triage quality worth the slower pre-filter vs keeping `gemma4:e2b` everywhere? Default to
   keeping `gemma4:e2b`; revisit after the rubric test.
