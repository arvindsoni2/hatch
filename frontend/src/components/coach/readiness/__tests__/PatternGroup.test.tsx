import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PatternGroup } from "@/components/coach/readiness/PatternGroup";

describe("PatternGroup", () => {
  it("shows the cold-start strip instead of a forming card for one session", () => {
    render(
      <PatternGroup
        group={{
          role_family: "Delivery Lead",
          interview_type: "behavioural",
          contract_version: "coach_conversational_report_v1",
          session_count: 1,
          patterns: [
            {
              fingerprint: "a".repeat(64),
              group: {
                role_family: "Delivery Lead",
                interview_type: "behavioural",
                contract_version: "coach_conversational_report_v1",
              },
              dimension: "specificity",
              kind: "forming",
              trend: "not_enough_evidence",
              trend_label: null,
              supporting: [],
              stale: false,
              dismissed: false,
              seen_again: false,
            },
          ],
        }}
      />,
    );

    expect(
      screen.getByText("Patterns appear after your second session here."),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Practise this role" })).toBeVisible();
    expect(screen.queryByText("Needs more practice")).not.toBeInTheDocument();
  });
});
