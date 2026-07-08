import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchAllAgentStatus = vi.fn();
const fetchAgentEvents = vi.fn();
const fetchPipelineStats = vi.fn();
const triggerAgent = vi.fn();
const fetchPendingApprovals = vi.fn();
const approveApplication = vi.fn();
const rejectApplication = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchAllAgentStatus: (...args: unknown[]) => fetchAllAgentStatus(...args),
    fetchAgentEvents: (...args: unknown[]) => fetchAgentEvents(...args),
    fetchPipelineStats: (...args: unknown[]) => fetchPipelineStats(...args),
    triggerAgent: (...args: unknown[]) => triggerAgent(...args),
    fetchPendingApprovals: (...args: unknown[]) => fetchPendingApprovals(...args),
    approveApplication: (...args: unknown[]) => approveApplication(...args),
    rejectApplication: (...args: unknown[]) => rejectApplication(...args),
  };
});

vi.mock("@/components/TriggerScrapeButton", () => ({
  TriggerScrapeButton: () => <button type="button">Run Scout</button>,
}));

vi.mock("@/components/AssistedApplyCard", () => ({
  AssistedApplyCard: () => <div data-testid="assisted-apply-card" />,
}));

describe("Agents and Approvals route states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchAllAgentStatus.mockResolvedValue({
      database: "healthy",
      uptime_seconds: 1860,
      agents: [
        { agent_name: "scout", status: "running", last_run_at: "2026-07-08T08:15:00Z" },
        { agent_name: "triage", status: "idle", last_run_at: null },
        { agent_name: "tailor", status: "error", last_run_at: "2026-07-08T07:45:00Z" },
        { agent_name: "scheduler", status: "mystery", last_run_at: null },
      ],
    });
    fetchAgentEvents.mockResolvedValue({
      total: 2,
      items: [
        {
          id: "event-processing",
          event_type: "job_scored",
          source_agent: "triage",
          payload: "{}",
          status: "processing",
          created_at: "2026-07-08T08:20:00Z",
          processed_at: null,
          error_message: null,
        },
        {
          id: "event-failed",
          event_type: "scout_error",
          source_agent: "scout",
          payload: "{}",
          status: "failed",
          created_at: "2026-07-08T08:10:00Z",
          processed_at: "2026-07-08T08:11:00Z",
          error_message: "Rate limited",
        },
      ],
    });
    fetchPipelineStats.mockResolvedValue({
      discovered: 4,
      scored: 3,
      shortlisted: 2,
      tailored: 1,
      approved: 0,
      coach_sessions: 0,
    });
    triggerAgent.mockResolvedValue(undefined);
    fetchPendingApprovals.mockResolvedValue([]);
    approveApplication.mockResolvedValue(undefined);
    rejectApplication.mockResolvedValue(undefined);
  });

  it("surfaces agent operational state with fresh evidence", async () => {
    const { default: AgentDashboardPage } = await import("@/app/agents/page");

    render(<AgentDashboardPage />);

    expect(await screen.findByRole("heading", { name: "Agent Dashboard" })).toBeVisible();
    expect(screen.getByText(/Last updated/i)).toBeVisible();
    expect(screen.getByText(/Uptime: 31min/)).toBeVisible();
    expect(screen.getByText(/DB: healthy/)).toBeVisible();

    const cards = screen.getAllByTestId("agent-status-card");
    expect(within(cards[0]).getByText("Running")).toBeVisible();
    expect(within(cards[1]).getByText("Idle")).toBeVisible();
    expect(within(cards[1]).getByText("Never run")).toBeVisible();
    expect(within(cards[2]).getByText("Failed")).toBeVisible();
    expect(within(cards[3]).getByText("Unknown")).toBeVisible();

    expect(screen.getByText("Processing")).toBeVisible();
    expect(screen.getByText("Rate limited")).toBeVisible();
  });

  it("shows no-pending approval next actions", async () => {
    const { default: ApprovalsPage } = await import("@/app/approvals/page");

    render(<ApprovalsPage />);

    expect(await screen.findByRole("heading", { name: "Shortlist" })).toBeVisible();
    expect(screen.getByText("No pending approvals")).toBeVisible();
    expect(screen.getByRole("button", { name: "Run Scout" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Jobs" })).toHaveAttribute("href", "/jobs");
  });

  it("requires confirmation before rejecting an approval", async () => {
    fetchPendingApprovals.mockResolvedValue([
      {
        application_id: "app-1",
        job_id: "job-1",
        job_title: "Senior Engineer",
        company: "Acme",
        rate_text: "GBP 650/day",
        job_url: "https://example.com/job",
        overall_score: 0.91,
        skill_match: 0.9,
        experience_match: 0.88,
        rate_match: 0.8,
        location_match: 0.95,
        status: "pending",
        approval_status: "pending",
        created_at: "2026-07-08T08:00:00Z",
      },
    ]);
    const { default: ApprovalsPage } = await import("@/app/approvals/page");

    render(<ApprovalsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    expect(rejectApplication).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeVisible();
    expect(screen.getByText("Reject this application?")).toBeVisible();
    expect(screen.getByText(/This removes it from your pending shortlist/i)).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Keep pending" }));
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject application" }));

    await waitFor(() => {
      expect(rejectApplication).toHaveBeenCalledWith("app-1");
    });
  });
});
