import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvaluationCard } from "@/components/coach/EvaluationCard";
import type { AnswerEvaluation } from "@/lib/api";

const noScore = (state: "unavailable" | "invalid"): AnswerEvaluation => ({
  evaluation_state: state,
  scores: {},
  overall: null,
  feedback: "Evaluation was unavailable.",
  strengths: [],
  improvements: [],
  follow_up_question: null,
  speech_coaching: [],
  retryable: true,
});

describe("EvaluationCard result states", () => {
  it.each(["unavailable", "invalid"] as const)(
    "does not render a numeric score for %s",
    (state) => {
      render(<EvaluationCard evaluation={noScore(state)} />);

      expect(screen.getByText(/evaluation could not be completed/i)).toBeVisible();
      expect(screen.getByText(/submit the answer again/i)).toBeVisible();
      expect(screen.queryByText(/\/10/)).not.toBeInTheDocument();
    },
  );
});
