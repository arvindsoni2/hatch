import { expect, test, type Page, type Route } from "@playwright/test";

import { bypassOnboarding } from "./fixtures";

const SESSION_ID = "session-review-e2e";
const ROOT_QUESTION_ID = "question-review-root";
const TRANSCRIPT = "I led a safe migration across three teams.";
const CONTENT_DIMENSIONS = [
  "relevance",
  "structure",
  "specificity",
  "impact",
  "role_depth",
  "clarity",
  "conciseness",
] as const;

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, json: body });
}

function question(
  id = ROOT_QUESTION_ID,
  text = "Describe a difficult delivery.",
  depth = 0,
) {
  return {
    id,
    text,
    category: "behavioural",
    difficulty: "realistic",
    question_kind: depth === 0 ? "planned" : "adaptive_follow_up",
    question_state: "answered",
    root_question_id: depth === 0 ? null : ROOT_QUESTION_ID,
    parent_question_id: depth === 0 ? null : ROOT_QUESTION_ID,
    follow_up_depth: depth,
    follow_up_reason: depth === 0 ? null : "clarify_example",
    attempts_created_count: 1,
    attempt_limit: 5,
    attempts_remaining: 4,
  };
}

function transcript(text = TRANSCRIPT, version = 1) {
  return {
    id: `transcript-review-${version}`,
    version_number: version,
    transcript: text,
    source: version === 1 ? "candidate_text" : "candidate_edit",
    edit_reason: version === 1 ? null : "transcription_error",
    created_by: "candidate",
    processing_generation: version,
    created_at: `2026-08-13T10:0${version}:00Z`,
  };
}

function attempt(
  id = "attempt-review-1",
  text = TRANSCRIPT,
  version = 1,
  selfAssessment: Record<string, unknown> | null = null,
) {
  return {
    id,
    question_id: ROOT_QUESTION_ID,
    recording_type: "text",
    attempt_number: 1,
    attempt_state: "completed",
    attempt_version: version + 1,
    processing_generation: version,
    processing_retry_count: 0,
    processing_retry_limit: 2,
    processing_retries_remaining: 2,
    audio_retention_policy: null,
    audio_retention_state: "not_applicable",
    transcript_version: transcript(text, version),
    self_assessment: selfAssessment,
  };
}

function review(
  text = TRANSCRIPT,
  overrides: Record<string, unknown> = {},
) {
  const excerpt = Array.from(text).slice(0, 5).join("");
  return {
    evaluation_id: "evaluation-review-1",
    evaluation_state: "completed",
    answer_level: "interview_ready",
    dimensions: Object.fromEntries(CONTENT_DIMENSIONS.map((name) => [name, {
      level: name === "impact" ? "developing" : "interview_ready",
      evidence: [{ transcript_start: 0, transcript_end: 5, excerpt }],
      rationale: `${name.replaceAll("_", " ")} is grounded in the answer.`,
      improvement: name === "impact" ? "Make the result more specific." : null,
    }])),
    delivery: { level: "not_assessed", observations: [] },
    evidence_consistency: "developing",
    evidence_findings: [{
      claim_id: "claim-review-1",
      claim_text: "three teams",
      transcript_start: 31,
      transcript_end: 42,
      status: "partially_supported",
      source_label: "Draft source",
      source_approval: "draft",
      explanation: "The selected draft supports part of this detail.",
      candidate_action: "Confirm the detail before reuse.",
    }],
    coaching: null,
    accepted_at: null,
    ...overrides,
  };
}

