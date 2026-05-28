# Hatch — Design-to-Implementation Gap Analysis & Claude Code Instructions

**Date:** 28 May 2026
**Design source:** Job_board.zip (6 pages, shell, styles, data, icons)
**Implementation:** https://github.com/arvindsoni2/hatch

---

## Summary

The design system (styles.css, shell.jsx, 6 page components) defines a polished, dark-first UI with a **sidebar navigation**, inbox-style approval queue, company colour marks, AI rationale cards, and a KPI-driven dashboard. Claude Code implemented the dashboard (page.tsx) and the CSS variables, but several structural differences remain between the design and the implementation.

---

## Gap 1: Navigation — sidebar vs top bar (MAJOR)

### Design spec (shell.jsx)
- **Sidebar navigation** — fixed left panel, 248px wide
- Grouped nav items: Discover (Home, Approval queue, Approved), Track (Pipeline, Analytics), Prepare (Interview prep)
- Brand mark with "Hatch" + "beta" tag
- User profile chip at the bottom (avatar, name, role, settings icon)
- Badges on nav items (7 for approval queue, 12 for pipeline)

### Current implementation (Navigation.tsx)
- **Top bar** — horizontal nav across the top, hidden on mobile
- Flat list of 6 items (no grouping)
- No user profile chip
- No sidebar

### What to change

The design uses a sidebar because it provides a better information hierarchy — grouped nav sections (Discover / Track / Prepare) help users understand the workflow. The current top bar flattens this hierarchy.

However, **the sidebar must collapse on mobile.** The design doesn't show mobile, but the correct pattern is:
- Desktop (≥ 1024px): persistent sidebar
- Tablet (768-1023px): collapsible sidebar (hamburger trigger)
- Mobile (< 768px): bottom tab bar (existing BottomNav.tsx)

---

## Gap 2: Approval queue — inbox pattern vs jobs listing (MAJOR)

### Design spec (pages/jobs.jsx)
- **Email inbox pattern**: left panel list + right panel detail
- List shows company mark, title, match score, salary chip, level chip, posted time
- Detail panel shows: company mark, title, match score (large), metadata chips, approve/pass/save buttons, AI rationale card, role description, responsibilities, skills matched vs required
- Tabs: All / High match / Recent
- Toast notification on approve/pass with undo possibility
- "Inbox zero" empty state when all reviewed
- Called "Approval queue" in the nav, not "Jobs"

### Current implementation
- Standard job listing table/cards at `/jobs`
- Separate approval page at `/approvals`
- No inbox split-panel pattern
- No AI rationale display
- No skills matched vs required display

### What to change

The design's inbox pattern is the core interaction — where users spend most of their time. This needs to be built as a new component, replacing or significantly reworking the approvals page.

---

## Gap 3: Home page — hero section + KPI strip (MODERATE)

### Design spec (pages/home.jsx)
- **Hero section**: personalised greeting + summary ("7 new roles overnight, 3 interviews this week") + two CTA buttons (Review roles, Open pipeline)
- **Status card** on the right of the hero: weekly progress (roles reviewed 23/30, applications sent 9, interviews booked 3, avg response time 2.4 days) with an "On track" chip
- **KPI strip**: 4 metrics (AI-sourced 287, Approval rate 22%, Applied 42, Offers 2) each with delta arrows
- **Top pick card**: the highest-match job with company mark, match score, salary/type/level chips, AI rationale, and approve/pass/save buttons
- **Upcoming interviews card**: list of interviews this week with company marks and "Prep →" links
- **Two-column body**: left (top pick + upcoming) / right (activity + sources)

### Current implementation (page.tsx)
- Has agent status banner, action cards, top matches list, pipeline bar, activity timeline
- Missing: hero greeting with summary text, status card with weekly goals, KPI strip with deltas, top pick card with inline approve/pass, upcoming interviews, source breakdown bars

### What to change

The dashboard needs to be restructured to match the design's visual hierarchy: hero → KPIs → two-column content.

---

## Gap 4: Pipeline — drag-and-drop Kanban (MODERATE)

### Design spec (pages/pipeline.jsx)
- Full drag-and-drop Kanban with columns: Saved → Applied → Interview → Offer → Closed
- Each card: company mark, title, company name, stage badge, days counter
- Column headers with coloured top border and count
- Drag states with overlay styling

### Current implementation
- Kanban exists at `/applications` but uses a different column structure (Discovered → Shortlisted → Applied → Interview → Offered)
- May not have smooth drag-and-drop

### What to change

Align column names and colours with the design. Ensure drag-and-drop works smoothly. Add company colour marks to cards.

---

## Gap 5: Analytics — funnel + donut + bar charts (MODERATE)

### Design spec (pages/analytics.jsx)
- Time range selector (7d / 30d / 90d / All) with Compare and Export buttons
- KPI strip: application rate, phone screen rate, onsite conversion, time-to-offer
- Horizontal funnel bars with counts and conversion percentages
- Donut chart for response outcomes (phone screen, onsite, offer, closed)
- Weekly volume bar chart
- Role type distribution (sparkline bars)
- Source performance table with success rates

