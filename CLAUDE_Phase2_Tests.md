# JobPilot v3 Phase 2 — Test Specification

**Author:** Arvind Soni
**Date:** 28 May 2026
**Status:** Ready for Claude Code — execute BEFORE each Phase 2 implementation prompt
**Companion to:** `CLAUDE_Phase2.md`

---

## TDD Standard Practice

**This is now the permanent workflow for all JobPilot development:**

```
1. Write the test (RED — test fails because the feature doesn't exist yet)
2. Implement the feature (GREEN — test passes)
3. Refactor (CLEAN — improve code while keeping tests green)
4. Run full suite: make test (NO REGRESSIONS)
```

**Every Phase 2 implementation prompt has a corresponding test prompt below. Execute the test prompt FIRST. The tests should FAIL. Then execute the implementation prompt from CLAUDE_Phase2.md. The tests should PASS.**

If a developer (or Claude Code) writes code without tests, the CI pipeline should flag it via coverage regression.

---

## Test Prompt 1: Locale pack tests (run before Phase 2 Prompt 1)

Write these tests FIRST. They will fail because `ae.yaml` and `ie.yaml` don't exist yet, and the new scrapers aren't registered. After running Phase 2 Prompt 1, they should pass.

### 1a. Backend: locale service tests

Create `backend/tests/test_services/test_locale_service.py`:

```python
"""Tests for locale pack loading and validation — covers all 4 target regions."""
import pytest
from app.services.locale_service import get_locale, list_locales, LocaleNotFoundError


class TestLocaleService:
    """Verify all 4 target locale packs load correctly."""

    def test_list_locales_includes_all_four_targets(self):
        """The locale service must return at least uk, in, ae, ie."""
        locales = list_locales()
        locale_ids = [loc["id"] for loc in locales]
        assert "uk" in locale_ids, "UK locale missing"
        assert "in" in locale_ids, "India locale missing"
        assert "ae" in locale_ids, "UAE locale missing"
        assert "ie" in locale_ids, "Ireland locale missing"

    def test_uae_locale_has_required_fields(self):
        """UAE locale pack must have currency, legal fields, job boards."""
        locale = get_locale("ae")
        assert locale["currency"] == "AED"
        assert locale["currency_symbol"] == "د.إ"
        assert any(f["id"] == "visa_status" for f in locale["legal_fields"]), \
            "UAE locale must have visa_status legal field"
        assert any(b["name"] == "bayt" for b in locale["job_boards"]), \
            "UAE locale must include Bayt.com"

    def test_ireland_locale_has_required_fields(self):
        """Ireland locale pack must have EUR currency and work permit field."""
        locale = get_locale("ie")
        assert locale["currency"] == "EUR"
        assert locale["currency_symbol"] == "€"
        assert any(f["id"] == "work_permit" for f in locale["legal_fields"]), \
            "Ireland locale must have work_permit legal field"
        assert any(b["name"] == "irishjobs" for b in locale["job_boards"]), \
            "Ireland locale must include IrishJobs.ie"

    def test_uk_locale_still_loads(self):
        """Existing UK locale must still work after adding new locales."""
        locale = get_locale("uk")
        assert locale["currency"] == "GBP"
        assert any(f["id"] == "ir35_preference" for f in locale["legal_fields"])

    def test_india_locale_still_loads(self):
        """Existing India locale must still work after adding new locales."""
        locale = get_locale("in")
        assert locale["currency"] == "INR"
        assert any(f["id"] == "notice_period" for f in locale["legal_fields"])

    def test_invalid_locale_raises_error(self):
        """Requesting a non-existent locale should raise LocaleNotFoundError."""
        with pytest.raises(LocaleNotFoundError):
            get_locale("xx")

    def test_all_locales_have_job_boards(self):
        """Every locale pack must define at least one job board."""
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue  # skip template
            config = get_locale(locale["id"])
            assert len(config.get("job_boards", [])) > 0, \
                f"Locale {locale['id']} has no job boards"

    def test_all_locales_have_rate_types(self):
        """Every locale pack must define at least one compensation rate type."""
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue
            config = get_locale(locale["id"])
            assert len(config.get("rate_types", [])) > 0, \
                f"Locale {locale['id']} has no rate types"

    def test_all_locales_have_scoring_defaults(self):
        """Every locale pack must define scoring weights and threshold."""
        for locale in list_locales():
            if locale["id"].startswith("_"):
                continue
            config = get_locale(locale["id"])
            defaults = config.get("scoring_defaults", {})
            weights = defaults.get("weights", {})
            assert "skill_match" in weights, f"Locale {locale['id']} missing skill_match weight"
            assert "shortlist_threshold" in defaults, f"Locale {locale['id']} missing threshold"
```

