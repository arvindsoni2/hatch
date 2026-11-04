import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchDebrief,
  saveDebrief,
  skipDebrief,
  type DebriefRead,
} from "@/lib/coachReadinessApi";
import { DebriefForm } from "../DebriefForm";

vi.mock("@/lib/coachReadinessApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/coachReadinessApi")>();
  return {
    ...actual,
    fetchDebrief: vi.fn(),
    saveDebrief: vi.fn(),
    skipDebrief: vi.fn(),
  };
});

const due: DebriefRead = {
  round_id: "round-1",
  application_id: "app-1",
  round_status: "completed",
  scheduled_at: "2026-11-10T10:00:00Z",
  duration_minutes: 60,
  status: "due",
  version: 0,
  overall: null,
  expectation: null,
  questions: [
    {
      id: "q1",
      text: "Tell me about a budget you owned.",
      source_ref: null,
      asked: false,
      rating: null,
      story_id: null,
      note: null,
    },
    {
      id: "q2",
      text: "Why this company?",
      source_ref: null,
      asked: false,
      rating: null,
      story_id: null,
      note: null,
    },
  ],
  went_well: null,
  do_differently: null,
  notes_text: null,
};

describe("DebriefForm", () => {
  beforeEach(() => {
    vi.mocked(fetchDebrief).mockResolvedValue(due);
    vi.mocked(saveDebrief).mockResolvedValue({ ...due, status: "saved", version: 1, overall: 4 });
    vi.mocked(skipDebrief).mockResolvedValue({ ...due, status: "skipped", version: 1 });
  });

  it("shows the question checklist first and saves with only an overall rating", async () => {
    const user = userEvent.setup();
    render(<DebriefForm roundId="round-1" />);

    expect(await screen.findByText("Tell me about a budget you owned.")).toBeVisible();
    expect(screen.getByText("Why this company?")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "4 Good" }));
    await user.click(screen.getByRole("button", { name: "Save debrief" }));

    expect(saveDebrief).toHaveBeenCalledWith(
      "round-1",
      expect.objectContaining({ expected_version: 0, overall: 4 }),
    );
  });

  it("keeps the draft and shows a message on 409", async () => {
    vi.mocked(saveDebrief).mockRejectedValue(
      Object.assign(new Error("version_conflict"), { status: 409 }),
    );
    const user = userEvent.setup();
    render(<DebriefForm roundId="round-1" />);

    const wentWell = await screen.findByLabelText("What went well");
    await user.type(wentWell, "Clear opening");
    await user.click(screen.getByRole("button", { name: "4 Good" }));
    await user.click(screen.getByRole("button", { name: "Save debrief" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Reload and re-apply");
    });
    expect(wentWell).toHaveValue("Clear opening");
  });

  it("labels the quick-add and free-text inputs", async () => {
    render(<DebriefForm roundId="round-1" />);

    expect(await screen.findByLabelText("Another question")).toBeVisible();
    expect(screen.getByLabelText("What went well")).toBeVisible();
    expect(screen.getByLabelText("What you would do differently")).toBeVisible();
  });

  it("shows per-question controls and the exact debrief copy", async () => {
    const user = userEvent.setup();
    render(<DebriefForm roundId="round-1" />);

    await user.click(await screen.findByRole("checkbox", { name: /Tell me about a budget/ }));
    expect(screen.getAllByText("How did it go?").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Story you used")).toBeVisible();
    expect(screen.getByLabelText("Note")).toHaveAttribute(
      "placeholder",
      "One line, optional",
    );
    expect(screen.getByText("Overall, how did it go?")).toBeVisible();
    expect(screen.getByText("Do you expect to move to the next round?")).toBeVisible();

    const another = screen.getByLabelText("Another question");
    expect(another).toHaveAttribute("placeholder", "Type a question you were asked");
    await user.type(another, "What would you change?");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("Added by you")).toBeVisible();
  });

  it("reloads on 409, keeps the draft and saves with the new version", async () => {
    vi.mocked(fetchDebrief)
      .mockResolvedValueOnce(due)
      .mockResolvedValueOnce({ ...due, version: 1 });
    vi.mocked(saveDebrief)
      .mockRejectedValueOnce(
        Object.assign(new Error("version_conflict"), { status: 409 }),
      )
      .mockResolvedValueOnce({ ...due, version: 2, status: "saved", overall: 4 });
    const user = userEvent.setup();
    render(<DebriefForm roundId="round-1" />);

    const wentWell = await screen.findByLabelText("What went well");
    await user.type(wentWell, "Kept the draft");
    await user.click(screen.getByRole("button", { name: "4 Good" }));
    await user.click(screen.getByRole("button", { name: "Save debrief" }));
    await screen.findByRole("button", { name: "Reload and re-apply" });
    await user.click(screen.getByRole("button", { name: "Reload and re-apply" }));
    await user.click(screen.getByRole("button", { name: "Save debrief" }));

    expect(wentWell).toHaveValue("Kept the draft");
    expect(saveDebrief).toHaveBeenLastCalledWith(
      "round-1",
      expect.objectContaining({ expected_version: 1, overall: 4 }),
    );
  });
});
