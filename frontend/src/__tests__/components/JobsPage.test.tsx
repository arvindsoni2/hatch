import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import JobsPage from "@/app/jobs/page";
import {
  fetchJobs,
  fetchRawProfile,
  fetchScoringInsights,
  type Job,
  type PaginatedResponse,
  type ScoringInsights,
} from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchJobs: vi.fn(),
    fetchRawProfile: vi.fn(),
    fetchScoringInsights: vi.fn(),
    runArchive: vi.fn(),
    rescoreUnscored: vi.fn(),
  };
});

const profile = {
  scoring: { shortlist_threshold: 0.75 },
};

const noJobs: PaginatedResponse<Job> = {
  items: [],
  total: 0,
  skip: 0,
  limit: 50,
};

const emptyInsights: ScoringInsights = {
  total_jobs_in_db: 0,
  total_scored: 0,
  scored_last_7d: 0,
  above_threshold: 0,
  in_band_below: 0,
  avg_score: null,
  distribution: [],
  recommendation: null,
  threshold: 0.75,
};

describe("Jobs page empty/loading/error states", () => {
  beforeEach(() => {
    vi.mocked(fetchRawProfile).mockResolvedValue(profile as Awaited<ReturnType<typeof fetchRawProfile>>);
    vi.mocked(fetchJobs).mockResolvedValue(noJobs);
    vi.mocked(fetchScoringInsights).mockResolvedValue(emptyInsights);
  });

  it("states the Jobs purpose using the route contract", async () => {
    render(<JobsPage />);

    expect(await screen.findByRole("heading", { name: "Jobs" })).toBeVisible();
    expect(screen.getByText("Review discovered roles and choose which opportunities to pursue.")).toBeVisible();
  });

  it("uses a skeleton-shaped loading state instead of only a spinner", () => {
    vi.mocked(fetchRawProfile).mockReturnValue(new Promise(() => {}));
    vi.mocked(fetchScoringInsights).mockReturnValue(new Promise(() => {}));

    render(<JobsPage />);

    expect(screen.getByRole("status", { name: "Loading jobs" })).toBeVisible();
    expect(screen.getAllByTestId("jobs-loading-skeleton")).toHaveLength(3);
  });

  it("shows retry and Diagnostics actions when jobs fail to load", async () => {
    vi.mocked(fetchJobs).mockRejectedValueOnce(new Error("backend unavailable"));

    render(<JobsPage />);

    expect(await screen.findByText("backend unavailable")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Diagnostics" })).toHaveAttribute("href", "/settings/system");
  });

  it("gives no-data users a primary scrape action and a secondary preferences link", async () => {
    render(<JobsPage />);

    const emptyState = await screen.findByRole("status", { name: "No jobs yet" });
    expect(within(emptyState).getByText("Run Job Scout to fetch roles that match your profile.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Scrape Now" })).toBeVisible();
    expect(within(emptyState).getByRole("link", { name: "Review Job Preferences" })).toHaveAttribute(
      "href",
      "/settings/preferences",
    );
  });
});