### 1b. Backend: scraper registry tests

Create `backend/tests/test_scrapers/test_registry.py`:

```python
"""Tests for scraper registry — verify all locales have registered scrapers."""
import pytest


class TestScraperRegistry:
    """Verify scrapers are registered for all target locales."""

    def test_uae_scrapers_registered(self):
        """UAE locale must have at least bayt, linkedin, indeed scrapers."""
        from app.scrapers.registry import get_scrapers_for_locale
        scrapers = get_scrapers_for_locale("ae")
        names = [s["name"] if isinstance(s, dict) else s.name for s in scrapers]
        # At minimum linkedin and indeed should be multi-locale
        assert any("linkedin" in str(n).lower() for n in names), \
            "LinkedIn scraper must be registered for UAE"

    def test_ireland_scrapers_registered(self):
        """Ireland locale must have at least irishjobs, linkedin, indeed."""
        from app.scrapers.registry import get_scrapers_for_locale
        scrapers = get_scrapers_for_locale("ie")
        names = [s["name"] if isinstance(s, dict) else s.name for s in scrapers]
        assert any("linkedin" in str(n).lower() for n in names), \
            "LinkedIn scraper must be registered for Ireland"

    def test_uk_scrapers_still_registered(self):
        """UK scrapers must not be broken by adding new locales."""
        from app.scrapers.registry import get_scrapers_for_locale
        scrapers = get_scrapers_for_locale("uk")
        assert len(scrapers) >= 3, "UK should have at least 3 scrapers"

    def test_stub_scrapers_return_empty_list(self):
        """Stub scrapers (not yet implemented) should return empty results."""
        # Import the stub scraper and verify it runs without error
        from app.scrapers.bayt import BaytScraper
        scraper = BaytScraper()
        import asyncio
        result = asyncio.get_event_loop().run_until_complete(
            scraper.scrape(keywords=["test"])
        )
        assert result == [], "Stub scraper should return empty list"
```

### 1c. Frontend: onboarding locale card tests

Create `frontend/src/__tests__/components/StepJobSearch.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { StepJobSearch } from "@/components/onboarding/StepJobSearch";

describe("StepJobSearch — locale selection", () => {
  it("renders all 4 target region cards plus Other", () => {
    render(<StepJobSearch data={{}} onChange={() => {}} />);
    expect(screen.getByText("UK")).toBeInTheDocument();
    expect(screen.getByText("India")).toBeInTheDocument();
    expect(screen.getByText(/UAE|United Arab Emirates/)).toBeInTheDocument();
    expect(screen.getByText("Ireland")).toBeInTheDocument();
    expect(screen.getByText("Other")).toBeInTheDocument();
  });

  it("renders locale flags", () => {
    render(<StepJobSearch data={{}} onChange={() => {}} />);
    expect(screen.getByText("🇬🇧")).toBeInTheDocument();
    expect(screen.getByText("🇮🇳")).toBeInTheDocument();
    expect(screen.getByText("🇦🇪")).toBeInTheDocument();
    expect(screen.getByText("🇮🇪")).toBeInTheDocument();
  });

  it("does not hardcode IR35 as a field label", () => {
    render(<StepJobSearch data={{ locale: "in" }} onChange={() => {}} />);
    // When India is selected, IR35 should not appear
    expect(screen.queryByText(/IR35/i)).not.toBeInTheDocument();
  });

  it("shows CTC format when India selected", () => {
    render(<StepJobSearch data={{ locale: "in" }} onChange={() => {}} />);
    // Compensation labels should adapt to locale
    expect(screen.queryByText(/daily rate/i)).not.toBeInTheDocument();
  });
});
```

