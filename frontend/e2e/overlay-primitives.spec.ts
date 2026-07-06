import { expect, test, type Page } from "@playwright/test";

async function mockUnlockedProfile(page: Page) {
  await page.route("**/api/app-lock/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        enabled: true,
        is_configured: true,
        is_unlocked: true,
      }),
    }),
  );
  await page.route("**/api/v2/profile/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        candidate_name: "Alex",
        onboarding_required: false,
        target_roles: ["Product Manager"],
      }),
    }),
  );
  await page.route("**/api/jobs/async/completed**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await mockUnlockedProfile(page);
  await page.goto("/today");
  await expect(page.locator("main")).toHaveCount(1);
});

test("user menu closes with Escape and restores focus", async ({ page }) => {
  const trigger = page.getByRole("button", { name: "Open user menu" });
  await trigger.click();
  await expect(page.getByRole("menu", { name: "User menu" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu", { name: "User menu" })).toBeHidden();
  await expect(trigger).toBeFocused();
});
