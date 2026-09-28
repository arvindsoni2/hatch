import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ConversationalProgressGroup, ConversationalProgressRead } from "@/lib/api";
import { ConversationalProgress } from "../ConversationalProgress";

const levels = { relevance: "developing", structure: "strong", specificity: "not_assessed",
  impact: "not_assessed", role_depth: "not_assessed", clarity: "not_assessed",
  conciseness: "not_assessed" } as const;
const group = (key: string, trend: "mixed" | "declining"): ConversationalProgressGroup => ({
  compatibility_key: key,
  context: { application_id: "app-ui", company_name: "Synthetic", role_title: "Engineer",
    role_family: "software_engineering", role_level: "senior", interview_type: "behavioural" },
  sessions: [{ session_id: `${key}-session`, activity_version: 1,
    completed_at: "2026-01-01T10:00:00", session_level: "developing", dimensions: levels }],
  current_levels: levels, previous_levels: { ...levels, relevance: "strong" },
  trends: { relevance: trend, structure: "improving", specificity: "not_enough_evidence",
    impact: "not_enough_evidence", role_depth: "not_enough_evidence",
    clarity: "not_enough_evidence", conciseness: "not_enough_evidence" },
  strongest_areas: [{ dimension: "structure", level: "strong", assessed_bundle_count: 2,
    contributor_attempt_ids: ["answer-1"] }],
  priority_areas: [{ dimension: "relevance", level: "developing", assessed_bundle_count: 2,
    contributor_attempt_ids: ["answer-1"], next_action: "Connect the example to the question." }],
  evidence_review_items: [],
});
const progress: ConversationalProgressRead = {
  selector_mode: "filtered", applied_filters: { application_id: "app-ui" }, group_limit: 20,
  total_groups: 2, returned_groups: 2, groups_truncated: false,
  groups: [group("key-a", "mixed"), group("key-b", "declining")],
  contract_version: "coach_conversational_progress_v2",
};

describe("ConversationalProgress", () => {
  it("renders separate dimension comparisons and source areas for each exact group", () => {
    render(<ConversationalProgress progress={progress} />);
    const tables = screen.getAllByRole("table");
    expect(tables).toHaveLength(2);
    expect(within(tables[0]).getByText("Mixed")).toBeVisible();
    expect(within(tables[0]).queryByText("Declining")).not.toBeInTheDocument();
    expect(within(tables[1]).getByText("Declining")).toBeVisible();
    for (const table of tables) {
      for (const column of ["Dimension", "Previous", "Current", "Trend"]) {
        expect(within(table).getByRole("columnheader", { name: column })).toBeVisible();
      }
      expect(within(table).getAllByText("Not enough evidence")).toHaveLength(5);
    }
    expect(screen.getAllByText("Connect the example to the question.")).toHaveLength(2);
    expect(screen.queryByText(/\d+%|overall trend/i)).not.toBeInTheDocument();
  });

  it("keeps empty progress and pre-truncation totals explicit", () => {
    const view = render(<ConversationalProgress progress={{ ...progress, groups: [],
      total_groups: 0, returned_groups: 0 }} />);
    expect(screen.getByText(/no compatible completed interviews/i)).toBeVisible();
    view.rerender(<ConversationalProgress progress={{ ...progress,
      total_groups: 3, groups_truncated: true }} />);
    expect(screen.getByText("Showing the first 2 of 3 groups.")).toBeVisible();
  });
});
