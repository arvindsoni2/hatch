import { expect, test, type Page, type Route } from "@playwright/test";

import { bypassOnboarding } from "./fixtures";

const SESSION_ID = "session-e2e";
const QUESTION_ID = "question-e2e-1";
const ATTEMPT_ID = "attempt-e2e-1";
const TRANSCRIPT = "Synthetic answer with <script>window.__coachXss = true</script> text.";

const sessionSummary = {
  id: SESSION_ID,
  application_id: null,
  experience_version: "conversational_v1",
  status: "active",
  company_name: "Synthetic Ltd",
  role_title: "Test Engineer",
  overall_score: null,
  questions: [],
  created_at: "2026-08-09T10:00:00Z",
  conversation_state: "asking",
  retention_summary: null,
};

function question() {
  return {
    id: QUESTION_ID,
    text: "Describe a synthetic delivery.",
    category: "behavioural",
    difficulty: "realistic",
    question_kind: "planned",
    question_state: "asked",
    root_question_id: null,
    parent_question_id: null,
    follow_up_depth: 0,
    follow_up_reason: null,
    attempts_created_count: 1,
    attempt_limit: 5,
    attempts_remaining: 4,
  };
}

function attempt(overrides: Record<string, unknown> = {}) {
  return {
    id: ATTEMPT_ID,
    question_id: QUESTION_ID,
    recording_type: "text",
    attempt_number: 1,
    attempt_state: "draft",
    attempt_version: 1,
    processing_generation: 0,
    processing_retry_count: 0,
    processing_retry_limit: 2,
    processing_retries_remaining: 2,
    audio_retention_policy: null,
    audio_retention_state: "not_applicable",
    transcript_version: null,
    ...overrides,
  };
}

function live(state = "asking", version = 1, overrides: Record<string, unknown> = {}) {
  return {
    session_id: SESSION_ID,
    experience_version: "conversational_v1",
    status: "active",
    conversation_state: state,
    state_version: version,
    activity_version: 1,
    retention_version: 0,
    active_question: question(),
    root_question: question(),
    active_attempt: null,
    processing: {
      job_id: null,
      stage: null,
      state: "not_started",
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
      current_audio_state: null,
    },
    allowed_commands: state === "asking" ? ["begin_answer", "pause"] : [],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    recoverable_error: null,
    report_state: "not_started",
    contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

type SyntheticRoutes = {
  commands: Array<Record<string, unknown>>;
  commandMutations: Array<Record<string, unknown>>;
  uploads: Array<{ uploadId: string | null; contentSha256: string | null }>;
  getLive: () => Record<string, unknown>;
  installOn: (page: Page) => Promise<void>;
  liveReads: () => number;
  setAvailable: (available: boolean) => void;
  setLive: (next: Record<string, unknown>) => void;
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, json: body });
}

type RouteOptions = {
  commandConflict?: string;
  finishStaysProcessing?: boolean;
  uploadOutcomes?: Array<"abort" | "completed" | "conflict">;
};

