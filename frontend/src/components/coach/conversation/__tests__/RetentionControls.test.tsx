import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getCoachConversationLive: vi.fn(),
  sendCoachConversationCommand: vi.fn(),
  uploadCoachAttemptAudio: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, ...api };
});

import type { ConversationLiveView } from "@/lib/api";
import { ConversationSession } from "../ConversationSession";
import { RetentionStatus } from "../RetentionStatus";

function live(overrides: Partial<ConversationLiveView> = {}): ConversationLiveView {
  return {
    session_id: "session-retention-1",
    experience_version: "conversational_v1",
    status: "active",
    conversation_state: "awaiting_next_action",
    state_version: 8,
    activity_version: 4,
    retention_version: 2,
    active_question: null,
    root_question: null,
    active_attempt: {
      id: "attempt-retention-1",
      question_id: "question-retention-1",
      recording_type: "audio",
      attempt_number: 1,
      attempt_state: "completed",
      attempt_version: 3,
      processing_generation: 1,
      processing_retry_count: 0,
      processing_retry_limit: 2,
      processing_retries_remaining: 2,
      audio_retention_policy: "delete_after_processing",
      audio_retention_state: "temporary",
      transcript_version: {
        id: "transcript-retention-1",
        version_number: 1,
        transcript: "A synthetic retained transcript.",
        source: "transcription",
        edit_reason: null,
        created_by: "system",
        processing_generation: 1,
        created_at: "2026-08-09T10:00:00Z",
      },
    },
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
      planned_questions_total: 3,
      planned_questions_completed: 1,
      follow_ups_completed: 0,
      current_planned_position: 2,
    },
    retention: {
      audio_policy: "retain_until_deleted",
      current_audio_state: "temporary",
    },
    allowed_commands: ["update_retention", "delete_audio"],
    silence_policy: { warning_ms: 4000, finish_prompt_ms: 9000 },
    recoverable_error: null,
    report_state: "not_started",
    contract_version: "coach_live_view_v1",
    ...overrides,
  };
}

