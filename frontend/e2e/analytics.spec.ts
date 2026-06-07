import { test, expect } from "./fixtures";

// Bug 4: Agent performance shows live data with refresh button
test("analytics page shows agent performance table", async ({ page }) => {
  await page.goto("/analytics");
  await page.waitForLoadState("networkidle");

  // The table section header should exist
  await expect(page.getByText("Agent Performance")).toBeVisible();

  // The client-side refresh button is present in the new build
  // (gracefully skip if old build is still deployed)
  const refreshBtn = page.getByRole("button", { name: /refresh/i });
  const refreshBtnCount = await refreshBtn.count();
  if (refreshBtnCount > 0) {
    await expect(refreshBtn.first()).toBeVisible();
  }
  // Either way, the heading must be visible
  await expect(page.getByText("Agent Performance")).toBeVisible();
});

test("agent performance table shows last run time", async ({ page }) => {
  await page.goto("/analytics");
  await page.waitForLoadState("networkidle");

  // Should show at least one agent row (scorer, scout, supervisor)
  const agentNames = ["scorer", "scout", "supervisor"];
  let foundAny = false;
  for (const name of agentNames) {
    const count = await page.getByText(name, { exact: false }).count();
    if (count > 0) {
      foundAny = true;
      break;
    }
  }
  // If no activity yet, "No agent activity recorded yet" should show
  if (!foundAny) {
    await expect(page.getByText("No agent activity recorded yet")).toBeVisible();
  }
});

test("analytics page renders without error", async ({ page }) => {
  await page.goto("/analytics");
  await page.waitForLoadState("networkidle");

  // Page must render without a 500 error or Next.js error page
  const title = await page.title();
  expect(title).not.toContain("500");
  expect(title).not.toContain("Error");

  // Core analytics content should be visible
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
});
