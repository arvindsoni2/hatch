---
title: Hatch v4.1 — Restore orphaned UX (onboarding gate, notifications, settings theming, dark-mode toggle)
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

# Hatch v4.1 — Restore orphaned UX (onboarding gate, notifications, settings theming, dark-mode toggle)

> **For agentic workers:** Use the project's standard TDD loop — write the test, run it red, implement, run it green, commit. Steps use checkbox (`- [ ]`) syntax for tracking. Do **not** rewrite working components; this is a **wiring** job.

**Date:** 6 June 2026
**Base commit:** `3d8611a` — "feat: Hatch v4 — two-step assisted apply + Agent Skills layer + Direction A UX"
**Repo:** `arvindsoni2/hatch`

---

## 1. Root cause (read this first)

The v4 "Direction A UX" rework replaced the app shell. `frontend/src/app/layout.tsx` now renders `HatchNavShell`, which renders only `HatchSidebar` (desktop) + `HatchNav` (mobile bottom tabs). The previous shell — `frontend/src/components/Navigation.tsx` — is the **only** place that imported `NotificationBell` and `ThemeToggle`, and it is no longer mounted anywhere. The features below are therefore **orphaned, not deleted**: the code exists and its tests pass, but nothing renders it.

| Feature | Working code that already exists | Why it disappeared |
|---|---|---|
| Onboarding | `app/onboarding/page.tsx` + `components/onboarding/*` (11 steps); `api.ts → fetchProfileStatus()` returns `onboarding_required` | No gate consumes `onboarding_required`; the shell never redirects first-run users |
| Notifications | `components/NotificationBell.tsx` (polls `listCompletedJobs`, badge + dropdown) | Imported only by the unmounted `Navigation.tsx`. `HatchTopBar` has a **static stub** bell, and `HatchTopBar` itself is not rendered by the shell |
| Settings + CV upload | `app/settings/page.tsx`, `app/settings/profile/page.tsx` (`saveProfile`), `app/settings/resume/page.tsx` (`uploadResume`) | Reachable from the sidebar, but pages use old light Tailwind (`bg-white`, `text-slate-900`) so they render as broken light islands in the dark-default app |
| Dark-mode toggle | `components/ThemeToggle.tsx` (sets `data-theme` + `.dark` + `localStorage`, correct mechanism) | Imported only by the unmounted `Navigation.tsx`. Boot script in `layout.tsx` forces dark with no UI switch |

**Theme mechanism (already standardised — do not change it):** `globals.css` defines tokens under `:root, [data-theme="dark"], .dark` and `[data-theme="light"], :root:not(.dark)`. The boot script in `layout.tsx` sets both `data-theme` and the `.dark` class. `ThemeToggle.tsx` already matches this exactly. New/edited UI must use CSS-variable tokens (`var(--bg)`, `var(--surface)`, `var(--text)`, `var(--text-dim)`, `var(--text-muted)`, `var(--border)`, `var(--accent)`, `var(--danger)`), **not** hardcoded slate/white utilities.

---

## 2. Guardrails

- **Wire, don't rebuild.** `NotificationBell`, `ThemeToggle`, and the onboarding steps work. Reuse them verbatim.
- **No regressions to v4.** The two-step assisted apply, Agent Skills layer, and Direction A sidebar/bottom-nav stay exactly as they are.
- **TDD is mandatory** (`vitest` for components, Playwright for E2E). Every task writes a failing test first.
- **CSS-variable tokens only** for any markup you touch. No new `bg-white`/`text-slate-*`.
- **Single-user, localhost.** No auth flows; the onboarding gate is a client redirect based on profile status.

---

## Task 1 — Render a desktop top bar so the bell + toggle have a home

The shell currently has no top bar; `HatchTopBar` exists but is unmounted. Mount it in the main content column.

**Files:**
- Create: `frontend/src/components/hatch/HatchTopBarSlot.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/__tests__/components/hatch/HatchTopBarSlot.test.tsx`

- [ ] **Step 1: Write the test (red).** Assert that `HatchTopBarSlot` renders a `banner`/`header` region, derives a page title from the pathname (e.g. `/today` → "Today", `/stream` → "Stream", `/tracker` → "Tracker", `/prep` → "Prep", `/settings` → "Settings"), and renders both a notifications control and a theme toggle (queried by accessible name, see Tasks 2–3). Mock `next/navigation`'s `usePathname` and `@/lib/api`'s `fetchProfileStatus` (resolve `{ candidate_name: "Arvind" }`).

```bash
cd frontend && npx vitest run src/__tests__/components/hatch/HatchTopBarSlot.test.tsx 2>&1 | tail -10
# Expected: Cannot find module '@/components/hatch/HatchTopBarSlot'
```

