import { test, expect, type APIRequestContext } from "@playwright/test";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { bypassOnboarding } from "./fixtures";

const ANSWER = "I led the migration and reduced deployment time by three hours.";

async function createSession(request: APIRequestContext, answerModes: ("text" | "audio")[] = ["text"]): Promise<string> {
  const created = await request.post("/api/coach/sessions", {
    data: {
      company_name: "Synthetic Browser Co",
      role_title: "Engineer",
      jd_text: "Build reliable software.",
      experience_version: "conversational_v1",
      conversational_config: {
        interview_type: "mixed",
        difficulty: "realistic",
        duration_minutes: 30,
        planned_question_count: 6,
        role_family: "software_engineering",
        role_level: "senior",
        industry: "technology",
        locale: "en-GB",
        focus_areas: ["delivery_execution"],
        allowed_answer_modes: answerModes,
        evidence_selection: {
          application_cv: "none",
          master_cv: "exclude",
          question_bank: "exclude",
          company_research: "exclude",
          draft_evidence_consent: false,
        },
      },
    },
  });
  expect(created.status(), await created.text()).toBe(202);
  const { session_id: sessionId, job_id: setupJobId } = await created.json();
  expect(sessionId).toBeTruthy();
  expect(setupJobId).toBeTruthy();
  await expect.poll(async () => {
    const job = await request.get(`/api/async-jobs/${setupJobId}`);
    expect(job.ok()).toBeTruthy();
    return (await job.json()).status;
  }, { timeout: 20_000 }).toBe("done");
  return sessionId;
}

async function sendCommand(
  request: APIRequestContext,
  sessionId: string,
  commandType: string,
  payload: Record<string, unknown>,
) {
  const live = await request.get(`/api/coach/sessions/${sessionId}/live`);
  expect(live.status()).toBe(200);
  const current = await live.json();
  const response = await request.post(`/api/coach/sessions/${sessionId}/commands`, {
    data: {
      command_id: randomUUID(),
      command_type: commandType,
      expected_state_version: current.state_version,
      payload,
      contract_version: "coach_conversation_command_v1",
    },
  });
  expect(response.status(), await response.text()).toBe(200);
  return response.json();
}

async function submitTypedAnswer(page: import("@playwright/test").Page): Promise<void> {
  await page.getByRole("button", { name: "Answer in writing" }).click();
  await page.getByRole("textbox", { name: "Your answer" }).fill(ANSWER);
  await page.getByRole("button", { name: "Submit written answer" }).click();
  await expect(page.getByRole("button", { name: "Accept attempt", exact: false }).first()).toBeVisible({ timeout: 30_000 });
}

test("Scenario A: real typed interview completes with a persisted named-level report", async ({ page, request }) => {
  const liveStatuses: string[] = [];
  page.on("response", (response) => {
    if (!new URL(response.url()).pathname.endsWith("/live")) return;
    liveStatuses.push(String(response.status()));
    void response.json().then((body) => {
      liveStatuses.push(String(response.status() === 200 ? body?.conversation_state : body?.error?.code));
    }).catch(() => liveStatuses.push("unreadable-response"));
  });
  const sessionId = await createSession(request);

  await bypassOnboarding(page); // Only non-Coach shell endpoints are mocked.
  await page.goto(`/coach/session/${sessionId}`);
  await page.getByRole("button", { name: "Start interview" }).click();
  for (let index = 0; index < 6; index += 1) {
    try {
      await submitTypedAnswer(page);
    } catch (error) {
      const direct = await request.get(`/api/coach/sessions/${sessionId}/live`);
      const directBody = await direct.json();
      throw new Error(`Review did not render for question ${index + 1}; browser live: ${liveStatuses.join(",")}; direct live: ${direct.status()} ${directBody?.conversation_state ?? directBody?.error?.code}`, { cause: error });
    }
    await page.getByRole("button", { name: "Accept attempt 1" }).click();
    await expect.poll(async () => {
      const live = await request.get(`/api/coach/sessions/${sessionId}/live`);
      expect(live.ok()).toBeTruthy();
      const state = await live.json();
      return state.progress.planned_questions_completed;
    }, { timeout: 20_000 }).toBeGreaterThanOrEqual(index + 1);
  }

  await expect.poll(async () => {
    const response = await request.get(`/api/coach/sessions/${sessionId}/report`);
    return response.status();
  }, { timeout: 20_000 }).toBe(200);
  const reportResponse = await request.get(`/api/coach/sessions/${sessionId}/report`);
  const report = await reportResponse.json();
  expect(report.counts.planned_questions_answered).toBe(6);
  expect(report.counts.accepted_attempts).toBe(6);
  expect(report.session_level).toBe("interview_ready");
  await page.goto(`/coach/report/${sessionId}`);
  await expect(page.getByRole("heading", { name: "Interview ready" })).toBeVisible();
});

