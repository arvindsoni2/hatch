import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BottomNav } from "@/components/BottomNav";

vi.mock("@/lib/api", () => ({
  fetchPendingApprovals: vi.fn().mockResolvedValue([]),
}));

describe("BottomNav", () => {
  it("renders all navigation items", () => {
    render(<BottomNav />);
    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Jobs")).toBeInTheDocument();
    expect(screen.getByText("Approvals")).toBeInTheDocument();
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Analytics")).toBeInTheDocument();
    expect(screen.getByText("Prep")).toBeInTheDocument();
  });

  it("shows approval badge when there are pending approvals", async () => {
    const { fetchPendingApprovals } = await import("@/lib/api");
    vi.mocked(fetchPendingApprovals).mockResolvedValueOnce([
      { id: "1", job_title: "Dev", company: "Acme", approval_status: "pending" } as never,
      { id: "2", job_title: "Lead", company: "Corp", approval_status: "pending" } as never,
    ]);
    render(<BottomNav />);
    await waitFor(() => {
      expect(screen.getByText("2")).toBeInTheDocument();
    });
  });

  it("has md:hidden class to hide on desktop", () => {
    const { container } = render(<BottomNav />);
    const nav = container.querySelector("nav");
    expect(nav?.className).toContain("md:hidden");
  });
});