- [ ] **Step 2: Implement `HatchTopBarSlot.tsx`** (client component). It:
  - reads `usePathname()` and maps it to `{ pageTitle, pageSub }` (reuse the route→label idea from `HatchNavShell.deriveTab`; add `/settings`, `/coach`, `/jobs`, `/applications`, `/analytics`, `/calendar`, with a sensible default);
  - fetches `fetchProfileStatus()` once on mount for `candidate_name` (fallback `"there"`);
  - renders `HatchTopBar` with `name`/`pageTitle`/`pageSub`, but with the **real** bell and toggle injected (Tasks 2–3 modify `HatchTopBar` to accept them).
  - It must be `hidden md:flex` so it only shows on desktop (mobile parity is Task 6).

- [ ] **Step 3: Mount it in `layout.tsx`.** Place `<HatchTopBarSlot />` at the very top of the `<main>` content column, above `{children}`:

```tsx
<div className="flex flex-col flex-1 min-w-0">
  <HatchTopBarSlot />
  <main className="flex-1 px-4 py-6 pb-24 md:px-8 md:py-6 md:pb-8">
    {children}
  </main>
</div>
```

- [ ] **Step 4: Run green, then commit.**

```bash
git add frontend/src/components/hatch/HatchTopBarSlot.tsx frontend/src/app/layout.tsx frontend/src/__tests__/components/hatch/HatchTopBarSlot.test.tsx
git commit -m "feat(shell): mount HatchTopBarSlot in main content column"
```

---

## Task 2 — Replace the static bell with the real `NotificationBell`

`HatchTopBar.tsx` has a dead `<button aria-label="Notifications">`. Swap it for the working component.

**Files:**
- Modify: `frontend/src/components/hatch/HatchTopBar.tsx`
- Modify (if needed): `frontend/src/__tests__/components/hatch/navigation.test.tsx`

- [ ] **Step 1: Write/extend the test (red).** Render `HatchTopBar`, assert the document contains the live `NotificationBell` (e.g. by mocking `listCompletedJobs` to return 3 done jobs and asserting the badge testid `bell-badge` shows `3`). Mock the API the way `NotificationBell.test.tsx` already does.

- [ ] **Step 2: Implement.** In `HatchTopBar.tsx`, delete the static bell `<button>` block and its `notifCount` prop usage. Import and render the real one:

```tsx
import { NotificationBell } from "@/components/NotificationBell";
// …in the toolbar cluster, before <UserAvatar/>:
<NotificationBell />
```

  Keep `NotificationBell`'s own styling, but if its hover classes (`hover:bg-slate-100`) clash with the dark shell, wrap it or pass through token-based classes — do not reintroduce light-only utilities. Remove the now-unused `notifCount` prop from the `HatchTopBarProps` interface and any callers.

- [ ] **Step 3: Run green, then commit.**

```bash
git add frontend/src/components/hatch/HatchTopBar.tsx frontend/src/__tests__/components/hatch/navigation.test.tsx
git commit -m "feat(notifications): wire real NotificationBell into HatchTopBar"
```

---

## Task 3 — Restore the dark/light toggle

`ThemeToggle.tsx` is correct and unused. Mount it in the top bar (desktop) — mobile is Task 6.

**Files:**
- Modify: `frontend/src/components/hatch/HatchTopBar.tsx`
- Create: `frontend/src/__tests__/components/hatch/HatchTopBar.theme.test.tsx`

- [ ] **Step 1: Write the test (red).** Render `HatchTopBar`, query `getByRole("button", { name: /toggle dark mode/i })`, click it, assert `document.documentElement` gets `data-theme="light"` and loses the `.dark` class; click again and assert it returns to dark. (Mirror `ThemeToggle.test.tsx`.)

- [ ] **Step 2: Implement.** In `HatchTopBar.tsx`:

```tsx
import { ThemeToggle } from "@/components/ThemeToggle";
// …in the toolbar cluster, between search and NotificationBell:
<ThemeToggle />
```

- [ ] **Step 3: Run green, then commit.**

```bash
git add frontend/src/components/hatch/HatchTopBar.tsx frontend/src/__tests__/components/hatch/HatchTopBar.theme.test.tsx
git commit -m "feat(theme): restore dark/light ThemeToggle in HatchTopBar"
```

---

## Task 4 — Restore the first-run onboarding gate

`fetchProfileStatus()` already returns `onboarding_required`. Nothing acts on it. Add a small client gate that redirects to `/onboarding` when required, and never traps the user *on* `/onboarding`.

**Files:**
- Create: `frontend/src/components/OnboardingGate.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/__tests__/components/OnboardingGate.test.tsx`

