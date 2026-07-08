import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ScreenWelcome } from "@/components/onboarding/ScreenWelcome";

describe("ScreenWelcome", () => {
  it("uses an upright track icon in the onboarding pipeline", () => {
    render(<ScreenWelcome hasSaved={false} onStart={vi.fn()} />);

    const trackRow = screen.getByText("Track").closest("div.flex.gap-3.py-2");
    expect(trackRow).toBeTruthy();

    const icon = trackRow?.querySelector("svg");
    expect(icon).toBeTruthy();
    expect(icon?.className.baseVal || icon?.className).toContain("lucide-clipboard-list");
    expect(icon?.className.baseVal || icon?.className).not.toContain("lucide-kanban");
  });

  it("switches the CTA based on saved progress", () => {
    const { rerender } = render(<ScreenWelcome hasSaved={false} onStart={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Get started →" })).toBeVisible();

    rerender(<ScreenWelcome hasSaved onStart={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Resume setup →" })).toBeVisible();
  });
});
