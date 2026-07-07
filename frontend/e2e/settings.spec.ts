import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

const profile = {
  candidate: {
    name: "Avery Morgan",
    title: "Transformation Director",
    years_experience: 14,
    summary: "Delivery leader.",
  },
  locale: "uk",
  search: {
    target_roles: ["Delivery Lead"],
    contract_type: "contract",
    locations: [{ city: "London", country: "GB", remote_preference: "hybrid" }],
  },
  job_boards: [
    { name: "LinkedIn", scraper: "linkedin", enabled: true },
    { name: "Indeed", scraper: "indeed", enabled: false },
  ],
  compensation: { min_rate: 650, max_rate: 800, currency: "GBP", rate_type: "daily" },
  skills: { primary: ["Agile delivery"], secondary: ["Stakeholder management"] },
  scoring: { shortlist_threshold: 0.75, weights: { skill_match: 0.35 } },
  perception: { face: { enabled: false } },
  llm: { provider: "llamacpp" },
};

async function mockSettingsProfile(page: Page) {
  await page.route("**/api/v2/profile", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(profile),
    });
  });
}

test("settings profile has active navigation and a sticky dirty save bar", async ({ page }) => {
  await mockSettingsProfile(page);
  await page.goto("/settings/profile");

  await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: "Profile" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByLabel("Settings section")).toHaveValue("/settings/profile");

  await page.getByRole("textbox", { name: "Full name" }).fill("Avery Stone");
  await expect(page.getByRole("status")).toContainText("Unsaved changes");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByRole("status")).toContainText("Profile saved.");
});

test("job preferences validates target-role entry and focuses the tag input", async ({ page }) => {
  await mockSettingsProfile(page);
  await page.goto("/settings/preferences");

  await expect(page.getByRole("heading", { name: "Job Preferences" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: "Job Preferences" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByLabel("Settings section")).toHaveValue("/settings/preferences");

  const targetRoles = page.getByRole("group", { name: "Target roles" });
  await targetRoles.getByRole("button", { name: "Remove Delivery Lead" }).click();
  await page.getByRole("button", { name: "Save job preferences" }).click();

  await expect(page.getByText("Add at least one target role.")).toBeVisible();
  await expect(targetRoles.getByRole("textbox", { name: "Add target role" })).toBeFocused();
});
