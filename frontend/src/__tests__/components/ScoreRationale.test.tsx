import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ScoreRationale } from "@/components/ScoreRationale";

describe("ScoreRationale", () => {
  it("renders the heading", () => {
    render(
      <ScoreRationale
        reasoning="Strong match on delivery skills."
        keywordMatches={["agile", "delivery"]}
        keywordMisses={["SAFe"]}
      />
    );
    expect(screen.getByText(/Why Hatch surfaced this/i)).toBeInTheDocument();
  });

  it("renders matched skills as green tags", () => {
    render(
      <ScoreRationale
        reasoning="Good skills."
        keywordMatches={["agile", "delivery"]}
        keywordMisses={[]}
      />
    );
    expect(screen.getByText(/agile/)).toBeInTheDocument();
    expect(screen.getByText(/delivery/)).toBeInTheDocument();
  });

  it("renders missing skills", () => {
    render(
      <ScoreRationale
        reasoning="Good match."
        keywordMatches={["agile"]}
        keywordMisses={["SAFe", "PRINCE2"]}
      />
    );
    expect(screen.getByText("SAFe")).toBeInTheDocument();
    expect(screen.getByText("PRINCE2")).toBeInTheDocument();
  });

  it("shows add-to-profile suggestion when skill gaps exist", () => {
    render(
      <ScoreRationale
        reasoning="Good match."
        keywordMatches={["agile"]}
        keywordMisses={["SAFe"]}
      />
    );
    expect(
      screen.getByText(/Consider adding these to your profile/i)
    ).toBeInTheDocument();
  });

  it("does not show gap suggestion when no missing skills", () => {
    render(
      <ScoreRationale
        reasoning="Perfect match."
        keywordMatches={["agile", "delivery"]}
        keywordMisses={[]}
      />
    );
    expect(
      screen.queryByText(/Consider adding these to your profile/i)
    ).not.toBeInTheDocument();
  });

  it("does not show internal reasoning string 'local-keyword'", () => {
    render(
      <ScoreRationale
        reasoning="local-keyword"
        keywordMatches={["python"]}
        keywordMisses={[]}
      />
    );
    expect(screen.queryByText("local-keyword")).not.toBeInTheDocument();
  });
});