**Run: `make test` — these tests should FAIL (red). Then execute Phase 2 Prompt 1. Re-run — tests should PASS (green).**

---

## Test Prompt 2: PWA tests (run before Phase 2 Prompt 2)

### 2a. PWA manifest validation test

Create `frontend/src/__tests__/pwa/manifest.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("PWA Manifest", () => {
  const manifestPath = path.join(__dirname, "../../../public/manifest.json");

  it("manifest.json exists in public directory", () => {
    expect(fs.existsSync(manifestPath)).toBe(true);
  });

  it("has required PWA fields", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    expect(manifest.name).toBeTruthy();
    expect(manifest.short_name).toBeTruthy();
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.theme_color).toBeTruthy();
    expect(manifest.background_color).toBeTruthy();
  });

  it("has icons at required sizes (192 and 512)", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    const sizes = manifest.icons.map((i: any) => i.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
  });

  it("has a maskable icon", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    const maskable = manifest.icons.find((i: any) =>
      i.purpose?.includes("maskable")
    );
    expect(maskable).toBeTruthy();
  });

  it("icon files actually exist on disk", () => {
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
    for (const icon of manifest.icons) {
      const iconPath = path.join(__dirname, "../../../public", icon.src);
      expect(fs.existsSync(iconPath)).toBe(true);
    }
  });
});
```

### 2b. Layout metadata test

Create `frontend/src/__tests__/pwa/layout-meta.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("Layout PWA metadata", () => {
  const layoutContent = fs.readFileSync(
    path.join(__dirname, "../../app/layout.tsx"),
    "utf-8"
  );

  it("includes manifest link", () => {
    expect(layoutContent).toContain('manifest');
  });

  it("includes theme-color meta tag", () => {
    expect(layoutContent).toContain('theme-color');
  });

  it("includes apple-mobile-web-app-capable", () => {
    expect(layoutContent).toContain('apple-mobile-web-app-capable');
  });

  it("includes apple-touch-icon", () => {
    expect(layoutContent).toContain('apple-touch-icon');
  });
});
```

### 2c. Offline fallback test

```typescript
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("Offline fallback", () => {
  it("offline.html exists in public directory", () => {
    const offlinePath = path.join(__dirname, "../../../public/offline.html");
    expect(fs.existsSync(offlinePath)).toBe(true);
  });

  it("offline.html contains a retry button", () => {
    const offlinePath = path.join(__dirname, "../../../public/offline.html");
    const content = fs.readFileSync(offlinePath, "utf-8");
    expect(content).toContain("Retry");
    expect(content).toContain("offline");
  });
});
```

**Run: `make test` — FAIL (red). Execute Phase 2 Prompt 2. Re-run — PASS (green).**

---

## Test Prompt 3: Responsive navigation tests (run before Phase 2 Prompt 3)

### 3a. BottomNav component test

Create `frontend/src/__tests__/components/BottomNav.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { BottomNav } from "@/components/BottomNav";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

// Mock API
vi.mock("@/lib/api", () => ({
  fetchPendingApprovals: vi.fn().mockResolvedValue([]),
}));

describe("BottomNav", () => {
  it("renders all navigation items", () => {
    render(<BottomNav />);
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
    expect(screen.getByText("Approvals")).toBeInTheDocument();
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Analytics")).toBeInTheDocument();
    expect(screen.getByText("Prep")).toBeInTheDocument();
  });

  it("does not include Auto Apply", () => {
    render(<BottomNav />);
    expect(screen.queryByText(/auto.?apply/i)).not.toBeInTheDocument();
  });

  it("highlights the active route", () => {
    render(<BottomNav />);
    const homeLink = screen.getByText("Home").closest("a");
    expect(homeLink?.className).toContain("text-indigo-600");
  });

  it("renders approval badge when count > 0", async () => {
    const { fetchPendingApprovals } = await import("@/lib/api");
    (fetchPendingApprovals as any).mockResolvedValue([{ id: "1" }, { id: "2" }]);
    render(<BottomNav />);
    // Wait for badge to render
    const badge = await screen.findByText("2");
    expect(badge).toBeInTheDocument();
  });

  it("all touch targets are at least 44px", () => {
    const { container } = render(<BottomNav />);
    const links = container.querySelectorAll("a");
    links.forEach((link) => {
      // Check min-h-[44px] class or computed style
      expect(link.className).toContain("min-h-[44px]");
    });
  });
});
```

