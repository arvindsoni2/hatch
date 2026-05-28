import { render } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Navigation } from "@/components/Navigation";

vi.mock("@/lib/api", () => ({
  fetchPendingApprovals: vi.fn().mockResolvedValue([]),
}));

describe("Navigation — responsive behaviour", () => {
  it("top nav header has hidden class for mobile breakpoint", () => {
    const { container } = render(<Navigation />);
    const header = container.querySelector("header");
    expect(header?.className).toContain("hidden");
    expect(header?.className).toContain("md:");
  });
});
