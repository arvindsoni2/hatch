import { test, expect } from "./fixtures";

test("onboarding welcome screen renders with Get started button", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");

  await expect(page.getByText("Your job search,")).toBeVisible();
  await expect(page.getByText("Get started")).toBeVisible();
});

test("onboarding step 1 shows numeral progress 01/06", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");

  await page.getByText("Get started").click();
  await page.waitForTimeout(300);

  await expect(page.getByText("01")).toBeVisible();
  await expect(page.getByText("/ 06")).toBeVisible();
});

test("onboarding step 1 heading is present", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");
  await page.getByText("Get started").click();
  await page.waitForTimeout(300);

  await expect(page.getByText("Who are we writing for?")).toBeVisible();
});

test("onboarding inline validation blocks advance when name is empty", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");
  await page.getByText("Get started").click();
  await page.waitForTimeout(300);

  await page.getByText("Continue →").click();
  await page.waitForTimeout(300);

  await expect(page.getByText("Who are we writing for?")).toBeVisible();
  await expect(page.getByText("Name is required.")).toBeVisible();
});
