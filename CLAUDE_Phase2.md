# JobPilot v3 Phase 2 — PWA + Cross-Platform + Locale Expansion

## Context

Phase 1 is complete: 31 backend test files, 9 frontend test files, auto-apply removed, .gitignore in place, CI pipeline running, onboarding decomposed into step components, and security fixes applied.

Phase 2 delivers: PWA installability, responsive design for all 22 pages, bottom navigation for mobile, offline read mode, locale packs for India/UK/Dubai/Ireland, and remaining IR35 hardcoding removal (12 files still reference it).

**Target regions:** India (in), United Kingdom (uk), United Arab Emirates (ae), Ireland (ie). Other countries can configure via `_template.yaml` — full support deferred to v4.

## Critical rules

1. **Mobile-first.** Write the 375px layout first, then add `md:` and `lg:` breakpoints.
2. **Test every change.** Run `make test` after each prompt. No regressions.
3. **Touch targets ≥ 44px.** Every button, link, and interactive element.
4. **CSS variables for all colours.** Dark mode must work — no hardcoded hex values.
5. **No new UK-specific hardcoding.** All locale-specific values come from locale packs.

---

## Prompt 1: Create Dubai and Ireland locale packs

Create locale packs for the two missing target regions.

### 1a. Create `locales/ae.yaml` (United Arab Emirates / Dubai)

```yaml
id: "ae"
name: "United Arab Emirates"
flag: "🇦🇪"

currency: "AED"
currency_symbol: "د.إ"
default_rate_type: "monthly"

rate_types:
  - id: "monthly"
    label: "Monthly salary"
    example: "AED 25,000/mo"
  - id: "annual"
    label: "Annual package"
    example: "AED 300,000/yr"

legal_fields:
  - id: "visa_status"
    label: "Visa status"
    type: "select"
    options:
      - value: "resident"
        label: "UAE resident visa"
      - value: "visit"
        label: "Visit visa (needs sponsorship)"
      - value: "golden"
        label: "Golden visa holder"
      - value: "freelance"
        label: "Freelance permit"
      - value: "any"
        label: "Any / not specified"
    default: "any"
  - id: "notice_period"
    label: "Notice period"
    type: "select"
    options:
      - value: "immediate"
        label: "Immediate"
      - value: "30_days"
        label: "30 days"
      - value: "60_days"
        label: "60 days"
      - value: "90_days"
        label: "90 days"
    default: "30_days"

job_boards:
  - name: "linkedin"
    label: "LinkedIn"
    scraper: "LinkedInScraper"
    default_enabled: true
  - name: "bayt"
    label: "Bayt.com"
    scraper: "BaytScraper"
    default_enabled: true
  - name: "indeed_ae"
    label: "Indeed UAE"
    scraper: "IndeedScraper"
    base_url: "https://ae.indeed.com"
    default_enabled: true
  - name: "gulftalent"
    label: "GulfTalent"
    scraper: "GulfTalentScraper"
    default_enabled: false
  - name: "naukrigulf"
    label: "Naukri Gulf"
    scraper: "NaukriGulfScraper"
    default_enabled: false

scoring_defaults:
  weights:
    skill_match: 0.40
    experience_match: 0.25
    compensation_match: 0.20
    location_match: 0.15
  shortlist_threshold: 0.70

onboarding_defaults:
  contract_type: "permanent"
  remote_preference: "onsite"
  scrape_interval_hours: 6
  example_city: "Dubai"
  example_role: "Project Manager"
```

### 1b. Create `locales/ie.yaml` (Ireland)

