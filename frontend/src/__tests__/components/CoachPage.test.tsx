import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";

const session: api.SessionListItem = {
  id: "progress-interview", company_name: "Synthetic", role_title: "Engineer",
  status: "completed", overall_score: null, created_at: "2026-01-01T10:00:00",
  experience_version: "conversational_v1", conversation_state: "completed",
  session_level: "not_assessed", retention_summary: null,
};
const report: api.ConversationalReportRead = {
  session_id: session.id, compatibility_key: "key-selected", report_state: "completed",
  activity_version: 1, retention_version: 0, session_level: "not_assessed",
  dimensions: { relevance: "not_assessed", structure: "not_assessed", specificity: "not_assessed",
    impact: "not_assessed", role_depth: "not_assessed", clarity: "not_assessed", conciseness: "not_assessed" },
  counts: { planned_questions_total: 0, planned_questions_answered: 0, planned_questions_skipped: 0,
    follow_ups_asked: 0, follow_ups_answered: 0, accepted_attempts: 0,
    retry_attempts: 0, unavailable_attempts: 0, hints_used: 0 },
  strengths: [], improvement_priorities: [], unassessed_areas: ["relevance", "structure", "specificity",
    "impact", "role_depth", "clarity", "conciseness"], evidence_review_items: [],
  question_summaries: [], practice_suggestions: [], candidate_reflection: null,
  retention_summary: { attempts: [] }, diagnostics: {}, contract_version: "coach_conversational_report_v1",
};
const emptyProgress: api.ConversationalProgressRead = {
  selector_mode: "exact", applied_filters: { compatibility_key: "key-selected" },
  group_limit: 20, total_groups: 0, returned_groups: 0, groups_truncated: false, groups: [],
  contract_version: "coach_conversational_progress_v2",
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listSessions: vi.fn().mockResolvedValue([]),
    getCoachCapabilities: vi.fn(),
    getSession: vi.fn(),
    getConversationalReport: vi.fn(),
    getConversationalProgress: vi.fn(),
  };
});

describe("CoachPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listSessions).mockResolvedValue([]);
    vi.mocked(api.getCoachCapabilities).mockResolvedValue({ face_analysis: false, tts: false,
      conversational_interview: true });
    vi.mocked(api.getSession).mockResolvedValue({ ...session, application_id: "selected-app", questions: [] });
    vi.mocked(api.getConversationalReport).mockResolvedValue(report);
    vi.mocked(api.getConversationalProgress).mockResolvedValue(emptyProgress);
  });

  it("explains live practice as distinct from the Interview Prep library", async () => {
    const { default: CoachPage } = await import("@/app/coach/page");

    render(<CoachPage />);

    expect(await screen.findByRole("heading", { name: "Interview Coach" })).toBeVisible();
    expect(screen.getAllByText(/live mock interviews/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /review prep materials/i })).toHaveAttribute("href", "/prep");
  });

  it("requires an eligible context rather than issuing an unfiltered progress request", async () => {
    const { default: CoachPage } = await import("@/app/coach/page");
    render(<CoachPage />);
    expect(await screen.findByText(/complete a conversational interview to select a progress context/i)).toBeVisible();
    expect(api.getConversationalProgress).not.toHaveBeenCalled();
  });

  it("selects an exact report key, then a legal application filter without combining them", async () => {
    vi.mocked(api.listSessions).mockResolvedValue([session]);
    const user = userEvent.setup();
    const { default: CoachPage } = await import("@/app/coach/page");
    render(<CoachPage />);
    await user.selectOptions(await screen.findByRole("combobox", { name: "Progress interview" }), session.id);
    expect(await screen.findByText(/no compatible completed interviews/i)).toBeVisible();
    expect(api.getConversationalProgress).toHaveBeenLastCalledWith({ compatibility_key: "key-selected" });
    await user.selectOptions(screen.getByRole("combobox", { name: "Compare interviews" }), "application");
    expect(await screen.findByText(/no compatible completed interviews/i)).toBeVisible();
    expect(api.getConversationalProgress).toHaveBeenLastCalledWith({ application_id: "selected-app" });
  });

  it("keeps progress failure independent and retries without showing private errors", async () => {
    vi.mocked(api.listSessions).mockResolvedValue([session]);
    vi.mocked(api.getConversationalProgress).mockRejectedValueOnce(new Error("private-error-canary"));
    const user = userEvent.setup();
    const { default: CoachPage } = await import("@/app/coach/page");
    render(<CoachPage />);
    await user.selectOptions(await screen.findByRole("combobox", { name: "Progress interview" }), session.id);
    expect(await screen.findByRole("alert")).toHaveTextContent("Progress could not be loaded.");
    expect(screen.queryByText("private-error-canary")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /synthetic/i })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry progress" }));
    expect(await screen.findByText(/no compatible completed interviews/i)).toBeVisible();
  });

  it("preserves legacy numeric history but never renders a numeric conversational score", async () => {
    vi.mocked(api.listSessions).mockResolvedValue([
      { ...session, overall_score: 9.1 },
      { ...session, id: "legacy-session", experience_version: "legacy_v1", overall_score: 8.2 },
    ]);
    const { default: CoachPage } = await import("@/app/coach/page");
    render(<CoachPage />);
    expect(await screen.findByText("8.2/10")).toBeVisible();
    expect(screen.queryByText("9.1/10")).not.toBeInTheDocument();
  });
});