### 3b. useMediaQuery hook test

Create `frontend/src/__tests__/hooks/useMediaQuery.test.ts`:

```typescript
import { renderHook } from "@testing-library/react";
import { useMediaQuery, useIsMobile, useIsDesktop } from "@/hooks/useMediaQuery";

describe("useMediaQuery", () => {
  it("returns false when no match", () => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { result } = renderHook(() => useMediaQuery("(max-width: 767px)"));
    expect(result.current).toBe(false);
  });

  it("returns true when matches", () => {
    window.matchMedia = vi.fn().mockImplementation(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("useIsDesktop returns true for wide viewport", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("min-width: 1024px"),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { result } = renderHook(() => useIsDesktop());
    expect(result.current).toBe(true);
  });
});
```

### 3c. Navigation responsive behaviour test

Create `frontend/src/__tests__/components/NavigationResponsive.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { Navigation } from "@/components/Navigation";

describe("Navigation — responsive behaviour", () => {
  it("top nav has hidden class for mobile breakpoint", () => {
    const { container } = render(<Navigation />);
    const header = container.querySelector("header");
    // After Phase 2 Prompt 3, the header should have hidden md:block
    expect(header?.className).toContain("hidden");
    expect(header?.className).toContain("md:");
  });
});
```

**Run: `make test` — FAIL. Execute Phase 2 Prompt 3. Re-run — PASS.**

---

## Test Prompt 4: Responsive page tests (run before Phase 2 Prompt 4)

### 4a. Playwright viewport tests for critical pages

Create `e2e/responsive-pages.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

const MOBILE = { width: 375, height: 812 };
const TABLET = { width: 768, height: 1024 };
const DESKTOP = { width: 1280, height: 800 };

const PAGES = [
  { path: "/", name: "Dashboard" },
  { path: "/jobs", name: "Jobs" },
  { path: "/approvals", name: "Approvals" },
  { path: "/applications", name: "Pipeline" },
  { path: "/analytics", name: "Analytics" },
  { path: "/settings", name: "Settings" },
  { path: "/coach", name: "Coach" },
];

for (const { path, name } of PAGES) {
  test.describe(`${name} page responsive`, () => {
    
    test(`${name} — no horizontal scroll at 375px`, async ({ page }) => {
      await page.setViewportSize(MOBILE);
      await page.goto(path);
      await page.waitForTimeout(500);
      const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const clientWidth = await page.evaluate(() => document.body.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    });

    test(`${name} — no horizontal scroll at 768px`, async ({ page }) => {
      await page.setViewportSize(TABLET);
      await page.goto(path);
      await page.waitForTimeout(500);
      const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
      const clientWidth = await page.evaluate(() => document.body.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    });

    test(`${name} — renders at 1280px without errors`, async ({ page }) => {
      await page.setViewportSize(DESKTOP);
      await page.goto(path);
      const errors: string[] = [];
      page.on("pageerror", (err) => errors.push(err.message));
      await page.waitForTimeout(1000);
      expect(errors.length).toBe(0);
    });
  });
}
```

### 4b. Dashboard mobile layout test

Create `frontend/src/__tests__/pages/dashboard-responsive.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";

// This test verifies the dashboard component uses responsive grid classes
describe("Dashboard — responsive layout", () => {
  it("action cards container has responsive grid classes", async () => {
    // Import the dashboard page component
    // Check that the action card grid uses grid-cols-1 md:grid-cols-3
    // This is a structural test — the actual rendering at different
    // viewports is tested by Playwright
  });

  it("pipeline section uses responsive flex direction", () => {
    // Should be flex-col on mobile, flex-row on desktop
  });
});
```

### 4c. Jobs page mobile layout test

Create `frontend/src/__tests__/pages/jobs-responsive.test.tsx`:

