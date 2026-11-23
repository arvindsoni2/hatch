import { type Route } from "@playwright/test";

import { expect, test, mockProtectedRouteApis } from "./fixtures";

const application = {
  id: "app-brief-e2e",
  job_id: null,
  status: "interview",
  priority: "normal",
  applied_date: null,
  cv_version: null,
  cover_letter_version: null,
  notes: null,
  recruiter_name: null,
  recruiter_email: null,
  recruiter_phone: null,
  agency_name: null,
  salary_offered: null,
  rejection_reason: null,
  agent_created: false,
  approval_status: "approved",
  cv_variant: null,
  cl_variant: null,
  response_received: false,
  response_date: null,
  is_active: true,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
  job: null,
  interviews: [
    {
      id: "round-1",
      application_id: "app-brief-e2e",
      round_number: 1,
      type: "behavioural",
      scheduled_at: "2026-12-20T10:00:00",
      duration_minutes: 60,
      location: "Video call",
      interviewer_name: "Priya",
      feedback: null,
      prep_notes: null,
      questions_asked: null,
      status: "scheduled",
      created_at: "2026-11-01T10:00:00Z",
      updated_at: "2026-11-01T10:00:00Z",
    },
  ],
};

const brief = {
  round_id: "round-1",
  state: "active",
  header: {
    company: "Northwind",
    role: "Delivery Lead",
    round_type: "behavioural",
    starts_at: "2026-12-20T10:00:00Z",
    display_timezone: "Europe/London",
    duration_minutes: 60,
    interviewer: "Priya",
    location: "Video call",
  },
  likely_questions: [
    { id: "q1", text: "Tell me about a delivery.", source: "question_bank" },
  ],
  stories: [
    {
      story_id: "s1",
      title: "Rescued a delivery",
      competencies: ["delivery"],
      score: 1,
      has_metric: true,
      talking_point: null,
    },
  ],
  watch_outs: [],
  gaps: [],
  ask_them: ["What does success look like?"],
  enhancement: {
    state: "none",
    fingerprint: "a".repeat(64),
    operation_id: null,
    model_identity: null,
  },
};

async function json(route: Route, body: unknown) {
  await route.fulfill({ status: 200, json: body });
}

test("test_print_layout_one_page", async ({ page }) => {
  await mockProtectedRouteApis(page);
  await page.route("**/api/applications/app-brief-e2e", (route) =>
    json(route, application)
  );
  await page.route("**/api/coach/readiness/rounds/round-1/brief", (route) =>
    json(route, brief)
  );

  await page.goto("/applications/app-brief-e2e");
  await page.getByRole("button", { name: "Interviews" }).click();
  await page.getByRole("tab", { name: "Brief", exact: true }).click();

  await expect(page.getByText("Likely questions")).toBeVisible();
  await expect(page.getByText("Your best stories")).toBeVisible();
  await expect(page.getByText("Questions to ask them")).toBeVisible();

  await page.emulateMedia({ media: "print" });
  await expect(
    page.getByRole("heading", { name: /behavioural interview with Northwind/i })
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Print brief" })).toBeHidden();

  const pdf = await page.pdf({ format: "A4", printBackground: true });
  const pages = pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) ?? [];
  expect(pages).toHaveLength(1);
});
