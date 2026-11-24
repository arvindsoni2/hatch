import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  extractDebriefNotes,
  saveDebrief,
  type DebriefRead,
} from "@/lib/coachReadinessApi";
import { DebriefNotesExtract } from "@/components/coach/readiness/DebriefNotesExtract";

vi.mock("@/lib/coachReadinessApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/coachReadinessApi")>();
  return {
    ...actual,
    extractDebriefNotes: vi.fn(),
    saveDebrief: vi.fn(),
  };
});

const draft: DebriefRead = {
  round_id: "round-1",
  application_id: "app-1",
  round_status: "completed",
  scheduled_at: null,
  duration_minutes: 60,
  status: "draft",
  version: 1,
  overall: null,
  expectation: null,
  questions: [],
  went_well: null,
  do_differently: null,
  notes_text: null,
  questions_added: 0,
};

describe("DebriefNotesExtract", () => {
  beforeEach(() => {
    vi.mocked(saveDebrief).mockResolvedValue({ ...draft });
    vi.mocked(extractDebriefNotes).mockResolvedValue({
      questions: ["How did you manage the budget?", "How did you handle sign-off?"],
    });
  });

  it("saves the notes as a draft before extraction can run", async () => {
    const user = userEvent.setup();
    const onDraftSaved = vi.fn();
    render(
      <DebriefNotesExtract
        roundId="round-1"
        version={0}
        savedNotes={null}
        onDraftSaved={onDraftSaved}
        onQuestionsProposed={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("Paste rough notes"), "Asked about budgets.");
    await user.click(screen.getByRole("button", { name: "Save notes" }));

    await waitFor(() => expect(onDraftSaved).toHaveBeenCalledWith(1, "Asked about budgets."));
    expect(vi.mocked(saveDebrief)).toHaveBeenCalledWith("round-1", {
      expected_version: 0,
      overall: null,
      notes_text: "Asked about budgets.",
    });
  });

  it("saves changed notes before extracting them", async () => {
    const user = userEvent.setup();
    const onDraftSaved = vi.fn();
    render(
      <DebriefNotesExtract
        roundId="round-1"
        version={0}
        savedNotes={null}
        onDraftSaved={onDraftSaved}
        onQuestionsProposed={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("Paste rough notes"), "Asked about budgets.");
    await user.click(screen.getByRole("button", { name: "Extract questions" }));

    expect(await screen.findByText("Proposed from your notes")).toBeVisible();
    expect(vi.mocked(saveDebrief)).toHaveBeenCalledWith("round-1", {
      expected_version: 0,
      overall: null,
      notes_text: "Asked about budgets.",
    });
    expect(vi.mocked(extractDebriefNotes)).toHaveBeenCalledWith("round-1");
    expect(onDraftSaved).toHaveBeenCalledWith(1, "Asked about budgets.");
    // The draft save runs before the extraction reads the notes.
    const saveOrder = vi.mocked(saveDebrief).mock.invocationCallOrder[0];
    const extractOrder = vi.mocked(extractDebriefNotes).mock.invocationCallOrder[0];
    expect(saveOrder).toBeLessThan(extractOrder);
  });

  it("extracts a proposal the candidate confirms into the checklist", async () => {
    const user = userEvent.setup();
    const onQuestionsProposed = vi.fn();
    render(
      <DebriefNotesExtract
        roundId="round-1"
        version={1}
        savedNotes="Asked about budgets."
        onDraftSaved={vi.fn()}
        onQuestionsProposed={onQuestionsProposed}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Extract questions" }));

    expect(await screen.findByText("Proposed from your notes")).toBeVisible();
    expect(screen.getByText("How did you manage the budget?")).toBeVisible();

    await user.click(screen.getByRole("button", { name: /Add 2 to the checklist/ }));

    expect(onQuestionsProposed).toHaveBeenCalledWith([
      "How did you manage the budget?",
      "How did you handle sign-off?",
    ]);
  });

  it("keeps the proposal unselected when the candidate unticks a question", async () => {
    const user = userEvent.setup();
    const onQuestionsProposed = vi.fn();
    render(
      <DebriefNotesExtract
        roundId="round-1"
        version={1}
        savedNotes="Asked about budgets."
        onDraftSaved={vi.fn()}
        onQuestionsProposed={onQuestionsProposed}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Extract questions" }));
    await user.click(await screen.findByText("How did you manage the budget?"));
    await user.click(screen.getByRole("button", { name: /Add 1 to the checklist/ }));

    expect(onQuestionsProposed).toHaveBeenCalledWith(["How did you handle sign-off?"]);
  });
});