test("Scenario B backend: prerecorded audio is transcribed and default-owned media is removed", async ({ request }) => {
  const sessionId = await createSession(request, ["text", "audio"]);
  await sendCommand(request, sessionId, "start", {});
  const begun = await sendCommand(request, sessionId, "begin_answer", {
    recording_type: "audio",
    client_attempt_id: randomUUID(),
  });
  const attemptId = begun.active_attempt_id as string;
  expect(attemptId).toBeTruthy();
  const audio = Buffer.from(readFileSync(join(__dirname, "fixtures/coach-synthetic-tone.webm.b64"), "utf8").trim(), "base64");
  const uploadId = randomUUID();
  const uploaded = await request.post(`/api/coach/sessions/${sessionId}/attempts/${attemptId}/audio`, {
    multipart: {
      upload_id: uploadId,
      content_sha256: createHash("sha256").update(audio).digest("hex"),
      audio: { name: "synthetic-tone.webm", mimeType: "audio/webm", buffer: audio },
    },
  });
  expect(uploaded.status()).toBe(200);
  expect((await uploaded.json()).audio_retention_state).toBe("temporary");
  await sendCommand(request, sessionId, "finish_answer", { attempt_id: attemptId, upload_id: uploadId });
  await expect.poll(async () => {
    const response = await request.get(`/api/coach/sessions/${sessionId}/live`);
    if (!response.ok()) return `${response.status()}:${(await response.json()).error?.code}`;
    const state = await response.json();
    return `${state.conversation_state}:${state.active_attempt?.audio_retention_state}`;
  }, { timeout: 30_000 }).toBe("awaiting_next_action:deleted");
  const finalLive = await (await request.get(`/api/coach/sessions/${sessionId}/live`)).json();
  expect(finalLive.active_attempt.transcript_version.transcript).toBe(ANSWER);
  expect(finalLive.answer_review.evaluation_state).toBe("completed");
  const mediaRoot = process.env.HATCH_COACH_TEST_MEDIA_ROOT;
  expect(mediaRoot).toBeTruthy();
  await expect.poll(() => existsSync(mediaRoot!)
    ? readdirSync(mediaRoot!, { recursive: true }).filter((name) => name.endsWith(".webm"))
    : [], { timeout: 10_000 }).toEqual([]);
});

for (const selectedAttempt of [1, 2] as const) {
  test(`Scenario C: retry accepts attempt ${selectedAttempt} and reports only that source`, async ({ page, request }) => {
    const sessionId = await createSession(request);
    await bypassOnboarding(page);
    await page.goto(`/coach/session/${sessionId}`);
    await page.getByRole("button", { name: "Start interview" }).click();

    await submitTypedAnswer(page);
    const firstLive = await (await request.get(`/api/coach/sessions/${sessionId}/live`)).json();
    const firstAttemptId = firstLive.active_attempt.id as string;
    const firstQuestionId = firstLive.active_question.id as string;
    await page.getByRole("button", { name: "Get coaching for attempt 1" }).click();
    await expect.poll(async () => {
      const live = await request.get(`/api/coach/sessions/${sessionId}/live`);
      if (!live.ok()) return `${live.status()}:${(await live.json()).error?.code}`;
      return `${live.status()}:${(await live.json()).conversation_state}`;
    }, { timeout: 10_000 }).toBe("200:coaching");
    await page.getByRole("button", { name: "Try this question again" }).click();

    await submitTypedAnswer(page);
    const secondLive = await (await request.get(`/api/coach/sessions/${sessionId}/live`)).json();
    const secondAttemptId = secondLive.active_attempt.id as string;
    expect(secondAttemptId).not.toBe(firstAttemptId);
    if (selectedAttempt === 1) {
      await page.getByText("Attempt 1 -", { exact: false }).click();
      await page.getByRole("button", { name: "Accept attempt 1" }).click();
    } else {
      await page.getByRole("button", { name: "Accept attempt 2" }).click();
    }
    await expect.poll(async () => {
      const live = await request.get(`/api/coach/sessions/${sessionId}/live`);
      return (await live.json()).progress.planned_questions_completed;
    }, { timeout: 20_000 }).toBe(1);

    for (let index = 1; index < 6; index += 1) {
      await submitTypedAnswer(page);
      await page.getByRole("button", { name: "Accept attempt 1" }).click();
      await expect.poll(async () => {
        const live = await request.get(`/api/coach/sessions/${sessionId}/live`);
        return (await live.json()).progress.planned_questions_completed;
      }, { timeout: 20_000 }).toBeGreaterThanOrEqual(index + 1);
    }
    await expect.poll(async () => (await request.get(`/api/coach/sessions/${sessionId}/report`)).status(), {
      timeout: 20_000,
    }).toBe(200);
    const report = await (await request.get(`/api/coach/sessions/${sessionId}/report`)).json();
    expect(report.counts.accepted_attempts).toBe(6);
    expect(report.counts.retry_attempts).toBe(1);
    const firstQuestion = report.question_summaries.find((item: { question_id: string }) => item.question_id === firstQuestionId);
    expect(firstQuestion.accepted_attempt_id).toBe(selectedAttempt === 1 ? firstAttemptId : secondAttemptId);
  });
}
