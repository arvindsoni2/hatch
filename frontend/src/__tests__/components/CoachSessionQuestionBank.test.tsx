import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "session-1" }),
  useRouter: () => ({ push }),
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

describe("Coach session Question Bank integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getSession.mockResolvedValue({
      id: "session-1",
      application_id: "app-1",
      company_name: "Example Cloud",
      role_title: "Solutions Architect",
      status: "active",
      overall_score: null,
      created_at: "2026-07-09T10:00:00Z",
      questions: [
        {
          id: "question-1",
          session_id: "session-1",
          question_num: 1,
          text: "Tell me about a complex migration.",
          category: "Behavioural",
          difficulty: "medium",
          context: null,
          model_answer: null,
          order_in_session: 1,
        },
      ],
    });
    api.researchCompany.mockResolvedValue(null);
    api.getCoachCapabilities.mockResolvedValue({ face_analysis: false, tts: false });
    api.saveQuestionBankFromInterviewAnswer.mockResolvedValue({ id: "qb-1" });
  });

  it("saves the typed answer for the active question to Question Bank", async () => {
    const { default: SessionPage } = await import("@/app/coach/session/[id]/page");

    render(<SessionPage />);

    const answer = await screen.findByPlaceholderText(/Type your answer using the STAR framework/i);
    fireEvent.change(answer, {
      target: { value: "I split the migration into waves and aligned stakeholders." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Save to Question Bank/i }));

    await waitFor(() => {
      expect(api.saveQuestionBankFromInterviewAnswer).toHaveBeenCalledWith({
        session_id: "session-1",
        question_id: "question-1",
        answer_draft: "I split the migration into waves and aligned stakeholders.",
        title: "Tell me about a complex migration.",
        confidence: "draft",
      });
    });
    expect(await screen.findByText("Saved to Question Bank.")).toBeVisible();
  }, 10000);
});
