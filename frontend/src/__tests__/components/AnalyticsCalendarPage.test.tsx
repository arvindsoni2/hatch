import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const serverApiFetch = vi.fn();
const getUpcomingInterviews = vi.fn();
const getOverdueFollowUps = vi.fn();
const completeFollowUp = vi.fn();

vi.mock("@/lib/server-api", () => ({
  serverApiFetch: (...args: unknown[]) => serverApiFetch(...args),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getUpcomingInterviews: (...args: unknown[]) => getUpcomingInterviews(...args),
    getOverdueFollowUps: (...args: unknown[]) => getOverdueFollowUps(...args),
    completeFollowUp: (...args: unknown[]) => completeFollowUp(...args),
  };
});

vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({ toString: () => "" }),
}));

function analyticsResponse(path: string) {
  if (path === "/api/analytics/dashboard") {
    return {
      stats: { active_count: 2, applied_count: 4, response_rate: 25 },
      funnel: { stages: [], total_tracked: 4 },
      trends: { weeks: [] },
      sources: [],
      avg_days_to_interview: null,
      avg_days_to_offer: null,
    };
  }
  if (path === "/api/analytics/ats-correlation") {
    return { buckets: [], total_scored: 0, message: "Score applications to compare ATS response rates." };
  }
  if (path.startsWith("/api/analytics/skill-frequency")) {
    return { skills: [], total_jobs_analyzed: 0, message: "Score more jobs to see skill demand." };
  }
  if (path.startsWith("/api/analytics/skill-gaps")) {
    return { skills: [], message: "No missing skills detected yet." };
  }
  if (path === "/api/analytics/score-distribution") {
    return { buckets: [], threshold: 0.7, total: 0 };
  }
  if (path === "/api/analytics/costs/monthly") {
    return { total: 0, currency: "GBP", by_agent: {}, budget: 5, budget_pct: 0 };
  }
  if (path.startsWith("/api/analytics/costs/daily")) {
    return { days: [] };
  }
  if (path === "/api/analytics/search-quality") {
    return {
      total_discovered: 0,
      passed_triage: 0,
      shortlisted: 0,
      triage_pass_rate: 0,
      shortlist_rate: 0,
      threshold: 0.7,
    };
  }
  if (path === "/api/agents/rate-limit-status") {
    return {
      rpm_used: 0,
      rpm_limit: 60,
      rpm_remaining: 60,
      rpd_used: 0,
      rpd_limit: 1000,
      rpd_remaining: 1000,
      wait_seconds: 0,
      throttled: false,
      last_429_at: null,
    };
  }
  if (path === "/api/analytics/agent-performance") {
    return { agents: [] };
  }
  if (path === "/api/outcome-learning/summary") {
    return {
      enabled: true,
      model_version: "test",
      confidence: "insufficient",
      resolved_applications: 0,
      effective_sample_size: 0,
      positive_responses: 0,
      global_response_rate: 0,
      minimum_required: 10,
      additional_required: 10,
      learning_since: null,
      top_positive_signals: [],
      top_negative_signals: [],
      variant_recommendations: [],
      variant_performance: {},
      last_recomputed_at: null,
    };
  }
  throw new Error(`Unhandled analytics path ${path}`);
}

describe("Analytics and Calendar route states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    serverApiFetch.mockImplementation((path: string) => Promise.resolve(analyticsResponse(path)));
    getUpcomingInterviews.mockResolvedValue([]);
    getOverdueFollowUps.mockResolvedValue([]);
    completeFollowUp.mockResolvedValue(undefined);
  });

  it("groups Analytics into Outcomes, Match Quality, AI Usage, and Reliability", async () => {
    const { default: AnalyticsPage } = await import("@/app/analytics/page");

    render(await AnalyticsPage());

    expect(screen.getByRole("heading", { name: "Analytics" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Outcomes" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Match Quality" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "AI Usage" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Reliability" })).toBeVisible();
  });

  it("shows Calendar empty actions for adding interview data or opening Applications", async () => {
    const { default: CalendarPage } = await import("@/app/calendar/page");

    render(<CalendarPage />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Calendar" })).toBeVisible();
    });
    expect(screen.getByText("No interviews or follow-ups scheduled")).toBeVisible();
    const applicationLinks = screen.getAllByRole("link", { name: "Open Applications" });
    expect(applicationLinks.some((link) => link.getAttribute("href") === "/tracker")).toBe(true);
  });
});