describe("RetentionStatus", () => {
  it("distinguishes future policy from the current answer snapshot", () => {
    const current = live();

    render(
      <RetentionStatus
        live={current}
        pending={false}
        onUpdatePolicy={vi.fn()}
        onDeleteAudio={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Future answers" })).toBeVisible();
    expect(screen.getByText("Keep audio until I delete it")).toBeVisible();
    expect(screen.getByRole("heading", { name: "This answer" })).toBeVisible();
    expect(screen.getByText("Delete audio after processing")).toBeVisible();
    expect(screen.getByText("Audio is temporarily retained until processing cleanup can run.")).toBeVisible();
  });

  it.each([
    ["not_applicable", "No audio was recorded for this answer."],
    ["temporary", "Audio is temporarily retained until processing cleanup can run."],
    ["retained", "Audio is retained for this answer."],
    ["delete_pending", "Audio deletion is in progress."],
    ["deleted", "Audio has been deleted. Your transcript, answer review, and saved delivery observations remain available."],
    ["delete_failed", "Audio could not be deleted. You can try again."],
  ] as const)("renders the %s backend retention state truthfully", (state, message) => {
    render(
      <RetentionStatus
        live={live({ retention: { audio_policy: "delete_after_processing", current_audio_state: state } })}
        pending={false}
        onUpdatePolicy={vi.fn()}
        onDeleteAudio={vi.fn()}
      />,
    );

    expect(screen.getByText(message)).toBeVisible();
  });

  it("explains that future policy changes cannot alter an existing answer", () => {
    render(
      <RetentionStatus
        live={live()}
        pending={false}
        onUpdatePolicy={vi.fn()}
        onDeleteAudio={vi.fn()}
      />,
    );

    expect(screen.getByText(
      "Changes apply only to future answers. They cannot restore deleted audio or remove audio retained for an earlier answer.",
    )).toBeVisible();
  });

  it("offers only server-advertised retention actions with exact targets", async () => {
    const user = userEvent.setup();
    const onUpdatePolicy = vi.fn();
    const onDeleteAudio = vi.fn();
    const view = render(
      <RetentionStatus
        live={live()}
        pending={false}
        onUpdatePolicy={onUpdatePolicy}
        onDeleteAudio={onDeleteAudio}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Delete audio after processing for future answers" }));
    await user.click(screen.getByRole("button", { name: "Delete audio for this answer" }));
    expect(onUpdatePolicy).toHaveBeenCalledOnce();
    expect(onUpdatePolicy).toHaveBeenCalledWith("delete_after_processing");
    expect(onDeleteAudio).toHaveBeenCalledOnce();
    expect(onDeleteAudio).toHaveBeenCalledWith("attempt-retention-1");

    view.rerender(
      <RetentionStatus
        live={live({ allowed_commands: [] })}
        pending={false}
        onUpdatePolicy={onUpdatePolicy}
        onDeleteAudio={onDeleteAudio}
      />,
    );
    expect(screen.queryByRole("button", { name: /future answers/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete audio for this answer" })).not.toBeInTheDocument();
  });

  it("disables advertised retention actions while another command is pending", () => {
    render(
      <RetentionStatus
        live={live()}
        pending
        onUpdatePolicy={vi.fn()}
        onDeleteAudio={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Delete audio after processing for future answers" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete audio for this answer" })).toBeDisabled();
  });
});

describe("ConversationSession retention authority", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.getCoachConversationLive.mockResolvedValue(live());
    api.sendCoachConversationCommand.mockResolvedValue({
      command_id: "command-result-1",
      result: "completed",
      session_id: "session-retention-1",
      state: "awaiting_next_action",
      state_version: 9,
      active_question_id: "question-retention-1",
      active_attempt_id: "attempt-retention-1",
      async_job_id: null,
      allowed_commands: ["update_retention", "delete_audio"],
      contract_version: "coach_conversation_command_result_v1",
    });
  });

  it("does not claim a transcript survived when terminal processing produced none", async () => {
    api.getCoachConversationLive.mockResolvedValueOnce(live({
      conversation_state: "awaiting_next_action",
      active_attempt: {
        ...live().active_attempt!,
        attempt_state: "unavailable",
        transcript_version: null,
      },
      processing: {
        job_id: null,
        stage: "transcription",
        state: "failed_terminal",
        retryable: false,
        retry_count: 2,
        retry_limit: 2,
        retries_remaining: 0,
      },
    }));

    render(<ConversationSession sessionId="session-retention-1" />);

    expect(await screen.findByRole("heading", { name: "Answer review unavailable" })).toBeVisible();
    expect(screen.getByText("No answer review or performance level was created.")).toBeVisible();
    expect(screen.queryByText(/answer and transcript remain available/i)).not.toBeInTheDocument();
  });

  it("creates a new command ID for each future-policy action", async () => {
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(live({
        state_version: 9,
        retention_version: 3,
        retention: { audio_policy: "delete_after_processing", current_audio_state: "temporary" },
      }))
      .mockResolvedValueOnce(live({ state_version: 10, retention_version: 4 }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-retention-1" />);

    await user.click(await screen.findByRole("button", {
      name: "Delete audio after processing for future answers",
    }));
    await user.click(await screen.findByRole("button", {
      name: "Keep audio for future answers until I delete it",
    }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(2));
    const first = api.sendCoachConversationCommand.mock.calls[0][1];
    const second = api.sendCoachConversationCommand.mock.calls[1][1];
    expect(first).toMatchObject({
      command_type: "update_retention",
      expected_state_version: 8,
      payload: { audio: "delete_after_processing" },
    });
    expect(second).toMatchObject({
      command_type: "update_retention",
      expected_state_version: 9,
      payload: { audio: "retain_until_deleted" },
    });
    expect(first.command_id).not.toBe(second.command_id);
  });

  it("retries one transport failure with the identical command envelope", async () => {
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(live({
        state_version: 9,
        retention_version: 3,
        retention: { audio_policy: "delete_after_processing", current_audio_state: "temporary" },
      }));
    api.sendCoachConversationCommand
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        command_id: "command-result-transport-retry",
        result: "completed",
        session_id: "session-retention-1",
        state: "awaiting_next_action",
        state_version: 9,
        active_question_id: "question-retention-1",
        active_attempt_id: "attempt-retention-1",
        async_job_id: null,
        allowed_commands: ["update_retention", "delete_audio"],
        contract_version: "coach_conversation_command_result_v1",
      });
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-retention-1" />);

    await user.click(await screen.findByRole("button", {
      name: "Delete audio after processing for future answers",
    }));

    await waitFor(() => expect(api.sendCoachConversationCommand).toHaveBeenCalledTimes(2));
    const firstRequest = api.sendCoachConversationCommand.mock.calls[0][1];
    const retryRequest = api.sendCoachConversationCommand.mock.calls[1][1];
    expect(retryRequest).toBe(firstRequest);
    expect(retryRequest).toMatchObject({
      command_id: firstRequest.command_id,
      command_type: "update_retention",
      expected_state_version: 8,
      payload: { audio: "delete_after_processing" },
    });
    expect(api.getCoachConversationLive).toHaveBeenCalledTimes(2);
  });

  it("deletes only the advertised answer audio and preserves transcript review", async () => {
    const markup = '<img src=x onerror="window.__coachRetentionXss=1">';
    const current = live({
      retention: { audio_policy: "retain_until_deleted", current_audio_state: "delete_failed" },
      active_attempt: {
        ...live().active_attempt!,
        transcript_version: { ...live().active_attempt!.transcript_version!, transcript: markup },
      },
    });
    api.getCoachConversationLive
      .mockResolvedValueOnce(current)
      .mockResolvedValueOnce(live({
        state_version: 9,
        retention_version: 3,
        retention: { audio_policy: "retain_until_deleted", current_audio_state: "deleted" },
        allowed_commands: ["update_retention"],
        active_attempt: {
          ...current.active_attempt!,
          audio_retention_state: "deleted",
        },
      }));
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-retention-1" />);

    expect(await screen.findByText(markup)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Delete audio for this answer" }));

    expect(await screen.findByText(
      "Audio has been deleted. Your transcript, answer review, and saved delivery observations remain available.",
    )).toBeVisible();
    expect(screen.getByText(markup)).toBeVisible();
    expect((window as Window & { __coachRetentionXss?: number }).__coachRetentionXss).toBeUndefined();
    expect(api.sendCoachConversationCommand).toHaveBeenCalledOnce();
    expect(api.sendCoachConversationCommand.mock.calls[0][1]).toMatchObject({
      command_type: "delete_audio",
      expected_state_version: 8,
      payload: { attempt_id: "attempt-retention-1" },
    });
  });

  it("does not retry a retention command after a 409 conflict", async () => {
    api.getCoachConversationLive
      .mockResolvedValueOnce(live())
      .mockResolvedValueOnce(live({ state_version: 9 }));
    api.sendCoachConversationCommand.mockRejectedValueOnce(
      Object.assign(new Error("The interview changed."), { status: 409 }),
    );
    const user = userEvent.setup();
    render(<ConversationSession sessionId="session-retention-1" />);

    await user.click(await screen.findByRole("button", {
      name: "Delete audio after processing for future answers",
    }));

    expect(await screen.findByText(
      "The interview changed on the server. Your unsent answer is still here.",
    )).toBeVisible();
    expect(api.sendCoachConversationCommand).toHaveBeenCalledOnce();
    expect(api.getCoachConversationLive).toHaveBeenCalledTimes(2);
  });

  it("contains no live score, confidence, voice-emotion or video output", async () => {
    render(<ConversationSession sessionId="session-retention-1" />);

    expect(await screen.findByRole("heading", { name: "Future answers" })).toBeVisible();
    expect(screen.queryByText(
      /wpm|filler|confidence|score|good answer|bad answer|emotion|personality|deception|presence|video/i,
    )).not.toBeInTheDocument();
  });
});