```yaml
id: "ie"
name: "Ireland"
flag: "🇮🇪"

currency: "EUR"
currency_symbol: "€"
default_rate_type: "annual"

rate_types:
  - id: "annual"
    label: "Annual salary"
    example: "€85,000/yr"
  - id: "daily"
    label: "Daily rate"
    example: "€600/day"
  - id: "hourly"
    label: "Hourly rate"
    example: "€75/hr"

legal_fields:
  - id: "work_permit"
    label: "Work authorisation"
    type: "select"
    options:
      - value: "citizen"
        label: "Irish / EU citizen"
      - value: "stamp4"
        label: "Stamp 4 (unrestricted)"
      - value: "critical_skills"
        label: "Critical Skills permit"
      - value: "general_permit"
        label: "General Employment permit"
      - value: "requires_sponsorship"
        label: "Requires sponsorship"
      - value: "any"
        label: "Any"
    default: "any"
  - id: "contract_type"
    label: "Employment type"
    type: "select"
    options:
      - value: "permanent"
        label: "Permanent"
      - value: "contract"
        label: "Contract (B2B)"
      - value: "fixed_term"
        label: "Fixed-term"
      - value: "any"
        label: "Any"
    default: "any"

job_boards:
  - name: "linkedin"
    label: "LinkedIn"
    scraper: "LinkedInScraper"
    default_enabled: true
  - name: "irishjobs"
    label: "IrishJobs.ie"
    scraper: "IrishJobsScraper"
    default_enabled: true
  - name: "indeed_ie"
    label: "Indeed Ireland"
    scraper: "IndeedScraper"
    base_url: "https://ie.indeed.com"
    default_enabled: true
  - name: "jobs_ie"
    label: "Jobs.ie"
    scraper: "JobsIeScraper"
    default_enabled: false
  - name: "reed_ie"
    label: "Reed Ireland"
    scraper: "ReedScraper"
    base_url: "https://www.reed.co.uk"
    default_enabled: false

scoring_defaults:
  weights:
    skill_match: 0.35
    experience_match: 0.30
    compensation_match: 0.20
    location_match: 0.15
  shortlist_threshold: 0.75

onboarding_defaults:
  contract_type: "permanent"
  remote_preference: "hybrid"
  scrape_interval_hours: 4
  example_city: "Dublin"
  example_role: "Software Engineer"
```

### 1c. Create stub scrapers for new boards

Create minimal scraper stubs so the scraper registry doesn't break. Each scraper should extend the base scraper and log a "not yet implemented" message:

- `backend/app/scrapers/bayt.py` — BaytScraper for UAE
- `backend/app/scrapers/gulftalent.py` — GulfTalentScraper for UAE
- `backend/app/scrapers/naukrigulf.py` — NaukriGulfScraper for UAE
- `backend/app/scrapers/irishjobs.py` — IrishJobsScraper for Ireland
- `backend/app/scrapers/jobs_ie.py` — JobsIeScraper for Ireland

Each stub should:
```python
from app.scrapers.base import BaseScraper

class BaytScraper(BaseScraper):
    """Bayt.com scraper for UAE job market. TODO: implement."""
    
    async def scrape(self, keywords: list[str], **kwargs) -> list[dict]:
        self.logger.info("BaytScraper not yet implemented — returning empty results")
        return []
```

### 1d. Update scraper registry

In `backend/app/scrapers/registry.py` (or wherever scrapers are registered), add the new scraper classes with their locale tags:

```python
# UAE scrapers
"bayt": {"class": BaytScraper, "locales": ["ae"]},
"gulftalent": {"class": GulfTalentScraper, "locales": ["ae"]},
"naukrigulf": {"class": NaukriGulfScraper, "locales": ["ae"]},

# Ireland scrapers  
"irishjobs": {"class": IrishJobsScraper, "locales": ["ie"]},
"jobs_ie": {"class": JobsIeScraper, "locales": ["ie"]},

# Multi-locale scrapers — add new locales
"linkedin": {"class": LinkedInScraper, "locales": ["uk", "us", "in", "de", "ae", "ie"]},
"indeed": {"class": IndeedScraper, "locales": ["uk", "us", "in", "de", "ae", "ie"]},
```

### 1e. Update onboarding locale cards

In `frontend/src/components/onboarding/StepJobSearch.tsx`, update the locale selection to show all 4 target regions plus an "Other" option:

```
🇬🇧 UK    🇮🇳 India    🇦🇪 UAE    🇮🇪 Ireland    🌍 Other
```

"Other" loads `_template.yaml` with generic defaults and shows a message: "Configure your region in Settings after setup."

### 1f. Write tests

