import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "session-1" }),
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

const api = vi.hoisted(() => ({
  getCoachConversationLive: vi.fn(),
  sendCoachConversationCommand: vi.fn(),
  getSession: vi.fn(),
  submitAnswer: vi.fn(),
  submitAudio: vi.fn(),
  endSession: vi.fn(),
  researchCompany: vi.fn(),
  getAsyncJob: vi.fn(),
  planFollowUpSession: vi.fn(),
  getProgressTrend: vi.fn(),
  getCoachCapabilities: vi.fn(),
  getTTSQuestionUrl: vi.fn(),
  saveQuestionBankFromInterviewAnswer: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, ...api };
});

import { ConversationSession } from "../ConversationSession";
import { ApiError, type ConversationCommandRequest } from "@/lib/api";

const validTypedFinish: ConversationCommandRequest = {
  command_id: "typed-command",
  command_type: "finish_answer",
  expected_state_version: 1,
  payload: { attempt_id: "attempt-1", transcript: "Typed answer" },
  contract_version: "coach_conversation_command_v1",
};
const validUploadFinish: ConversationCommandRequest = {
  command_id: "upload-command",
  command_type: "finish_answer",
  expected_state_version: 1,
  payload: { attempt_id: "attempt-1", upload_id: "upload-1" },
  contract_version: "coach_conversation_command_v1",
};
const validTypedFinishWithExplicitNullUpload: ConversationCommandRequest = {
  command_id: "typed-command-canonical-null",
  command_type: "finish_answer",
  expected_state_version: 1,
  payload: { attempt_id: "attempt-1", transcript: "Typed answer", upload_id: null },
  contract_version: "coach_conversation_command_v1",
};
const validUploadFinishWithExplicitNullTranscript: ConversationCommandRequest = {
  command_id: "upload-command-canonical-null",
  command_type: "finish_answer",
  expected_state_version: 1,
  payload: { attempt_id: "attempt-1", transcript: null, upload_id: "upload-1" },
  contract_version: "coach_conversation_command_v1",
};
const invalidFinishWithBothSources: ConversationCommandRequest = {
  command_id: "invalid-both",
  command_type: "finish_answer",
  expected_state_version: 1,
  // @ts-expect-error finish_answer requires exactly one answer source
  payload: { attempt_id: "attempt-1", transcript: "Typed", upload_id: "upload-1" },
  contract_version: "coach_conversation_command_v1",
};
// @ts-expect-error finish_answer requires exactly one answer source
const invalidFinishWithoutSource: ConversationCommandRequest = {
  command_id: "invalid-neither",
  command_type: "finish_answer",
  expected_state_version: 1,
  payload: { attempt_id: "attempt-1" },
  contract_version: "coach_conversation_command_v1",
};
const invalidFinishWithNullSources: ConversationCommandRequest = {
  command_id: "invalid-null-sources",
  command_type: "finish_answer",
  expected_state_version: 1,
  // @ts-expect-error finish_answer requires one non-null answer source
  payload: { attempt_id: "attempt-1", transcript: null, upload_id: null },
  contract_version: "coach_conversation_command_v1",
};
const validAcceptedEnd: ConversationCommandRequest = {
  command_id: "valid-end",
  command_type: "end_session",
  expected_state_version: 1,
  payload: { unaccepted_attempt_action: "accept_attempt", attempt_id: "attempt-1" },
  contract_version: "coach_conversation_command_v1",
};
const invalidAcceptedEndWithoutAttempt: ConversationCommandRequest = {
  command_id: "invalid-end-missing",
  command_type: "end_session",
  expected_state_version: 1,
  // @ts-expect-error accept_attempt requires attempt_id
  payload: { unaccepted_attempt_action: "accept_attempt" },
  contract_version: "coach_conversation_command_v1",
};
const invalidAcceptedEndWithNullAttempt: ConversationCommandRequest = {
  command_id: "invalid-end-null",
  command_type: "end_session",
  expected_state_version: 1,
  // @ts-expect-error accept_attempt requires a non-null attempt_id
  payload: { unaccepted_attempt_action: "accept_attempt", attempt_id: null },
  contract_version: "coach_conversation_command_v1",
};
const invalidExcludedEndWithAttempt: ConversationCommandRequest = {
  command_id: "invalid-end-extra",
  command_type: "end_session",
  expected_state_version: 1,
  // @ts-expect-error exclude_attempt forbids attempt_id
  payload: { unaccepted_attempt_action: "exclude_attempt", attempt_id: "attempt-1" },
  contract_version: "coach_conversation_command_v1",
};
const validExcludedEnd: ConversationCommandRequest = {
  command_id: "valid-end-exclude",
  command_type: "end_session",
  expected_state_version: 1,
  payload: { unaccepted_attempt_action: "exclude_attempt" },
  contract_version: "coach_conversation_command_v1",
};
const validNotApplicableEnd: ConversationCommandRequest = {
  command_id: "valid-end-not-applicable",
  command_type: "end_session",
  expected_state_version: 1,
  payload: { unaccepted_attempt_action: "not_applicable" },
  contract_version: "coach_conversation_command_v1",
};
const validExcludedEndWithExplicitNullAttempt: ConversationCommandRequest = {
  command_id: "valid-end-exclude-canonical-null",
  command_type: "end_session",
  expected_state_version: 1,
  payload: { unaccepted_attempt_action: "exclude_attempt", attempt_id: null },
  contract_version: "coach_conversation_command_v1",
};
const validNotApplicableEndWithExplicitNullAttempt: ConversationCommandRequest = {
  command_id: "valid-end-not-applicable-canonical-null",
  command_type: "end_session",
  expected_state_version: 1,
  payload: { unaccepted_attempt_action: "not_applicable", attempt_id: null },
  contract_version: "coach_conversation_command_v1",
};
const invalidNotApplicableEndWithAttempt: ConversationCommandRequest = {
  command_id: "invalid-end-not-applicable-extra",
  command_type: "end_session",
  expected_state_version: 1,
  // @ts-expect-error not_applicable forbids attempt_id
  payload: { unaccepted_attempt_action: "not_applicable", attempt_id: "attempt-1" },
  contract_version: "coach_conversation_command_v1",
};

