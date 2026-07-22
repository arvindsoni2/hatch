import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "session-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const api = vi.hoisted(() => ({
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

vi.mock("@/components/coach/CoachModalitySelector", () => ({
  CoachModalitySelector: ({ onModeChange }: { onModeChange: (mode: string) => void }) => (
    <div>
      <button type="button" onClick={() => onModeChange("text")}>Text</button>
      <button type="button" onClick={() => onModeChange("voice")}>Voice</button>
    </div>
  ),
}));

vi.mock("@/components/coach/AudioBlobRecorder", () => ({
  AudioBlobRecorder: ({ onSubmit }: { onSubmit: (blob: Blob, durationMs: number) => void }) => (
    <button
      type="button"
      onClick={() => onSubmit(new Blob(["audio"], { type: "audio/webm" }), 100)}
    >
      Submit recorded audio
    </button>
  ),
}));

const unavailableEvaluation = {
  evaluation_state: "unavailable",
  scores: {},
  overall: null,
  feedback: "Evaluation could not be completed. Please try again.",
  strengths: [],
  improvements: [],
  follow_up_question: null,
  speech_coaching: [],
  retryable: true,
};

describe("Coach session retryable no-score results", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSession.mockResolvedValue({
      id: "session-1",
      application_id: null,
      company_name: "Example Cloud",
      role_title: "Solutions Architect",
      status: "active",
      overall_score: null,
      created_at: "2026-07-22T10:00:00Z",
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
    });
    api.researchCompany.mockResolvedValue(null);
    api.getCoachCapabilities.mockResolvedValue({ face_analysis: false, tts: false });
    api.submitAnswer.mockResolvedValue({ job_id: "text-job" });
    api.submitAudio.mockResolvedValue({ job_id: "audio-job" });
    api.getAsyncJob.mockResolvedValue({
      status: "done",
      result: unavailableEvaluation,
    });
  });

  it("keeps a text question unanswered and restores text controls on retry", async () => {
    const { default: SessionPage } = await import("@/app/coach/session/[id]/page");
    render(<SessionPage />);

    const answer = await screen.findByPlaceholderText(/Type your answer using the STAR framework/i);
    fireEvent.change(answer, { target: { value: "I planned the migration in waves." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit Answer" }));

    const retry = await screen.findByRole("button", { name: "Try this question again" });
    expect(screen.getByText("0/1 answered")).toBeVisible();
    expect(screen.queryByRole("button", { name: /View Feedback Report/ })).toBeNull();

    fireEvent.click(retry);
    expect(await screen.findByPlaceholderText(/Type your answer using the STAR framework/i)).toBeVisible();
  });

  it("restores voice controls in the same mode on retry", async () => {
    const { default: SessionPage } = await import("@/app/coach/session/[id]/page");
    render(<SessionPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Voice" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit recorded audio" }));

    fireEvent.click(await screen.findByRole("button", { name: "Try this question again" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Submit recorded audio" })).toBeVisible();
    });
    expect(api.submitAudio).toHaveBeenCalledOnce();
  });
});
