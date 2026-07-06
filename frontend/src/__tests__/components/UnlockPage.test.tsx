import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import UnlockPage from "@/app/unlock/page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><UnlockPage /></QueryClientProvider>);
}

describe("UnlockPage", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
  });

  it("renders first-run setup and submits matching passwords", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          enabled: true,
          configured_source: "none",
          is_configured: false,
          is_unlocked: false,
        }),
      } as Response)
      .mockResolvedValue({
        ok: true,
        json: async () => ({ unlocked: true }),
      } as Response);

    renderPage();
    expect(await screen.findByText("Protect your Hatch workspace")).toBeInTheDocument();
    const fields = screen.getAllByLabelText(/password/i);
    fireEvent.change(fields[0], { target: { value: "safe-password-1" } });
    fireEvent.change(fields[1], { target: { value: "safe-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Set password and continue" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/app-lock/setup",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("keeps setup disabled until the shared policy and confirmation pass", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        configured_source: "none",
        is_configured: false,
        is_unlocked: false,
      }),
    } as Response);
    renderPage();
    await screen.findByText("Protect your Hatch workspace");
    const fields = screen.getAllByLabelText(/password/i);
    const submit = screen.getByRole("button", { name: "Set password and continue" });

    fireEvent.change(fields[0], { target: { value: "abc123" } });
    fireEvent.change(fields[1], { target: { value: "abc123" } });
    expect(submit).toBeDisabled();

    fireEvent.change(fields[0], { target: { value: "valid-password-1" } });
    expect(submit).toBeDisabled();
    fireEvent.change(fields[1], { target: { value: "valid-password-1" } });
    expect(submit).toBeEnabled();
  });

  it("can reveal and hide the password without storing it", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        configured_source: "database",
        is_configured: true,
        is_unlocked: false,
      }),
    } as Response);
    renderPage();
    const field = await screen.findByLabelText("Password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(field).toHaveAttribute("type", "password");
  });

  it("renders unlock mode for an existing password", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        enabled: true,
        configured_source: "database",
        is_configured: true,
        is_unlocked: false,
      }),
    } as Response);
    renderPage();
    expect(await screen.findByText("Unlock Hatch")).toBeInTheDocument();
    expect(screen.queryByLabelText("Confirm password")).not.toBeInTheDocument();
  });
});