- Backend: test that `ae.yaml` and `ie.yaml` load correctly via the locale service
- Frontend: test that StepJobSearch renders all 5 locale cards

Run: `make test`

---

## Prompt 2: PWA foundation — manifest, service worker, icons

### 2a. Install PWA dependency

```bash
cd frontend && npm install @ducanh2912/next-pwa
```

### 2b. Update next.config.js

```javascript
const withPWA = require("@ducanh2912/next-pwa").default({
  dest: "public",
  disable: process.env.NODE_ENV === "development",
  register: true,
  skipWaiting: true,
  runtimeCaching: [
    {
      urlPattern: /^https?:\/\/.*\/api\/.*/,
      handler: "StaleWhileRevalidate",
      options: {
        cacheName: "api-cache",
        expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 },
      },
    },
    {
      urlPattern: /\/_next\/static\/.*/,
      handler: "CacheFirst",
      options: {
        cacheName: "static-cache",
        expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 * 30 },
      },
    },
  ],
});

const nextConfig = {
  // ... existing config ...
};

module.exports = withPWA(nextConfig);
```

### 2c. Create manifest

Create `frontend/public/manifest.json`:
```json
{
  "name": "JobPilot — Autonomous Job Search",
  "short_name": "JobPilot",
  "description": "AI-powered job search automation with human-in-the-loop approvals",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#f8fafc",
  "theme_color": "#4f46e5",
  "orientation": "any",
  "categories": ["productivity", "business"],
  "icons": [
    { "src": "/icons/icon-72x72.png", "sizes": "72x72", "type": "image/png" },
    { "src": "/icons/icon-96x96.png", "sizes": "96x96", "type": "image/png" },
    { "src": "/icons/icon-128x128.png", "sizes": "128x128", "type": "image/png" },
    { "src": "/icons/icon-144x144.png", "sizes": "144x144", "type": "image/png" },
    { "src": "/icons/icon-152x152.png", "sizes": "152x152", "type": "image/png" },
    { "src": "/icons/icon-192x192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-384x384.png", "sizes": "384x384", "type": "image/png" },
    { "src": "/icons/icon-512x512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icons/icon-maskable-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

### 2d. Generate PWA icons

Use the existing "JP" brand mark (indigo background, white text) to generate all required icon sizes. Create a simple script or use a tool like `pwa-asset-generator`:

Create `frontend/public/icons/` directory with all sizes. At minimum, create the icons programmatically using a canvas script or SVG → PNG conversion:

```bash
# In frontend/ directory, create a generate-icons.js script that creates 
# PNG files from the JP logo at all required sizes.
# Or manually create icon-192x192.png and icon-512x512.png as indigo 
# rounded squares with white "JP" text.
```

### 2e. Update layout.tsx

Add to `frontend/src/app/layout.tsx` `<head>`:
```html
<link rel="manifest" href="/manifest.json" />
<meta name="theme-color" content="#4f46e5" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="default" />
<link rel="apple-touch-icon" href="/icons/icon-192x192.png" />
```

### 2f. Create offline fallback

Create `frontend/public/offline.html`:
```html
<!DOCTYPE html>
<html><head><title>JobPilot — Offline</title>
<style>body{font-family:system-ui;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f8fafc;color:#1e293b;text-align:center}
.box{max-width:400px;padding:2rem}h1{font-size:1.5rem;margin:0 0 1rem}p{color:#64748b;line-height:1.6}</style>
</head><body><div class="box"><h1>You're offline</h1><p>JobPilot needs a connection to your backend. Check your network and try again.</p><button onclick="location.reload()" style="margin-top:1rem;padding:12px 24px;background:#4f46e5;color:white;border:none;border-radius:8px;cursor:pointer;font-size:14px">Retry</button></div></body></html>
```

### 2g. Run Lighthouse PWA audit

After building (`cd frontend && npm run build`), serve and run Lighthouse to verify installability.

---

## Prompt 3: Responsive navigation — bottom tab bar on mobile

### 3a. Create BottomNav component

Create `frontend/src/components/BottomNav.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Search, CheckSquare, Columns3, BarChart3, GraduationCap } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchPendingApprovals } from "@/lib/api";

