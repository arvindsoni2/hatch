---
title: Handoff: Hatch — Proactive Agent Cockpit (Direction A)
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

# Handoff: Hatch — Proactive Agent Cockpit (Direction A)

## Overview

This package redesigns **Hatch** — the open-source, self-hosted autonomous AI job-search app
(Scout → Scorer → Tailor → Coach agent pipeline) — to fix one core problem: the engine works
autonomously, but the UI is passive and the agent hand-offs are invisible. Users reported the flow
*"feels disconnected — I'd expect Scout → Scorer → Tailoring → Coach flowing seamlessly."*

The redesign does three things:

1. **Collapses the redundant Discover area** (the old Home + Inbox + Shortlist, which overlapped) into
   a single proactive **Today** cockpit plus one continuous **Stream**.
2. **Makes the agents proactive** — every surface leads with what the agents did and the single thing
   they need from the user, with one-tap actions.
3. **Visualizes the pipeline as one motion** — a four-colour agent spectrum (Scout blue → Scorer
   purple → Tailor green → Coach amber) runs through every card so a role's place in the
   Scout→Score→Tailor→Coach journey is always legible.

There are two layouts to implement, both the **same product, same IA, same design system**:

- **Mobile (PWA)** — `Hatch Prototype.html` — the primary target.
- **Desktop (web)** — `Hatch Desktop.html` — sidebar-led, matches the existing Hatch desktop chrome.

> A second exploratory direction ("Mission Control" — a living pipeline spine + conversational agent
> feed) is included in `Hatch Redesign (exploration).html` for context only. **Do not implement
> Direction B** unless explicitly asked — the chosen, built-out direction is **A**.

---

## About the Design Files

The files in this bundle are **design references created in HTML/React (via inline Babel)** —
prototypes showing the intended look and behaviour. **They are not production code to copy directly.**

The task is to **recreate these designs inside the existing Hatch codebase** and its established
patterns:

- **Frontend stack (from the repo):** Next.js (App Router, `frontend/src/app/`), React, TypeScript,
  **Tailwind CSS** (`darkMode: "class"`), with design tokens defined as CSS custom properties in
  `frontend/src/app/globals.css`. Existing reusable components live in `frontend/src/components/`
  (e.g. `Sidebar.tsx`, `JobCard.tsx`, `ScoreBadge.tsx`, `ATSScoreCard.tsx`, `ActivityFeed.tsx`).
- Reuse the codebase's existing Tailwind tokens, dark-mode setup, `date-fns` for relative times, and
  component conventions. Map the prototype's inline style values (documented below) onto the existing
  CSS variables / Tailwind theme rather than hard-coding new hex values where an equivalent token
  already exists.

The prototypes use inline `style={{}}` objects purely so they run standalone in a single file. In the
real app these become Tailwind classes / styled components per the codebase's convention.

---

## Fidelity

**High-fidelity (hifi).** Final colours, typography, spacing, layout, copy, and interactions are all
intentional and specified below. Recreate the UI to match, using the codebase's existing
libraries/patterns. Where the existing Hatch design system already defines an equivalent token
(colour, radius, spacing), prefer it; the values below are the source of truth for anything new.

---

## Design Tokens

All values are lifted from the prototype's shared token object (`hatch-ui.jsx` → `HT`), which itself
mirrors the dark theme in the repo's `globals.css`.

### Colour — surfaces & text (dark theme)
| Token | Hex | Use |
|---|---|---|
| `bg` | `#0b0b0f` | App background |
| `bgEl` | `#101014` | Elevated bg (sidebar, top bars, footers, kanban columns) |
| `surface` | `#16161c` | Card background |
| `s2` | `#1d1d25` | Inset rows / chips / inner wells |
| `s3` | `#24242e` | Toast / strongest inset |
| `border` | `#26262f` | Default 1px border |
| `borderStrong` | `#32323d` | Emphasis border / dividers in arrows |
| `borderSubtle` | `#1d1d25` | List-row separators |
| `text` | `#f1f1f4` | Primary text |
| `dim` | `#a8a8b3` | Secondary text / body copy |
| `muted` | `#74747f` | Tertiary / meta / placeholders |