async function installRoutes(
  page: Page,
  initialLive: Record<string, unknown> = live(),
  options: RouteOptions = {},
): Promise<SyntheticRoutes> {
  let currentLive = initialLive;
  let available = true;
  let liveReadCount = 0;
  const commands: Array<Record<string, unknown>> = [];
  const commandMutations: Array<Record<string, unknown>> = [];
  const uploads: Array<{ uploadId: string | null; contentSha256: string | null }> = [];

  const installOn = async (targetPage: Page) => {
    await bypassOnboarding(targetPage);
    await targetPage.route(`**/api/coach/sessions/${SESSION_ID}`, (route) => json(route, sessionSummary));
    await targetPage.route(`**/api/coach/sessions/${SESSION_ID}/live`, (route) => {
      liveReadCount += 1;
      if (!available) return route.abort("failed");
      return json(route, currentLive);
    });
    await targetPage.route(`**/api/coach/sessions/${SESSION_ID}/commands`, async (route) => {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      commands.push(body);
      const commandType = body.command_type;
      const payload = body.payload as Record<string, unknown>;
      const version = Number(body.expected_state_version) + 1;

      if (commandType === options.commandConflict) {
        return json(route, {
          error: {
            code: "coach_conversation_version_conflict",
            message: "The interview changed since this view was loaded.",
            current_state_version: Number(body.expected_state_version) + 1,
            current_state: currentLive.conversation_state,
            retryable: false,
          },
        }, 409);
      }

      commandMutations.push(body);

      if (commandType === "begin_answer") {
        const recordingType = payload.recording_type;
        currentLive = live("listening", version, {
          active_attempt: attempt({
            recording_type: recordingType,
            audio_retention_policy: recordingType === "audio" ? "delete_after_processing" : null,
            audio_retention_state: recordingType === "audio" ? "temporary" : "not_applicable",
          }),
          retention: {
            audio_policy: "delete_after_processing",
            current_audio_state: recordingType === "audio" ? "temporary" : "not_applicable",
          },
          allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
        });
      } else if (commandType === "finish_answer") {
        const isAudio = payload.upload_id !== undefined && payload.upload_id !== null;
        currentLive = options.finishStaysProcessing ? live("processing_answer", version, {
          active_attempt: attempt({
            recording_type: isAudio ? "audio" : "text",
            attempt_state: "pending_processing",
            processing_generation: 1,
            audio_retention_policy: isAudio ? "delete_after_processing" : null,
            audio_retention_state: isAudio ? "temporary" : "not_applicable",
            transcript_version: isAudio ? null : {
              id: "transcript-e2e-1",
              version_number: 1,
              transcript: payload.transcript ?? TRANSCRIPT,
              source: "candidate_text",
              edit_reason: null,
              created_by: "candidate",
              processing_generation: 1,
              created_at: "2026-08-09T10:01:00Z",
            },
          }),
          processing: {
            job_id: "job-e2e-1",
            stage: isAudio ? "transcription" : "content_evaluation",
            state: "running",
            retryable: false,
            retry_count: 0,
            retry_limit: 2,
            retries_remaining: 2,
          },
          retention: {
            audio_policy: "delete_after_processing",
            current_audio_state: isAudio ? "temporary" : "not_applicable",
          },
          allowed_commands: [],
        }) : live("awaiting_next_action", version, {
          active_attempt: attempt({
            recording_type: isAudio ? "audio" : "text",
            attempt_state: "unavailable",
            attempt_version: 2,
            processing_generation: 1,
            audio_retention_policy: isAudio ? "delete_after_processing" : null,
            audio_retention_state: isAudio ? "deleted" : "not_applicable",
            transcript_version: {
              id: "transcript-e2e-1",
              version_number: 1,
              transcript: isAudio ? "Synthetic audio transcript remains visible." : payload.transcript ?? TRANSCRIPT,
              source: isAudio ? "transcription" : "candidate_text",
              edit_reason: null,
              created_by: isAudio ? "system" : "candidate",
              processing_generation: 1,
              created_at: "2026-08-09T10:01:00Z",
            },
          }),
          processing: {
            job_id: null,
            stage: "content_evaluation",
            state: "unavailable",
            retryable: false,
            retry_count: 0,
            retry_limit: 2,
            retries_remaining: 2,
          },
          retention: {
            audio_policy: "delete_after_processing",
            current_audio_state: isAudio ? "deleted" : "not_applicable",
          },
          allowed_commands: ["retry_answer", "accept_attempt", "update_retention"],
        });
      } else if (commandType === "keep_speaking") {
        currentLive = { ...currentLive, state_version: version };
      } else if (commandType === "pause") {
        currentLive = { ...currentLive, conversation_state: "paused", state_version: version, allowed_commands: ["resume"] };
      } else if (commandType === "resume") {
        currentLive = {
          ...currentLive,
          conversation_state: "listening",
          state_version: version,
          allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
        };
      } else if (commandType === "cancel_attempt") {
        currentLive = live("asking", version);
      } else if (commandType === "update_retention") {
        currentLive = {
          ...currentLive,
          state_version: version,
          retention_version: Number(currentLive.retention_version) + 1,
          retention: {
            ...(currentLive.retention as Record<string, unknown>),
            audio_policy: payload.audio,
          },
        };
      } else if (commandType === "delete_audio") {
        currentLive = {
          ...currentLive,
          state_version: version,
          retention_version: Number(currentLive.retention_version) + 1,
          retention: {
            ...(currentLive.retention as Record<string, unknown>),
            current_audio_state: "deleted",
          },
          active_attempt: {
            ...(currentLive.active_attempt as Record<string, unknown>),
            audio_retention_state: "deleted",
          },
          allowed_commands: ["update_retention", "retry_answer"],
        };
      }

      return json(route, {
        command_id: body.command_id,
        result: commandType === "finish_answer" ? "accepted_processing" : "completed",
        session_id: SESSION_ID,
        state: currentLive.conversation_state,
        state_version: currentLive.state_version,
        active_question_id: QUESTION_ID,
        active_attempt_id: ATTEMPT_ID,
        async_job_id: commandType === "finish_answer" ? "job-e2e-1" : null,
        allowed_commands: currentLive.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      });
    });
    await targetPage.route(`**/api/coach/sessions/${SESSION_ID}/attempts/${ATTEMPT_ID}/audio`, async (route) => {
      const multipart = route.request().postData() ?? "";
      const field = (name: string) => multipart.match(
        new RegExp(`name="${name}"\\r\\n\\r\\n([^\\r\\n]+)`),
      )?.[1] ?? null;
      uploads.push({
        uploadId: field("upload_id"),
        contentSha256: field("content_sha256"),
      });
      const outcome = options.uploadOutcomes?.shift() ?? "completed";
      if (outcome === "abort") return route.abort("failed");
      if (outcome === "conflict") {
        return json(route, {
          error: {
            code: "coach_audio_upload_idempotency_conflict",
            message: "This upload ID was already used for different audio.",
            retryable: false,
          },
        }, 409);
      }
      return json(route, {
        attempt_id: ATTEMPT_ID,
        upload_id: uploads.at(-1)?.uploadId,
        result: "completed",
        content_sha256: uploads.at(-1)?.contentSha256,
        byte_size: 15,
        mime_type: "audio/webm",
        audio_retention_state: "temporary",
        contract_version: "coach_attempt_audio_upload_v1",
      });
    });
  };

  await installOn(page);

  return {
    commands,
    commandMutations,
    uploads,
    getLive: () => currentLive,
    installOn,
    liveReads: () => liveReadCount,
    setAvailable: (next) => {
      available = next;
    },
    setLive: (next) => {
      currentLive = next;
    },
  };
}

