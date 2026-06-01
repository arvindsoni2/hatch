import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepSkills } from "@/components/onboarding/StepSkills";

const defaultSkills = { primary: [], secondary: [], certifications: [] };
const defaultDomains = { preferred: [], excluded: [] };

describe("StepSkills", () => {
  it("renders core skills, supporting skills, and certifications inputs", () => {
    render(
      <StepSkills
        skills={defaultSkills}
        onSkillsChange={vi.fn()}
        domains={defaultDomains}
        onDomainsChange={vi.fn()}
        proofPoints={[]}
        onProofPointsChange={vi.fn()}
      />
    );
    expect(screen.getAllByText(/core skills/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/supporting skills/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/certifications/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows Add proof point button", () => {
    render(
      <StepSkills
        skills={defaultSkills}
        onSkillsChange={vi.fn()}
        domains={defaultDomains}
        onDomainsChange={vi.fn()}
        proofPoints={[]}
        onProofPointsChange={vi.fn()}
      />
    );
    expect(screen.getByText(/add proof point/i)).toBeInTheDocument();
  });

  it("shows proof point form when Add proof point is clicked", () => {
    const onProofPointsChange = vi.fn();
    render(
      <StepSkills
        skills={defaultSkills}
        onSkillsChange={vi.fn()}
        domains={defaultDomains}
        onDomainsChange={vi.fn()}
        proofPoints={[]}
        onProofPointsChange={onProofPointsChange}
      />
    );
    fireEvent.click(screen.getByText(/add proof point/i));
    expect(onProofPointsChange).toHaveBeenCalledWith(expect.arrayContaining([
      expect.objectContaining({ summary: "", context: "", metrics: "" }),
    ]));
  });

  it("calls onProofPointsChange when Add proof point is clicked", () => {
    const onProofPointsChange = vi.fn();
    render(
      <StepSkills
        skills={defaultSkills}
        onSkillsChange={vi.fn()}
        domains={defaultDomains}
        onDomainsChange={vi.fn()}
        proofPoints={[]}
        onProofPointsChange={onProofPointsChange}
      />
    );
    fireEvent.click(screen.getByText(/add proof point/i));
    expect(onProofPointsChange).toHaveBeenCalledWith(expect.arrayContaining([
      expect.objectContaining({ summary: "", context: "", metrics: "" }),
    ]));
  });
});
