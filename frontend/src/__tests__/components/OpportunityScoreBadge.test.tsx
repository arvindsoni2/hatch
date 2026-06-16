import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OpportunityScoreBadge } from "@/components/OpportunityScoreBadge";

describe("OpportunityScoreBadge", () => {
  it("shows score, confidence, sample size, and cautious explanation", () => {
    render(<OpportunityScoreBadge score={0.84} adjustment={0.04} confidence="medium" sampleSize={24} reasons={[{ signal: "source", value: "direct", direction: "positive", contribution: 0.02, segment_rate: 0.2, baseline_rate: 0.1, sample_size: 8, message: "Applications from this source have received more responses in your recent history." }]} />);
    fireEvent.click(screen.getByText("Opportunity 84%"));
    expect(screen.getByText(/24 resolved applications/)).toBeTruthy();
    expect(screen.getByText(/not a response probability/)).toBeTruthy();
    expect(screen.getByText(/8 samples/)).toBeTruthy();
  });
});
