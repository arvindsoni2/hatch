import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PatternTips } from "@/components/coach/readiness/PatternTips";

describe("PatternTips", () => {
  it("shows skeleton lines while tips arrive in a polite region", () => {
    render(<PatternTips tips={null} loading />);

    expect(screen.getByLabelText("Adding tips")).toBeVisible();
    expect(screen.getByText("Tips").parentElement).toHaveAttribute("aria-live", "polite");
  });

  it("renders the tips returned by the model", () => {
    render(<PatternTips tips={["Say what you did.", "Name the result."]} loading={false} />);

    expect(screen.getByText("Say what you did.")).toBeVisible();
    expect(screen.getByText("Name the result.")).toBeVisible();
  });
});
