import { expect, test, type Page, type Route } from "@playwright/test";

import { bypassOnboarding } from "./fixtures";

const SESSION_ID = "session-report-privacy-e2e";
const ATTEMPT_ID = "attempt-report-privacy-e2e";
const HOSTILE_TRANSCRIPT = '<img src=x onerror="window.__coachPrivacyXss=true">';

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, json: body });
}

function live(overrides: Record<string, unknown> = {}) {
  return {
    session_id: SESSION_ID,
    experience_version: "conversational_v1",
    status: "active",
    conversation_state: "awaiting_next_action",
    state_version: 4,
    activity_version: 2,
    retention_version: 1,
    active_question: {
      id: "question-report-privacy-e2e",
      text: "Describe a difficult delivery.",
      category: "behavioural",
      difficulty: "realistic",
      question_kind: "planned",
      question_state: "answered",
      root_question_id: null,
      parent_question_id: null,
      follow_up_depth: 0,
      follow_up_reason: null,
      attempts_created_count: 1,
      attempt_limit: 5,
      attempts_remaining: 4,
    },
    root_question: null,
    active_attempt: {
      id: ATTEMPT_ID,
      question_id: "question-report-privacy-e2e",
      recording_type: "text",
      attempt_number: 1,
      attempt_state: "completed",
      attempt_version: 2,
      processing_generation: 1,
      processing_retry_count: 0,
      processing_retry_limit: 2,
      processing_retries_remaining: 2,
      audio_retention_policy: null,
      audio_retention_state: "not_applicable",
      transcript_version: {
        id: "transcript-report-privacy-e2e",
        version_number: 1,
        transcript: HOSTILE_TRANSCRIPT,
        source: "candidate_text",
        edit_reason: null,
        created_by: "candidate",
        processing_generation: 1,
        created_at: "2026-08-13T10:00:00Z",
      },
      self_assessment: null,
    },
    answer_review: null,
    attempt_history: [],
    processing: {
      job_id: null,
      stage: null,
      state: "completed",
      retryable: false,
      retry_count: 0,
      retry_limit: 2,
      retries_remaining: 2,
    },
    progress: {
      planned_questions_total: 1,
      planned_questions_completed: 1,
      follow_ups_completed: 0,
      current_planned_position: 1,
    },
    retention: {
      audio_policy: "delete_after_processing",
      current_audio_state: "not_applicable",
      retryable_audio_cleanup_attempt_id: null,
    },
    allowed_commands: ["delete_transcript"],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    recoverable_error: null,
    report_state: "completed",
    contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

async function installRoutes(page: Page) {
  let current = live();
  const commands: Array<Record<string, unknown>> = [];
  await bypassOnboarding(page);
  await page.route(`**/api/coach/sessions/${SESSION_ID}`, (route) => json(route, {
    id: SESSION_ID,
    application_id: null,
    experience_version: "conversational_v1",
    status: "active",
    company_name: "Synthetic Ltd",
    role_title: "Test Engineer",
    overall_score: null,
    questions: [],
    created_at: "2026-08-13T10:00:00Z",
    conversation_state: current.conversation_state,
    retention_summary: null,
  }));
  await page.route(`**/api/coach/sessions/${SESSION_ID}/live`, (route) => json(route, current));
  await page.route(`**/api/coach/sessions/${SESSION_ID}/diagnostics`, (route) => json(route, {
    session_id: SESSION_ID,
    status: "active",
    conversation_state: current.conversation_state,
    report_state: current.report_state,
    error_code: null,
    contract_version: "coach_support_diagnostics_v1",
  }));
  await page.route(`**/api/coach/sessions/${SESSION_ID}/commands`, async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    commands.push(body);
    current = live({
      ...current,
      state_version: Number(current.state_version) + 1,
      active_attempt: {
        ...(current.active_attempt as Record<string, unknown>),
        transcript_version: null,
      },
      allowed_commands: [],
    });
    await json(route, {
      command_id: body.command_id,
      result: "completed",
      session_id: SESSION_ID,
      state: current.conversation_state,
      state_version: current.state_version,
      active_question_id: null,
      active_attempt_id: ATTEMPT_ID,
      async_job_id: null,
      allowed_commands: [],
      contract_version: "coach_conversation_command_result_v1",
    });
  });
  await page.route(`**/api/coach/sessions/${SESSION_ID}/deletion-commands`, async (route) => {
    await json(route, {
      session_id: SESSION_ID,
      request_id: "deletion-request-report-privacy-e2e",
      result_state: "processing",
      error_code: null,
      receipt_expires_at: "2026-09-12T10:00:00Z",
      contract_version: "coach_session_hard_delete_v1",
    });
  });
  return commands;
}

test("renders hostile transcript text without executing it and confirms transcript deletion in-app", async ({ page }) => {
  const commands = await installRoutes(page);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await expect(page.getByRole("heading", { name: "Privacy controls" })).toBeVisible();
  await expect(page.getByText(HOSTILE_TRANSCRIPT).first()).toBeVisible();
  await expect(page.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __coachPrivacyXss?: boolean }).__coachPrivacyXss)).toBeUndefined();

  await page.getByRole("button", { name: "Delete transcript" }).click();
  await expect(page.getByRole("alertdialog", { name: "Confirm transcript deletion" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm transcript deletion" }).click();
  await expect.poll(() => commands.filter((item) => item.command_type === "delete_transcript").length).toBe(1);
});

test("submits hard deletion only after accessible confirmation and never opens a browser dialog", async ({ page }) => {
  await installRoutes(page);
  let browserDialogOpened = false;
  page.on("dialog", () => { browserDialogOpened = true; });
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Delete interview" }).click();
  await expect(page.getByRole("alertdialog", { name: "Confirm interview deletion" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm interview deletion" }).click();
  await expect(page.getByText("Deletion is processing.")).toBeVisible();
  expect(browserDialogOpened).toBe(false);
});
