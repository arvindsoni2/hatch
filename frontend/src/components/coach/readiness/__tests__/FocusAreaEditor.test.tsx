import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FocusAreaEditor } from "@/components/coach/readiness/FocusAreaEditor";
import type { FocusArea } from "@/lib/coachReadinessApi";

const area: FocusArea = {
  id: "focus-1",
  version: 2,
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
  criteria: [],
  every_criterion_met: false,
  created_at: "2026-05-01T10:00:00Z",
};

function response(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

describe("FocusAreaEditor", () => {
  it("keeps the draft and offers reload on a version conflict", async () => {
    const user = userEvent.setup();
    vi.mocked(global.fetch).mockImplementation(async () => response({ detail: "version_conflict" }, 409));
    render(
      <FocusAreaEditor open area={area} onClose={vi.fn()} onSaved={vi.fn()} />,
    );

    const title = screen.getByLabelText("Title");
    await user.clear(title);
    await user.type(title, "My kept draft");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(/Reload and re-apply/),
    ).toBeVisible();
    expect(title).toHaveValue("My kept draft");
  });

  it("creates a focus area with the selected criteria", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    vi.mocked(global.fetch).mockImplementation(async () => response(area, 201));
    render(<FocusAreaEditor open onClose={vi.fn()} onSaved={onSaved} />);

    await user.type(screen.getByLabelText("Title"), "Make answers specific");
    await user.click(screen.getByRole("button", { name: "Add focus area" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/coach/readiness/focus-areas"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});
