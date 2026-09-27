import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ConversationalReportRead } from "@/lib/api";
import { ConversationalReport } from "../ConversationalReport";

const report: ConversationalReportRead = {
  session_id: "report-ui", report_state: "completed", activity_version: 3,
  retention_version: 1, session_level: "developing", compatibility_key: "key-ui",
  dimensions: {
    relevance: "strong", structure: "developing", specificity: "interview_ready",
    impact: "interview_ready", role_depth: "not_assessed", clarity: "strong",
    conciseness: "developing",
  },
  counts: {
    planned_questions_total: 2, planned_questions_answered: 2, planned_questions_skipped: 0,
    follow_ups_asked: 1, follow_ups_answered: 1, accepted_attempts: 3,
    retry_attempts: 1, unavailable_attempts: 0, hints_used: 2,
  },
  strengths: [{ dimension: "relevance", level: "strong", assessed_bundle_count: 2,
    contributor_attempt_ids: ["answer-1", "answer-2"] }],
  improvement_priorities: [{ dimension: "structure", level: "developing",
    assessed_bundle_count: 2, contributor_attempt_ids: ["answer-1", "answer-2"],
    next_action: "Practise a concise situation and your action." }],
  unassessed_areas: ["role_depth"],
  evidence_review_items: [{ attempt_id: "answer-1", claim_id: "claim-1",
    claim_text: '<img src=x onerror="window.reportXss=true">', transcript_start: 0,
    transcript_end: 47, status: "partially_supported", evidence_ids: ["evidence-1"],
    explanation: "The selected source supports the action, not the result.",
    candidate_action: "Check the result before reusing this answer." }],
  question_summaries: [{ question_id: "question-1", root_question_id: "question-1",
    question_kind: "planned", question_state: "answered", question_text: "Describe a delivery.",
    accepted_attempt_id: "answer-1", answer_level: "developing" }],
  practice_suggestions: [{ dimension: "structure",
    next_action: "Practise a concise situation and your action.",
    contributor_attempt_ids: ["answer-1", "answer-2"] }],
  candidate_reflection: { note: "I can describe my action more clearly." },
  retention_summary: { attempts: [{ attempt_id: "answer-1", audio_policy: null,
    audio_state: "not_applicable", transcript_state: "retained", audio_cleanup_retryable: false }] },
  diagnostics: {}, contract_version: "coach_conversational_report_v1",
};

describe("ConversationalReport", () => {
  it("renders populated analytical sections and all nine lifecycle counts", () => {
    render(<ConversationalReport report={report} />);
    for (const heading of ["Strengths", "Improvement priorities", "Question summaries",
      "Evidence review", "Practice suggestions", "Unassessed areas", "Interview counts"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeVisible();
    }
    expect(screen.getByText("Describe a delivery.")).toBeVisible();
    expect(screen.getAllByText("Practise a concise situation and your action.")).toHaveLength(2);
    for (const [name, value] of [
      ["Planned questions", "2"], ["Planned answered", "2"], ["Planned skipped", "0"],
      ["Follow-ups asked", "1"], ["Follow-ups answered", "1"], ["Accepted attempts", "3"],
      ["Retry attempts", "1"], ["Unavailable attempts", "0"], ["Hints used", "2"],
    ]) {
      const term = screen.getByText(name);
      expect(within(term.parentElement!).getByText(value)).toBeVisible();
    }
    const priorities = screen.getByRole("heading", { name: "Improvement priorities" }).parentElement!;
    expect(within(priorities).queryByText("Role depth")).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+%|\d+\/10/)).not.toBeInTheDocument();
  });

  it("renders evidence as untrusted text and labels source matching limits", () => {
    const { container } = render(<ConversationalReport report={report} />);
    expect(screen.getByText(report.evidence_review_items[0].claim_text)).toBeVisible();
    expect(container.querySelector("img, script")).toBeNull();
    expect(screen.getByText(/source matching, not independent verification/i)).toBeVisible();
    expect(screen.getByText("Check the result before reusing this answer.")).toBeVisible();
  });

  it("shows explicit empty sections without fabricating analytical items", () => {
    render(<ConversationalReport report={{ ...report, strengths: [], improvement_priorities: [],
      question_summaries: [], evidence_review_items: [], practice_suggestions: [] }} />);
    for (const text of ["No assessed strengths are available.", "No assessed priorities are available.",
      "No question summaries are available.", "No evidence findings are available.",
      "No practice suggestions are available."]) {
      expect(screen.getByText(text)).toBeVisible();
    }
  });
});
