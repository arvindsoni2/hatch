import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StepPasswordSetup } from "@/components/onboarding/StepPasswordSetup";

describe("StepPasswordSetup", () => {
  it("blocks weak passwords and sets the app-lock password without exposing it in browser storage", async () => {
    const onComplete = vi.fn();
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ unlocked: true }),
    } as Response);

    render(<StepPasswordSetup onComplete={onComplete} />);

    const password = screen.getByLabelText("Password");
    const confirm = screen.getByLabelText("Confirm password");
    const submit = screen.getByRole("button", { name: "Set password and continue" });

    fireEvent.change(password, { target: { value: "validpassword1" } });
    fireEvent.change(confirm, { target: { value: "validpassword1" } });
    expect(submit).toBeDisabled();

    fireEvent.change(password, { target: { value: "valid-password-1" } });
    fireEvent.change(confirm, { target: { value: "valid-password-1" } });
    fireEvent.click(submit);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/app-lock/setup",
        expect.objectContaining({
          body: JSON.stringify({ password: "valid-password-1" }),
          method: "POST",
        }),
      );
      expect(onComplete).toHaveBeenCalledTimes(1);
    });
    expect(localStorage.getItem("hatch_onboarding_v2")).toBeNull();
  });
});
