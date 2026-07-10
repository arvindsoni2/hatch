import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StepExperienceChoice } from "@/components/onboarding/StepExperienceChoice";

describe("StepExperienceChoice", () => {
  it("renders Essential, Full AI, and Custom as distinct setup choices", () => {
    render(
      <StepExperienceChoice
        value="essential"
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "Choose your Hatch experience" })).toBeVisible();
    expect(screen.getByRole("button", { name: /Use Essential/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Check this computer/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /Customise capabilities/i })).toBeVisible();
    expect(screen.getByText(/Full AI does not download local models automatically/i)).toBeVisible();
    expect(screen.getByText(/Cloud provider and local model setup stay separate/i)).toBeVisible();
  });

  it("keeps AI mode and backend profile independent when selecting Full AI", () => {
    const onChange = vi.fn();
    render(
      <StepExperienceChoice
        value="essential"
        onChange={onChange}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: /Check this computer/i }));

    expect(onChange).toHaveBeenCalledWith({
      experience: "full_ai",
      aiMode: "ai-later",
      backendProfile: "full",
      acknowledgement: false,
    });
  });
});