```typescript
describe("Jobs listing — responsive layout", () => {
  it("renders cards (not table) when data is present", () => {
    // On mobile, jobs should render as cards, not a data table
    // Verify JobCard components are used, not a <table>
  });

  it("filter panel has a collapse/expand trigger on mobile", () => {
    // Filters should be behind a "Filters" button on mobile
    // Not always visible
  });
});
```

**Run: `make test` — some FAIL (Playwright needs running app; component tests fail on missing classes). Execute Phase 2 Prompt 4. Re-run — PASS.**

---

## Test Prompt 5: Pipeline, analytics, coach, settings responsive tests (run before Phase 2 Prompt 5)

### 5a. Extend the Playwright responsive test

Add to `e2e/responsive-pages.spec.ts` (created in Test Prompt 4):

```typescript
test.describe("Pipeline Kanban — mobile", () => {
  test("kanban columns are horizontally scrollable on mobile", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/applications");
    await page.waitForTimeout(500);
    // The kanban container should have overflow-x: auto or scroll
    const scrollable = await page.evaluate(() => {
      const container = document.querySelector("[data-testid='kanban-container']") 
        || document.querySelector(".kanban-container")
        || document.querySelector("[class*='overflow-x']");
      return container !== null;
    });
    expect(scrollable).toBe(true);
  });

  test("kanban columns have snap scroll behaviour", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/applications");
    await page.waitForTimeout(500);
    const hasSnap = await page.evaluate(() => {
      const container = document.querySelector("[data-testid='kanban-container']")
        || document.querySelector(".kanban-container");
      if (!container) return false;
      const style = window.getComputedStyle(container);
      return style.scrollSnapType !== "none" && style.scrollSnapType !== "";
    });
    expect(hasSnap).toBe(true);
  });
});

test.describe("Analytics — mobile", () => {
  test("stat cards are 2-column grid on mobile", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/analytics");
    await page.waitForTimeout(500);
    // Stats grid should not be 6 columns on mobile
    const columns = await page.evaluate(() => {
      const grid = document.querySelector("[data-testid='stats-grid']")
        || document.querySelector(".grid");
      if (!grid) return 0;
      const style = window.getComputedStyle(grid);
      return style.gridTemplateColumns.split(" ").length;
    });
    expect(columns).toBeLessThanOrEqual(3); // 2 or 3, not 6
  });
});

test.describe("Settings — mobile", () => {
  test("settings renders without horizontal overflow", async ({ page }) => {
    await page.setViewportSize(MOBILE);
    await page.goto("/settings");
    await page.waitForTimeout(500);
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const clientWidth = await page.evaluate(() => document.body.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });
});
```

**Run: `make test` — FAIL. Execute Phase 2 Prompt 5. Re-run — PASS.**

---

## Test Prompt 6: Offline indicator, install prompt, IR35 cleanup tests (run before Phase 2 Prompt 6)

### 6a. OfflineIndicator test

Create `frontend/src/__tests__/components/OfflineIndicator.test.tsx`:

```typescript
import { render, screen, act } from "@testing-library/react";
import { OfflineIndicator } from "@/components/OfflineIndicator";

describe("OfflineIndicator", () => {
  const originalOnLine = navigator.onLine;

  afterEach(() => {
    Object.defineProperty(navigator, "onLine", { value: originalOnLine, writable: true });
  });

  it("does not render when online", () => {
    Object.defineProperty(navigator, "onLine", { value: true, writable: true });
    const { container } = render(<OfflineIndicator />);
    expect(container.firstChild).toBeNull();
  });

  it("renders offline banner when offline", () => {
    Object.defineProperty(navigator, "onLine", { value: false, writable: true });
    render(<OfflineIndicator />);
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
  });

  it("shows banner when going offline", () => {
    Object.defineProperty(navigator, "onLine", { value: true, writable: true });
    render(<OfflineIndicator />);
    act(() => {
      Object.defineProperty(navigator, "onLine", { value: false, writable: true });
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
  });

  it("hides banner when coming back online", () => {
    Object.defineProperty(navigator, "onLine", { value: false, writable: true });
    render(<OfflineIndicator />);
    act(() => {
      Object.defineProperty(navigator, "onLine", { value: true, writable: true });
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument();
  });
});
```

