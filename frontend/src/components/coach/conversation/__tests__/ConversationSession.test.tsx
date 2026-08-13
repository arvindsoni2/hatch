import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "session-1" }),
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

const api = vi.hoisted(() => ({
  getCoachConversationLive: vi.fn(),
  sendCoachConversationCommand: vi.fn(),
  uploadCoachAttemptAudio: vi.fn(),
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
import { ApiError, type ConversationCommandRequest, type ConversationLiveView } from "@/lib/api";

declare global {
  var __coachMediaTest: {
    reset: () => void;
    stream: { getTracks: () => Array<{ stop: ReturnType<typeof vi.fn> }> };
    latestRecorder: () => {
      state: RecordingState;
      pause: ReturnType<typeof vi.fn>;
      resume: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
    } | null;
    setAnalyserDb: (db: number) => void;
  };
}

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
    answer_review: null,
    attempt_history: [],
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
      retryable_audio_cleanup_attempt_id: null,
    },
    allowed_commands: ["begin_answer", "pause"],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    recoverable_error: null,
    report_state: "not_started",
    contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

function answerReview() {
  return {
    evaluation_id: "evaluation-1",
    evaluation_state: "completed",
    answer_level: "interview_ready",
    dimensions: {
      relevance: {
        level: "interview_ready",
        evidence: [{ transcript_start: 0, transcript_end: 5, excerpt: "I led" }],
        rationale: "The example answers the question.",
        improvement: null,
      },
    },
    delivery: { level: "not_assessed", observations: [] },
    evidence_consistency: "developing",
    evidence_findings: [{
      claim_id: "claim-1",
      claim_text: "three teams",
      transcript_start: 27,
      transcript_end: 38,
      status: "partially_supported",
      source_label: "Draft source",
      source_approval: "draft",
      explanation: "The draft supports part of this claim.",
      candidate_action: "Confirm the detail before reuse.",
    }],
    coaching: null,
    accepted_at: null,
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

function audioAttempt() {
  return {
    id: "attempt-audio-1",
    question_id: "question-1",
    recording_type: "audio",
    attempt_number: 1,
    attempt_state: "draft",
    attempt_version: 1,
    processing_generation: 0,
    processing_retry_count: 0,
    processing_retry_limit: 2,
    processing_retries_remaining: 2,
    audio_retention_policy: "delete_after_processing",
    audio_retention_state: "temporary",
    transcript_version: null,
  };
}

function commandResult(overrides: Record<string, unknown> = {}) {
  return {
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
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
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
    globalThis.__coachMediaTest?.reset();
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
    api.uploadCoachAttemptAudio.mockResolvedValue({
      attempt_id: "attempt-audio-1",
      upload_id: "upload-1",
      result: "completed",
      content_sha256: "a".repeat(64),
      byte_size: 5,
      mime_type: "audio/webm",
      audio_retention_state: "temporary",
      contract_version: "coach_attempt_audio_upload_v1",
    });
  });

  afterEach(() => {
    vi.useRealTimers();
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

  it("accepts a delayed higher state version even when a lower version request started later", async () => {
    const delayedHigher = deferred<ReturnType<typeof live>>();
    api.getCoachConversationLive
      .mockReturnValueOnce(delayedHigher.promise)
      .mockResolvedValueOnce(live({ state_version: 7 }));

    render(<ConversationSession sessionId="session-1" />);
    await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(1));
    act(() => window.dispatchEvent(new Event("focus")));

    expect(await screen.findByRole("button", { name: "Start audio answer" })).toBeVisible();
    await act(async () => delayedHigher.resolve(live({
      conversation_state: "paused",
      state_version: 8,
      allowed_commands: ["resume"],
    })));

    expect(await screen.findByRole("button", { name: "Resume interview" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Start audio answer" })).not.toBeInTheDocument();
  });

  it("renders transcript markup as text rather than executable HTML", async () => {
    const markup = '<img src=x onerror="window.__pwned=1">';
    api.getCoachConversationLive.mockResolvedValue(live({
      conversation_state: "awaiting_next_action",
      active_attempt: textAttempt(markup),
      allowed_commands: ["retry_answer"],
    }));

    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findAllByText(markup)).not.toHaveLength(0);
    expect(document.querySelector("img")).toBeNull();
  });

  it("renders authoritative review, transcript editing, and attempt history and dispatches review commands", async () => {
    const user = userEvent.setup();
    const reviewed = live({
      conversation_state: "awaiting_next_action",
      state_version: 8,
      active_attempt: textAttempt("I led the migration across three teams."),
      answer_review: answerReview(),
      attempt_history: [{
        attempt_id: "attempt-1",
        attempt_number: 1,
        answer_level: "interview_ready",
        accepted: false,
        transcript_available: true,
        audio_state: "not_applicable",
      }],
      allowed_commands: ["record_self_assessment", "edit_transcript", "accept_attempt"],
    });
    api.getCoachConversationLive.mockResolvedValue(reviewed);
    api.sendCoachConversationCommand.mockResolvedValue({
      command_id: "accepted-reflection",
      result: "completed",
      state: "awaiting_next_action",
      state_version: 9,
      active_attempt_id: "attempt-1",
      job_id: null,
      error: null,
      contract_version: "coach_conversation_command_result_v1",
    });

    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findByRole("heading", { name: "Answer quality" })).toBeVisible();
    expect(screen.getByText("Overall: Interview-ready")).toBeVisible();
    expect(screen.getByText("Draft source")).toBeVisible();
    expect(screen.getByRole("region", { name: "Transcript" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Attempt history" })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Save reflection" }));
    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledOnce());
    expect(api.sendCoachConversationCommand.mock.calls[0][1]).toMatchObject({
      command_type: "record_self_assessment",
      expected_state_version: 8,
      payload: {
        attempt_id: "attempt-1",
        comfort_level: "medium",
        felt_complete: false,
        note: null,
      },
    });
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

  it("keeps the typed control enabled and uses the existing live region when microphone access is denied", async () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockRejectedValue(
          new DOMException("Permission denied", "NotAllowedError"),
        ),
      },
    });
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/microphone access was not granted/i));
    expect(screen.getByRole("button", { name: "Answer in writing" })).toBeEnabled();
    expect(screen.getAllByRole("status")).toHaveLength(1);
    expect(screen.getByRole("status")).toHaveTextContent(/microphone access was not granted/i);
  });

  it("routes silence advisories through the sole polite live region", async () => {
    vi.useFakeTimers();
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    act(() => vi.advanceTimersByTime(500));
    globalThis.__coachMediaTest.setAnalyserDb(-25);
    act(() => vi.advanceTimersByTime(1600));
    globalThis.__coachMediaTest.setAnalyserDb(-55);
    act(() => vi.advanceTimersByTime(4000));

    expect(screen.getByRole("status")).toHaveTextContent(/quiet for a few seconds/i);
    expect(screen.getAllByRole("status")).toHaveLength(1);
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByRole("status")).toHaveTextContent(/are you finished/i);
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("retries one hard-stop envelope after transport failure and preserves captured audio", async () => {
    vi.useFakeTimers();
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt", "record_capture_hard_stop"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce({ ...listening, state_version: 5 });
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1",
        state: "listening",
        state_version: 4,
        active_attempt_id: "attempt-audio-1",
        allowed_commands: listening.allowed_commands,
      }))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(commandResult({
        command_id: "hard-stop-1",
        state: "listening",
        state_version: 5,
        active_attempt_id: "attempt-audio-1",
        allowed_commands: listening.allowed_commands,
      }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await act(async () => vi.advanceTimersByTime(600_000));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(3));
    const [firstHardStop, retryHardStop] = api.sendCoachConversationCommand.mock.calls.slice(1);
    expect(firstHardStop[1]).toMatchObject({
      command_type: "record_capture_hard_stop",
      expected_state_version: 4,
      payload: { attempt_id: "attempt-audio-1" },
    });
    expect(retryHardStop[1]).toEqual(firstHardStop[1]);
    act(() => window.dispatchEvent(new Event("focus")));
    expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("button", { name: "Upload captured answer" })).toBeEnabled();
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);
  });

  it("refreshes authoritative state after a hard-stop conflict without discarding audio", async () => {
    vi.useFakeTimers();
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt", "record_capture_hard_stop"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce({ ...listening, state_version: 5 });
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1",
        state: "listening",
        state_version: 4,
        active_attempt_id: "attempt-audio-1",
        allowed_commands: listening.allowed_commands,
      }))
      .mockRejectedValueOnce(new ApiError("Conflict", 409, {
        error: { code: "coach_conversation_version_conflict" },
      }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await act(async () => vi.advanceTimersByTime(600_000));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(2));
    expect(api.sendCoachConversationCommand.mock.calls[1][1]).toMatchObject({
      command_type: "record_capture_hard_stop",
      expected_state_version: 4,
      payload: { attempt_id: "attempt-audio-1" },
    });
    expect(await screen.findByRole("button", { name: "Upload captured answer" })).toBeEnabled();
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);
  });

  it("shows discard recovery instead of a fabricated resume after refreshing a paused audio draft", async () => {
    api.getCoachConversationLive.mockResolvedValue(live({
      conversation_state: "paused",
      state_version: 5,
      active_attempt: audioAttempt(),
      allowed_commands: ["resume"],
    }));
    render(<ConversationSession sessionId="session-1" />);

    expect(await screen.findByText(/this browser no longer has the live recording/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Discard recording and try again" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Resume interview" })).not.toBeInTheDocument();
    expect(screen.queryByText(/recording resumed/i)).not.toBeInTheDocument();
  });

  it("discards a refreshed paused draft through explicit resume then cancel commands", async () => {
    const paused = live({
      conversation_state: "paused",
      state_version: 5,
      active_attempt: audioAttempt(),
      allowed_commands: ["resume"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(paused)
      .mockResolvedValueOnce({
        ...paused,
        conversation_state: "listening",
        state_version: 6,
        allowed_commands: ["finish_answer", "pause", "cancel_attempt"],
      })
      .mockResolvedValueOnce(live({ state_version: 7 }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Discard recording and try again" }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(2));
    expect(api.sendCoachConversationCommand.mock.calls[0][1]).toMatchObject({
      command_type: "resume",
      expected_state_version: 5,
      payload: {},
    });
    expect(api.sendCoachConversationCommand.mock.calls[1][1]).toMatchObject({
      command_type: "cancel_attempt",
      expected_state_version: 6,
      payload: { attempt_id: "attempt-audio-1" },
    });
    expect(api.sendCoachConversationCommand.mock.calls[0][1].command_id)
      .not.toBe(api.sendCoachConversationCommand.mock.calls[1][1].command_id);
  });

  it("cancels a local paused recording through authoritative resume, refresh, then cancel", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const paused = {
      ...listening,
      conversation_state: "paused",
      state_version: 5,
      allowed_commands: ["resume"],
    };
    const resumed = { ...listening, state_version: 6 };
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(paused)
      .mockResolvedValueOnce(resumed)
      .mockResolvedValueOnce(live({ state_version: 7 }));
    api.sendCoachConversationCommand
      .mockResolvedValueOnce({
        command_id: "begin-1", result: "completed", session_id: "session-1",
        state: "listening", state_version: 4, active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1", async_job_id: null,
        allowed_commands: listening.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      })
      .mockResolvedValueOnce({
        command_id: "pause-1", result: "completed", session_id: "session-1",
        state: "paused", state_version: 5, active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1", async_job_id: null,
        allowed_commands: ["resume"], contract_version: "coach_conversation_command_result_v1",
      })
      .mockResolvedValueOnce({
        command_id: "resume-1", result: "completed", session_id: "session-1",
        state: "listening", state_version: 6, active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1", async_job_id: null,
        allowed_commands: resumed.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      })
      .mockResolvedValueOnce({
        command_id: "cancel-1", result: "completed", session_id: "session-1",
        state: "asking", state_version: 7, active_question_id: "question-1",
        active_attempt_id: null, async_job_id: null, allowed_commands: ["begin_answer", "pause"],
        contract_version: "coach_conversation_command_result_v1",
      });
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
    await user.click(await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(4));
    expect(api.sendCoachConversationCommand.mock.calls.slice(2).map((call) => call[1])).toEqual([
      expect.objectContaining({ command_type: "resume", expected_state_version: 5, payload: {} }),
      expect.objectContaining({
        command_type: "cancel_attempt",
        expected_state_version: 6,
        payload: { attempt_id: "attempt-audio-1" },
      }),
    ]);
  });

  it("cancels with the accepted resume result version when the resume refresh is unavailable", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const paused = {
      ...listening,
      conversation_state: "paused",
      state_version: 5,
      allowed_commands: ["resume"],
    };
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(paused)
      .mockRejectedValueOnce(new Error("offline after resume"))
      .mockResolvedValueOnce(live({ state_version: 7 }));
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1", state: "listening", state_version: 4,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "pause-1", state: "paused", state_version: 5,
        active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "resume-1", state: "listening", state_version: 6,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockResolvedValueOnce(commandResult({ command_id: "cancel-1", state_version: 7 }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
    await user.click(await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(4));
    expect(api.sendCoachConversationCommand.mock.calls[3][1]).toMatchObject({
      command_type: "cancel_attempt",
      expected_state_version: 6,
      payload: { attempt_id: "attempt-audio-1" },
    });
    await waitFor(() => expect(globalThis.__coachMediaTest.latestRecorder()?.stop).toHaveBeenCalledOnce());
    expect(globalThis.__coachMediaTest.latestRecorder()?.state).toBe("inactive");
  });

  it("resumes the local recorder when accepted resume cannot complete cancellation", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const paused = {
      ...listening,
      conversation_state: "paused",
      state_version: 5,
      allowed_commands: ["resume"],
    };
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(paused)
      .mockRejectedValueOnce(new Error("offline after resume"));
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1", state: "listening", state_version: 4,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "pause-1", state: "paused", state_version: 5,
        active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "resume-1", state: "listening", state_version: 6,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockRejectedValueOnce(new Error("cancel unavailable"));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
    await user.click(await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(4));
    expect(globalThis.__coachMediaTest.latestRecorder()?.resume).toHaveBeenCalledOnce();
    expect(globalThis.__coachMediaTest.latestRecorder()?.state).toBe("recording");
    expect(screen.getByRole("status")).toHaveTextContent(/cancel is pending/i);
  });

  it("keeps the local recorder paused when cancel conflict refresh proves same-attempt paused authority", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const paused = {
      ...listening,
      conversation_state: "paused",
      state_version: 5,
      allowed_commands: ["resume"],
    };
    const refreshedPaused = { ...paused, state_version: 7 };
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(paused)
      .mockRejectedValueOnce(new Error("offline after resume"))
      .mockResolvedValueOnce(refreshedPaused);
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1", state: "listening", state_version: 4,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "pause-1", state: "paused", state_version: 5,
        active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "resume-1", state: "listening", state_version: 6,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockRejectedValueOnce(new ApiError("Conflict", 409, {
        error: { code: "coach_conversation_version_conflict" },
      }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
    await user.click(await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(4));
    expect(globalThis.__coachMediaTest.latestRecorder()?.resume).not.toHaveBeenCalled();
    expect(globalThis.__coachMediaTest.latestRecorder()?.state).toBe("paused");
    expect(screen.getByRole("status")).toHaveTextContent(/remains paused.*cancel/i);
  });

  it("clears local capture when cancel conflict refresh proves replacement authority", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const paused = {
      ...listening,
      conversation_state: "paused",
      state_version: 5,
      allowed_commands: ["resume"],
    };
    const replacement = {
      ...listening,
      state_version: 7,
      active_attempt: { ...audioAttempt(), id: "attempt-replacement" },
    };
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(paused)
      .mockRejectedValueOnce(new Error("offline after resume"))
      .mockResolvedValueOnce(replacement);
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1", state: "listening", state_version: 4,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "pause-1", state: "paused", state_version: 5,
        active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "resume-1", state: "listening", state_version: 6,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockRejectedValueOnce(new ApiError("Conflict", 409, {
        error: { code: "coach_conversation_version_conflict" },
      }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
    await user.click(await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }));

    await waitFor(() => expect(globalThis.__coachMediaTest.latestRecorder()?.stop).toHaveBeenCalledOnce());
    expect(globalThis.__coachMediaTest.latestRecorder()?.resume).not.toHaveBeenCalled();
    expect(screen.queryByText(/microphone paused|microphone recording/i)).not.toBeInTheDocument();
  });

  it.each(["paused", "listening", "mismatch", "unavailable"] as const)(
    "aligns cancel to the newest %s authority when its own refresh becomes stale",
    async (latestOutcome) => {
      const listening = live({
        conversation_state: "listening",
        state_version: 4,
        active_attempt: audioAttempt(),
        allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
      });
      const paused = {
        ...listening,
        conversation_state: "paused",
        state_version: 5,
        allowed_commands: ["resume"],
      };
      const staleCancelRefresh = deferred<ReturnType<typeof live>>();
      const latest = (latestOutcome === "paused"
        ? { ...paused, state_version: 7 }
        : latestOutcome === "listening"
          ? { ...listening, state_version: 7 }
          : {
              ...listening,
              state_version: 7,
              active_attempt: { ...audioAttempt(), id: "attempt-replacement" },
            }) as ConversationLiveView;
      const reads = api.getCoachConversationLive
        .mockResolvedValueOnce(live())
        .mockResolvedValueOnce(listening)
        .mockResolvedValueOnce(paused)
        .mockRejectedValueOnce(new Error("offline after resume"))
        .mockReturnValueOnce(staleCancelRefresh.promise);
      if (latestOutcome === "unavailable") {
        reads.mockRejectedValueOnce(new Error("newest read unavailable"));
      } else {
        reads.mockResolvedValueOnce(latest);
      }
      api.sendCoachConversationCommand
        .mockResolvedValueOnce(commandResult({
          command_id: "begin-1", state: "listening", state_version: 4,
          active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
        }))
        .mockResolvedValueOnce(commandResult({
          command_id: "pause-1", state: "paused", state_version: 5,
          active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
        }))
        .mockResolvedValueOnce(commandResult({
          command_id: "resume-1", state: "listening", state_version: 6,
          active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
        }))
        .mockRejectedValueOnce(new ApiError("Conflict", 409, {
          error: { code: "coach_conversation_version_conflict" },
        }));
      const user = userEvent.setup();
      render(<ConversationSession sessionId="session-1" />);

      await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
      await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
      const cancelClick = user.click(
        await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }),
      );
      await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(5));
      act(() => window.dispatchEvent(new Event("focus")));
      await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(6));
      await act(async () => staleCancelRefresh.resolve({ ...listening, state_version: 6 }));
      await cancelClick;

      const recorder = globalThis.__coachMediaTest.latestRecorder();
      if (latestOutcome === "paused") {
        expect(recorder?.resume).not.toHaveBeenCalled();
        expect(recorder?.state).toBe("paused");
        expect(screen.getByRole("status")).toHaveTextContent(/remains paused.*cancel/i);
      } else if (latestOutcome === "mismatch") {
        await waitFor(() => expect(recorder?.stop).toHaveBeenCalledOnce());
        expect(recorder?.resume).not.toHaveBeenCalled();
        expect(screen.queryByText(/microphone paused|microphone recording/i)).not.toBeInTheDocument();
      } else {
        await waitFor(() => expect(recorder?.resume).toHaveBeenCalledOnce());
        expect(recorder?.state).toBe("recording");
        expect(screen.getByRole("status")).toHaveTextContent(/cancel is pending/i);
      }
    },
  );

  it.each(["paused", "listening", "mismatch", "unavailable"] as const)(
    "keeps cancel paused until a newer pending %s authority read settles",
    async (latestOutcome) => {
      const listening = live({
        conversation_state: "listening",
        state_version: 4,
        active_attempt: audioAttempt(),
        allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
      });
      const paused = {
        ...listening,
        conversation_state: "paused",
        state_version: 5,
        allowed_commands: ["resume"],
      };
      const staleCancelRefresh = deferred<ReturnType<typeof live>>();
      const latestRead = deferred<ConversationLiveView>();
      const latest = (latestOutcome === "paused"
        ? { ...paused, state_version: 7 }
        : latestOutcome === "listening"
          ? { ...listening, state_version: 7 }
          : {
              ...listening,
              state_version: 7,
              active_attempt: { ...audioAttempt(), id: "attempt-replacement" },
            }) as ConversationLiveView;
      api.getCoachConversationLive
        .mockResolvedValueOnce(live())
        .mockResolvedValueOnce(listening)
        .mockResolvedValueOnce(paused)
        .mockRejectedValueOnce(new Error("offline after resume"))
        .mockReturnValueOnce(staleCancelRefresh.promise)
        .mockReturnValueOnce(latestRead.promise);
      api.sendCoachConversationCommand
        .mockResolvedValueOnce(commandResult({
          command_id: "begin-1", state: "listening", state_version: 4,
          active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
        }))
        .mockResolvedValueOnce(commandResult({
          command_id: "pause-1", state: "paused", state_version: 5,
          active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
        }))
        .mockResolvedValueOnce(commandResult({
          command_id: "resume-1", state: "listening", state_version: 6,
          active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
        }))
        .mockRejectedValueOnce(new ApiError("Conflict", 409, {
          error: { code: "coach_conversation_version_conflict" },
        }));
      const user = userEvent.setup();
      render(<ConversationSession sessionId="session-1" />);

      await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
      await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
      const cancelClick = user.click(
        await screen.findByRole("button", { name: "Cancel audio answer and discard recording" }),
      );
      await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(5));
      act(() => window.dispatchEvent(new Event("focus")));
      await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(6));
      await act(async () => staleCancelRefresh.resolve({ ...listening, state_version: 6 }));

      const recorder = globalThis.__coachMediaTest.latestRecorder();
      expect(recorder?.resume).not.toHaveBeenCalled();
      expect(recorder?.state).toBe("paused");

      await act(async () => {
        if (latestOutcome === "unavailable") {
          latestRead.reject(new Error("newest read unavailable"));
        } else {
          latestRead.resolve(latest);
        }
      });
      await cancelClick;

      if (latestOutcome === "paused") {
        expect(recorder?.resume).not.toHaveBeenCalled();
        expect(recorder?.state).toBe("paused");
        expect(screen.getByRole("status")).toHaveTextContent(/remains paused.*cancel/i);
      } else if (latestOutcome === "mismatch") {
        await waitFor(() => expect(recorder?.stop).toHaveBeenCalledOnce());
        expect(recorder?.resume).not.toHaveBeenCalled();
        expect(screen.queryByText(/microphone paused|microphone recording/i)).not.toBeInTheDocument();
      } else {
        await waitFor(() => expect(recorder?.resume).toHaveBeenCalledOnce());
        expect(recorder?.state).toBe("recording");
        expect(screen.getByRole("status")).toHaveTextContent(/cancel is pending/i);
      }
    },
  );

  it("uses versioned audio begin, upload, and finish boundaries without browser transcript text", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(live({
        conversation_state: "processing_answer",
        state_version: 5,
        active_attempt: { ...audioAttempt(), attempt_state: "pending_processing", processing_generation: 1 },
        allowed_commands: [],
        processing: {
          job_id: "job-1",
          stage: "transcription",
          state: "running",
          retryable: false,
          retry_count: 0,
          retry_limit: 2,
          retries_remaining: 2,
        },
      }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    expect(await screen.findByText("Microphone recording")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Finish audio answer while recording" }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(2));
    expect(api.sendCoachConversationCommand.mock.calls[0][1]).toMatchObject({
      command_type: "begin_answer",
      expected_state_version: 3,
      payload: { recording_type: "audio", client_attempt_id: expect.any(String) },
    });
    expect(api.uploadCoachAttemptAudio).toHaveBeenCalledOnce();
    expect(api.sendCoachConversationCommand.mock.calls[1][1]).toMatchObject({
      command_type: "finish_answer",
      expected_state_version: 4,
      payload: { attempt_id: "attempt-audio-1", upload_id: expect.any(String) },
    });
    expect(api.sendCoachConversationCommand.mock.calls[1][1].payload).not.toHaveProperty("transcript");
  });

  it("preserves the unsent audio island when a finish conflict cannot refresh server authority", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(listening);
    api.sendCoachConversationCommand
      .mockResolvedValueOnce({
        command_id: "begin-1",
        result: "completed",
        session_id: "session-1",
        state: "listening",
        state_version: 4,
        active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1",
        async_job_id: null,
        allowed_commands: listening.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      })
      .mockRejectedValueOnce(new ApiError("Conflict", 409, {
        error: { code: "coach_conversation_version_conflict" },
      }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Finish audio answer while recording" }));

    expect(await screen.findByText(
      "Your captured audio is preserved locally while interview status is unavailable.",
    )).toBeVisible();
    expect(screen.queryByRole("button", { name: "Upload captured answer again" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause audio recording" })).not.toBeInTheDocument();
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);

    await user.click(screen.getByRole("button", { name: "Try refreshing interview" }));
    expect(await screen.findByRole("button", { name: "Upload captured answer" })).toBeEnabled();
  });

  it("offers a local-only stop when an accepted audio begin cannot refresh authority", async () => {
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockRejectedValueOnce(new Error("offline after begin"));
    api.sendCoachConversationCommand.mockResolvedValueOnce(commandResult({
      command_id: "begin-1",
      state: "listening",
      state_version: 4,
      active_attempt_id: "attempt-audio-1",
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));

    expect(await screen.findByText("Microphone recording")).toBeVisible();
    expect(screen.getByRole("button", { name: "Stop recording and preserve captured audio" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Pause audio recording" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel audio answer and discard recording" })).not.toBeInTheDocument();
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);
  });

  it("preserves captured audio with a local stop when focus refresh loses authority", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockRejectedValueOnce(new Error("focus refresh offline"))
      .mockResolvedValueOnce(listening);
    api.sendCoachConversationCommand.mockResolvedValueOnce(commandResult({
      command_id: "begin-1", state: "listening", state_version: 4,
      active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
    }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    act(() => window.dispatchEvent(new Event("focus")));
    await user.click(await screen.findByRole("button", { name: "Stop recording and preserve captured audio" }));

    await waitFor(() => expect(globalThis.__coachMediaTest.latestRecorder()?.stop).toHaveBeenCalledOnce());
    expect(screen.getByRole("status")).toHaveTextContent(/captured audio is preserved/i);
    expect(screen.getByText("Your captured audio is preserved locally while interview status is unavailable."))
      .toBeVisible();
    expect(screen.queryByRole("button", { name: /upload captured answer/i })).not.toBeInTheDocument();
    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);

    act(() => window.dispatchEvent(new Event("focus")));
    expect(await screen.findByRole("button", { name: "Upload captured answer" })).toBeEnabled();
  });

  it("keeps an accepted local pause when its follow-up live refresh is unavailable", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockRejectedValueOnce(new Error("offline"));
    api.sendCoachConversationCommand
      .mockResolvedValueOnce({
        command_id: "begin-1",
        result: "completed",
        session_id: "session-1",
        state: "listening",
        state_version: 4,
        active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1",
        async_job_id: null,
        allowed_commands: listening.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      })
      .mockResolvedValueOnce({
        command_id: "pause-1",
        result: "completed",
        session_id: "session-1",
        state: "paused",
        state_version: 5,
        active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1",
        async_job_id: null,
        allowed_commands: ["resume"],
        contract_version: "coach_conversation_command_result_v1",
      });
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));

    await waitFor(() => expect(api.getCoachConversationLive).toHaveBeenCalledTimes(3));
    expect(globalThis.__coachMediaTest.latestRecorder()?.state).toBe("paused");
    expect(globalThis.__coachMediaTest.latestRecorder()?.resume).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(/could not refresh/i);
  });

  it("offers a local-only stop when an accepted resume cannot refresh authority", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    const paused = {
      ...listening,
      conversation_state: "paused",
      state_version: 5,
      allowed_commands: ["resume"],
    };
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(paused)
      .mockRejectedValueOnce(new Error("offline after resume"));
    api.sendCoachConversationCommand
      .mockResolvedValueOnce(commandResult({
        command_id: "begin-1", state: "listening", state_version: 4,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "pause-1", state: "paused", state_version: 5,
        active_attempt_id: "attempt-audio-1", allowed_commands: ["resume"],
      }))
      .mockResolvedValueOnce(commandResult({
        command_id: "resume-1", state: "listening", state_version: 6,
        active_attempt_id: "attempt-audio-1", allowed_commands: listening.allowed_commands,
      }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));
    await user.click(await screen.findByRole("button", { name: "Resume paused audio recording" }));

    expect(await screen.findByText("Microphone recording")).toBeVisible();
    expect(screen.getByRole("button", { name: "Stop recording and preserve captured audio" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Pause audio recording" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel audio answer and discard recording" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/could not refresh/i);
  });

  it("rolls a local pause back when a successful POST result rejects the transition", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce({
        ...listening,
        conversation_state: "paused",
        state_version: 5,
        allowed_commands: ["resume"],
      });
    api.sendCoachConversationCommand
      .mockResolvedValueOnce({
        command_id: "begin-1",
        result: "completed",
        session_id: "session-1",
        state: "listening",
        state_version: 4,
        active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1",
        async_job_id: null,
        allowed_commands: listening.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      })
      .mockResolvedValueOnce({
        command_id: "pause-rejected-1",
        result: "invalid_state",
        session_id: "session-1",
        state: "listening",
        state_version: 4,
        active_question_id: "question-1",
        active_attempt_id: "attempt-audio-1",
        async_job_id: null,
        allowed_commands: listening.allowed_commands,
        contract_version: "coach_conversation_command_result_v1",
      });
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    await user.click(await screen.findByRole("button", { name: "Pause audio recording" }));

    await waitFor(() => expect(globalThis.__coachMediaTest.latestRecorder()?.resume).toHaveBeenCalledOnce());
    expect(globalThis.__coachMediaTest.latestRecorder()?.state).toBe("recording");
  });

  it("stops local capture when fresh authority reports that the attempt was cancelled remotely", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce(live({ state_version: 5 }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    const recorder = globalThis.__coachMediaTest.latestRecorder();
    act(() => window.dispatchEvent(new Event("focus")));

    await waitFor(() => expect(recorder?.stop).toHaveBeenCalledOnce());
    expect(screen.queryByText("Microphone recording")).not.toBeInTheDocument();
    expect(globalThis.__coachMediaTest.stream.getTracks()[0].stop).toHaveBeenCalledOnce();
  });

  it("stops local capture when fresh authority replaces it with a different audio attempt", async () => {
    const listening = live({
      conversation_state: "listening",
      state_version: 4,
      active_attempt: audioAttempt(),
      allowed_commands: ["finish_answer", "keep_speaking", "pause", "cancel_attempt"],
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(listening)
      .mockResolvedValueOnce({
        ...listening,
        state_version: 5,
        active_attempt: { ...audioAttempt(), id: "attempt-audio-remote" },
      });
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-1" />);

    await user.click(await screen.findByRole("button", { name: "Start audio answer" }));
    const recorder = globalThis.__coachMediaTest.latestRecorder();
    act(() => window.dispatchEvent(new Event("focus")));

    await waitFor(() => expect(recorder?.stop).toHaveBeenCalledOnce());
    expect(screen.queryByText("Microphone recording")).not.toBeInTheDocument();
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
