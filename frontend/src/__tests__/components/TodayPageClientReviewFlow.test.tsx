import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

const push = vi.fn();
const approveJob = vi.fn();
const getAsyncJob = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    approveJob,
    rejectApplication: vi.fn().mockResolvedValue(undefined),
    markApplied: vi.fn().mockResolvedValue(undefined),
    revertApplication: vi.fn().mockResolvedValue(undefined),
    getApplicationPackage: vi.fn().mockRejectedValue(new Error("not ready")),
    getAsyncJob,
  };
});

const readyJob = (id: string, title: string): HatchJob => ({
  id,
  jobPostingId: `posting-${id}`,
  title,
  company: "Example Ltd",
  loc: "London",
  rate: "Competitive",
  score: 0.91,
  state: "ready",
});

describe("TodayPageClient review flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    approveJob.mockResolvedValue({ async_job_id: "async-1" });
    getAsyncJob.mockResolvedValue({
      id: "async-1",
      type: "application_package",
      status: "running",
      result: null,
      error: null,
      created_at: "2026-07-10T09:00:00Z",
    });
  });

  it("lets users generate the next role while the previous CV pack is still running", async () => {
    const { TodayPageClient } = await import("@/app/today/TodayPageClient");
    render(
      <TodayPageClient
        jobs={[
          readyJob("job-1", "First Role"),
          readyJob("job-2", "Second Role"),
        ]}
        funnel={{ scout: 0, scorer: 0, tailor: 2, coach: 0 }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Review roles" }));
    expect(screen.getByText("Application 1 of 2")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Generate CV pack" }));

    await waitFor(() => expect(screen.getByText("Application 2 of 2")).toBeVisible());
    const nextGenerate = screen.getByRole("button", { name: "Generate CV pack" });
    expect(nextGenerate).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Preparing CV pack/i })).not.toBeInTheDocument();
  }, 15000);
});
