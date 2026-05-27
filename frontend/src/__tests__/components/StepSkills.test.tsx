import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepSkills } from "@/components/onboarding/StepSkills";

const defaultSkills = { primary: [], secondary: [], certifications: [] };
const defaultDomains = { preferred: [], excluded: [] };

describe("StepSkills", () => {
  it("renders primary skills, secondary skills, and certifications inputs", () => {
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
    expect(screen.getAllByText(/primary skills/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/secondary skills/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/certifications/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows warning when fewer than 3 primary skills", () => {
    render(
      <StepSkills
        skills={{ ...defaultSkills, primary: ["Agile", "AWS"] }}
        onSkillsChange={vi.fn()}
        domains={defaultDomains}
        onDomainsChange={vi.fn()}
        proofPoints={[]}
        onProofPointsChange={vi.fn()}
      />
    );
    expect(screen.getByText(/3 primary skills/i)).toBeInTheDocument();
  });

  it("shows Add achievement button and empty state message", () => {
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
    expect(screen.getByText(/add achievement/i)).toBeInTheDocument();
    expect(screen.getByText(/no achievements added yet/i)).toBeInTheDocument();
  });

  it("calls onProofPointsChange when Add achievement is clicked", () => {
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
    fireEvent.click(screen.getByText(/add achievement/i));
    expect(onProofPointsChange).toHaveBeenCalledWith(expect.arrayContaining([
      expect.objectContaining({ summary: "", context: "", metrics: "" }),
    ]));
  });
});
