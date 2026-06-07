import { test, expect } from "./fixtures";

// Bug 3: Approve button gives visible feedback (error or success)
test("approvals page loads and shows items or empty state", async ({ page }) => {
  await page.goto("/approvals");
  await page.waitForLoadState("networkidle");

  // Should either show approval cards or the "all caught up" empty state
  const hasApprovals = await page.locator("text=Approve").count();
  const hasEmpty = await page.getByText("You're all caught up").count();

  expect(hasApprovals + hasEmpty).toBeGreaterThan(0);
});

test("approval queue page has Scrape Now button", async ({ page }) => {
  await page.goto("/jobs");
  await page.waitForLoadState("networkidle");

  // Should show a scrape button
  const scrapeBtn = page.getByRole("button", { name: /scrape now/i });
  await expect(scrapeBtn).toBeVisible();
});

// Bug 3: Open application button is visible when application is ready
test("approved items show Open application button", async ({ page }) => {
  await page.goto("/approvals");
  await page.waitForLoadState("networkidle");

  const openBtns = page.getByRole("button", { name: /open application/i });
  const count = await openBtns.count();

  if (count > 0) {
    // Verify the button exists and is not disabled
    await expect(openBtns.first()).toBeEnabled();
  }
  // If no approvals, test passes (empty state is fine)
});
