import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AttemptHistory } from "../AttemptHistory";

const attempts = [
  {
    attempt_id: "attempt-1",
    attempt_number: 1,
    answer_level: "developing",
    accepted: false,
    transcript_available: true,
    audio_state: "deleted",
  },
  {
    attempt_id: "attempt-2",
    attempt_number: 2,
    answer_level: "interview_ready",
    accepted: true,
    transcript_available: true,
    audio_state: "retained",
  },
] as const;

describe("AttemptHistory", () => {
  it("renders named comparisons and explicit accepted state", () => {
    render(<AttemptHistory attempts={attempts} allowedCommands={[]} pending={false} onCommand={vi.fn()} />);

    expect(screen.getByText("Attempt 1 - Developing - not accepted")).toBeVisible();
    expect(screen.getByText("Attempt 2 - Interview-ready - accepted")).toBeVisible();
    expect(screen.getByText("Audio deleted")).toBeVisible();
    expect(screen.getByText("Audio retained")).toBeVisible();
    expect(screen.queryByText(/\/10|\d+%/)).not.toBeInTheDocument();
  });

  it("accepts a specific attempt only when the server advertises the action", async () => {
    const user = userEvent.setup();
    const onCommand = vi.fn();
    render(
      <AttemptHistory
        attempts={attempts}
        allowedCommands={["accept_attempt"]}
        pending={false}
        onCommand={onCommand}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Accept attempt 1" }));
    expect(onCommand).toHaveBeenCalledWith("accept_attempt", { attempt_id: "attempt-1" });
    expect(screen.queryByRole("button", { name: "Accept attempt 2" })).not.toBeInTheDocument();
  });
});
