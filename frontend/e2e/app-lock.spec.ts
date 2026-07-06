import { expect, test, type Page } from "@playwright/test";

const policy = {
  min_length: 12,
  max_length: 128,
  require_letter: true,
  require_number: true,
  reject_edge_whitespace: true,
};

async function mockStatus(page: Page, configuredSource: "none" | "database") {
  await page.route("**/api/app-lock/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        enabled: true,
        configured_source: configuredSource,
        is_configured: configuredSource !== "none",
        is_unlocked: false,
        password_policy: policy,
      }),
    }),
  );
}

test("first-run setup rejects weak passwords and submits a valid password", async ({ page }) => {
  await mockStatus(page, "none");
  await page.route("**/api/app-lock/setup", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ unlocked: true }),
    }),
  );
  await page.goto("/unlock");

  const password = page.getByRole("textbox", { name: "Password", exact: true });
  const confirm = page.getByRole("textbox", { name: "Confirm password", exact: true });
  const submit = page.getByRole("button", { name: "Set password and continue" });

  await password.fill("abc123");
  await confirm.fill("abc123");
  await expect(submit).toBeDisabled();

  await password.fill("valid-password-1");
  await confirm.fill("valid-password-1");
  await expect(submit).toBeEnabled();
  const request = page.waitForRequest((candidate) =>
    candidate.url().endsWith("/api/app-lock/setup") && candidate.method() === "POST",
  );
  await submit.click();
  expect((await request).postDataJSON()).toEqual({ password: "valid-password-1" });
});

test("configured workspace reveals and submits its existing password", async ({ page }) => {
  await mockStatus(page, "database");
  await page.route("**/api/app-lock/unlock", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ unlocked: true }),
    }),
  );
  await page.goto("/unlock");

  const password = page.getByRole("textbox", { name: "Password", exact: true });
  await password.fill("legacy-password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(password).toHaveAttribute("type", "text");

  const request = page.waitForRequest((candidate) =>
    candidate.url().endsWith("/api/app-lock/unlock") && candidate.method() === "POST",
  );
  await page.getByRole("button", { name: "Unlock" }).click();
  expect((await request).postDataJSON()).toEqual({ password: "legacy-password" });
});