async function installSyntheticMedia(page: Page) {
  await page.clock.install({ time: new Date("2026-08-09T10:00:00Z") });
  await page.addInitScript(() => {
    let analyserDb = -52;
    let id = 0;
    Object.defineProperty(window, "__setCoachAnalyserDb", {
      configurable: true,
      value: (value: number) => {
        analyserDb = value;
      },
    });
    Object.defineProperty(crypto, "randomUUID", {
      configurable: true,
      value: () => {
        id += 1;
        return `00000000-0000-4000-8000-${id.toString().padStart(12, "0")}`;
      },
    });

    const stream = {
      getTracks: () => [{ stop: () => undefined }],
    };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => stream },
    });

    class SyntheticMediaRecorder {
      state: RecordingState = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      onerror: (() => void) | null = null;

      constructor(_stream: unknown) {}
      start() { this.state = "recording"; }
      pause() { this.state = "paused"; }
      resume() { this.state = "recording"; }
      stop() {
        if (this.state === "inactive") return;
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["synthetic-audio"], { type: this.mimeType }) });
        this.onstop?.();
      }
    }
    Object.defineProperty(window, "MediaRecorder", {
      configurable: true,
      value: SyntheticMediaRecorder,
    });

    class SyntheticAudioContext {
      state = "running";
      createMediaStreamSource() {
        return { connect: () => undefined, disconnect: () => undefined };
      }
      createAnalyser() {
        return {
          fftSize: 0,
          disconnect: () => undefined,
          getFloatTimeDomainData: (values: Float32Array) => {
            values.fill(10 ** (analyserDb / 20));
          },
        };
      }
      async close() { this.state = "closed"; }
    }
    Object.defineProperty(window, "AudioContext", {
      configurable: true,
      value: SyntheticAudioContext,
    });
  });
}

