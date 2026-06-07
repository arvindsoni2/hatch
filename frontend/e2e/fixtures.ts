/**
 * Shared Playwright fixtures for Job Pilot v2 E2E tests.
 *
 * bypassOnboarding: mocks the profile status API so OnboardingGate does
 * not redirect pages to /onboarding during test runs with no seeded DB.
 *
 * Also mocks other polling endpoints so networkidle doesn't stall.
 */
import { test as base, expect, type Page } from "@playwright/test";

export async function bypassOnboarding(page: Page) {
  // Profile status — tells OnboardingGate not to redirect
  await page.route("**/api/v2/profile/status", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        onboarding_required: false,
        candidate_name: "Test User",
        has_resume: true,
        llm_provider: "openai",
        target_roles: ["Software Engineer"],
      }),
    });
  });

  // Agent performance table polls every 30s — mock so networkidle can settle
  await page.route("**/api/v1/agents/performance", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ agents: [] }),
    });
  });

  // Notifications polling
  await page.route("**/api/v2/notifications**", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

// Extended test with onboarding bypass and polling mocks applied automatically
export const test = base.extend<{ page: Page }>({
  page: async ({ page }, use) => {
    await bypassOnboarding(page);
    await use(page);
  },
});

export { expect };