### Colour — accents
| Token | Hex | Soft (14% alpha) | Meaning |
|---|---|---|---|
| `accent` (Scout) | `#5b9bff` | `rgba(91,155,255,.14)` | Primary action / Scout agent / "Discovered" |
| `purple` (Scorer) | `#b794ff` | `rgba(183,148,255,.14)` | Scorer agent / "Applied" / categories |
| `success` (Tailor) | `#3ddc97` | `rgba(61,220,151,.14)` | Tailor agent / approve / ready / positive |
| `warning` (Coach) | `#f5b950` | `rgba(245,185,80,.14)` | Coach agent / interview / "parked below bar" |
| `danger` | `#ff6b6b` | `rgba(255,107,107,.14)` | Reject / overdue / notification dot |

> **Accent is themeable.** The prototype exposes a Tweak to switch the primary accent. The user's
> selected default is **teal `#36c5a8`** (used as the desktop default). Implement `accent` as a single
> swappable token; the four *agent* colours above stay fixed regardless of accent.

### The agent spectrum (fixed identity colours — the core visual system)
| Agent | Colour | Role label | Icon (lucide-equivalent) |
|---|---|---|---|
| **Scout** | `#5b9bff` blue | "Finds roles" | `compass` |
| **Scorer** | `#b794ff` purple | "Ranks matches" | `target` |
| **Tailor** | `#3ddc97` green | "Writes your CV" | `file-text` |
| **Coach** | `#f5b950` amber | "Preps interviews" | `mic` |

Pipeline order is always **Scout → Scorer → Tailor → Coach**.

### Typography
- **Sans:** `Inter` (weights 400/500/600/700/800). Body letter-spacing `-0.005em`; headings `-0.02em` to `-0.03em`.
- **Mono:** `Roboto Mono` (500/700) — used for all numbers: scores, counts, stats, list indices.
- **Serif:** the repo also imports `Newsreader` (`@fontsource/newsreader`) for editorial accents — not used in these screens but available.

Type scale used:
| Role | Size / weight |
|---|---|
| Page title (mobile) | 26px / 700 |
| Page title (desktop greeting) | 28px / 800 |
| Card title | 14–17px / 700 |
| Body / description | 12.5–14.5px / 400–500, line-height ~1.55 |
| Meta / labels | 10.5–12px / 500–600 |
| Table header | 11px / 700, letter-spacing 0.04em, uppercase |
| Big stat number | 24–36px / 800, mono |

### Spacing, radius, shadow
- **Radius:** chips/pills 999px; buttons & inset rows 9–11px; cards 14–18px; modal 20px; agent badge = `size × 0.3`.
- **Card padding:** 14–20px. **Page padding:** mobile 18px horizontal; desktop 32px horizontal.
- **Gaps:** card stacks 11–16px; inline groups 6–13px. Always use fl/grid `gap`, not margins.
- **Shadows:** cards are flat (border-only). Overlays: modal `0 30px 80px rgba(0,0,0,.6)`; toast `0 14px 36px rgba(0,0,0,.5)`; swipe card `0 16px 40px rgba(0,0,0,.35)`.
- **Accent ring** (on the highlighted "ready" card): `border: 1px solid accent` + `box-shadow: 0 0 0 3px accentSoft`.

### Icons
Minimal 24×24 stroke icons, `stroke-width` 2–2.4, round caps/joins. The set used maps 1:1 to
**lucide-react** (bell, search, check, check-circle, chevron-right, clock, file-text, send, target,
mic, compass, layers, home, inbox, briefcase, calendar, map-pin, building, external-link, x, plus,
sliders, message, etc.). Use the codebase's existing icon library if it has one; otherwise lucide-react.

---

## Shared Components (build these first)

These are defined in `hatch-ui.jsx` and reused across both layouts. Recreate them as real components.

