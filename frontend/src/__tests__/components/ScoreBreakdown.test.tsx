import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";

const baseProps = {
  skillMatch: 0.9,
  experienceMatch: 0.85,
  rateMatch: 0.7,
  locationMatch: 1.0,
  overallScore: 0.87,
  scoringMethod: "llm" as const,
  reasoning: "Strong match on delivery and cloud architecture.",
  keywordMatches: ["agile", "delivery", "cloud"],
  keywordMisses: ["SAFe"],
};

describe("ScoreBreakdown", () => {
  it("renders all 4 dimension bars with labels", () => {
    render(<ScoreBreakdown {...baseProps} />);
    expect(screen.getByText("Skill match")).toBeInTheDocument();
    expect(screen.getByText("Experience")).toBeInTheDocument();
    expect(screen.getByText("Compensation")).toBeInTheDocument();
    expect(screen.getByText("Location")).toBeInTheDocument();
  });

  it("shows the AI assessment method badge for llm scoring", () => {
    render(<ScoreBreakdown {...baseProps} scoringMethod="llm" />);
    expect(screen.getByText("AI assessment")).toBeInTheDocument();
  });

  it("shows the Quick estimate badge for local scoring", () => {
    render(<ScoreBreakdown {...baseProps} scoringMethod="local" />);
    expect(screen.getByText("Quick estimate")).toBeInTheDocument();
  });

  it("shows quick estimate note for local scoring", () => {
    render(<ScoreBreakdown {...baseProps} scoringMethod="local" />);
    expect(screen.getByText(/Quick keyword estimate/i)).toBeInTheDocument();
  });

  it("shows the reasoning text when present", () => {
    render(<ScoreBreakdown {...baseProps} />);
    expect(
      screen.getByText("Strong match on delivery and cloud architecture.")
    ).toBeInTheDocument();
  });

  it("does not show reasoning note when reasoning is local-keyword", () => {
    render(
      <ScoreBreakdown {...baseProps} scoringMethod="local" reasoning="local-keyword" />
    );
    // "local-keyword" is internal — not shown to user
    expect(screen.queryByText("local-keyword")).not.toBeInTheDocument();
  });

  it("highlights the weakest dimension", () => {
    // rateMatch=0.7 is the weakest among the props
    render(<ScoreBreakdown {...baseProps} />);
    const weakLabel = screen.getByTestId("weakest-dimension");
    expect(weakLabel).toBeInTheDocument();
  });

  it("renders percentage values for each dimension", () => {
    render(<ScoreBreakdown {...baseProps} />);
    expect(screen.getByText("90%")).toBeInTheDocument(); // skill
    expect(screen.getByText("85%")).toBeInTheDocument(); // experience
    expect(screen.getByText("70%")).toBeInTheDocument(); // rate
    expect(screen.getByText("100%")).toBeInTheDocument(); // location
  });
});
