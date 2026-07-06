import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}));

vi.mock("@/lib/api", () => ({
  fetchProfileStatus: vi.fn().mockResolvedValue({
    candidate_name: "Arvind",
    onboarding_required: false,
  }),
  listCompletedJobs: vi.fn().mockResolvedValue([]),
}));

describe("HatchTopBarSlot", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders a utility header without duplicating the route heading", async () => {
    const { HatchTopBarSlot } = await import("@/components/hatch/HatchTopBarSlot");
    await act(async () => { render(<HatchTopBarSlot />); });

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.getByText(/Arvind/)).toBeInTheDocument();
  });

  it("renders notifications and the user menu", async () => {
    const { HatchTopBarSlot } = await import("@/components/hatch/HatchTopBarSlot");
    await act(async () => { render(<HatchTopBarSlot />); });

    expect(screen.getByRole("button", { name: /notifications/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open user menu/i })).toBeInTheDocument();
  });
});