void [
  validTypedFinish,
  validUploadFinish,
  validTypedFinishWithExplicitNullUpload,
  validUploadFinishWithExplicitNullTranscript,
  invalidFinishWithBothSources,
  invalidFinishWithoutSource,
  invalidFinishWithNullSources,
  validAcceptedEnd,
  invalidAcceptedEndWithoutAttempt,
  invalidAcceptedEndWithNullAttempt,
  invalidExcludedEndWithAttempt,
  validExcludedEnd,
  validNotApplicableEnd,
  validExcludedEndWithExplicitNullAttempt,
  validNotApplicableEndWithExplicitNullAttempt,
  invalidNotApplicableEndWithAttempt,
];

type LiveOverrides = Record<string, unknown>;

function live(overrides: LiveOverrides = {}) {
  return {
    session_id: "session-1",
    experience_version: "conversational_v1",
    status: "active",
    conversation_state: "asking",
    state_version: 3,
    activity_version: 2,
    retention_version: 1,
    active_question: {
      id: "question-1",
      text: "Tell me about a difficult delivery.",
      category: "behavioural",
      difficulty: "realistic",
      question_kind: "planned",
      question_state: "asked",
      root_question_id: null,
      parent_question_id: null,
      follow_up_depth: 0,
      follow_up_reason: null,
      attempts_created_count: 0,
      attempt_limit: 5,
      attempts_remaining: 5,
    },
    root_question: {
      id: "question-1",
      text: "Tell me about a difficult delivery.",
      category: "behavioural",
      difficulty: "realistic",
      question_kind: "planned",
      question_state: "asked",
      root_question_id: null,
      parent_question_id: null,
      follow_up_depth: 0,
      follow_up_reason: null,
      attempts_created_count: 0,
      attempt_limit: 5,
      attempts_remaining: 5,
    },
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
      planned_questions_total: 6,
      planned_questions_completed: 1,
      follow_ups_completed: 0,
      current_planned_position: 2,
    },
    retention: {
      audio_policy: "delete_after_processing",
      current_audio_state: null,
    },
    allowed_commands: ["begin_answer", "pause"],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    recoverable_error: null,
    report_state: "not_started",
    contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

function textAttempt(transcript: string | null = null) {
  return {
    id: "attempt-1",
    question_id: "question-1",
    recording_type: "text",
    attempt_number: 1,
    attempt_state: transcript === null ? "draft" : "completed",
    attempt_version: 1,
    processing_generation: transcript === null ? 0 : 1,
    processing_retry_count: 0,
    processing_retry_limit: 2,
    processing_retries_remaining: 2,
    audio_retention_policy: null,
    audio_retention_state: "not_applicable",
    transcript_version: transcript === null ? null : {
      id: "transcript-1",
      version_number: 1,
      transcript,
      source: "candidate_text",
      edit_reason: null,
      created_by: "candidate",
      processing_generation: 1,
      created_at: "2026-08-08T10:00:00Z",
    },
  };
}

function legacySession() {
  return {
    id: "session-1",
    application_id: null,
    company_name: "Example Cloud",
    role_title: "Solutions Architect",
    status: "active",
    overall_score: null,
    created_at: "2026-08-08T10:00:00Z",
    experience_version: "legacy_v1",
    questions: [{
      id: "question-1",
      session_id: "session-1",
      question_num: 1,
      text: "Tell me about a migration.",
      category: "Behavioural",
      difficulty: "medium",
      context: null,
      model_answer: null,
      order_in_session: 1,
    }],
  };
}

describe("ConversationSession server authority", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.getCoachConversationLive.mockResolvedValue(live());
    api.sendCoachConversationCommand.mockResolvedValue({
      command_id: "command-1",
      result: "completed",
      session_id: "session-1",
      state: "asking",
      state_version: 4,
      active_question_id: "question-1",
      active_attempt_id: null,
      async_job_id: null,
      allowed_commands: [],
      contract_version: "coach_conversation_command_result_v1",
    });
  });

  it("renders refreshed server state without inferring advancement locally", async () => {
    api.getCoachConversationLive.mockResolvedValue(live({
      conversation_state: "processing_answer",
      allowed_commands: [],
      active_attempt: textAttempt("A persisted answer"),
      processing: {
        job_id: "job-1",
        stage: "content_evaluation",
        state: "running",
        retryable: false,
        retry_count: 0,
        retry_limit: 2,
        retries_remaining: 2,
      },
    }));

    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findByText("Reviewing answer")).toBeVisible();
    expect(screen.queryByRole("button", { name: /accept/i })).not.toBeInTheDocument();
  });

  it("renders controls only when the server advertises their commands", async () => {
    api.getCoachConversationLive.mockResolvedValue(live({
      conversation_state: "paused",
      allowed_commands: ["resume"],
    }));

    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findByRole("button", { name: "Resume interview" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Pause interview" })).not.toBeInTheDocument();
  });

  it("refreshes once on 409 without duplicating the command or losing unsent text", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: textAttempt(),
      allowed_commands: ["finish_answer", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce({ ...listening, state_version: 5 });
    api.sendCoachConversationCommand.mockRejectedValueOnce(
      Object.assign(new Error("The interview changed."), { status: 409 }),
    );
    const user = userEvent.setup();

    render(<ConversationSession sessionId="session-1" />);
    const answer = await screen.findByRole("textbox", { name: "Your answer" });
    await user.type(answer, "An unsent local answer");
    await user.click(screen.getByRole("button", { name: "Pause interview" }));

    await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(2));
    expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox", { name: "Your answer" })).toHaveValue(
      "An unsent local answer",
    );
    expect(screen.getByText("The interview changed on the server. Your unsent answer is still here.")).toBeVisible();
  });

  it("hides stale controls when a 409 refresh fails and restores unsent text only after retry succeeds", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: textAttempt(),
      allowed_commands: ["finish_answer", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(listening)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ ...listening, state_version: 5 });
    api.sendCoachConversationCommand.mockRejectedValueOnce(
      Object.assign(new Error("The interview changed."), { status: 409 }),
    );
    const user = userEvent.setup();

    render(<ConversationSession sessionId="session-1" />);
    const answer = await screen.findByRole("textbox", { name: "Your answer" });
    await user.type(answer, "Preserve this draft");
    await user.click(screen.getByRole("button", { name: "Pause interview" }));

    expect(await screen.findByText("The interview changed, but we could not refresh it. Your unsent answer is still here.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Pause interview" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Submit written answer" })).not.toBeInTheDocument();
    expect(screen.queryByText("The interview changed on the server. Your unsent answer is still here.")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try refreshing interview" }));

    expect(await screen.findByRole("textbox", { name: "Your answer" })).toHaveValue("Preserve this draft");
    expect(screen.getByRole("button", { name: "Pause interview" })).toBeVisible();
  });

  it("does not let a delayed older live response overwrite a newer accepted snapshot", async () => {
    let resolveOlder!: (value: ReturnType<typeof live>) => void;
    const older = new Promise<ReturnType<typeof live>>((resolve) => {
      resolveOlder = resolve;
    });
    api.getCoachConversationLive
      .mockReturnValueOnce(older)
      .mockResolvedValueOnce(live({
        conversation_state: "paused",
        state_version: 8,
        allowed_commands: ["resume"],
      }));

    render(<ConversationSession sessionId="session-1" />);
    await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(1));
    act(() => window.dispatchEvent(new Event("focus")));

    expect(await screen.findByRole("button", { name: "Resume interview" })).toBeVisible();
    await act(async () => {
      resolveOlder(live({ state_version: 7, allowed_commands: ["begin_answer", "pause"] }));
      await older;
    });

    expect(screen.getByRole("button", { name: "Resume interview" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Answer in writing" })).not.toBeInTheDocument();
  });

  it("renders transcript markup as text rather than executable HTML", async () => {
    const markup = '<img src=x onerror="window.__pwned=1">';
    api.getCoachConversationLive.mockResolvedValue(live({
      conversation_state: "awaiting_next_action",
      active_attempt: textAttempt(markup),
      allowed_commands: ["retry_answer"],
    }));

    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findByText(markup)).toBeVisible();
    expect(document.querySelector("img")).toBeNull();
  });

  it("uses one polite status region for loading, errors, and state announcements", async () => {
    let rejectLive!: (error: Error) => void;
    api.getCoachConversationLive.mockReturnValue(new Promise((_, reject) => {
      rejectLive = reject;
    }));

    render(<ConversationSession sessionId="session-1" />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Loading interview");
    rejectLive(new Error("offline"));
    expect(await screen.findByText("We could not refresh this interview. Try again.")).toBeVisible();
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("dispatches one stable typed begin-answer command from a native button", async () => {
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    const button = await screen.findByRole("button", { name: "Answer in writing" });
    expect(button.tagName).toBe("BUTTON");
    await user.click(button);

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledOnce());
    const request = api.sendCoachConversationCommand.mock.calls[0][1];
    expect(request).toEqual({
      command_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      command_type: "begin_answer",
      expected_state_version: 3,
      payload: {
        recording_type: "text",
        client_attempt_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
      },
      contract_version: "coach_conversation_command_v1",
    });
  });

  it("does not expose future review and report commands in the Task 7 shell", async () => {
    api.getCoachConversationLive.mockResolvedValue(live({
      conversation_state: "awaiting_next_action",
      active_attempt: textAttempt("A completed answer"),
      allowed_commands: [
        "accept_attempt",
        "request_coaching",
        "return_to_review",
        "retry_report",
        "retry_answer",
        "pause",
      ],
    }));

    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findByRole("button", { name: "Try this question again" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Pause interview" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Accept this answer" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Get coaching" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Return to answer review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry report" })).not.toBeInTheDocument();
  });
});

describe("coach session experience dispatch", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.researchCompany.mockResolvedValue(null);
    api.getCoachCapabilities.mockResolvedValue({ face_analysis: false, tts: false });
  });

  it("selects the conversational shell from the tracked experience discriminator", async () => {
    api.getSession.mockResolvedValue({
      ...legacySession(),
      experience_version: "conversational_v1",
      conversation_state: "asking",
    });
    api.getCoachConversationLive.mockResolvedValue(live());
    const { default: SessionPage } = await import("@/app/coach/session/[id]/page");

    render(<SessionPage />);

    expect(await screen.findByText("Tell me about a difficult delivery.")).toBeVisible();
    expect(api.researchCompany).not.toHaveBeenCalled();
  });

  it("preserves the legacy page for legacy and pre-discriminator fixtures", async () => {
    api.getSession.mockResolvedValue(legacySession());
    const { default: SessionPage } = await import("@/app/coach/session/[id]/page");

    render(<SessionPage />);

    expect(await screen.findByText("Tell me about a migration.")).toBeVisible();
    expect(screen.getByPlaceholderText(/Type your answer using the STAR framework/i)).toBeVisible();
    expect(api.researchCompany).toHaveBeenCalledWith("Example Cloud");
  });

  it("distinguishes a missing session from an unavailable summary endpoint", async () => {
    api.getSession.mockRejectedValueOnce(
      new ApiError("Session not found", 404, { detail: "Session not found" }),
    );
    const { default: SessionPage } = await import("@/app/coach/session/[id]/page");
    const first = render(<SessionPage />);

    expect(await screen.findByText("Session not found")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try loading interview again" })).not.toBeInTheDocument();
    first.unmount();

    api.getSession
      .mockRejectedValueOnce(new ApiError("Server unavailable", 503, { detail: "Unavailable" }))
      .mockResolvedValueOnce(legacySession());
    const user = userEvent.setup();
    render(<SessionPage />);

    expect(await screen.findByText("We could not load this interview. Try again.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Try loading interview again" }));
    expect(await screen.findByText("Tell me about a migration.")).toBeVisible();
  });
});

