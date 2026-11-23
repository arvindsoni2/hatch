import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InterviewBrief } from "@/components/coach/readiness/InterviewBrief";

const brief = {
  round_id: "round-1",
  state: "active",
  header: {
    company: "Northwind", role: "Delivery Lead", round_type: "behavioural",
    starts_at: "2026-12-20T10:00:00", display_timezone: "Europe/London",
    duration_minutes: 60, interviewer: "Priya", location: "Video call",
  },
  likely_questions: [{ id: "q1", text: "Tell me about a delivery.", source: "question_bank" }],
  stories: [],
  watch_outs: [],
  gaps: [],
  ask_them: ["What does success look like?"],
  enhancement: { state: "none", fingerprint: "a".repeat(64), operation_id: null, model_identity: null },
};

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("InterviewBrief", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/brief")) return response(brief);
      if (url.includes("/display-timezone")) return response({ display_timezone: "Europe/London" });
      return response({});
    });
  });

  it("renders all sections and the display timezone", async () => {
    render(<InterviewBrief roundId="round-1" />);

    expect(await screen.findByText(/behavioural interview with Northwind/i)).toBeVisible();
    expect(screen.getByText("Likely questions")).toBeVisible();
    expect(screen.getByText("Your best stories")).toBeVisible();
    expect(screen.getByText("Watch-outs")).toBeVisible();
    expect(screen.getByText("Gaps")).toBeVisible();
    expect(screen.getByText("Questions to ask them")).toBeVisible();
    expect(screen.getByText("Logistics")).toBeVisible();
    expect(screen.getAllByText(/2026/).length).toBeGreaterThan(0);
  });

  it("test_brief_times_in_display_timezone", async () => {
    render(<InterviewBrief roundId="round-1" />);
    expect((await screen.findAllByText(/20 Dec 2026/)).length).toBeGreaterThan(0);
  });
});
