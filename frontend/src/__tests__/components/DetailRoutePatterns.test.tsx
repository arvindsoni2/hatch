import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Application, Job } from "@/lib/api";

const serverApiFetch = vi.fn();
const fetchApplication = vi.fn();
const getDocumentHistory = vi.fn();
const updateApplicationStatus = vi.fn();
const addApplicationNote = vi.fn();
const completeFollowUp = vi.fn();
const createInterview = vi.fn();
const downloadDocument = vi.fn();

vi.mock("@/lib/server-api", () => ({
  serverApiFetch: (...args: unknown[]) => serverApiFetch(...args),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchApplication: (...args: unknown[]) => fetchApplication(...args),
    getDocumentHistory: (...args: unknown[]) => getDocumentHistory(...args),
    updateApplicationStatus: (...args: unknown[]) => updateApplicationStatus(...args),
    addApplicationNote: (...args: unknown[]) => addApplicationNote(...args),
    completeFollowUp: (...args: unknown[]) => completeFollowUp(...args),
    createInterview: (...args: unknown[]) => createInterview(...args),
    downloadDocument: (...args: unknown[]) => downloadDocument(...args),
  };
});

vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({ toString: () => "" }),
}));

const jobFixture: Job = {
  id: "job-1",
  title: "Principal Platform Engineer",
  company: "Acme",
  location: "London",
  rate_text: "GBP 700/day",
  rate_min: 650,
  rate_max: 750,
  currency: "GBP",
  ir35_status: "outside",
  legal_fields: { ir35: "outside" },
  contract_length: "6 months",
  description: "Build resilient internal platforms.",
  url: "https://example.com/job",
  source: "manual",
  posted_at: "2026-07-07T08:00:00Z",
  scraped_at: "2026-07-08T08:00:00Z",
  skills: ["platform", "typescript"],
  is_active: true,
  sync_status: "synced",
  created_at: "2026-07-08T08:00:00Z",
  updated_at: "2026-07-08T08:00:00Z",
  employment_type: "contract",
  working_pattern: "hybrid",
  match_score: 0.88,
  match_reasons: ["Strong platform fit"],
  skill_match: 0.9,
  experience_match: 0.86,
  rate_match: 0.82,
  location_match: 0.8,
  scoring_method: "semantic",
  score_reasoning: "Strong match.",
  keyword_matches: ["platform"],
  keyword_misses: [],
  fit_reasoning: "Your platform background lines up well.",
  score_strengths: ["Platform engineering"],
  score_gaps: [],
  ghost_score: null,
  ghost_verdict: null,
  ghost_signals: null,
  ghost_analysed_at: null,
};

const applicationFixture: Application = {
  id: "app-1",
  job_id: "job-1",
  status: "interview",
  priority: "high",
  applied_date: "2026-07-08T08:00:00Z",
  cv_version: null,
  cover_letter_version: null,
  notes: "Follow up with hiring manager.",
  recruiter_name: "Ria",
  recruiter_email: "ria@example.com",
  recruiter_phone: null,
  agency_name: "Acme Talent",
  salary_offered: null,
  rejection_reason: null,
  is_active: true,
  created_at: "2026-07-08T08:00:00Z",
  updated_at: "2026-07-08T08:00:00Z",
  interviews: [],
  follow_ups: [],
  activity: [],
  agent_created: true,
  approval_status: "approved",
  job: {
    id: "job-1",
    title: "Principal Platform Engineer",
    company: "Acme",
    location: "London",
    rate_text: "GBP 700/day",
    rate_min: 650,
    rate_max: 750,
    url: "https://example.com/job",
    source: "manual",
    ir35_status: "outside",
  },
};

describe("Detail route shared patterns", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    serverApiFetch.mockImplementation((path: string) => {
      if (path === "/api/jobs/job-1") return Promise.resolve(jobFixture);
      if (path === "/api/jobs/job-1/decisions") {
        return Promise.resolve({ job_id: "job-1", job_title: jobFixture.title, steps: [], total_cost_usd: 0 });
      }
      if (path === "/api/v2/scoring/job-1") {
        return Promise.resolve({
          id: "score-1",
          job_id: "job-1",
          overall_score: 0.88,
          skill_match: 0.9,
          experience_match: 0.86,
          rate_match: 0.82,
          location_match: 0.8,
          reasoning: "Strong match.",
          scored_at: "2026-07-08T08:30:00Z",
        });
      }
      throw new Error(`Unhandled server path ${path}`);
    });
    fetchApplication.mockResolvedValue(applicationFixture);
    getDocumentHistory.mockResolvedValue([]);
    updateApplicationStatus.mockResolvedValue(undefined);
    addApplicationNote.mockResolvedValue(undefined);
    completeFollowUp.mockResolvedValue(undefined);
    createInterview.mockResolvedValue(undefined);
    downloadDocument.mockResolvedValue(undefined);
  });

  it("renders Jobs detail with breadcrumb, metadata, and primary action patterns", async () => {
    const { default: JobDetailPage } = await import("@/app/jobs/[id]/page");

    render(await JobDetailPage({ params: Promise.resolve({ id: "job-1" }) }));

    expect(screen.getByRole("navigation", { name: "Job detail breadcrumb" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("href", "/jobs");
    expect(screen.getByRole("heading", { name: "Principal Platform Engineer" })).toBeVisible();
    expect(screen.getByText("Acme")).toBeVisible();
    expect(screen.getByText("London")).toBeVisible();
    expect(screen.getByText("GBP 700/day")).toBeVisible();
    expect(screen.getAllByText("88%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("link", { name: "Create CV pack" })).toHaveAttribute("href", "/tailor?jobUrl=https%3A%2F%2Fexample.com%2Fjob");
  });

  it("renders Application detail with a named sheet header and back action", async () => {
    const { ApplicationDetail } = await import("@/components/ApplicationDetail");
    const onClose = vi.fn();

    render(<ApplicationDetail applicationId="app-1" onClose={onClose} />);

    expect(await screen.findByRole("dialog", { name: "Principal Platform Engineer application details" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Back to Applications" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Principal Platform Engineer" })).toBeVisible();
    expect(screen.getByText("Acme")).toBeVisible();
    expect(screen.getAllByText("interview").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("high")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Back to Applications" }));

    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    });
  });
});
