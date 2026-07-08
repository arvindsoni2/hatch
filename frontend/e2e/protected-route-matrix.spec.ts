import { expect, test, mockProtectedRouteApis } from "./fixtures";

const clientRoutes = [
  { path: "/jobs", heading: "Jobs" },
  { path: "/tailor", heading: "CV Studio" },
  { path: "/coach", heading: "Interview Coach" },
  { path: "/calendar", heading: "Calendar" },
  { path: "/agents", heading: "Agent Dashboard" },
  { path: "/approvals", heading: "Shortlist" },
  { path: "/settings/profile", heading: "Profile" },
  { path: "/settings/preferences", heading: "Job Preferences" },
  { path: "/settings/ai", heading: "AI Provider" },
  { path: "/settings/resume", heading: "Master CV" },
  { path: "/settings/security", heading: "Security & App Lock" },
  { path: "/settings/system", heading: "System Logs" },
];

const serverRoutesPendingUnlock = [
  { path: "/today", heading: "Today" },
  { path: "/stream", heading: "Pipeline" },
  { path: "/tracker", heading: "Applications" },
  { path: "/prep", heading: "Interview Prep" },
  { path: "/analytics", heading: "Analytics" },
];

test.describe("protected route matrix", () => {
  for (const route of clientRoutes) {
    test(`${route.path} renders one main landmark and one route H1`, async ({ page }) => {
      await mockProtectedRouteApis(page);
      await page.goto(route.path);

      await expect(page.locator("main")).toHaveCount(1);
      await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
      await expect(page.locator("h1")).toHaveCount(1);
      await expect(page).not.toHaveURL(/\/unlock|\/onboarding/);
    });
  }

  test.describe.skip("server-rendered route matrix pending unlocked backend", () => {
    for (const route of serverRoutesPendingUnlock) {
      test(`${route.path} renders one main landmark and one route H1 when the backend is unlocked`, async ({ page }) => {
        await page.goto(route.path);
        await expect(page.locator("main")).toHaveCount(1);
        await expect(page.getByRole("heading", { level: 1, name: route.heading })).toBeVisible();
        await expect(page.locator("h1")).toHaveCount(1);
        await expect(page).not.toHaveURL(/\/onboarding/);
      });
    }
  });
});