test("typed answer refresh restores a terminal unavailable review exactly once", async ({ page }) => {
  const routes = await installRoutes(page);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Answer in writing" }).click();
  await page.getByRole("textbox", { name: "Your answer" }).fill(TRANSCRIPT);
  await page.getByRole("button", { name: "Submit written answer" }).click();
  await expect(page.getByText("Answer review unavailable")).toBeVisible();
  const context = page.context();
  const commandCountBeforeRestore = routes.commands.length;
  await page.close();
  const restoredPage = await context.newPage();
  await routes.installOn(restoredPage);
  await restoredPage.goto(`/coach/session/${SESSION_ID}`);

  await expect(restoredPage.getByText("Answer review unavailable")).toBeVisible();
  await expect(restoredPage.getByText(TRANSCRIPT)).toBeVisible();
  expect(routes.commands).toHaveLength(commandCountBeforeRestore);
  expect(routes.commands.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
});

test("a command transport retry reuses the identical request and mutates once", async ({ page }) => {
  const routes = await installRoutes(page);
  const posts: Array<{ raw: string | null; body: Record<string, unknown> }> = [];
  await page.route(`**/api/coach/sessions/${SESSION_ID}/commands`, async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    if (body.command_type !== "finish_answer") {
      await route.fallback();
      return;
    }
    posts.push({
      raw: route.request().postData(),
      body,
    });
    if (posts.length === 1) {
      await route.abort("failed");
      return;
    }
    await route.fallback();
  });
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Answer in writing" }).click();
  await page.getByRole("textbox", { name: "Your answer" }).fill("Synthetic command retry answer.");
  await page.getByRole("button", { name: "Submit written answer" }).click();

  await expect(page.getByText("Answer review unavailable")).toBeVisible();
  expect(posts).toHaveLength(2);
  expect(posts[1].raw).toBe(posts[0].raw);
  expect(posts[1].body).toEqual(posts[0].body);
  expect(posts[1].body.command_id).toBe(posts[0].body.command_id);
  expect(routes.commands.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
  expect(routes.commandMutations.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
});

test("audio silence prompt keeps speaking then deletes audio while retaining transcript", async ({ page }) => {
  await installSyntheticMedia(page);
  const routes = await installRoutes(page);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Start audio answer" }).click();
  await expect(page.getByText("Microphone recording")).toBeVisible();
  await page.clock.runFor(500);
  await page.evaluate(() => {
    (window as unknown as { __setCoachAnalyserDb: (value: number) => void }).__setCoachAnalyserDb(-25);
  });
  await page.clock.runFor(1600);
  await page.evaluate(() => {
    (window as unknown as { __setCoachAnalyserDb: (value: number) => void }).__setCoachAnalyserDb(-55);
  });
  await page.clock.runFor(9000);

  await expect(page.getByRole("region", { name: "Silence check" })).toBeVisible();
  await page.getByRole("button", { name: "Keep speaking and continue recording" }).click();
  await expect(page.getByRole("region", { name: "Silence check" })).not.toBeVisible();
  await page.getByRole("button", { name: "Finish audio answer while recording" }).click();

  await expect(page.getByText(
    "Audio has been deleted. Your transcript, answer review, and saved delivery observations remain available.",
  )).toBeVisible();
  await expect(page.getByText("Synthetic audio transcript remains visible.")).toBeVisible();
  expect(routes.uploads).toHaveLength(1);
  expect(routes.commands.filter((command) => command.command_type === "keep_speaking")).toHaveLength(1);
  expect(routes.commands.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
});

test("paused refresh without an in-memory recorder offers truthful recovery only", async ({ page }) => {
  const paused = live("paused", 5, {
    active_attempt: attempt({
      recording_type: "audio",
      audio_retention_policy: "delete_after_processing",
      audio_retention_state: "temporary",
    }),
    retention: { audio_policy: "delete_after_processing", current_audio_state: "temporary" },
    allowed_commands: ["resume", "update_retention"],
  });
  const routes = await installRoutes(page, paused);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await expect(page.getByText(
    "This browser no longer has the live recording. The interview remains paused on the server.",
  )).toBeVisible();
  await expect(page.getByRole("button", { name: "Discard recording and try again" })).toBeVisible();
  await expect(page.getByRole("button", { name: /submit|upload captured/i })).not.toBeVisible();
  await expect(page.getByText("Interview paused")).toBeVisible();
  expect(routes.commands).toHaveLength(0);
});

test("backend restart reconciles terminal authority without duplicate begin or finish", async ({ page }) => {
  const routes = await installRoutes(page, live(), { finishStaysProcessing: true });
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Answer in writing" }).click();
  await page.getByRole("textbox", { name: "Your answer" }).fill("Synthetic restart answer.");
  await page.getByRole("button", { name: "Submit written answer" }).click();
  await expect(page.getByText("Reviewing answer").first()).toBeVisible();
  const context = page.context();
  const commandCountBeforeRestart = routes.commands.length;
  routes.setAvailable(false);
  await page.close();

  const unavailablePage = await context.newPage();
  await routes.installOn(unavailablePage);
  await unavailablePage.goto(`/coach/session/${SESSION_ID}`);
  await expect(unavailablePage.getByRole("button", { name: "Try refreshing interview" })).toBeVisible();
  expect(routes.commands).toHaveLength(commandCountBeforeRestart);
  await unavailablePage.close();

  routes.setLive(live("awaiting_next_action", 4, {
    active_attempt: attempt({
      attempt_state: "unavailable",
      attempt_version: 2,
      processing_generation: 1,
      transcript_version: {
        id: "transcript-e2e-restart",
        version_number: 1,
        transcript: "Synthetic restart answer.",
        source: "candidate_text",
        edit_reason: null,
        created_by: "candidate",
        processing_generation: 1,
        created_at: "2026-08-09T10:01:00Z",
      },
    }),
    processing: {
      job_id: null,
      stage: "content_evaluation",
      state: "unavailable",
      retryable: false,
      retry_count: 0,
      retry_limit: 2,
      retries_remaining: 2,
    },
    allowed_commands: ["retry_answer", "accept_attempt", "update_retention"],
  }));
  routes.setAvailable(true);

  const restartedPage = await context.newPage();
  await routes.installOn(restartedPage);
  await restartedPage.goto(`/coach/session/${SESSION_ID}`);
  await expect(restartedPage.getByText("Answer review unavailable")).toBeVisible();
  await expect(restartedPage.getByText("Synthetic restart answer.")).toBeVisible();

  expect(routes.commands.filter((command) => command.command_type === "begin_answer")).toHaveLength(1);
  expect(routes.commands.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
  expect(routes.commands).toHaveLength(commandCountBeforeRestart);
  expect(routes.commandMutations.filter((command) => command.command_type === "begin_answer")).toHaveLength(1);
  expect(routes.commandMutations.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
});

test("future retention update does not rewrite the current answer snapshot", async ({ page }) => {
  const current = live("awaiting_next_action", 8, {
    active_attempt: attempt({
      recording_type: "audio",
      attempt_state: "completed",
      audio_retention_policy: "delete_after_processing",
      audio_retention_state: "retained",
      transcript_version: {
        id: "transcript-e2e-retention",
        version_number: 1,
        transcript: "Synthetic retained transcript.",
        source: "transcription",
        edit_reason: null,
        created_by: "system",
        processing_generation: 1,
        created_at: "2026-08-09T10:02:00Z",
      },
    }),
    retention: { audio_policy: "retain_until_deleted", current_audio_state: "retained" },
    allowed_commands: ["update_retention"],
  });
  const routes = await installRoutes(page, current);
  await page.goto(`/coach/session/${SESSION_ID}`);

  const privacy = page.getByRole("region", { name: "Audio privacy" });
  await expect(privacy.getByRole("heading", { name: "Future answers" })).toBeVisible();
  await expect(privacy.getByText("Keep audio until I delete it")).toBeVisible();
  await expect(privacy.getByRole("heading", { name: "This answer" })).toBeVisible();
  await expect(privacy.getByText("Delete audio after processing", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Delete audio after processing for future answers" }).click();

  await expect(page.getByRole("button", { name: "Keep audio for future answers until I delete it" })).toBeVisible();
  await expect(privacy.getByText("Audio is retained for this answer.")).toBeVisible();
  expect(routes.commands).toHaveLength(1);
  expect(routes.commands[0]).toMatchObject({
    command_type: "update_retention",
    payload: { audio: "delete_after_processing" },
  });
});

test("explicit audio deletion preserves transcript review and reports deleted state", async ({ page }) => {
  const current = live("awaiting_next_action", 8, {
    active_attempt: attempt({
      recording_type: "audio",
      attempt_state: "completed",
      audio_retention_policy: "retain_until_deleted",
      audio_retention_state: "retained",
      transcript_version: {
        id: "transcript-e2e-delete",
        version_number: 1,
        transcript: "Transcript survives explicit audio deletion.",
        source: "transcription",
        edit_reason: null,
        created_by: "system",
        processing_generation: 1,
        created_at: "2026-08-09T10:03:00Z",
      },
    }),
    retention: { audio_policy: "retain_until_deleted", current_audio_state: "retained" },
    allowed_commands: ["delete_audio", "update_retention"],
  });
  const routes = await installRoutes(page, current);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Delete audio for this answer" }).click();

  await expect(page.getByText(
    "Audio has been deleted. Your transcript, answer review, and saved delivery observations remain available.",
  )).toBeVisible();
  await expect(page.getByText("Transcript survives explicit audio deletion.")).toBeVisible();
  expect(routes.commands).toHaveLength(1);
  expect(routes.commands[0]).toMatchObject({
    command_type: "delete_audio",
    payload: { attempt_id: ATTEMPT_ID },
  });
});

test("true upload transport retry reuses its ID and finishes once", async ({ page }) => {
  await installSyntheticMedia(page);
  const routes = await installRoutes(page, live(), { uploadOutcomes: ["abort", "completed"] });
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Start audio answer" }).click();
  await page.getByRole("button", { name: "Finish audio answer while recording" }).click();
  await expect(page.getByText("Your captured answer is still available. Upload it again when you are ready.")).toBeVisible();
  await page.getByRole("button", { name: "Upload captured answer again" }).click();

  await expect(page.getByText("Synthetic audio transcript remains visible.")).toBeVisible();
  expect(routes.uploads).toHaveLength(2);
  expect(routes.uploads[0].uploadId).toBe(routes.uploads[1].uploadId);
  expect(routes.uploads[0].contentSha256).toBe(routes.uploads[1].contentSha256);
  expect(routes.commands.filter((command) => command.command_type === "finish_answer")).toHaveLength(1);
});

test("409 retention conflict refreshes once and is not retried", async ({ page }) => {
  const current = live("awaiting_next_action", 8, {
    active_attempt: attempt({
      recording_type: "audio",
      attempt_state: "completed",
      audio_retention_policy: "delete_after_processing",
      audio_retention_state: "retained",
    }),
    retention: { audio_policy: "retain_until_deleted", current_audio_state: "retained" },
    allowed_commands: ["update_retention"],
  });
  const routes = await installRoutes(page, current, { commandConflict: "update_retention" });
  await page.goto(`/coach/session/${SESSION_ID}`);
  const updatePolicy = page.getByRole("button", { name: "Delete audio after processing for future answers" });
  await expect(updatePolicy).toBeVisible();
  const liveReadsBeforeAction = routes.liveReads();

  await updatePolicy.click();

  await expect(page.getByRole("status")).toContainText("The interview changed on the server.");
  expect(routes.commands).toHaveLength(1);
  expect(routes.liveReads()).toBe(liveReadsBeforeAction + 1);
});

test("upload 409 is not automatically retried", async ({ page }) => {
  await installSyntheticMedia(page);
  const routes = await installRoutes(page, live(), { uploadOutcomes: ["conflict", "completed"] });
  await page.goto(`/coach/session/${SESSION_ID}`);

  await page.getByRole("button", { name: "Start audio answer" }).click();
  await page.getByRole("button", { name: "Finish audio answer while recording" }).click();

  await expect(page.getByText("Your captured answer is still available. Upload it again when you are ready.")).toBeVisible();
  expect(routes.uploads).toHaveLength(1);
  expect(routes.commands.filter((command) => command.command_type === "finish_answer")).toHaveLength(0);
});

test("capture and review expose no prohibited live output and render XSS as text", async ({ page }) => {
  const xss = '<img src=x onerror="window.__coachXss=true">';
  const current = live("awaiting_next_action", 8, {
    active_attempt: attempt({
      attempt_state: "unavailable",
      transcript_version: {
        id: "transcript-e2e-xss",
        version_number: 1,
        transcript: xss,
        source: "candidate_text",
        edit_reason: null,
        created_by: "candidate",
        processing_generation: 1,
        created_at: "2026-08-09T10:04:00Z",
      },
    }),
    processing: {
      job_id: null,
      stage: "content_evaluation",
      state: "unavailable",
      retryable: false,
      retry_count: 0,
      retry_limit: 2,
      retries_remaining: 2,
    },
    retention: { audio_policy: "delete_after_processing", current_audio_state: "not_applicable" },
    allowed_commands: ["retry_answer", "update_retention"],
  });
  await installRoutes(page, current);
  await page.goto(`/coach/session/${SESSION_ID}`);

  await expect(page.getByText(xss)).toBeVisible();
  expect(await page.evaluate(() => (window as Window & { __coachXss?: boolean }).__coachXss)).toBeUndefined();
  const visible = await page.locator("#main-content").innerText();
  expect(visible).not.toMatch(
    /wpm|filler|confidence|score|good answer|bad answer|emotion|personality|deception|presence|voice analysis|video/i,
  );
});