function reviewLive(overrides: Record<string, unknown> = {}) {
  const currentAttempt = attempt();
  return {
    session_id: SESSION_ID,
    experience_version: "conversational_v1",
    status: "active",
    conversation_state: "awaiting_next_action",
    state_version: 5,
    activity_version: 3,
    retention_version: 0,
    active_question: question(),
    root_question: question(),
    active_attempt: currentAttempt,
    answer_review: review(),
    attempt_history: [{
      attempt_id: currentAttempt.id,
      attempt_number: 1,
      answer_level: "interview_ready",
      accepted: false,
      transcript_available: true,
      audio_state: "not_applicable",
    }],
    processing: {
      job_id: null,
      stage: "content_evaluation",
      state: "completed",
      retryable: false,
      retry_count: 0,
      retry_limit: 2,
      retries_remaining: 2,
    },
    progress: {
      planned_questions_total: 3,
      planned_questions_completed: 0,
      follow_ups_completed: 0,
      current_planned_position: 1,
    },
    retention: {
      audio_policy: "delete_after_processing",
      current_audio_state: "not_applicable",
      retryable_audio_cleanup_attempt_id: null,
    },
    allowed_commands: [
      "record_self_assessment",
      "request_coaching",
      "edit_transcript",
      "accept_attempt",
      "retry_answer",
    ],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    recoverable_error: null,
    report_state: "not_started",
    contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

type ReviewController = {
  commands: Array<Record<string, unknown>>;
  getLive: () => Record<string, unknown>;
  setLive: (value: Record<string, unknown>) => void;
};

async function installReviewRoutes(
  page: Page,
  initial: Record<string, unknown> = reviewLive(),
): Promise<ReviewController> {
  let current: Record<string, unknown> = initial;
  let followUpsPresented = 0;
  let attemptCounter = 1;
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
  await page.route(`**/api/coach/sessions/${SESSION_ID}/commands`, async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    const payload = body.payload as Record<string, unknown>;
    const commandType = body.command_type;
    const nextVersion = Number(body.expected_state_version) + 1;
    commands.push(body);

    if (commandType === "record_self_assessment") {
      current = {
        ...current,
        state_version: nextVersion,
        active_attempt: {
          ...(current.active_attempt as Record<string, unknown>),
          self_assessment: {
            comfort_level: payload.comfort_level,
            felt_complete: payload.felt_complete,
            note: payload.note ?? null,
            recorded_at: "2026-08-13T10:10:00Z",
            contract_version: "coach_candidate_self_assessment_v1",
          },
        },
      };
    } else if (commandType === "request_coaching") {
      current = {
        ...current,
        conversation_state: "coaching",
        state_version: nextVersion,
        allowed_commands: ["record_self_assessment", "return_to_review", "accept_attempt"],
        answer_review: {
          ...(current.answer_review as Record<string, unknown>),
          coaching: {
            positive_observation: "Your action is easy to follow.",
            priority_improvement: "Make the verified outcome clearer.",
            suggested_structure: "Keep the situation, action, and result order.",
            practice_instruction: "Practise once using only confirmed details.",
            example_revision: "I led the migration and achieved [add verified outcome].",
          },
        },
      };
    } else if (commandType === "return_to_review") {
      current = {
        ...current,
        conversation_state: "awaiting_next_action",
        state_version: nextVersion,
        allowed_commands: ["record_self_assessment", "request_coaching", "edit_transcript", "accept_attempt"],
      };
    } else if (commandType === "edit_transcript") {
      const corrected = String(payload.transcript);
      current = {
        ...current,
        state_version: nextVersion,
        active_attempt: attempt(String(payload.attempt_id), corrected, 2),
        answer_review: review(corrected, { evaluation_id: "evaluation-review-2" }),
      };
    } else if (commandType === "retry_answer") {
      attemptCounter += 1;
      current = {
        ...current,
        conversation_state: "listening",
        state_version: nextVersion,
        active_attempt: {
          ...attempt(`attempt-review-${attemptCounter}`),
          attempt_number: attemptCounter,
          attempt_state: "draft",
          transcript_version: null,
        },
        answer_review: null,
        allowed_commands: ["finish_answer", "cancel_attempt"],
      };
    } else if (commandType === "finish_answer") {
      const answer = String(payload.transcript);
      const active = current.active_attempt as Record<string, unknown>;
      current = {
        ...current,
        conversation_state: "awaiting_next_action",
        state_version: nextVersion,
        active_attempt: {
          ...attempt(String(active.id), answer),
          question_id: (current.active_question as Record<string, unknown>).id,
          attempt_number: active.attempt_number,
        },
        answer_review: review(answer, { evaluation_id: `evaluation-review-${attemptCounter}` }),
        attempt_history: [{
          attempt_id: active.id,
          attempt_number: active.attempt_number,
          answer_level: "interview_ready",
          accepted: false,
          transcript_available: true,
          audio_state: "not_applicable",
        }],
        allowed_commands: ["accept_attempt", "record_self_assessment", "request_coaching"],
      };
    } else if (commandType === "accept_attempt") {
      followUpsPresented += 1;
      const hasFollowUp = followUpsPresented <= 2;
      const nextQuestion = hasFollowUp
        ? question(
            `question-review-follow-up-${followUpsPresented}`,
            followUpsPresented === 1
              ? "What verified outcome followed?"
              : "What action did you personally own?",
            followUpsPresented,
          )
        : question("question-review-next-planned", "Describe another delivery.");
      current = {
        ...current,
        conversation_state: "asking",
        state_version: nextVersion,
        active_question: { ...nextQuestion, question_state: "asked", attempts_created_count: 0, attempts_remaining: 5 },
        active_attempt: null,
        answer_review: null,
        attempt_history: [],
        progress: {
          ...(current.progress as Record<string, unknown>),
          follow_ups_completed: Math.min(followUpsPresented, 2),
        },
        allowed_commands: ["begin_answer"],
      };
    } else if (commandType === "begin_answer") {
      attemptCounter += 1;
      const activeQuestion = current.active_question as Record<string, unknown>;
      current = {
        ...current,
        conversation_state: "listening",
        state_version: nextVersion,
        active_attempt: {
          ...attempt(`attempt-review-${attemptCounter}`),
          question_id: activeQuestion.id,
          attempt_number: 1,
          attempt_state: "draft",
          transcript_version: null,
        },
        allowed_commands: ["finish_answer", "cancel_attempt"],
      };
    }

    await json(route, {
      command_id: body.command_id,
      result: commandType === "finish_answer" || commandType === "edit_transcript"
        ? "accepted_processing"
        : "completed",
      session_id: SESSION_ID,
      state: current.conversation_state,
      state_version: current.state_version,
      active_question_id: (current.active_question as Record<string, unknown> | null)?.id ?? null,
      active_attempt_id: (current.active_attempt as Record<string, unknown> | null)?.id ?? null,
      async_job_id: null,
      allowed_commands: current.allowed_commands,
      contract_version: "coach_conversation_command_result_v1",
    });
  });
  return {
    commands,
    getLive: () => current,
    setLive: (value) => { current = value; },
  };
}

test("typed answer review shows only named levels and Not assessed delivery", async ({ page }) => {
  await installReviewRoutes(page);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await expect(page.getByRole("heading", { name: "Answer quality" })).toBeVisible();
  await expect(page.getByText("Overall: Interview-ready")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Delivery observations" })).toBeVisible();
  await expect(page.getByText("Not assessed").first()).toBeVisible();
  await expect(page.getByText("Draft source")).toBeVisible();
  await expect(page.locator("main.mx-auto").getByText(/score|confidence|personality/i)).toHaveCount(0);
});

test("candidate reflection saves and overwrites without changing review quality", async ({ page }) => {
  const routes = await installReviewRoutes(page);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByLabel("Comfort level").selectOption("high");
  await page.getByLabel("My answer felt complete").check();
  await page.getByLabel("Reflection note").fill("The outcome needs one clearer sentence.");
  await page.getByRole("button", { name: "Save reflection" }).click();
  await expect(page.getByText("Overall: Interview-ready")).toBeVisible();

  await page.getByLabel("Comfort level").selectOption("low");
  await page.getByLabel("Reflection note").fill("I will verify the team count.");
  await page.getByRole("button", { name: "Save reflection" }).click();

  const reflections = routes.commands.filter((item) => item.command_type === "record_self_assessment");
  expect(reflections).toHaveLength(2);
  expect((reflections[0].payload as Record<string, unknown>).note).toBe("The outcome needs one clearer sentence.");
  expect((reflections[1].payload as Record<string, unknown>).note).toBe("I will verify the team count.");
  expect((routes.getLive().answer_review as Record<string, unknown>).answer_level).toBe("interview_ready");
});

test("optional coaching preserves the rubric and returns to review", async ({ page }) => {
  const routes = await installReviewRoutes(page);
  const originalReview = structuredClone(routes.getLive().answer_review);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Get coaching for attempt 1" }).click();
  await expect(page.getByRole("heading", { name: "Coaching" })).toBeVisible();
  await expect(page.getByText("Make the verified outcome clearer.")).toBeVisible();
  expect((routes.getLive().answer_review as Record<string, unknown>).dimensions)
    .toEqual((originalReview as Record<string, unknown>).dimensions);

  await page.getByRole("button", { name: "Return to review" }).click();
  await expect(page.getByRole("button", { name: "Get coaching for attempt 1" })).toBeVisible();
});

test("transcript correction publishes a new version while retaining original delivery", async ({ page }) => {
  const routes = await installReviewRoutes(page);
  const originalDelivery = structuredClone(
    (routes.getLive().answer_review as Record<string, unknown>).delivery,
  );
  await page.goto(`/coach/session/${SESSION_ID}`);

  const editor = page.getByLabel("Corrected transcript");
  await editor.fill("I led a safe migration across four teams.");
  await page.getByRole("button", { name: "Re-run review with corrected transcript" }).click();

  await expect(page.getByText("Candidate correction, version 2")).toBeVisible();
  await expect(editor).toHaveValue("I led a safe migration across four teams.");
  expect((routes.getLive().answer_review as Record<string, unknown>).delivery).toEqual(originalDelivery);
  expect(routes.commands.filter((item) => item.command_type === "edit_transcript")).toHaveLength(1);
});

test("attempt history exposes server acceptance controls without numeric scoring", async ({ page }) => {
  await installReviewRoutes(page, reviewLive({
    attempt_history: [
      {
        attempt_id: "attempt-review-old",
        attempt_number: 1,
        answer_level: "developing",
        accepted: false,
        transcript_available: true,
        audio_state: "deleted",
      },
      {
        attempt_id: "attempt-review-1",
        attempt_number: 2,
        answer_level: "interview_ready",
        accepted: false,
        transcript_available: true,
        audio_state: "not_applicable",
      },
    ],
  }));
  await page.goto(`/coach/session/${SESSION_ID}`);

  await expect(page.getByText("Attempt 1 - Developing - not accepted")).toBeVisible();
  await expect(page.getByText("Attempt 2 - Interview-ready - not accepted")).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept attempt 1" })).toBeVisible();
  await expect(page.getByText(/\b\d+(?:\.\d+)?%\b/)).toHaveCount(0);
});

test("two grounded follow-ups are presented and a third is not created", async ({ page }) => {
  const routes = await installReviewRoutes(page);
  await page.goto(`/coach/session/${SESSION_ID}`);

  for (const expectedQuestion of [
    "What verified outcome followed?",
    "What action did you personally own?",
    "Describe another delivery.",
  ]) {
    await page.getByRole("button", { name: /Accept attempt/ }).first().click();
    await expect(page.getByRole("heading", { name: expectedQuestion })).toBeVisible();
    if (expectedQuestion === "Describe another delivery.") break;
    await page.getByRole("button", { name: "Answer in writing" }).click();
    await page.getByRole("textbox", { name: "Your answer" }).fill("I supplied a grounded follow-up answer.");
    await page.getByRole("button", { name: "Submit written answer" }).click();
    await expect(page.getByRole("heading", { name: "Answer quality" })).toBeVisible();
  }

  expect(routes.commands.filter((item) => item.command_type === "accept_attempt")).toHaveLength(3);
  expect((routes.getLive().active_question as Record<string, unknown>).question_kind).toBe("planned");
  expect((routes.getLive().progress as Record<string, unknown>).follow_ups_completed).toBe(2);
});

test("unsafe review and transcript strings remain inert text", async ({ page }) => {
  const unsafe = '<img src=x onerror="window.__reviewPwned=true">';
  await installReviewRoutes(page, reviewLive({
    active_attempt: attempt("attempt-review-1", unsafe),
    answer_review: review(unsafe, {
      coaching: {
        positive_observation: unsafe,
        priority_improvement: unsafe,
        suggested_structure: unsafe,
        practice_instruction: unsafe,
        example_revision: unsafe,
      },
    }),
    conversation_state: "coaching",
    allowed_commands: ["return_to_review"],
  }));
  await page.goto(`/coach/session/${SESSION_ID}`);

  await expect(page.getByText(unsafe).first()).toBeVisible();
  await expect(page.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { __reviewPwned?: boolean }).__reviewPwned))
    .toBeUndefined();
});
