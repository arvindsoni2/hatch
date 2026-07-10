import { expect, test } from "@playwright/test";
import { mkdir, stat } from "node:fs/promises";
import path from "node:path";

const ROOT = path.resolve(__dirname, "../..");
const IMAGE_DIR = path.join(ROOT, "docs/visual-evidence/readme");

const SCREENS = [
  "onboarding",
  "today-ready",
  "pipeline",
  "applications",
  "cv-studio",
  "interview-prep",
] as const;

test.describe("README screenshots", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/app-lock/status", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: false,
          configured_source: "none",
          is_configured: false,
          is_unlocked: true,
          password_policy: {
            min_length: 12,
            max_length: 128,
            require_letter: true,
            require_number: true,
            reject_edge_whitespace: true,
          },
        }),
      });
    });
    await page.route("**/api/v2/profile/status", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          onboarding_required: false,
          candidate_name: "Preview User",
          has_resume: true,
          llm_provider: "local",
          target_roles: ["Delivery Lead"],
        }),
      });
    });
    await page.clock.setFixedTime(new Date("2026-07-10T09:30:00Z"));
    await page.addStyleTag({
      content: `
        *, *::before, *::after {
          animation-duration: 0s !important;
          animation-delay: 0s !important;
          transition-duration: 0s !important;
          scroll-behavior: auto !important;
        }
      `,
    });
  });

  for (const screen of SCREENS) {
    test(`captures ${screen}.png`, async ({ page }) => {
      await mkdir(IMAGE_DIR, { recursive: true });
      await page.goto(`/readme-preview/${screen}`, { waitUntil: "networkidle" });

      await expect(page.getByTestId(`readme-preview-${screen}`)).toBeVisible();
      await expect(page.locator("body")).not.toContainText("Application error");

      const filePath = path.join(IMAGE_DIR, `${screen}.png`);
      await page.screenshot({ path: filePath, fullPage: true });

      const info = await stat(filePath);
      expect(info.size).toBeGreaterThan(0);
    });
  }
});