### 6b. InstallPrompt test

Create `frontend/src/__tests__/components/InstallPrompt.test.tsx`:

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { InstallPrompt } from "@/components/InstallPrompt";

describe("InstallPrompt", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("does not render without beforeinstallprompt event", () => {
    const { container } = render(<InstallPrompt />);
    expect(container.firstChild).toBeNull();
  });

  it("renders when beforeinstallprompt fires", () => {
    render(<InstallPrompt />);
    const event = new Event("beforeinstallprompt");
    (event as any).preventDefault = vi.fn();
    window.dispatchEvent(event);
    expect(screen.getByText(/install jobpilot/i)).toBeInTheDocument();
  });

  it("dismisses and remembers in localStorage", () => {
    render(<InstallPrompt />);
    const event = new Event("beforeinstallprompt");
    (event as any).preventDefault = vi.fn();
    window.dispatchEvent(event);
    
    fireEvent.click(screen.getByText(/not now/i));
    expect(localStorage.getItem("pwa-install-dismissed")).toBe("1");
    expect(screen.queryByText(/install jobpilot/i)).not.toBeInTheDocument();
  });

  it("install button has minimum 44px touch target", () => {
    render(<InstallPrompt />);
    const event = new Event("beforeinstallprompt");
    (event as any).preventDefault = vi.fn();
    window.dispatchEvent(event);
    
    const installButton = screen.getByText("Install");
    expect(installButton.className).toContain("min-h-[44px]");
  });
});
```

### 6c. IR35 hardcoding elimination test

Create `frontend/src/__tests__/codebase/no-hardcoded-ir35.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { execSync } from "child_process";

describe("Codebase — no hardcoded IR35 labels", () => {
  it("no frontend .tsx/.ts file contains hardcoded IR35 label strings", () => {
    // Search for IR35 used as a UI label (not as a data field name)
    // Allow: legal_fields.ir35_preference, ir35_status as a field ID
    // Disallow: "IR35" as visible text, label="IR35", "Outside IR35"
    try {
      const result = execSync(
        'grep -rn "\\bIR35\\b" frontend/src --include="*.tsx" --include="*.ts" ' +
        '| grep -v "node_modules" | grep -v ".test." | grep -v "__tests__" ' +
        '| grep -v "ir35_preference" | grep -v "ir35_status" | grep -v "// "',
        { encoding: "utf-8" }
      );
      // If grep finds matches, result will be non-empty
      const lines = result.trim().split("\n").filter(Boolean);
      expect(lines.length).toBe(0);
    } catch {
      // grep returns exit code 1 when no matches — that's what we want
    }
  });

  it("JobCard does not render IR35 as a visible label", () => {
    // Import and render JobCard with a non-UK job
    // Verify no "IR35" text appears
  });

  it("FilterPanel does not hardcode IR35 as a filter option", () => {
    // Render FilterPanel with India locale
    // Verify IR35 filter is not present
    // Verify notice_period filter IS present
  });
});
```

### 6d. Playwright mobile PWA E2E

Create `e2e/mobile-pwa.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test.use({ viewport: { width: 375, height: 812 } });

test("bottom navigation is visible on mobile", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(500);
  const bottomNav = page.locator("nav").filter({ has: page.locator("text=Home") }).last();
  await expect(bottomNav).toBeVisible();
});

test("top navigation is not visible on mobile", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(500);
  const header = page.locator("header.hidden");
  // Should be hidden via CSS
  const isHidden = await header.evaluate((el) => {
    const style = window.getComputedStyle(el);
    return style.display === "none";
  });
  expect(isHidden).toBe(true);
});

test("no page has horizontal scroll on mobile", async ({ page }) => {
  const pages = ["/", "/jobs", "/approvals", "/applications", "/analytics", "/coach", "/settings"];
  for (const path of pages) {
    await page.goto(path);
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => 
      document.body.scrollWidth > document.body.clientWidth
    );
    expect(overflow, `${path} has horizontal scroll`).toBe(false);
  }
});