### Current implementation
- Has some analytics at `/analytics` but with different metrics and layout
- Missing: time range selector, donut chart, conversion percentages on funnel, weekly bar chart, source performance table

---

## Gap 6: Interview prep — tabbed with per-company cards (MODERATE)

### Design spec (pages/interview.jsx)
- Three tabs: Per-company prep / Question bank / AI mock interview
- Per-company: cards with company marks, role, stage, progress bar, task count
- Question bank: categorised questions (behavioural, technical, etc.) with expandable answers and "Practice" buttons
- AI mock interview: chat-style interface with system/user messages, voice recording controls

### Current implementation
- Coach page exists at `/coach` but is simpler
- Missing: per-company prep cards with progress, AI mock chat interface, practice/voice buttons

---

## Gap 7: Company colour marks (VISUAL)

### Design spec
- Every company has a colour + initial displayed as a coloured circle/square throughout the UI
- `CompanyMark` component renders consistently across all pages

### Current implementation
- No `CompanyMark` component
- Companies shown as text only

---

## Gap 8: Design tokens — fonts and theme toggle (VISUAL)

### Design spec (styles.css)
- Uses 'Geist' as primary font, 'Geist Mono' for monospace
- Dark theme is DEFAULT, light is opt-in
- Theme toggle via `data-theme="light"` attribute on root

### Current implementation (globals.css)
- Uses 'Inter' as primary font (close but not identical)
- Dark/light theme variables are defined but theme toggle implementation uses Tailwind `dark:` classes AND CSS variables simultaneously — potential conflict
- Implementation has both `:root:not(.dark)` and `[data-theme="light"]` selectors — could cause specificity issues

### What to change

Standardise on one theme mechanism: either `data-theme` attribute (matching the design) or Tailwind's `dark:` class — not both. The design uses `data-theme`, which is cleaner for CSS variables.

---

## Claude Code Instructions

### Prompt 1: Sidebar navigation (replaces top bar)

```
Replace the top bar navigation with a sidebar matching the design spec 
in shell.jsx.

1. Create frontend/src/components/Sidebar.tsx:
   - Fixed left sidebar, 248px wide (var(--sidebar-width))
   - Brand section: "H" mark (indigo square) + "Hatch" text + "beta" tag
   - Three nav groups with labels: "Discover" (Home, Approval queue, Approved), 
     "Track" (Pipeline, Analytics), "Prepare" (Interview prep)
   - Each nav item: icon (lucide-react) + label + optional badge
   - Active state: accent background
   - User chip at bottom: initials avatar + name + role from profile + 
     settings gear icon
   - Use CSS variables from the design (var(--surface), var(--border), etc.)

2. Update frontend/src/app/layout.tsx:
   - Desktop (≥ 1024px): render Sidebar + main content area with 
     left margin of var(--sidebar-width)
   - Tablet (768-1023px): sidebar hidden, show hamburger button in a 
     minimal top bar, sidebar slides in as overlay
   - Mobile (< 768px): no sidebar, use existing BottomNav

3. Create frontend/src/components/Topbar.tsx matching the design:
   - Page title + subtitle (dynamic per route)
   - Search input with ⌘K shortcut hint
   - Theme toggle button
   - Notifications bell button
   - Only renders in the main content area (not in sidebar)

4. Remove or hide the old Navigation.tsx on desktop. Keep it only 
   as a fallback for the tablet hamburger state.

5. Update globals.css:
   - Add sidebar-specific styles from the design's styles.css:
     .sidebar, .brand, .brand-mark, .nav-group-label, .nav-item, 
     .nav-badge, .sidebar-foot, .user-chip, .avatar
   - Copy these exactly from the design's styles.css

Style reference: see shell.jsx lines 39-82 and styles.css sidebar section.
```

### Prompt 2: Approval queue inbox pattern

```
Rebuild the approvals page as an inbox-style split panel matching 
pages/jobs.jsx from the design.

1. Create frontend/src/app/approvals/page.tsx (or update existing):
   - Split layout: left list panel (40%) + right detail panel (60%)
   - Left panel:
     - Header: "{count} for review" + tabs (All / High match / Recent)
     - Scrollable list of job cards, each showing:
       CompanyMark, title, match score, company + location, 
       salary chip, level chip, posted time
     - Selected state: accent border left
     - Empty state: "Inbox zero" with checkmark
   - Right panel:
     - Company mark (large) + title + company + match score (large, accent)
     - Metadata chips: salary, location, type, level, posted
     - Action buttons: Approve (green), Pass (red), Save for later
     - AI rationale card with sparkle icon: "Why Hatch surfaced this"
     - About the role section
     - "What you'll do" responsibilities list
     - Skills section: matched (green check + tag) vs required (plain tag)
   - Toast notification on approve/pass/save with auto-dismiss
   
2. On mobile (< 768px): show list only, tapping opens detail as 
   full-screen overlay with back button.

3. Create frontend/src/components/CompanyMark.tsx:
   - Takes company name, generates a deterministic colour from the 
     name (hash to hue) and shows the first letter
   - Sizes: sm (28px), md (36px), lg (48px)
   - Used throughout all pages

4. Connect to backend: fetch pending approvals via existing API, 
   map to the inbox items format.

Data shape reference: data.js inbox array (lines 21-130).
Style reference: pages/jobs.jsx + styles.css .inbox-* classes.
```