- [ ] **Step 1: Write the test (red).** With `usePathname` → `/today` and `fetchProfileStatus` → `{ onboarding_required: true }`, assert `router.replace("/onboarding")` is called. With `onboarding_required: false`, assert no redirect. With pathname already `/onboarding`, assert no redirect (no loop). Mock `next/navigation` (`usePathname`, `useRouter`).

- [ ] **Step 2: Implement `OnboardingGate.tsx`** (client, renders `null`):

```tsx
"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchProfileStatus } from "@/lib/api";

export function OnboardingGate() {
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    if (pathname.startsWith("/onboarding")) return;
    let cancelled = false;
    fetchProfileStatus()
      .then((s) => { if (!cancelled && s.onboarding_required) router.replace("/onboarding"); })
      .catch(() => {/* offline / backend down: stay put */});
    return () => { cancelled = true; };
  }, [pathname, router]);
  return null;
}
```

- [ ] **Step 3: Mount in `layout.tsx`** just inside `<body>`, before the layout `flex` wrapper:

```tsx
<OnboardingGate />
```

- [ ] **Step 4 (optional polish):** the `/onboarding` route should render full-screen *without* the sidebar/top bar. The onboarding page already uses `position: fixed; inset-0; z-50` (`data-onboarding="true"`), so it overlays the shell — acceptable. If you want it clean, branch in `HatchNavShell`/`HatchTopBarSlot` to render `null` when `pathname.startsWith("/onboarding")`.

- [ ] **Step 5: Run green, then commit.**

```bash
git add frontend/src/components/OnboardingGate.tsx frontend/src/app/layout.tsx frontend/src/__tests__/components/OnboardingGate.test.tsx
git commit -m "feat(onboarding): redirect first-run users via OnboardingGate (consumes onboarding_required)"
```

---

## Task 5 — Re-theme Settings to CSS-var tokens; verify param editing + CV upload

Settings is reachable (sidebar → `/settings`) and the backend wiring works (`saveProfile`, `uploadResume`, `fetchResumeStatus`). The problem is purely presentation: the pages use light Tailwind utilities and look broken in the dark shell.

**Files:**
- Modify: `frontend/src/app/settings/page.tsx`
- Modify: `frontend/src/app/settings/profile/page.tsx`
- Modify: `frontend/src/app/settings/resume/page.tsx`
- Modify: `frontend/src/app/settings/system/page.tsx`
- Create: `frontend/src/__tests__/pages/settings-theme.test.tsx` (codebase guard)

- [ ] **Step 1: Write a codebase guard test (red).** Read each settings page file and assert it contains **no** hardcoded `bg-white`, `text-slate-900`, `text-slate-800`, `border-slate-200` (allow `dark:` variants only if paired). The intent: settings must use `var(--surface)`, `var(--text)`, `var(--border)`, etc. (Model it on the existing `__tests__/codebase/*` tests and the IR35-elimination guard in `CLAUDE_Phase2_Tests.md`.)

- [ ] **Step 2: Re-theme.** Replace the local `SectionCard`/`FieldRow`/`Badge` primitives' light classes with token styles, e.g.:
  - card: `style={{ background: "var(--surface)", border: "1px solid var(--border)" }}`
  - title text: `color: var(--text)`; muted: `color: var(--text-muted)`
  - inputs (`@/components/ui/input`): ensure they inherit `var(--surface-2)` bg, `var(--border)`, `var(--text)`.
  Leave all logic (`saveProfile`, digest settings, `uploadResume`, drag-drop) untouched.

- [ ] **Step 3: Verify functionality (manual + assert).** Confirm:
  - `/settings/profile` saves target roles, locations, compensation, `scoring.shortlist_threshold`, scrape interval, and LLM provider/models via `saveProfile` (PUT `/api/v2/profile`).
  - `/settings/resume` uploads `.docx`/`.pdf` via `uploadResume` and reflects `fetchResumeStatus`.
  Add a light render test for `/settings/profile` asserting the save button and at least one editable field are present.

- [ ] **Step 4 (discoverability):** add a "Settings" entry consistent with Direction A. The sidebar already links `/settings` at the foot; also expose it on mobile — either add a 5th item to `HatchNav` or surface it via the top-bar/user avatar. Pick one and keep it themed.

- [ ] **Step 5: Run green, then commit.**

```bash
git add frontend/src/app/settings frontend/src/__tests__/pages/settings-theme.test.tsx
git commit -m "fix(settings): re-theme to CSS-var tokens; verify param editing + CV upload reachable"
```

---

## Task 6 — Mobile parity for notifications + theme

`HatchTopBar`/`HatchTopBarSlot` are desktop-only (`hidden md:flex`). On mobile the bell and toggle would still be missing.

