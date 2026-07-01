import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TailoringReviewPanel } from "@/components/TailoringReviewPanel";
import type { TailoringReview } from "@/lib/api";

const review: TailoringReview = {
  application_id: "app-1",
  match_summary: {
    role_title: "Programme Manager",
    overall_match: 82,
    summary: "Strong delivery and governance alignment.",
  },
  ats_keyword_coverage: {
    covered: ["Agile", "PMP"],
    missing: ["Python"],
    coverage_pct: 67,
  },
  evidence_used: [
    { requirement: "Agile", evidence: "PMI-ACP and delivery history", confidence: "high" },
  ],
  weak_or_unsupported_requirements: [
    { requirement: "Python", reason: "No grounded evidence.", suggestion: "Confirm before claiming." },
  ],
  warnings: [],
  documents: [
    { id: "cv-1", type: "cv", template_id: "ats_classic" },
    { id: "cl-1", type: "cover_letter", template_id: "ats_classic" },
  ],
  template_id: "ats_classic",
  variant: "A",
  created_at: "2026-07-01T12:00:00",
};

describe("TailoringReviewPanel", () => {
  it("renders match, coverage, grounded evidence and unsupported requirements", () => {
    render(<TailoringReviewPanel review={review} regenerating={false} onRegenerate={vi.fn()} />);
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("PMI-ACP and delivery history")).toBeInTheDocument();
    expect(screen.getByText("Python", { selector: "strong" })).toBeInTheDocument();
  });

  it("maps a regeneration choice to the callback", () => {
    const onRegenerate = vi.fn();
    render(<TailoringReviewPanel review={review} regenerating={false} onRegenerate={onRegenerate} />);
    fireEvent.click(screen.getByRole("button", { name: "Make more ATS-focused" }));
    expect(onRegenerate).toHaveBeenCalledWith("Make more ATS-focused");
  });

  it("supports older generations without review data", () => {
    render(<TailoringReviewPanel review={null} regenerating={false} onRegenerate={vi.fn()} />);
    expect(screen.getByText("No review data available for this generation.")).toBeInTheDocument();
  });
});
