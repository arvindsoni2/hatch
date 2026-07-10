import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

const approveJob = vi.fn();
const getAsyncJob = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
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
  score: 0.9,
  state: "ready",
});

describe("StreamPageClient bulk prep", () => {
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

  it("starts selected Pipeline CV packs sequentially and leaves the page responsive", async () => {
    const { StreamPageClient } = await import("@/app/stream/StreamPageClient");
    render(
      <StreamPageClient
        jobs={[
          readyJob("job-1", "First Role"),
          readyJob("job-2", "Second Role"),
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Select CV packs" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select First Role" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Second Role" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate 2 CV packs" }));

    await waitFor(() => {
      expect(approveJob).toHaveBeenNthCalledWith(1, "posting-job-1");
      expect(approveJob).toHaveBeenNthCalledWith(2, "posting-job-2");
    });
    expect(await screen.findByText("Bulk prep started for 2 roles.")).toBeVisible();
    expect(screen.getByText("All").closest("button")).toBeEnabled();
  }, 15000);
});
