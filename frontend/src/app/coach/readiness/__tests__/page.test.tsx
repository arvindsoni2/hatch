import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReadinessPage from "@/app/coach/readiness/page";

const group = {
  role_family: "Delivery Lead",
  interview_type: "behavioural",
  contract_version: "coach_conversational_report_v1",
  session_count: 2,
  patterns: [
    {
      fingerprint: "a".repeat(64),
      group: {
        role_family: "Delivery Lead",
        interview_type: "behavioural",
        contract_version: "coach_conversational_report_v1",
      },
      dimension: "specificity",
      kind: "focus",
      trend: "declining",
      trend_label: null,
      supporting: [
        {
          session_id: "s1",
          completed_at: "2026-05-01T10:00:00Z",
          level: "developing",
          difficulty: "realistic",
          role_level: "senior",
        },
      ],
      stale: false,
      dismissed: false,
      seen_again: false,
    },
    {
      fingerprint: "b".repeat(64),
      group: {
        role_family: "Delivery Lead",
        interview_type: "behavioural",
        contract_version: "coach_conversational_report_v1",
      },
      dimension: "clarity",
      kind: "strength",
      trend: "stable",
      trend_label: null,
      supporting: [
        {
          session_id: "s2",
          completed_at: "2026-05-02T10:00:00Z",
          level: "strong",
          difficulty: "realistic",
          role_level: "senior",
        },
      ],
      stale: false,
      dismissed: true,
      seen_again: false,
    },
  ],
};

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("Readiness page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      if (String(input).includes("/api/coach/readiness/patterns")) {
        return response({ groups: [group], include_stale: true });
      }
      return response({});
    });
  });

  it("does not render a dismissed pattern after reload", async () => {
    render(<ReadinessPage />);

    expect(await screen.findByText("specificity")).toBeVisible();
    expect(screen.queryByText("clarity")).not.toBeInTheDocument();
  });
});
