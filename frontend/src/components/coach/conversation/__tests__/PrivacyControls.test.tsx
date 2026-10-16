import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PrivacyControls } from "../PrivacyControls";

describe("PrivacyControls", () => {
  it("requires an accessible in-app confirmation before destructive deletion", async () => {
    const user = userEvent.setup();
    const onDeleteSession = vi.fn();

    render(
      <PrivacyControls
        canDeleteTranscript={false}
        canDeleteSession
        onDeleteTranscript={vi.fn()}
        onDeleteSession={onDeleteSession}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Delete interview" }));
    expect(screen.getByRole("alertdialog", { name: "Confirm interview deletion" })).toBeVisible();
    expect(onDeleteSession).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirm interview deletion" }));
    expect(onDeleteSession).toHaveBeenCalledOnce();
  });
});
