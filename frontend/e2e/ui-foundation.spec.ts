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
}

for (const route of ["/today", "/jobs", "/coach"]) {
  test(`${route} renders one main landmark and one route-owned H1`, async ({ page }) => {
    await mockUnlockedProfile(page);
    await page.goto(route);

    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.locator("h1")).toHaveCount(1);
  });
}

test("keyboard focus starts with the skip link", async ({ page }) => {
  await mockUnlockedProfile(page);
  await page.goto("/coach");
  await expect(page.locator("main")).toHaveCount(1);

  await page.keyboard.press("Tab");
  if (await page.evaluate(() => document.activeElement?.tagName === "NEXTJS-PORTAL")) {
    await page.keyboard.press("Tab");
  }
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();

  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});
