import { type Route } from "@playwright/test";

import { expect, test, mockProtectedRouteApis } from "./fixtures";

const KINDS = [
  "dismissed_patterns",
  "focus_areas_and_plans",
  "briefs",
  "debriefs",
  "explain_tips",
  "competency_overrides",
  "job_competencies",
] as const;

function inventory(count = 1) {
  return {
    kinds: KINDS.map((kind, index) => ({
      kind,
      count: index === 6 ? count : 2,
      last_updated: "2026-11-02T10:00:00Z",
    })),
  };
}

async function json(route: Route, body: unknown) {
  await route.fulfill({ status: 200, json: body });
}

test("test_remembers_page_lists_and_deletes", async ({ page }) => {
  await mockProtectedRouteApis(page);
  let current = inventory();
  await page.route("**/api/coach/readiness/memory**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (method === "GET") return json(route, current);
    if (method === "DELETE" && url.includes("/memory/debriefs")) {
      current = {
        kinds: current.kinds.map((item) =>
          item.kind === "debriefs" ? { ...item, count: 0, last_updated: null } : item,
        ),
      };
      return json(route, { kind: "debriefs", removed: 2 });
    }
    if (method === "DELETE" && url.endsWith("/memory")) {
      const removed = Object.fromEntries(
        current.kinds.map((item) => [item.kind, item.count]),
      );
      current = {
        kinds: current.kinds.map((item) => ({ ...item, count: 0, last_updated: null })),
      };
      return json(route, { removed });
    }
    return json(route, {});
  });

  await page.goto("/settings/privacy/remembers");

  await expect(page.getByRole("heading", { name: "Privacy" })).toBeVisible();
  await expect(page.getByText("Patterns", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Delete practice sessions in Coach" }),
  ).toHaveAttribute("href", "/coach");

  const rows = page.getByRole("listitem");
  await expect(rows).toHaveCount(8);
  await expect(rows.nth(7)).toContainText("Job description competencies");
  await expect(rows.nth(7)).toContainText("1 row");

  // Debrief delete: the option explains that it clears the rounds' whole list.
  await page.getByRole("button", { name: "Delete Debriefs" }).click();
  await expect(page.getByText("Delete debriefs?")).toBeVisible();
  await expect(
    page.getByText(/clears the whole question list on each round whose debrief is deleted/),
  ).toBeVisible();
  await page.getByLabel("Also clear questions on the round").check();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Delete", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Debriefs: removed 2.");

  // Delete-all confirm dialog.
  await page.getByRole("button", { name: "Delete all Coach readiness data" }).click();
  await expect(page.getByText("Delete all Coach readiness data?")).toBeVisible();
  await expect(
    page.getByText(/stories and Question Bank entries are untouched/),
  ).toBeVisible();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Delete all Coach readiness data" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    /Removed .* readiness items\./,
  );
  await expect(page.getByText("0 rows")).toHaveCount(7);
});

test("test_readiness_footer_links_to_remembers", async ({ page }) => {
  await mockProtectedRouteApis(page);
  await page.route("**/api/coach/readiness/patterns**", (route) =>
    json(route, { groups: [], include_stale: true }),
  );
  await page.route("**/api/coach/readiness/focus-areas", (route) =>
    json(route, { items: [], active_count: 0, active_limit: 3 }),
  );
  await page.route("**/api/coach/readiness/plans", (route) =>
    json(route, { active: null, draft: null }),
  );
  await page.route("**/api/coach/readiness/coverage/overview", (route) =>
    json(route, { gaps: [], signals: [] }),
  );
  await page.route("**/api/interviews/upcoming**", (route) => json(route, []));
  await page.route("**/api/coach/readiness/display-timezone", (route) =>
    json(route, { display_timezone: null }),
  );

  await page.goto("/coach/readiness");

  const footer = page.getByText(/Hatch keeps patterns, plans, briefs and debriefs/);
  await expect(footer).toBeVisible();
  await expect(
    page.getByRole("link", { name: "What Hatch remembers" }),
  ).toHaveAttribute("href", "/settings/privacy/remembers");
});

test("test_general_settings_shows_display_timezone", async ({ page }) => {
  await mockProtectedRouteApis(page);
  await page.route("**/api/coach/readiness/display-timezone", (route) =>
    json(route, { display_timezone: "Europe/London" }),
  );

  await page.goto("/settings/general");

  await expect(page.getByRole("heading", { name: "General" })).toBeVisible();
  await expect(page.getByText("Display timezone: Europe/London")).toBeVisible();
  await expect(
    page.getByText(/Interview times are stored as UTC and shown in this zone/),
  ).toBeVisible();
});