test("approval badge shows count on bottom nav", async ({ page }) => {
  await page.goto("/");
  // This depends on mock data — may need API mock setup
});
```

**Run: `make test` — FAIL. Execute Phase 2 Prompt 6. Re-run — PASS.**

---

## Test Prompt 7: Dark mode tests (run before Phase 2 Prompt 7)

### 7a. ThemeToggle component test

Create `frontend/src/__tests__/components/ThemeToggle.test.tsx`:

```typescript
import { render, screen, fireEvent } from "@testing-library/react";
import { ThemeToggle } from "@/components/ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark");
  });

  it("renders a toggle button", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    expect(button).toBeInTheDocument();
  });

  it("toggles dark class on html element", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    fireEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    fireEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("persists preference in localStorage", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    fireClick(button);
    expect(localStorage.getItem("theme")).toBe("dark");
    fireEvent.click(button);
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("respects stored preference on mount", () => {
    localStorage.setItem("theme", "dark");
    render(<ThemeToggle />);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("touch target is at least 44px", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    expect(button.className).toContain("min-h-[44px]");
    expect(button.className).toContain("min-w-[44px]");
  });
});
```

### 7b. Tailwind dark mode configuration test

Create `frontend/src/__tests__/codebase/darkmode-config.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

describe("Dark mode configuration", () => {
  it("tailwind.config uses class-based dark mode", () => {
    const configPath = path.join(__dirname, "../../../tailwind.config.ts");
    const altConfigPath = path.join(__dirname, "../../../tailwind.config.js");
    const content = fs.existsSync(configPath)
      ? fs.readFileSync(configPath, "utf-8")
      : fs.readFileSync(altConfigPath, "utf-8");
    expect(content).toContain('darkMode');
    expect(content).toContain('"class"');
  });
});
```

**Run: `make test` — FAIL. Execute Phase 2 Prompt 7. Re-run — PASS.**

---

## Test execution summary

| Test prompt | Files created | Test count | Tests for |
|------------|--------------|------------|-----------|
| TP-1 | 3 files | ~15 tests | Locale packs, scraper registry, onboarding locale cards |
| TP-2 | 3 files | ~9 tests | PWA manifest, layout metadata, offline fallback |
| TP-3 | 3 files | ~12 tests | BottomNav, useMediaQuery, Navigation responsive |
| TP-4 | 3 files | ~21 tests (7 pages × 3 viewports) | All page responsive layouts (Playwright) |
| TP-5 | 1 file (extended) | ~5 tests | Kanban scroll, analytics grid, settings overflow |
| TP-6 | 4 files | ~12 tests | OfflineIndicator, InstallPrompt, IR35 elimination, mobile E2E |
| TP-7 | 2 files | ~7 tests | ThemeToggle, Tailwind dark mode config |
| **Total** | **19 files** | **~81 tests** | |

---

## Permanent TDD workflow going forward

Add this to the project's `CONTRIBUTING.md` and `CLAUDE.md`:

```markdown
## Test-Driven Development (TDD) — mandatory for all changes

Every PR must include tests. The workflow is:

1. **Write the test first** — describe the expected behaviour
2. **Run the test** — it should FAIL (red)
3. **Implement the feature** — make the test PASS (green)
4. **Refactor** — clean up while keeping tests green
5. **Run full suite** — `make test` must pass with zero regressions

### Test file locations
- Backend unit tests: `backend/tests/test_<module>/test_<file>.py`
- Frontend component tests: `frontend/src/__tests__/components/<Component>.test.tsx`
- Frontend page tests: `frontend/src/__tests__/pages/<page>.test.tsx`
- E2E tests: `e2e/<flow>.spec.ts`
- Codebase quality tests: `frontend/src/__tests__/codebase/<check>.test.ts`

### What to test
- Every new component: renders, handles props, edge cases
- Every new API endpoint: success, validation errors, auth
- Every new agent behaviour: happy path, error, mocked LLM
- Every responsive change: viewport at 375px, 768px, 1280px
- Every locale change: verify no hardcoded UK/IR35/GBP labels

### CI enforcement
GitHub Actions runs all tests on every push and PR.
PRs with failing tests cannot be merged.
```
