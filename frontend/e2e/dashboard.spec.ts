import { test, expect } from "./fixtures";

// Root redirects to /today
test("root redirect lands on today screen", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  expect(page.url()).toContain("/today");
});

// Today screen renders greeting (always "Good morning" — static by design in v4)
test("today screen shows greeting", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(/Good morning/).first()).toBeVisible();
});

// Today screen shows pipeline briefing card
test("today screen shows agents active briefing card", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Agents active")).toBeVisible();
});

// Sidebar navigation has Direction A labels (v4.1)
test("sidebar contains Direction A navigation links", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("domcontentloaded");

  // HatchSidebar renders as <aside> — use link roles to avoid strict-mode violations
  await expect(page.getByRole("link", { name: "Today" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Stream" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Tracker" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Prep" }).first()).toBeVisible();
});

// Notification bell is present (v4.1 live bell in HatchTopBar)
test("notification bell is present and clickable", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("domcontentloaded");

  const bellButton = page.getByRole("button", { name: /notifications/i });
  await expect(bellButton.first()).toBeVisible();

  await bellButton.first().click();
  await page.waitForTimeout(500);

  const isDisabled = await bellButton.first().getAttribute("disabled");
  expect(isDisabled).toBeNull();
});

// Theme toggle is present in top bar (v4.1 ThemeToggle in HatchTopBar)
test("theme toggle is present in top bar", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("networkidle");

  const toggleButton = page.getByRole("button", { name: /toggle dark mode/i });
  await expect(toggleButton.first()).toBeVisible();
});

// Theme toggle switches theme attribute on html element
test("theme toggle switches data-theme attribute", async ({ page }) => {
  await page.goto("/today");
  // Wait for React hydration so ThemeToggle's useEffect has run and resolved
  // the initial theme (boot script sets dark, useEffect may override to light)
  const toggleButton = page.getByRole("button", { name: /toggle dark mode/i });
  await expect(toggleButton.first()).toBeVisible();
  await page.waitForTimeout(200); // allow useEffect to settle

  const initialTheme = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme")
  );

  await toggleButton.first().click();
  await page.waitForTimeout(300);

  const newTheme = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme")
  );
  expect(newTheme).not.toBe(initialTheme);
});
