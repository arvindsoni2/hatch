import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PracticePlan } from "@/components/coach/readiness/PracticePlan";

const plan = {
  id: "plan-1",
  version: 2,
  status: "active",
  minutes: 30,
  target_round_id: null,
  items: [
    {
      id: "item-1",
      type: "practice_session",
      title: "Practise a behavioural session — Delivery Lead",
      minutes: 15,
      status: "done",
      group: null,
      focus_area_ids: ["focus-1"],
      due_at: null,
      auto: true,
      completed_at: "2026-05-01T10:00:00Z",
    },
    {
      id: "item-2",
      type: "review_answer",
      title: "Re-read your answer to Tell me about a delivery",
      minutes: 5,
      status: "todo",
      group: null,
      focus_area_ids: [],
      due_at: null,
      auto: false,
      completed_at: null,
    },
  ],
  unallocated_minutes: 10,
  done_count: 1,
  total_count: 2,
  started_at: "2026-05-01T09:00:00Z",
  completed_at: null,
};

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("PracticePlan", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/coach/readiness/plans")) {
        return response({ active: plan, draft: null });
      }
      if (url.includes("/api/interviews/upcoming")) return response([]);
      if (url.includes("/items/item-2") && init?.method === "PATCH") {
        return response({ ...plan, done_count: 2, items: [
          plan.items[0], { ...plan.items[1], status: "done" },
        ] });
      }
      return response({});
    });
  });

  it("shows minutes, the done badge and auto-ticked copy", async () => {
    render(<PracticePlan />);

    expect(await screen.findByText("1 of 2 done")).toBeVisible();
    expect(screen.getByText("15 min")).toHaveClass("font-mono");
    expect(screen.getByText(/Ticked automatically when you finished a session/)).toBeVisible();
    expect(screen.getByText("10 minutes unallocated.")).toBeVisible();
  });

  it("ticks a manual item from the keyboard", async () => {
    const user = userEvent.setup();
    render(<PracticePlan />);

    const checkbox = await screen.findByRole("checkbox", {
      name: /Mark Re-read your answer to Tell me about a delivery done/,
    });
    checkbox.focus();
    await user.keyboard("[Space]");

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/items/item-2"),
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ action: "done" }) }),
      );
    });
  });
});
