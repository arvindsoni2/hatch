import { render, screen, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { NotificationBell } from "@/components/NotificationBell";

const mockFetch = vi.fn();
global.fetch = mockFetch;

function makeJobs(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `job-${i}`,
    type: "tailor_analyse",
    status: "done",
    result: null,
    error: null,
    created_at: new Date().toISOString(),
  }));
}

describe("NotificationBell", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  it("shows no badge when there are no completed jobs", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => [] });

    await act(async () => { render(<NotificationBell />); });

    expect(screen.queryByTestId("bell-badge")).toBeNull();
  });

  it("shows badge count when there are unseen completed jobs", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => makeJobs(3) });

    await act(async () => { render(<NotificationBell />); });

    const badge = screen.getByTestId("bell-badge");
    expect(badge).toBeTruthy();
    expect(badge.textContent).toBe("3");
  });

  it("shows job type label in the dropdown when bell is clicked", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [{
        id: "job-1", type: "tailor_analyse", status: "done",
        result: null, error: null, created_at: new Date().toISOString(),
      }],
    });

    await act(async () => { render(<NotificationBell />); });

    const bell = screen.getByRole("button", { name: /notifications/i });
    await act(async () => { bell.click(); });

    expect(screen.getByText("JD Analysis complete")).toBeTruthy();
  });
});
