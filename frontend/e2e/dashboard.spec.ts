import { test, expect } from "./fixtures";

// Root redirects to /today
test("root redirect lands on today screen", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  expect(page.url()).toContain("/today");
});

// Today screen renders time-based greeting (morning/afternoon/evening)
test("today screen shows greeting", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText(/Good (morning|afternoon|evening)/).first()).toBeVisible();
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

// User menu avatar is present in top bar (v4.1 UserMenu replaces standalone ThemeToggle + UserAvatar)
test("user menu avatar is present in top bar", async ({ page }) => {
  await page.goto("/today");
  await page.waitForLoadState("domcontentloaded");

  const avatarButton = page.getByRole("button", { name: /open user menu/i });
  await expect(avatarButton.first()).toBeVisible();
});

// Theme toggle is accessible via user menu dropdown
test("theme toggle switches data-theme attribute via user menu", async ({ page }) => {
  await page.goto("/today");
  // Target topbar's UserMenu specifically (header element) to avoid sidebar's UserMenu at bottom
  const avatarButton = page.locator("header").getByRole("button", { name: /open user menu/i });
  await expect(avatarButton).toBeVisible();
  await avatarButton.click();

  // Wait for ThemeToggle to be visible in the dropdown + allow useEffect to settle
  const toggleButton = page.getByRole("button", { name: /toggle dark mode/i });
  await expect(toggleButton).toBeVisible();
  await page.waitForTimeout(200);

  const initialTheme = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme")
  );

  await toggleButton.click();
  await page.waitForTimeout(300);

  const newTheme = await page.evaluate(() =>
    document.documentElement.getAttribute("data-theme")
  );
  expect(newTheme).not.toBe(initialTheme);
});
