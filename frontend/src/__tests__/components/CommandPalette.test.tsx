import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/CommandPalette";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("CommandPalette route vocabulary", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.scrollIntoView = vi.fn();
    render(<CommandPalette />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  });

  it("uses the canonical job-search capability labels", () => {
    expect(screen.getByText("Jobs")).toBeInTheDocument();
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Applications")).toBeInTheDocument();
    expect(screen.getByText("Interview Prep")).toBeInTheDocument();
    expect(screen.getByText("Interview Coach")).toBeInTheDocument();
    expect(screen.queryByText("Coach")).not.toBeInTheDocument();
  });
});
