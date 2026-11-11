import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FocusAreas } from "@/components/coach/readiness/FocusAreas";
import type { FocusArea } from "@/lib/coachReadinessApi";

const area: FocusArea = {
  id: "focus-1",
  version: 1,
  status: "active",
  active_slot: 1,
  title: "Make answers specific",
  dimension: "specificity",
  group: {
    role_family: "Delivery Lead",
    interview_type: "behavioural",
    contract_version: "coach_conversational_report_v1",
  },
  application_id: null,
  criteria: [
    {
      kind: "practice", label: "Finish 3 plan items", status: "in_progress",
      completed: 1, target: 3,
    },
  ],
  every_criterion_met: false,
  created_at: "2026-05-01T10:00:00Z",
};

describe("FocusAreas", () => {
  it("shows N of 3 in use and a labelled progress bar", () => {
    render(<FocusAreas areas={[area]} activeCount={1} onAdd={vi.fn()} onMarkAchieved={vi.fn()} />);

    expect(screen.getByText("1 of 3 in use")).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "Finish 3 plan items" })).toHaveAttribute(
      "aria-valuenow", "1",
    );
    expect(screen.getByText("1 of 3")).toBeVisible();
  });

  it("offers Mark achieved only when every criterion is met", async () => {
    const user = userEvent.setup();
    const onMarkAchieved = vi.fn();
    const met = {
      ...area,
      every_criterion_met: true,
      criteria: [{ ...area.criteria[0], status: "met" as const, completed: 3 }],
    };
    render(<FocusAreas areas={[met]} activeCount={1} onAdd={vi.fn()} onMarkAchieved={onMarkAchieved} />);

    expect(screen.getByText("Every criterion is met.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Mark achieved" }));
    expect(onMarkAchieved).toHaveBeenCalledWith(met);
  });
});
