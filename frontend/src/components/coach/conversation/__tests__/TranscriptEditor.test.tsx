import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TranscriptEditor } from "../TranscriptEditor";

const attempt = {
  id: "attempt-2",
  attempt_number: 2,
  transcript_version: {
    id: "transcript-2",
    version_number: 1,
    transcript: "The original transcript.",
    source: "transcription",
    edit_reason: null,
    created_by: "system",
    processing_generation: 1,
    created_at: "2026-08-12T08:00:00Z",
  },
} as const;

describe("TranscriptEditor", () => {
  it("explains immutable delivery observations before sending a correction", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    render(
      <TranscriptEditor
        attempt={attempt}
        allowedCommands={["edit_transcript"]}
        pending={false}
        onCommand={onCommand}
      />,
    );

    expect(screen.getByText("Editing corrects transcription and re-runs answer and evidence review.")).toBeVisible();
    expect(screen.getByText("Delivery observations remain based on the original audio.")).toBeVisible();
    const editor = screen.getByLabelText("Corrected transcript");
    await user.clear(editor);
    await user.type(editor, "The corrected transcript.");
    await user.click(screen.getByRole("button", { name: "Re-run review with corrected transcript" }));
    expect(onCommand).toHaveBeenCalledWith("edit_transcript", {
      attempt_id: "attempt-2",
      transcript: "The corrected transcript.",
      edit_reason: "transcription_error",
    });
  });

  it("shows edit provenance but no editor when the server does not allow editing", () => {
    render(
      <TranscriptEditor
        attempt={{
          ...attempt,
          transcript_version: {
            ...attempt.transcript_version,
            version_number: 2,
            source: "candidate_edit",
            edit_reason: "transcription_error",
            created_by: "candidate",
          },
        }}
        allowedCommands={[]}
        pending={false}
        onCommand={vi.fn()}
      />,
    );

    expect(screen.getByText("Candidate correction, version 2")).toBeVisible();
    expect(screen.queryByLabelText("Corrected transcript")).not.toBeInTheDocument();
  });

  it("does not submit an empty canonical correction", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    render(
      <TranscriptEditor
        attempt={attempt}
        allowedCommands={["edit_transcript"]}
        pending={false}
        onCommand={onCommand}
      />,
    );

    const editor = screen.getByLabelText("Corrected transcript");
    await user.clear(editor);
    await user.type(editor, "   ");
    expect(screen.getByRole("button", { name: "Re-run review with corrected transcript" })).toBeDisabled();
    expect(onCommand).not.toHaveBeenCalled();
  });
});
