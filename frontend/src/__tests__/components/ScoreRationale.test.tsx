import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ScoreRationale } from "@/components/ScoreRationale";
import type { Job } from "@/lib/api";

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    title: "Test Role",
    company: "Test Corp",
    location: "Remote",
    rate_text: null,
    rate_min: null,
    rate_max: null,
    currency: "USD",
    ir35_status: null,
    contract_length: null,
    description: null,
    url: "https://example.com/job",
    source: "test",
    posted_at: null,
    scraped_at: "2026-01-01T00:00:00Z",
    skills: null,
    is_active: true,
    sync_status: "pending",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    employment_type: null,
    working_pattern: null,
    match_score: null,
    match_reasons: null,
    skill_match: null,
    experience_match: null,
    rate_match: null,
    location_match: null,
    scoring_method: null,
    score_reasoning: null,
    keyword_matches: null,
    keyword_misses: null,
    fit_reasoning: null,
    score_strengths: null,
    score_gaps: null,
    ghost_score: null,
    ghost_verdict: null,
    ghost_signals: null,
    ghost_analysed_at: null,
    legal_fields: {},
    ...overrides,
  };
}

describe("ScoreRationale", () => {
  it("renders_score_and_method_badge — score 88% and AI assessment badge", () => {
    const job = makeJob({ match_score: 0.88, scoring_method: "llm" });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText("88%")).toBeInTheDocument();
    expect(screen.getByText("AI assessment")).toBeInTheDocument();
  });

  it("renders semantic scoring_method as AI assessment badge", () => {
    const job = makeJob({ match_score: 0.75, scoring_method: "semantic" });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText("AI assessment")).toBeInTheDocument();
  });

  it("renders local scoring_method as Quick estimate badge", () => {
    const job = makeJob({ match_score: 0.60, scoring_method: "local" });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText("Quick estimate")).toBeInTheDocument();
  });

  it("shows_rationale_when_present — fit_reasoning paragraph renders", () => {
    const job = makeJob({
      match_score: 0.88,
      scoring_method: "llm",
      fit_reasoning: "Strong fit because of extensive delivery background.",
    });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText("Strong fit because of extensive delivery background.")).toBeInTheDocument();
  });

  it("shows_strengths_and_gaps — score_strengths and score_gaps render as pills", () => {
    const job = makeJob({
      match_score: 0.80,
      scoring_method: "llm",
      fit_reasoning: "Good match.",
      score_strengths: ["PMP certified"],
      score_gaps: ["No cloud exp"],
    });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText("PMP certified")).toBeInTheDocument();
    expect(screen.getByText("No cloud exp")).toBeInTheDocument();
  });

  it("shows_upload_nudge_for_local_scoring — shows CV upload nudge when local and no fit_reasoning", () => {
    const job = makeJob({
      match_score: 0.55,
      scoring_method: "local",
      fit_reasoning: null,
    });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText(/Upload your CV for more accurate matching/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Go to profile/i })).toBeInTheDocument();
  });

  it("shows analysing placeholder when non-local and no fit_reasoning", () => {
    const job = makeJob({
      match_score: 0.75,
      scoring_method: "llm",
      fit_reasoning: null,
    });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText(/Analysing fit/i)).toBeInTheDocument();
  });

  it("does not show upload nudge when fit_reasoning is present", () => {
    const job = makeJob({
      match_score: 0.75,
      scoring_method: "local",
      fit_reasoning: "Good fit.",
    });
    render(<ScoreRationale job={job} />);
    expect(screen.queryByText(/Upload your CV/i)).not.toBeInTheDocument();
  });

  it("does not show strengths section when score_strengths is empty/null", () => {
    const job = makeJob({
      match_score: 0.75,
      scoring_method: "llm",
      fit_reasoning: "Great.",
      score_strengths: null,
    });
    render(<ScoreRationale job={job} />);
    expect(screen.queryByText(/Your strengths/i)).not.toBeInTheDocument();
  });

  it("renders the section heading", () => {
    const job = makeJob({ match_score: 0.80, scoring_method: "llm" });
    render(<ScoreRationale job={job} />);
    expect(screen.getByText("Match assessment")).toBeInTheDocument();
  });
});
