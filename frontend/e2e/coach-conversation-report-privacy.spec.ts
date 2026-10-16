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

// Mocked HTTP responses exercise browser wiring/rendering only, not integrated
// backend execution, report reconstruction, privacy outcomes or model acceptance.
test("selects legal progress contexts and keeps dimension groups and hostile findings separate", async ({ page }) => {
  await bypassOnboarding(page);
  const requests: Array<Record<string, string>> = [];
  const dimensions = { relevance: "developing", structure: "strong", specificity: "not_assessed",
    impact: "not_assessed", role_depth: "not_assessed", clarity: "not_assessed", conciseness: "not_assessed" };
  const session = { id: SESSION_ID, company_name: "Synthetic", role_title: "Engineer",
    status: "completed", overall_score: null, created_at: "2026-01-01T10:00:00",
    experience_version: "conversational_v1", conversation_state: "completed",
    session_level: "developing", retention_summary: null };
  await page.route("**/api/coach/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/coach/capabilities") return json(route, {
      face_analysis: false, tts: false, conversational_interview: true,
    });
    if (url.pathname === "/api/coach/sessions") return json(route, [session]);
    if (url.pathname === `/api/coach/sessions/${SESSION_ID}`) return json(route, {
      ...session, application_id: "application-progress-ui", questions: [],
    });
    if (url.pathname === `/api/coach/sessions/${SESSION_ID}/report`) return json(route, {
      session_id: SESSION_ID, report_state: "completed", activity_version: 1, retention_version: 0,
      session_level: "developing", dimensions, compatibility_key: "key-a",
      counts: { planned_questions_total: 2, planned_questions_answered: 2, planned_questions_skipped: 0,
        follow_ups_asked: 0, follow_ups_answered: 0, accepted_attempts: 2,
        retry_attempts: 0, unavailable_attempts: 0, hints_used: 0 },
      strengths: [], improvement_priorities: [], unassessed_areas: ["specificity", "impact", "role_depth", "clarity", "conciseness"],
      evidence_review_items: [], question_summaries: [], practice_suggestions: [],
      candidate_reflection: null, retention_summary: { attempts: [] }, diagnostics: {},
      contract_version: "coach_conversational_report_v1",
    });
    if (url.pathname === "/api/coach/conversational-progress") {
      const filters = Object.fromEntries(url.searchParams.entries());
      requests.push(filters);
      const keys = "application_id" in filters ? ["a", "b"] : ["a"];
      return json(route, {
        selector_mode: "application_id" in filters ? "filtered" : "exact", applied_filters: filters,
        group_limit: 20, total_groups: keys.length, returned_groups: keys.length, groups_truncated: false,
        groups: keys.map((key) => ({
          compatibility_key: `key-${key}`, context: { application_id: "application-progress-ui",
            company_name: "Synthetic", role_title: `Format ${key.toUpperCase()}`,
            role_family: "software_engineering", role_level: "senior", interview_type: "behavioural" },
          sessions: [{ session_id: `session-${key}`, activity_version: 1,
            completed_at: "2026-01-01T10:00:00", session_level: "developing", dimensions }],
          current_levels: dimensions, previous_levels: { ...dimensions, relevance: "strong" },
          trends: { relevance: key === "a" ? "mixed" : "declining", structure: "stable",
            specificity: "not_enough_evidence", impact: "not_enough_evidence",
            role_depth: "not_enough_evidence", clarity: "not_enough_evidence", conciseness: "not_enough_evidence" },
          strongest_areas: [], priority_areas: [], evidence_review_items: [{
            attempt_id: ATTEMPT_ID, claim_id: `claim-${key}`, claim_text: HOSTILE_TRANSCRIPT,
            transcript_start: 0, transcript_end: Array.from(HOSTILE_TRANSCRIPT).length,
            status: "not_verifiable", evidence_ids: [], explanation: "No permitted matching source.",
            candidate_action: "Review the source before reuse.",
          }],
        })), contract_version: "coach_conversational_progress_v2",
      });
    }
    return route.fallback();
  });
  await page.goto("/coach");
  await expect(page.getByRole("combobox", { name: "Progress interview" })).toBeVisible();
  expect(requests).toEqual([]);
  await page.getByRole("combobox", { name: "Progress interview" }).selectOption(SESSION_ID);
  await expect(page.getByRole("heading", { name: "Format A" })).toBeVisible();
  const tables = page.getByRole("table");
  await expect(tables).toHaveCount(1);
  await expect(tables.nth(0).getByText("Mixed")).toBeVisible();
  await expect(page.getByText(HOSTILE_TRANSCRIPT).first()).toBeVisible();
  await expect(page.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __coachPrivacyXss?: boolean }).__coachPrivacyXss)).toBeUndefined();
  expect(requests.at(-1)).toEqual({ compatibility_key: "key-a" });
  await page.getByRole("combobox", { name: "Compare interviews" }).selectOption("application");
  await expect.poll(() => requests.at(-1)).toEqual({ application_id: "application-progress-ui" });
  await expect(tables).toHaveCount(2);
  await expect(tables.nth(0).getByText("Mixed")).toBeVisible();
  await expect(tables.nth(1).getByText("Declining")).toBeVisible();
});
