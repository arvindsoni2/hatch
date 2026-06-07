/**
 * v4.1 smoke tests — cover every Direction A route and critical UX invariants.
 * Regression pack: if any of these break, a core v4.1 feature is lost.
 */
import { test, expect } from "./fixtures";

// ── Direction A routes ─────────────────────────────────────────────────────────

test("today screen renders at /today", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("domcontentloaded");
  await expect(page.getByText(/Good morning/).first()).toBeVisible();
  await expect(page.getByText("Agents active")).toBeVisible();
});

test("stream screen renders at /stream", async ({ page }) => {
  await page.goto("/stream");
  await page.waitForLoadState("domcontentloaded");
  const title = await page.title();
  expect(title).not.toContain("500");
  expect(title).not.toContain("Error");
  // Stream heading is in the page nav area
  await expect(page.getByRole("link", { name: "Stream" }).first()).toBeVisible();
});

test("tracker screen renders at /tracker", async ({ page }) => {
  await page.goto("/tracker");
  await page.waitForLoadState("domcontentloaded");
  const title = await page.title();
  expect(title).not.toContain("500");
  expect(title).not.toContain("Error");
  // Tracker heading rendered in TrackerScreen
  await expect(page.getByText("Tracker").first()).toBeVisible();
});

test("prep screen renders at /prep", async ({ page }) => {
  await page.goto("/prep");
  await page.waitForLoadState("domcontentloaded");
  const title = await page.title();
  expect(title).not.toContain("500");
  expect(title).not.toContain("Error");
  // Use link role to avoid strict-mode violation — "Prep" text appears in nav + page heading
  await expect(page.getByRole("link", { name: "Prep" }).first()).toBeVisible();
});

// ── Settings pages themed ─────────────────────────────────────────────────────

test("settings page renders without error", async ({ page }) => {
  await page.goto("/settings");
  await page.waitForLoadState("domcontentloaded");
  const title = await page.title();
  expect(title).not.toContain("500");
  expect(title).not.toContain("Error");
  await expect(page.getByText("Settings").first()).toBeVisible();
});

// ── Onboarding gate ───────────────────────────────────────────────────────────

test("onboarding page is reachable at /onboarding", async ({ page }) => {
  // Navigate directly — fixture mocks profile but onboarding route is accessible
  await page.goto("/onboarding");
  await page.waitForLoadState("domcontentloaded");
  const title = await page.title();
  expect(title).not.toContain("500");
  await expect(page.getByText("Get started")).toBeVisible();
});

// ── Shell contract: bell + toggle present on all Direction A routes ────────────

for (const route of ["/today", "/stream", "/tracker", "/prep"]) {
  test(`notification bell visible on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("domcontentloaded");
    const bell = page.getByRole("button", { name: /notifications/i });
    await expect(bell.first()).toBeVisible();
  });

  test(`theme toggle visible on ${route}`, async ({ page }) => {
    await page.goto(route);
    await page.waitForLoadState("domcontentloaded");
    const toggle = page.getByRole("button", { name: /toggle dark mode/i });
    await expect(toggle.first()).toBeVisible();
  });
}
