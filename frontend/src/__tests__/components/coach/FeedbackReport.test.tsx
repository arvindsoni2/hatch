import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FeedbackReport } from "@/components/coach/FeedbackReport";
import type { SessionFeedbackReport } from "@/lib/api";

const fallbackReport: SessionFeedbackReport = {
  session_id: "session-1",
  report_state: "fallback",
  overall_score: null,
  category_scores: {},
  executive_summary: "No completed evaluations were available.",
  strengths: [],
  improvement_areas: [],
  coaching_points: [],
  practice_plan: [],
  question_evaluations: [],
};

describe("FeedbackReport result states", () => {
  it("renders a null fallback score without inventing zero", () => {
    render(<FeedbackReport report={fallbackReport} />);

    expect(screen.getByText(/no score available/i)).toBeVisible();
    expect(screen.getByText(/deterministic fallback feedback/i)).toBeVisible();
    expect(screen.queryByText(/0(?:\.0)?\/10/)).not.toBeInTheDocument();
  });
});
