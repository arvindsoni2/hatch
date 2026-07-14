import { test, expect, mockIncompleteOnboarding } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockIncompleteOnboarding(page);
});

test("onboarding welcome screen renders with Get started button", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");

  await expect(page.getByText("Your job search,")).toBeVisible();
  await expect(page.getByText("Get started")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toHaveCount(0);
  await expect(page.getByRole("main")).toHaveCount(1);
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

  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForTimeout(300);

  await expect(page.getByText("Who are we writing for?")).toBeVisible();
  await expect(page.getByText("Name is required.")).toBeVisible();
});

test("onboarding browser draft excludes identity details", async ({ page }) => {
  await page.goto("/onboarding");
  await page.waitForLoadState("networkidle");
  await page.getByText("Get started").click();

  await page.getByRole("textbox", { name: "Full name" }).fill("Avery Morgan");
  await page.getByRole("textbox", { name: "Current or target title" }).fill("Transformation Director");
  await page.getByRole("spinbutton", { name: "Years of experience" }).fill("14");
  await page.getByRole("textbox", { name: "Professional summary" }).fill("Identifying career summary");

  await expect.poll(async () => page.evaluate(() => (
    sessionStorage.getItem("hatch_onboarding_v2")
  ))).not.toBeNull();

  const stored = await page.evaluate(() => sessionStorage.getItem("hatch_onboarding_v2") ?? "");
  expect(stored).not.toContain("Avery Morgan");
  expect(stored).not.toContain("Transformation Director");
  expect(stored).not.toContain("Identifying career summary");
  expect(stored).not.toContain("candidate");
});