1. **`AgentBadge`** — rounded-square chip (radius = size×0.3) in the agent's soft colour, containing
   the agent's icon in its solid colour. Props: `agent` (scout|scorer|tailor|coach), `size`, `ring`
   (adds `0 0 0 3px soft` glow). Sizes used: 22, 26, 30, 34, 40, 42.

2. **`StageTrack`** — the signature element. A horizontal Scout→Scorer→Tailor→Coach track of 4 nodes
   connected by 2px lines. Props: `stage` (0–3 = index reached), `pct` (score shown on Scorer node when
   it's the current stage), `compact`, `labels` (show agent names beneath). Reached nodes use the agent
   colour (filled soft bg + 1.5px coloured border + icon); a completed node shows a `check`; the current
   node gets a soft glow ring; unreached nodes are grey (`s2` bg, `border`, muted icon). Connector line
   segments before the current stage take the *next* agent's colour at 50% opacity.

3. **`ScorePill`** — match-score pill, mono font. `pct = round(score×100)`. Colour-graded vs a
   threshold (default 0.75): ≥threshold → green; ≥threshold×0.66 → amber; else → muted grey. Two
   sizes (`md` ~42px min-width, `lg` ~54px). Background is the soft variant of the grade colour.

4. **`Chip`** — pill, 11.5px/600, optional leading icon. Props: `color`, `bg`, `icon`.

5. **`Dot`** — status dot; `pulse` adds a soft halo (used on "live/active" and "ready" states).

6. **`Btn`** — kinds: `primary` (accent bg, white text), `soft` (s2 bg, text, border), `ghost`
   (transparent, dim, border), `success` (green bg, dark-green text `#06231a`). Sizes `sm`/`md`.
   Optional leading `icon` / trailing `iconR`. `full` = 100% width. Always `white-space: nowrap`.

7. **`Card`** — `surface` bg, 1px `border`, radius 16. `accent` prop swaps to the accent ring treatment.

8. **`UserAvatar`** — 999px circle, gradient `linear-gradient(135deg,#f97316,#ec4899)`, white initials.

---

## Screens / Views

> Two layouts share these screens. Differences are called out per screen.

### Navigation / IA (replaces old Home + Inbox + Shortlist)
Four destinations: **Today · Stream · Tracker · Prep**.
- **Mobile:** bottom tab bar (4 tabs, icon + 10.5px label; active = accent). 56px top status inset, 30px bottom home-indicator inset.
- **Desktop:** 248px left sidebar — logo, the 4 nav items (with count badges), a pinned **"Agents running"** status card listing the 4 agents + roles, and a user row at the bottom. Main area = sticky top bar (page title + sub, 240px search field, bell with red dot) over a scrolling content region.

Sidebar nav item: 10px×12px padding, radius 10; active = `accentSoft` bg + accent text/icon + filled count badge; idle = transparent + dim. Count badges use mono 11px.

---

### 1 · TODAY (the cockpit)
**Purpose:** The proactive home. Answers "what did my agents do, and what needs me right now?"

**Mobile layout (top → bottom):**
- **Briefing card** — header row: pulsing green `Dot` + "Agents active" + "last run 3h ago" (right). Body sentence (first-person when `voice` tweak on): *"Overnight I moved **75 new roles** down the pipeline. **3 are tailored** and waiting on your call."* Then a **mini funnel**: 4 `FunnelStep`s (AgentBadge + mono count + agent-colour name) separated by `chevron-right` connectors — Scout 75 → Scorer 12 → Tailor {readyCount} → Coach 1.
- **"Needs you" section header** + count chip.
- **Action 1 — Approve (accent-ring card):** Tailor badge (with ring) + "{n} applications ready to send" + sub. Then one tappable inset row per ready role (`ScorePill` + title/company + "ATS {n}" chip). Footer: full-width primary **"Review & approve"** → opens Review queue with all ready ids.
- **Action 2 — Interview prep card:** Coach badge + "Interview Tuesday, 9am" + "Lead Architect · Capgemini · in 3 days" + prep sub + soft **"Review prep"** button → navigates to Prep.
- **Action 3 — Follow-ups card:** red `clock` tile + "2 follow-ups overdue" + meta + chevron.
- *Empty state* (after all approved): centered green check, "Approval queue clear".

**Desktop layout:**
- Greeting top bar: **"Good morning, Arvind"** + "Thursday · 6 June — here's what your agents did overnight".
- **Hero `PipelineRail`** (full-width card): 4 big stations (42px AgentBadge, 30px mono count, agent-colour name, sub-label) separated by `arrow-right` connectors that show in-transit counts ("63 →", "9 →", "2 →"). Clicking a station jumps to Stream. **This is the centrepiece that makes the pipeline feel continuous.**
- Two-column grid below (`1.55fr / 1fr`):
  - **Left "Needs you":** the same Approve card (now with a "Review all" button top-right + richer rows), the interview-prep card, and the follow-ups card (with a "Nudge both" action).
  - **Right:** **"Agent activity"** feed (Card listing the 4 most recent agent actions — AgentBadge + name + time + text + tag chip), and a **"This week"** stats card (2×2 grid: Applied 14 / Interviews 2 / Response rate 21% / Avg match 83%, each a big mono number in an agent colour).

---

### 2 · STREAM (unifies Inbox + Shortlist)
**Purpose:** Every role, every pipeline stage, in one filterable place.

**Filter chips:** All / Ready / Tailoring / Parked, each with a live mono count. Active = `accentSoft`.

**Mobile:** a vertical list of role **cards**. Each card: title (+ `external-link` glyph) and company·loc·rate on the left, `ScorePill` right; a full **`StageTrack`** (with labels + score on Scorer); a status line (coloured, pulsing dot if "ready") and either a green **Approve** button (ready) or a chevron. Tapping the card body opens Review.

**Desktop:** a **table** inside one Card. Columns: `ROLE | MATCH | PIPELINE STAGE | STATUS | ACTION`
(grid `2.4fr .7fr 2fr 1.4fr 1fr`). Each row: role title+meta, `ScorePill`, a **compact label-less
`StageTrack`**, coloured status text, and a right-aligned action (green **Approve** if ready, else
ghost **Open**). Ready rows get an `accentSoft` row background. Clicking the row opens Review;
clicking the action does NOT propagate (stopPropagation).

**Status → colour/label map:**
`ready` → green "Ready to send" · `tailoring` → green "Tailoring…" · `parked` → amber "Below match
bar" · `applied` → accent "Applied" · `rejected` → muted "Dismissed".

---

### 3 · TRACKER (kanban pipeline)
**Purpose:** Applications across the funnel.

Four columns: **Discovered** (accent) · **Applied** (purple) · **Interview** (amber) · **Offered**
(green). Column header: coloured dot + label + mono count. Cards: title + `ScorePill`, company·loc
meta, and an optional status chip (Interview cards show a `calendar` chip "Tue 9:00am"; Applied cards
show a `clock` chip "Sent 2d ago"). Empty columns show a dashed "Nothing here yet" placeholder.

- **Mobile:** horizontally-scrolling columns, 230px wide.
- **Desktop:** 4-column responsive grid (`repeat(4,1fr)`), columns on `bgEl` with 16px radius.

**Live behaviour:** approving a role moves it from Discovered → Applied here (see State Management).

---

### 4 · PREP (interview coach)
**Purpose:** Coach's per-interview prep.

- **Session list:** each session = Coach badge + role/company + a status indicator
  (`ready` green / `progress` accent / `generating` amber). Only `ready` sessions open.
- **Detail view:**
  - Header: Coach badge + "Lead Architect · Capgemini" + date + "Add to calendar" button.
  - **"Company research"** card — short brief paragraph.
  - **"12 likely questions"** — accordion list. Each item: mono index (`01`), question, a category
    `Chip` (Behavioural/Technical/Leadership in purple). Expanding reveals a **STAR answer** block:
    `s2` bg with a 2px green left-border, a "STAR ANSWER · from your story bank" label, and the answer.

- **Mobile:** list is the screen; tapping a session pushes a full-screen detail overlay (back chevron).
- **Desktop:** master-detail — 320px session list column + detail pane side by side.

---

### 5 · REVIEW (the human-in-the-loop decision gate)
**Purpose:** The key approval moment. Opened from Today or Stream. Works as a **queue** — approving
or rejecting advances to the next item ("Application _n_ of _N_") and closes when done.

**Contents (both layouts):**
- Job header: title + company·loc·**rate**.
- **Score card:** large `ScorePill` + verdict ("Excellent match" if ≥0.9 else "Strong match") +
  "Scored by Scorer across 4 dimensions", then 4 `DimBar`s (Skills 92 / Experience 85 / Rate 90 /
  Location 80) — thin progress bars, colour-graded (≥85 green, ≥70 accent, else amber).
- **Tailored docs:** "Tailored by Tailor" + "ATS {n}%" chip; **CV / Cover letter** tab toggle; a
  faux document preview (light `#f7f7f4` paper with grey text lines and accent-coloured headers).
- An accent info strip: *"Approve → moves to **Applied**. Mark an interview and **Coach** preps automatically."*
- **Actions:** ghost **Reject** + primary **Approve & apply** (desktop also has a soft **Edit CV**).

- **Mobile:** full-screen overlay (slide-up), sticky bottom action bar.
- **Desktop:** centered **modal** (920px, blurred backdrop), two-column body (score+why-you-fit left,
  docs right), action bar in the footer. Desktop adds a **"Why you're a fit"** checklist
  (3 green-check bullets) under the score.

---

## Interactions & Behavior

- **Navigation:** tab bar (mobile) / sidebar (desktop) switches the active screen. State only — no routing in the prototype, but in the real app these should be App-Router routes (`/today`, `/stream`, `/tracker`, `/prep`) so they're linkable, matching the existing Next.js structure.
- **Open Review:** tapping a ready-card row, a Stream card/row, or "Review & approve / Review all" opens the Review queue with one or many job ids.
- **Approve:** sets the job's `state → 'applied'`, shows a success toast ("Applied · moved to Tracker → Applied"), and advances the queue. The role then appears in Tracker's Applied column and disappears from Stream's open list. The Today funnel/counts and sidebar badges update live.
- **Reject:** sets `state → 'rejected'`, toast "Dismissed", advances queue.
- **Queue advance:** `idx+1`; if past the end, close the overlay/modal.
- **Prep accordion:** single-open; clicking an open item closes it.
- **Toast:** auto-dismisses after 2.6s. Mobile: above the tab bar; desktop: bottom-center.
- **Transitions:** overlays/modals fade+rise ~0.18–0.22s ease-out. Respect `prefers-reduced-motion`.
- **Hover (desktop):** rows/buttons should have subtle hover affordances per the codebase's conventions (the prototype omits hover for brevity — add them).
- **Empty states:** Today shows "Approval queue clear" when no ready items; Stream shows "Nothing in this stage"; Tracker columns show dashed placeholders.

---

## State Management

Minimal client state (the prototype uses React `useState`; map onto the codebase's data layer / API).

**Per-job state machine:** `new → scored → tailoring → ready → applied → (interview → offered)`, plus
`parked` (scored but below the user's match threshold) and `rejected`. The prototype seeds jobs across
`ready` / `tailoring` / `parked`, plus separate seed lists for `applied` and `interview` (shown in
Tracker/Prep).

State variables:
- `items` — array of job objects: `{ id, title, company, loc, rate, score (0–1), ats, state, age }`.
- `activeTab` — today | stream | track | prep.
- `review` — `{ queue: id[], idx }` or null.
- `toast` — message string or null (timeout-cleared).
- Stream filter, Prep selected session + open accordion index.

Derived: ready count (drives badges, funnel, the Today approve card), Stream filter counts, Tracker
column membership.

**Data requirements for the real app:** the agent pipeline already exists server-side in Hatch
(`backend/`). The UI needs endpoints/streams for: the agent run summary + per-stage counts (Today
briefing & PipelineRail), the job list with stage/score/ATS (Stream/Tracker), the tailored CV +
cover-letter + score breakdown (Review), interview prep content (Prep), and an **approve/reject**
mutation that transitions job state and triggers the apply action. Relative times via `date-fns`
(already a dependency).

---

## Assets

No external image assets. Everything is drawn with CSS + inline-SVG icons:
- **Icons:** map to **lucide-react** (or the codebase's icon set). List in the Icons token section.
- **Document previews** in Review are faux CSS placeholders (light paper + grey bars) — in production,
  render the real generated CV/cover-letter (PDF/HTML preview).
- **User avatar** is a CSS gradient with initials — swap for the real profile photo if available.
- **Fonts:** Inter + Roboto Mono (Google Fonts in the prototype; the repo already vendors fonts via
  `@fontsource` — use that mechanism).

---

## Screenshots

Rendered PNGs of every screen live in `screenshots/` for quick visual reference:

| File | Screen |
|---|---|
| `desktop-1-today.png` | Desktop — Today cockpit (hero pipeline rail + Needs-you + activity/stats) |
| `desktop-2-stream.png` | Desktop — Stream table with inline pipeline tracks |
| `desktop-3-tracker.png` | Desktop — Tracker kanban (Discovered/Applied/Interview/Offered) |
| `desktop-4-prep.png` | Desktop — Prep master-detail (sessions + questions + STAR answers) |
| `desktop-5-review-modal.png` | Desktop — Review decision modal (score + why-fit + tailored docs) |
| `mobile-1-today.png` | Mobile — Today cockpit |
| `mobile-2-stream.png` | Mobile — Stream cards |
| `mobile-3-tracker.png` | Mobile — Tracker (horizontally-scrolling columns) |
| `mobile-4-prep.png` | Mobile — Prep session list |

> The **mobile Review** screen is a full-screen slide-up overlay; its layout mirrors the desktop
> Review modal (`desktop-5-review-modal.png`) — same content, stacked single-column with a sticky
> bottom action bar. Open `Hatch Prototype.html` and tap "Review & approve" to see it live.
> The accent in these renders is the user-selected teal (`#36c5a8`).

## Files

In this bundle (design references):

| File | What it is |
|---|---|
| `Hatch Prototype.html` | **Mobile** Direction A — interactive (open in a browser). Primary target. |
| `Hatch Desktop.html` | **Desktop** Direction A — interactive, sidebar-led. |
| `Hatch Redesign (exploration).html` | Side-by-side canvas: the thesis + Direction A & B options. Context only — implement A. |
| `hatch-ui.jsx` | **Shared design system** — `HT` tokens, agent identities, icons, and all primitives (AgentBadge, StageTrack, ScorePill, Chip, Dot, Btn, Card, etc.). Start here. |
| `proto-app.jsx` | Mobile app — all screens, navigation, approve loop, overlays. |
| `desktop-app.jsx` | Desktop app — sidebar/topbar shell + all screens + Review modal. |
| `screens-a.jsx` / `screens-b.jsx` | Static screen sources used by the exploration canvas. |
| `ios-frame.jsx`, `tweaks-panel.jsx`, `design-canvas.jsx` | Prototype scaffolding only — **not** part of the product (device bezel, tweak panel, canvas). Ignore for implementation. |

**Recommended reading order:** `hatch-ui.jsx` (tokens + primitives) → `desktop-app.jsx` or
`proto-app.jsx` (screens + behaviour). Cross-reference the existing repo: `frontend/src/app/globals.css`
(tokens), `frontend/src/components/` (existing components to extend), `frontend/src/app/` (routes).

### Tweaks (optional, prototype-only)
Both prototypes expose a Tweaks panel: **agent first-person voice** on/off (affects briefing copy) and
**primary accent** colour (user chose teal `#36c5a8`). These are demonstration toggles — implement
voice as a copy variant and accent as a theme token; the Tweaks panel UI itself is not part of the product.
