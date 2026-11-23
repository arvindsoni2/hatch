import { act, render, screen } from "@testing-library/react";
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

  it("renders current talking points and watch-out sentences", async () => {
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/brief")) {
        return response({
          ...brief,
          stories: [{
            story_id: "s1", title: "Rescued a delivery", competencies: ["delivery"],
            score: 1, has_metric: true, talking_point: "Lead with the deadline.",
          }],
          watch_outs: [{
            fingerprint: "f".repeat(64), dimension: "specificity",
            source: "practice", sentence: "Name the decision you made.",
          }],
          enhancement: { ...brief.enhancement, state: "current" },
        });
      }
      if (url.includes("/display-timezone")) return response({ display_timezone: "Europe/London" });
      return response({});
    });

    render(<InterviewBrief roundId="round-1" />);

    expect(await screen.findByText("Lead with the deadline.")).toBeVisible();
    expect(screen.getByText(/Name the decision you made\./)).toBeVisible();
  });

  it("polls while tips are enhancing and stops when current", async () => {
    vi.useFakeTimers();
    try {
      const enhancing = { ...brief, enhancement: { ...brief.enhancement, state: "enhancing" } };
      const current = { ...brief, enhancement: { ...brief.enhancement, state: "current" } };
      const briefs = [enhancing, current];
      let briefCalls = 0;
      vi.mocked(global.fetch).mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/display-timezone")) return response({ display_timezone: "Europe/London" });
        if (url.includes("/brief")) return response(briefs[Math.min(briefCalls++, briefs.length - 1)]);
        return response({});
      });

      render(<InterviewBrief roundId="round-1" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(briefCalls).toBe(1);

      await act(async () => { await vi.advanceTimersByTimeAsync(2_000); });
      expect(briefCalls).toBe(2);

      await act(async () => { await vi.advanceTimersByTimeAsync(4_000); });
      expect(briefCalls).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows an Archived badge and no Try again when archived", async () => {
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/display-timezone")) return response({ display_timezone: "Europe/London" });
      if (url.includes("/brief")) {
        return response({ ...brief, state: "archived", enhancement: { ...brief.enhancement, state: "unavailable" } });
      }
      return response({});
    });

    render(<InterviewBrief roundId="round-1" />);

    expect(await screen.findByText("Archived")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("announces tips in a polite live region with skeletons while enhancing", async () => {
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/display-timezone")) return response({ display_timezone: "Europe/London" });
      if (url.includes("/brief")) {
        return response({
          ...brief,
          stories: [{
            story_id: "s1", title: "Rescued a delivery", competencies: ["delivery"],
            score: 1, has_metric: true, talking_point: null,
          }],
          watch_outs: [{
            fingerprint: "f".repeat(64), dimension: "specificity",
            source: "practice", sentence: null,
          }],
          enhancement: { ...brief.enhancement, state: "enhancing" },
        });
      }
      return response({});
    });

    render(<InterviewBrief roundId="round-1" />);

    expect(await screen.findByText("Adding tips")).toBeVisible();
    const skeletons = screen.getAllByTestId("tips-skeleton");
    expect(skeletons.length).toBeGreaterThan(0);
    for (const skeleton of skeletons) {
      expect(skeleton.closest('[aria-live="polite"]')).not.toBeNull();
    }
  });

  it("test_brief_times_in_display_timezone", async () => {
    render(<InterviewBrief roundId="round-1" />);
    expect((await screen.findAllByText(/20 Dec 2026/)).length).toBeGreaterThan(0);
  });
});
