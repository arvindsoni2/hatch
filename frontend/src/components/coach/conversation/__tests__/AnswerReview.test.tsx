import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AnswerReview } from "../AnswerReview";
import { sliceCodePoints } from "../CodePointExcerpt";

const reviewFixture = {
  evaluation_id: "evaluation-1",
  evaluation_state: "completed",
  answer_level: "interview_ready",
  dimensions: {
    relevance: {
      level: "interview_ready",
      rationale: "The answer stays focused on the migration.",
      improvement: null,
      evidence: [{
        transcript_start: 0,
        transcript_end: 11,
        excerpt: "I led 😊 the",
      }],
    },
  },
  delivery: {
    level: "developing",
    observations: [{ severity: "moderate", label: "The pace varied during the answer." }],
  },
  evidence_consistency: "interview_ready",
  evidence_findings: [{
    claim_id: "claim-1",
    claim_text: "three regional teams",
    transcript_start: 20,
    transcript_end: 40,
    status: "partially_supported",
    source_label: "Candidate-selected draft",
    source_approval: "draft",
    explanation: "The selected draft supports the team scope, but not the timing.",
    candidate_action: "Check the timing before reusing this answer.",
  }],
  coaching: null,
  accepted_at: null,
} as const;

const liveFixture = {
  conversation_state: "awaiting_next_action",
  allowed_commands: ["accept_attempt", "request_coaching", "record_self_assessment"],
  active_attempt: {
    id: "attempt-1",
    attempt_number: 1,
    transcript_version: {
      transcript: "I led 😊 the migration across three regional teams.",
    },
    self_assessment: null,
  },
  answer_review: reviewFixture,
} as const;

describe("AnswerReview", () => {
  it("renders four named review panels without numeric or inferred judgements", () => {
    render(<AnswerReview live={liveFixture} pending={false} onCommand={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Answer quality" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Delivery observations" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Evidence check" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Your reflection" })).toBeVisible();
    expect(screen.getByText("Interview-ready")).toBeVisible();
    expect(screen.getByText("Candidate-selected draft")).toBeVisible();
    expect(screen.getByText("I led 😊 the")).toBeVisible();
    expect(screen.queryByText(/\/10|\d+%|confidence|personality/i)).not.toBeInTheDocument();
  });

  it("uses only server-advertised review actions and exact attempt ids", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    const view = render(
      <AnswerReview live={liveFixture} pending={false} onCommand={onCommand} />,
    );

    await user.click(screen.getByRole("button", { name: "Accept attempt 1" }));
    await user.click(screen.getByRole("button", { name: "Get coaching for attempt 1" }));
    expect(onCommand).toHaveBeenNthCalledWith(1, "accept_attempt", { attempt_id: "attempt-1" });
    expect(onCommand).toHaveBeenNthCalledWith(2, "request_coaching", { attempt_id: "attempt-1" });

    view.rerender(
      <AnswerReview
        live={{ ...liveFixture, allowed_commands: [] }}
        pending={false}
        onCommand={onCommand}
      />,
    );
    expect(screen.queryByRole("button", { name: /accept attempt/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /get coaching/i })).not.toBeInTheDocument();
  });

  it("labels review actions with the authoritative attempt number", () => {
    render(
      <AnswerReview
        live={{
          ...liveFixture,
          active_attempt: { ...liveFixture.active_attempt, attempt_number: 3 },
        }}
        pending={false}
        onCommand={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Accept attempt 3" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Get coaching for attempt 3" })).toBeVisible();
  });

  it("submits candidate reflection and returns from coaching only when allowed", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    render(
      <AnswerReview
        live={{
          ...liveFixture,
          conversation_state: "coaching",
          allowed_commands: ["record_self_assessment", "return_to_review"],
        }}
        pending={false}
        onCommand={onCommand}
      />,
    );

    await user.selectOptions(screen.getByLabelText("Comfort level"), "medium");
    await user.click(screen.getByRole("checkbox", { name: "My answer felt complete" }));
    await user.type(screen.getByLabelText("Reflection note"), "I want to make the outcome clearer.");
    await user.click(screen.getByRole("button", { name: "Save reflection" }));
    expect(onCommand).toHaveBeenCalledWith("record_self_assessment", {
      attempt_id: "attempt-1",
      comfort_level: "medium",
      felt_complete: true,
      note: "I want to make the outcome clearer.",
    });

    await user.click(screen.getByRole("button", { name: "Return to review" }));
    expect(onCommand).toHaveBeenCalledWith("return_to_review", {});
  });

  it("renders untrusted review strings as inert text", () => {
    render(
      <AnswerReview
        live={{
          ...liveFixture,
          answer_review: {
            ...reviewFixture,
            dimensions: {
              relevance: {
                ...reviewFixture.dimensions.relevance,
                rationale: '<img src=x onerror="window.__reviewXss=1">',
              },
            },
          },
        }}
        pending={false}
        onCommand={vi.fn()}
      />,
    );

    expect(screen.getByText('<img src=x onerror="window.__reviewXss=1">')).toBeVisible();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("sliceCodePoints", () => {
  it("uses canonical Unicode code points for emoji, combining marks, Hindi, and CRLF", () => {
    expect(sliceCodePoints("A😊B", 1, 2)).toBe("😊");
    expect(sliceCodePoints("Cafe\u0301", 3, 4)).toBe("é");
    expect(sliceCodePoints("नमस्ते", 0, 2)).toBe("नम");
    expect(sliceCodePoints("a\r\nb", 1, 3)).toBe("\nb");
  });
});
