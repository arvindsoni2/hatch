import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CVQualityGatePanel } from "@/components/tailor/CVQualityGatePanel";

describe("CVQualityGatePanel", () => {
  it("shows high-risk acknowledgement status", () => {
    render(<CVQualityGatePanel quality={{
      pre_generation: { status: "advisory", keyword_gaps: ["Python"] },
      post_generation: { ats_readability: "poor", keyword_coverage: { coverage_pct: 20, missing: ["Python"] },
        unsupported_claims: [{ claim: "Azure", reason: "No evidence", severity: "high" }],
        export_confidence: "acknowledge_required", core_sections: { experience: false } },
      document_id: "doc", pack_version: 1,
    }} />);
    expect(screen.getByText("Acknowledgement required")).toBeTruthy();
    expect(screen.getByText("Unsupported claims")).toBeTruthy();
  });
});
