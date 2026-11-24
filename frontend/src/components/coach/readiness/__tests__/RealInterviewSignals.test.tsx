import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RealInterviewSignals } from "@/components/coach/readiness/RealInterviewSignals";

describe("RealInterviewSignals", () => {
  it("shows the empty line before any signal exists", () => {
    render(<RealInterviewSignals signals={[]} />);

    expect(screen.getByText("From your real interviews")).toBeVisible();
    expect(
      screen.getByText(/No signals yet. They appear once a competency comes up/),
    ).toBeVisible();
  });

  it("lists each signal with its counts and a draft-story link", () => {
    render(
      <RealInterviewSignals
        signals={[
          {
            display: "Stakeholder management",
            fingerprint: "a".repeat(64),
            asked_rounds: 3,
            low_rating_debriefs: 2,
            last_at: "2026-11-20T10:00:00Z",
          },
        ]}
      />,
    );

    expect(screen.getByText("Stakeholder management")).toBeVisible();
    expect(screen.getByText(/Asked in 3 real interviews/)).toBeVisible();
    expect(
      screen.getByText(/You rated yourself 2 or less in 2 debriefs/),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Draft a story" })).toHaveAttribute(
      "href",
      "/coach/stories/new?competency=Stakeholder%20management",
    );
  });

  it("hides the low-rating line until two debriefs rate it low", () => {
    render(
      <RealInterviewSignals
        signals={[
          {
            display: "Budget ownership",
            fingerprint: "b".repeat(64),
            asked_rounds: 2,
            low_rating_debriefs: 1,
            last_at: null,
          },
        ]}
      />,
    );

    expect(screen.queryByText(/rated yourself/i)).not.toBeInTheDocument();
  });
});