### Prompt 3: Home page redesign to match design

```
Redesign the home dashboard page to match pages/home.jsx from the design.

1. Hero section (top):
   - Left: personalised greeting ("Good morning, {name}"), summary text 
     with bold count of new roles and interviews this week, two CTA 
     buttons (Review N new roles → /approvals, Open pipeline → /applications)
   - Right: weekly status card with stats (roles reviewed, applications 
     sent, interviews booked, avg response time) and an "On track" chip
   
2. KPI strip (below hero):
   - 4 cards in a grid: AI-sourced (total discovered), Approval rate %, 
     Applied count, Offers count
   - Each with delta arrow (up green or down red) comparing vs last period
   
3. Two-column body:
   - Left column:
     a. Top pick card: highest-match job with CompanyMark, match score, 
        salary/type/level chips, AI rationale, inline approve/pass/save buttons
     b. Upcoming this week: list of interviews with CompanyMark, role, 
        date/time, stage, "Prep →" button
   - Right column:
     a. Recent activity feed: coloured dots + text + timestamp
     b. Source breakdown: bar charts showing where Hatch found jobs

4. Use CSS variables throughout — no Tailwind colour classes for 
   surfaces/borders/text.

5. Fetch all data from existing API endpoints. For data not yet 
   available (weekly goals, delta comparisons), use reasonable defaults 
   or zero values with "Set weekly goals" link.

Layout reference: pages/home.jsx (full file).
Style reference: styles.css .hero, .kpi-grid, .home-grid, .card-* classes.
```

### Prompt 4: Analytics page redesign

```
Rebuild the analytics page to match pages/analytics.jsx from the design.

1. Time range selector: 7d / 30d / 90d / All tabs + date range display 
   + Compare and Export buttons

2. KPI strip: application rate, phone screen rate, onsite conversion, 
   time-to-offer — each with delta

3. Funnel section: horizontal bars showing pipeline stages with counts 
   and conversion percentages between stages

4. Two-column section:
   - Left: outcome donut chart (SVG) showing phone screen, onsite, 
     offer, closed
   - Right: weekly volume stacked bar chart

5. Bottom: source performance table with scraper name, total found, 
   applied count, and success rate percentage

Connect to existing analytics API endpoints. Use CSS from the design 
system for chart styling.

Reference: pages/analytics.jsx (full file).
```

### Prompt 5: Pipeline Kanban alignment

```
Update the pipeline/kanban page to match pages/pipeline.jsx from the design.

1. Column headers: coloured top border + column name + count badge
2. Columns: Saved → Applied → Interview → Offer → Closed
3. Cards: CompanyMark + title + company + stage info + days counter
4. Drag-and-drop: smooth drag with overlay styling
5. Summary stats bar at top: total cards, cards per stage
6. Add application button per column

Reference: pages/pipeline.jsx (full file).
```

### Prompt 6: Interview prep page with tabs

```
Rebuild the coach/interview prep page to match pages/interview.jsx.

1. Three tabs: Per-company prep / Question bank / AI mock interview

2. Per-company tab:
   - Grid of company prep cards, each with: CompanyMark, company name, 
     role, stage, progress bar, task count, status chip (Ready/In progress/Catch up)
   - Clicking opens the prep detail

3. Question bank tab:
   - Category filter: Behavioral / Technical / System Design / Product / Leadership
   - Expandable question cards: question text, model answer (collapsed), 
     "Practice" button, difficulty chip
   - Progress tracking: answered/total per category

4. AI mock interview tab:
   - Chat interface: system messages (questions) + user messages (answers)
   - Voice recording controls
   - "Start mock interview" button to begin
   - Session history

Reference: pages/interview.jsx (full file).
```

### Prompt 7: Theme system standardisation

```
Fix the dual theme system conflict.

1. Standardise on data-theme attribute (matching the design system):
   - Remove all Tailwind dark: class usage from components
   - Use CSS variables exclusively for colours
   - ThemeToggle should set data-theme="dark" or data-theme="light" 
     on the html element + localStorage
   - Default: dark (matching the design)

2. Update globals.css:
   - Remove the conflicting .dark selector
   - Keep only :root (dark default) and [data-theme="light"]
   - Copy any missing CSS variables from the design's styles.css

3. Update tailwind.config:
   - Set darkMode: ['selector', '[data-theme="dark"]'] 
     (if any Tailwind dark: classes remain) or remove darkMode config 
     entirely if all colours use CSS variables

4. Font: update --font-sans to include 'Geist' before 'Inter' 
   (matching the design). If Geist isn't available, Inter is the fallback.

5. Verify both themes render correctly on all pages.
```