describe("conversational API boundaries", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("preserves structured 409 metadata for conflict recovery", async () => {
    const actual = await vi.importActual<Record<string, unknown>>("@/lib/api");
    const getLive = actual.getCoachConversationLive as (sessionId: string) => Promise<unknown>;
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      error: {
        code: "coach_conversation_version_conflict",
        message: "The interview changed since this view was loaded.",
        retryable: false,
        current_state: "asking",
        current_state_version: 7,
        correlation_id: "correlation-1",
        details: {},
      },
    }), { status: 409, headers: { "Content-Type": "application/json" } }));

    const error = await getLive("session-1").catch((caught: unknown) => caught);

    expect(error).toMatchObject({
      status: 409,
      code: "coach_conversation_version_conflict",
      data: {
        error: {
          current_state_version: 7,
        },
      },
    });
  });

  it("posts the exact versioned command envelope to the conversational route", async () => {
    const actual = await vi.importActual<Record<string, unknown>>("@/lib/api");
    const send = actual.sendCoachConversationCommand as (
      sessionId: string,
      command: Record<string, unknown>,
    ) => Promise<unknown>;
    const command = {
      command_id: "command-1",
      command_type: "pause",
      expected_state_version: 6,
      payload: {},
      contract_version: "coach_conversation_command_v1",
    };
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      command_id: "command-1",
      result: "completed",
      session_id: "session-1",
      state: "paused",
      state_version: 7,
      active_question_id: "question-1",
      active_attempt_id: null,
      async_job_id: null,
      allowed_commands: ["resume"],
      contract_version: "coach_conversation_command_result_v1",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await send("session-1", command);

    expect(fetch).toHaveBeenCalledWith(
      "/api/coach/sessions/session-1/commands",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(command),
      }),
    );
  });

  it("sends the exact multipart audio contract without interpreting the filename", async () => {
    const actual = await vi.importActual<Record<string, unknown>>("@/lib/api");
    const upload = actual.uploadCoachAttemptAudio as (
      sessionId: string,
      attemptId: string,
      request: { uploadId: string; contentSha256: string; audio: Blob },
    ) => Promise<unknown>;
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      attempt_id: "attempt-1",
      upload_id: "upload-1",
      result: "completed",
      content_sha256: "a".repeat(64),
      byte_size: 5,
      mime_type: "audio/webm",
      audio_retention_state: "temporary",
      contract_version: "coach_attempt_audio_upload_v1",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await upload("session-1", "attempt-1", {
      uploadId: "upload-1",
      contentSha256: "a".repeat(64),
      audio: new Blob(["audio"], { type: "audio/webm" }),
    });

    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/coach/sessions/session-1/attempts/attempt-1/audio");
    expect(options?.method).toBe("POST");
    expect(options?.headers).toEqual({});
    const body = options?.body as FormData;
    expect(body.get("upload_id")).toBe("upload-1");
    expect(body.get("content_sha256")).toBe("a".repeat(64));
    expect(body.get("audio")).toBeInstanceOf(Blob);
  });
});
