import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

test.setTimeout(60_000);

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

async function mockAISetup(page: Page) {
  let intent = { schema_version: 2, ai_mode: "none", backend_profile: "core", experience: "essential" };
  await page.route("**/api/setup/status", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      schema_version: 2,
      overall_status: "ready",
      onboarding: { status: "complete", last_completed_step: "protect-workspace" },
      intent,
      ai: { mode: intent.ai_mode, status: "ready", healthy: true },
      capabilities: { profile: "core", selected_profile: intent.backend_profile, enabled: [], operation: null },
      next_actions: [],
      runtime: { ai_mode: "not_configured", quality_mode: "not_configured", provider: null, warnings: [] },
      restart_required: false,
      next_command: "hatch apply-ai-config",
    }),
  }));
  await page.route("**/api/setup/providers", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ providers: [{
      id: "anthropic",
      label: "Anthropic",
      primary_model: "claude-sonnet-5",
      triage_model: "claude-haiku-4-5",
      models: ["claude-sonnet-5", "claude-haiku-4-5"],
      privacy: "Prompts are sent to Anthropic.",
      cost: "External API charges apply.",
      configured: false,
    }] }),
  }));
  await page.route("**/api/setup/intent", async (route) => {
    intent = { ...intent, ...route.request().postDataJSON() };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ intent }) });
  });
  await page.route("**/api/setup/hardware", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      detected: true,
      snapshot: {
        platform: { os_family: "linux", arch: "x86_64" },
        memory: { total_gb: 32 },
        storage: { models_dir_free_gb: 184 },
      },
    }),
  }));
  await page.route("**/api/setup/models/catalog", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      models: [{
        id: "qwen3-medium",
        display_name: "Qwen3 Medium",
        role: "combined_capable_primary",
        download_size_gb: 5.6,
        min_ram_gb: 16,
        recommended_ram_gb: 32,
      }],
    }),
  }));
  await page.route("**/api/setup/models/recommendations", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      recommended: [{ model_id: "qwen3-medium", already_downloaded: false }],
      compatible: [],
      not_recommended: [],
    }),
  }));
  await page.route("**/api/setup/models/discovery", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      source: "live",
      models: [],
      compatible: [],
      recommended_primary: null,
      recommended_triage: null,
    }),
  }));
}

test("settings profile has active navigation and a sticky dirty save bar", async ({ page }) => {
  await mockSettingsProfile(page);
  await page.goto("/settings/profile");

  await expect(page.getByRole("heading", { name: "Profile", exact: true })).toBeVisible({ timeout: 45_000 });
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

  await expect(page.getByRole("heading", { name: "Job Preferences", exact: true })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("link", { name: "Job Preferences" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByLabel("Settings section")).toHaveValue("/settings/preferences");

  const targetRoles = page.getByRole("group", { name: "Target roles" });
  await targetRoles.getByRole("button", { name: "Remove Delivery Lead" }).click();
  await page.getByRole("button", { name: "Save job preferences" }).click();

  await expect(page.getByText("Add at least one target role.")).toBeVisible();
  await expect(targetRoles.getByRole("textbox", { name: "Add target role" })).toBeFocused();
});

test("AI and capabilities keeps cloud and local routing separate", async ({ page }) => {
  await mockAISetup(page);
  await page.goto("/settings/ai");

  await expect(page.getByRole("heading", { name: "AI & Capabilities", exact: true })).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("link", { name: "AI & Capabilities" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("radio", { name: "Standard Hatch" })).toBeChecked();

  await page.getByRole("radio", { name: "Cloud" }).click();
  await expect(page.getByLabel("Primary cloud model")).toBeVisible();
  await expect(page.getByText("Hugging Face recommendations")).toHaveCount(0);
  await expect(page.getByText(/hatch secrets set anthropic/)).toBeVisible();

  await page.getByRole("radio", { name: "Local" }).click();
  await expect(page.getByText("Hugging Face recommendations")).toBeVisible();
  await expect(page.getByLabel("Primary cloud model")).toHaveCount(0);
});
