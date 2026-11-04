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

    const wentWell = await screen.findByLabelText("Went well");
    await user.type(wentWell, "Clear opening");
    await user.click(screen.getByRole("button", { name: "4 Good" }));
    await user.click(screen.getByRole("button", { name: "Save debrief" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Your draft is kept");
    });
    expect(wentWell).toHaveValue("Clear opening");
  });

  it("labels the quick-add and free-text inputs", async () => {
    render(<DebriefForm roundId="round-1" />);

    expect(await screen.findByLabelText("Quick-add question")).toBeVisible();
    expect(screen.getByLabelText("Went well")).toBeVisible();
    expect(screen.getByLabelText("Do differently")).toBeVisible();
  });
});
