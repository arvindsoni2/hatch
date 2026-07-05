import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResumeStudio } from "@/components/tailor/ResumeStudio";
import type { ResumeTemplateResponse } from "@/lib/api";

const settings = { template_id: "ats_classic", page_target: "two_page", density: "standard", section_order_preset: "standard", accent_color: "navy", font_family: "aptos" } as const;
const data: ResumeTemplateResponse = {
  templates: [{ id: "ats_classic", name: "ATS Classic", description: "Safe", best_for: [], layout: "single_column", content_density: "standard", default_page_target: "auto", default_section_order: "standard", ats_safety_notes: [] }],
  default_template_id: "ats_classic", default_design_settings: settings,
  controls: { page_targets: ["two_page"], densities: ["standard"], section_order_presets: ["standard"], accent_colors: ["navy"], font_families: ["aptos"] },
};

describe("ResumeStudio", () => {
  it("renders CV design controls and the final-layout notice", () => {
    const onChange = vi.fn();
    render(<ResumeStudio data={data} value={settings} analysis={null} generated={false} onChange={onChange} />);
    expect(screen.getByText("CV design")).toBeTruthy();
    expect(screen.getByText(/generated DOCX is the final layout/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Page target"), { target: { value: "two_page" } });
    expect(onChange).toHaveBeenCalled();
  });
});