const BOTTOM_NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home, exact: true },
  { href: "/jobs", label: "Jobs", icon: Search, exact: false },
  { href: "/approvals", label: "Approvals", icon: CheckSquare, exact: false, badge: true },
  { href: "/applications", label: "Pipeline", icon: Columns3, exact: false },
  { href: "/analytics", label: "Analytics", icon: BarChart3, exact: false },
  { href: "/coach", label: "Prep", icon: GraduationCap, exact: false },
];

export function BottomNav() {
  const pathname = usePathname();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    async function loadCount() {
      try {
        const approvals = await fetchPendingApprovals();
        setPendingCount(approvals.length);
      } catch { /* non-critical */ }
    }
    void loadCount();
    const interval = setInterval(() => void loadCount(), 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-slate-200 bg-white/95 backdrop-blur-sm pb-safe md:hidden">
      <div className="flex items-stretch">
        {BOTTOM_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href) && item.href !== "/";

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] transition-colors min-h-[44px] justify-center ${
                isActive ? "text-indigo-600 font-medium" : "text-slate-400"
              }`}
            >
              <span className="relative">
                <Icon size={20} />
                {item.badge && pendingCount > 0 && (
                  <span className="absolute -top-1.5 -right-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-medium text-white">
                    {pendingCount}
                  </span>
                )}
              </span>
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
```

### 3b. Update Navigation.tsx

Add `md:hidden` / `hidden md:flex` to make the top bar desktop-only:

In the existing `Navigation` component, add `className="hidden md:block"` to the `<header>` wrapper so it's hidden on mobile.

### 3c. Update layout.tsx

Import and render both navigations:
```tsx
import { Navigation } from "@/components/Navigation";
import { BottomNav } from "@/components/BottomNav";

// In the layout body:
<Navigation />        {/* Shows on md+ only */}
<main className="pb-20 md:pb-0">  {/* Bottom padding for mobile nav */}
  {children}
</main>
<BottomNav />          {/* Shows on mobile only */}
```

### 3d. Create useMediaQuery hook

Create `frontend/src/hooks/useMediaQuery.ts`:
```typescript
import { useState, useEffect } from "react";

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const listener = (e: MediaQueryListEvent) => setMatches(e.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [query]);
  return matches;
}

export const useIsMobile = () => useMediaQuery("(max-width: 767px)");
export const useIsTablet = () => useMediaQuery("(min-width: 768px) and (max-width: 1023px)");
export const useIsDesktop = () => useMediaQuery("(min-width: 1024px)");
```

### 3e. Write tests

- Test BottomNav renders all items
- Test BottomNav shows approval badge
- Test Navigation hidden class on mobile

Run: `make test`

---

## Prompt 4: Responsive redesign — dashboard, jobs, approvals

Make the three most-used pages fully responsive. Mobile-first approach.

### 4a. Dashboard (page.tsx)

Current: 3-column grid for action cards, side-by-side pipeline + activity.

Mobile (< 768px):
- Action cards: stack vertically, full width
- Top matches: full-width cards, compact layout
- Pipeline bar: full width, smaller labels
- Activity: full width below pipeline
- Agent status strip: wrap to 2 lines if needed

Changes:
```
grid-cols-1 md:grid-cols-3     (action cards)
flex-col md:flex-row           (pipeline + activity side-by-side)
```

### 4b. Jobs listing (jobs/page.tsx)

Current: table layout with many columns.

Mobile (< 768px):
- Switch from table to card stack
- Each card: score badge + title + company + location + status pill
- No table headers — they're redundant on cards
- Filters: collapse into a "Filters" button that opens a sheet/modal
- Search: full width

Desktop (≥ 768px):
- Keep table layout (or large card grid)

### 4c. Approval detail (approvals/[id]/page.tsx)

Current: likely side-by-side layout.

Mobile (< 768px):
- Stack everything: score breakdown → CV preview → cover letter → actions
- Action buttons: full width, sticky at bottom
- Score breakdown: horizontal bar charts instead of radar

Desktop (≥ 768px):
- Side-by-side: score + preview on left, documents on right

### 4d. General rules for all pages

- Replace any `px-8` or wider horizontal padding with `px-4 md:px-6 lg:px-8`
- Replace fixed widths with `max-w-7xl mx-auto w-full`
- All grids: start with `grid-cols-1` and add `md:grid-cols-2 lg:grid-cols-3`
- All `hidden` elements should use `hidden md:block` or `md:hidden` consciously
- All buttons: `min-h-[44px]` on mobile

Run: `make test` — no visual tests break.

---

## Prompt 5: Responsive redesign — pipeline, analytics, coach, settings

### 5a. Pipeline/Kanban (applications/page.tsx)

Mobile (< 768px):
- Horizontal scroll with CSS `scroll-snap-type: x mandatory`
- Each Kanban column: `min-width: 280px`, `scroll-snap-align: start`
- Stats cards: 2×2 grid instead of 4 across
- "New Application" button: floating action button (FAB) at bottom-right

```css
.kanban-container {
  display: flex;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  -webkit-overflow-scrolling: touch;
  gap: 12px;
  padding-bottom: 8px;
}
.kanban-column {
  min-width: 280px;
  scroll-snap-align: start;
  flex-shrink: 0;
}
```

### 5b. Analytics (analytics/page.tsx)

Mobile (< 768px):
- Stats cards: 2×3 grid (2 per row, 3 rows) instead of 6 across
- All charts: full width, stacked vertically
- Agent performance table: horizontal scroll with sticky first column
- Score distribution chart: reduce bar count or use horizontal bars

### 5c. Coach pages (coach/*)

Mobile (< 768px):
- Session launcher: full-width cards
- Question list: accordion-style (tap to expand answer)
- Practice button: full width, prominent
- STAR answer sections: stacked, not tabbed

### 5d. Settings (settings/page.tsx)

Mobile (< 768px):
- Tabs become an accordion — each section expands/collapses on tap
- Form fields: full width
- Provider cards: 2×2 grid (already should work)

### 5e. All remaining pages

Apply the general responsive rules from 4d to every remaining page:
- `calendar/page.tsx`
- `agents/page.tsx`
- `tailor/page.tsx`
- `coach/session/[id]`, `coach/report/[id]`, `coach/stories/*`
- `settings/profile`, `settings/resume`, `settings/system`

Run: `make test`

---

## Prompt 6: Offline indicator, install prompt, and remaining IR35 cleanup

### 6a. Offline indicator

Create `frontend/src/components/OfflineIndicator.tsx`:
```tsx
"use client";
import { useState, useEffect } from "react";

export function OfflineIndicator() {
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    setIsOffline(!navigator.onLine);
    const handleOffline = () => setIsOffline(true);
    const handleOnline = () => setIsOffline(false);
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[60] bg-amber-500 text-white text-center py-2 text-sm font-medium">
      You're offline — showing cached data
    </div>
  );
}
```

Add to layout.tsx above the Navigation component.

### 6b. Install prompt

Create `frontend/src/components/InstallPrompt.tsx`:
```tsx
"use client";
import { useState, useEffect } from "react";

export function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (localStorage.getItem("pwa-install-dismissed")) {
      setDismissed(true);
      return;
    }
    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
    };
    window.addEventListener("beforeinstallprompt", handler);
    return () => window.removeEventListener("beforeinstallprompt", handler);
  }, []);

  if (!deferredPrompt || dismissed) return null;

  return (
    <div className="fixed bottom-20 md:bottom-4 left-4 right-4 md:left-auto md:right-4 md:w-80 z-50 bg-white border border-slate-200 rounded-xl shadow-lg p-4">
      <p className="font-medium text-sm text-slate-900 mb-1">Install JobPilot</p>
      <p className="text-xs text-slate-500 mb-3">Add to your home screen for quick access on any device.</p>
      <div className="flex gap-2">
        <button
          onClick={() => { deferredPrompt.prompt(); setDeferredPrompt(null); }}
          className="flex-1 bg-indigo-600 text-white rounded-lg py-2.5 text-sm font-medium min-h-[44px]"
        >
          Install
        </button>
        <button
          onClick={() => { setDismissed(true); localStorage.setItem("pwa-install-dismissed", "1"); }}
          className="px-4 text-slate-400 text-sm min-h-[44px]"
        >
          Not now
        </button>
      </div>
    </div>
  );
}
```

Add to layout.tsx.

### 6c. Fix remaining 12 files with IR35 references

Run this to find them:
```bash
grep -rn "IR35\|ir35" frontend/src --include="*.tsx" --include="*.ts" -l
```

For each file:
- Replace hardcoded `"IR35"` label strings with a dynamic label from the locale config or the job's `legal_fields` object
- Replace `job.ir35_status` with `job.legal_fields?.ir35_preference` (for UK jobs) or a generic legal field renderer
- In filter components: replace the IR35 filter dropdown with a dynamic legal field filter based on the active locale

### 6d. Write Playwright E2E test for mobile

Create `e2e/mobile-pwa.spec.ts`:
```typescript
import { test, expect } from "@playwright/test";

test.use({ viewport: { width: 375, height: 812 } }); // iPhone 12

test("mobile dashboard renders without horizontal scroll", async ({ page }) => {
  await page.goto("/");
  const body = page.locator("body");
  const scrollWidth = await body.evaluate((el) => el.scrollWidth);
  const clientWidth = await body.evaluate((el) => el.clientWidth);
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});

test("bottom navigation is visible on mobile", async ({ page }) => {
  await page.goto("/");
  const bottomNav = page.locator("nav.fixed.bottom-0");
  await expect(bottomNav).toBeVisible();
});

test("top navigation is hidden on mobile", async ({ page }) => {
  await page.goto("/");
  const topNav = page.locator("header.hidden");
  await expect(topNav).toBeHidden();
});
```

### 6e. Run full test suite

```bash
make test
```

---

## Prompt 7: Dark mode support

### 7a. Add theme toggle

Create `frontend/src/components/ThemeToggle.tsx`:
```tsx
"use client";
import { useState, useEffect } from "react";
import { Moon, Sun } from "lucide-react";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const isDark = stored === "dark" || (!stored && prefersDark);
    setDark(isDark);
    document.documentElement.classList.toggle("dark", isDark);
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  return (
    <button
      onClick={toggle}
      className="p-2 rounded-lg text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300 min-h-[44px] min-w-[44px] flex items-center justify-center"
      aria-label="Toggle dark mode"
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
```

### 7b. Update tailwind.config

Ensure `darkMode: "class"` is set in `tailwind.config.ts`.

### 7c. Audit all pages for dark mode

Add `dark:` variants to:
- Backgrounds: `bg-white dark:bg-slate-900`, `bg-slate-50 dark:bg-slate-800`
- Text: `text-slate-900 dark:text-slate-100`, `text-slate-500 dark:text-slate-400`
- Borders: `border-slate-200 dark:border-slate-700`
- Cards: `bg-white dark:bg-slate-800/50`
- Navigation: both top and bottom nav need dark variants
- Input fields: `bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700`

### 7d. Add ThemeToggle to navigation

Place the toggle next to the settings gear icon in both top nav and settings page.

Run: `make test`

---

## Phase 2 completion checklist

After all 7 prompts:

- [ ] `locales/ae.yaml` and `locales/ie.yaml` exist with complete schemas
- [ ] Onboarding shows 5 locale options (UK, India, UAE, Ireland, Other)
- [ ] PWA manifest at `public/manifest.json` with all icon sizes
- [ ] Service worker caches API responses and static assets
- [ ] Bottom tab navigation visible on mobile (< 768px)
- [ ] Top navigation hidden on mobile
- [ ] All 22 pages render without horizontal scroll at 375px
- [ ] Touch targets ≥ 44px on all interactive elements
- [ ] Offline indicator appears when backend is unreachable
- [ ] Install prompt appears on first visit (dismissable)
- [ ] Zero files reference hardcoded "IR35" — all legal fields are locale-driven
- [ ] Dark mode toggle works and persists preference
- [ ] `make test` passes — no regressions
- [ ] Lighthouse PWA score ≥ 90
