import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listSessions: vi.fn().mockResolvedValue([]),
  };
});

describe("CoachPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("explains live practice as distinct from the Interview Prep library", async () => {
    const { default: CoachPage } = await import("@/app/coach/page");

    render(<CoachPage />);

    expect(await screen.findByRole("heading", { name: "Interview Coach" })).toBeVisible();
    expect(screen.getAllByText(/live mock interviews/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /review prep materials/i })).toHaveAttribute("href", "/prep");
  });
});