**Files:**
- Modify: `frontend/src/components/hatch/HatchNav.tsx` **or** create `frontend/src/components/hatch/HatchMobileBar.tsx`
- Create: `frontend/src/__tests__/components/hatch/mobile-controls.test.tsx`

- [ ] **Step 1: Decide the pattern.** Cleanest: a slim mobile top bar (`md:hidden`) showing the brand "H", `NotificationBell`, and `ThemeToggle`, mounted in `layout.tsx` above `<main>` alongside `HatchTopBarSlot`. The bottom `HatchNav` (Today/Stream/Tracker/Prep) stays as-is.

- [ ] **Step 2: Write the test (red)** asserting the mobile bar renders the bell and the toggle (accessible names), and is `md:hidden`.

- [ ] **Step 3: Implement** the mobile bar reusing `NotificationBell` and `ThemeToggle` verbatim; token styling only.

- [ ] **Step 4: Run green, then commit.**

```bash
git add frontend/src/components/hatch frontend/src/app/layout.tsx frontend/src/__tests__/components/hatch/mobile-controls.test.tsx
git commit -m "feat(mobile): surface notifications + theme toggle on mobile bar"
```

---

## Task 7 — Decommission the dead shell + full regression sweep

- [ ] **Step 1: Resolve `Navigation.tsx`.** It is now fully superseded. Either delete it (and `__tests__/components/.../Navigation*`) or, if other code still imports it, reduce it to a thin re-export. Run `grep -rl "components/Navigation" frontend/src` first; only delete if nothing else depends on it.
- [ ] **Step 2:** Confirm `HatchTopBar` no longer carries the unused `notifCount` prop and the static bell markup is gone.
- [ ] **Step 3: Full suite.**

```bash
cd frontend && npx vitest run 2>&1 | tail -20
npx playwright test 2>&1 | tail -20   # if E2E configured
```

- [ ] **Step 4: Commit.**

```bash
git add -A
git commit -m "chore: remove dead Navigation shell; full test sweep for v4.1 UX restore"
```

---

## 3. Design module (Claude Design) — companion changes

I could not open the shared Design document directly, so this describes what to add there so design and code stay in sync. Add these screens/states to the Direction A design file:

1. **Top bar (desktop)** — a 60px bar in the main column containing: page title + greeting/subtitle, search field, **theme toggle (sun/moon)**, **notification bell with red count badge + dropdown**, user avatar. The current design shows a sidebar + content but no populated top-bar controls.
2. **Notification dropdown** — 72-unit-wide panel: header "Notifications" + "Mark all read", list rows (job-type label + relative time), and an empty state "No new notifications".
3. **Onboarding flow** — the 8 screens (Welcome → About you → Your market → Location & pay → Eligibility → Skills → AI & launch → Success) as a full-screen overlay (no sidebar), with the numeral step progress. This is the first-run experience the gate redirects to.
4. **Settings** — themed (dark-default) screens for: Profile/parameters (roles, locations, pay, scoring threshold, scrape interval), AI provider + API key, **CV upload** (drag-drop dropzone with parsed-section checklist), Job boards, System.
5. **Dark/light parity** — show both theme variants for the top bar and settings so the toggle's effect is specified.
6. **Mobile** — a slim mobile top bar (brand + bell + toggle) above the existing bottom tab bar.

---

## 4. Acceptance checklist

- [ ] First run (no `profile.yaml` / `onboarding_required: true`) redirects to `/onboarding`; completing it lands back in the app and never loops.
- [ ] Desktop top bar is visible with a **working** bell (badge updates from `listCompletedJobs`, dropdown opens, "Mark all read" clears) and a **working** dark/light toggle (persists across reload via `localStorage.theme` + `data-theme`).
- [ ] Mobile shows the bell and toggle; bottom tabs unchanged.
- [ ] `/settings` is reachable on desktop and mobile, renders in the active theme (no light islands), and supports editing search parameters + uploading a CV.
- [ ] No file reintroduces hardcoded `bg-white`/`text-slate-900` in the touched settings pages.
- [ ] Dead `Navigation.tsx` removed (or proven still required); no orphaned imports.
- [ ] `npx vitest run` passes with zero regressions; v4 assisted-apply + Agent Skills untouched.

---

## 5. Suggested commit sequence (summary)

1. `feat(shell): mount HatchTopBarSlot in main content column`
2. `feat(notifications): wire real NotificationBell into HatchTopBar`
3. `feat(theme): restore dark/light ThemeToggle in HatchTopBar`
4. `feat(onboarding): redirect first-run users via OnboardingGate`
5. `fix(settings): re-theme to CSS-var tokens; verify param editing + CV upload`
6. `feat(mobile): surface notifications + theme toggle on mobile bar`
7. `chore: remove dead Navigation shell; full test sweep for v4.1 UX restore`
