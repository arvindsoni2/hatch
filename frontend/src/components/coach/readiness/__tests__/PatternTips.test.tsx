import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PatternTips } from "@/components/coach/readiness/PatternTips";

describe("PatternTips", () => {
  it("shows skeleton lines while tips arrive in a polite region", () => {
    render(<PatternTips tips={null} loading />);

    expect(screen.getByLabelText("Adding tips")).toBeVisible();
    expect(screen.getByText("Adding tips…")).toBeVisible();
    expect(screen.getByText("Tips").parentElement).toHaveAttribute("aria-live", "polite");
  });

  it("shows the AI-off state", () => {
    render(<PatternTips tips={null} loading={false} aiOff />);
    expect(screen.getByText("Turn on local AI for tips")).toBeVisible();
  });

  it("offers a retry when tips are unavailable or fenced", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<PatternTips tips={null} loading={false} unavailable onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: "Tips unavailable — try again" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("renders the tips returned by the model", () => {
    render(<PatternTips tips={["Say what you did.", "Name the result."]} loading={false} />);

    expect(screen.getByText("Say what you did.")).toBeVisible();
    expect(screen.getByText("Name the result.")).toBeVisible();
  });
});
