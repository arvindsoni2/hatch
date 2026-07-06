import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SecuritySettingsPage from "@/app/settings/security/page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SecuritySettingsPage />
    </QueryClientProvider>,
  );
}

const databaseStatus = {
  enabled: true,
  configured_source: "database",
  is_configured: true,
  is_unlocked: true,
  password_policy: {
    min_length: 12,
    max_length: 128,
    require_letter: true,
    require_number: true,
    reject_edge_whitespace: true,
  },
};

describe("Security settings", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
  });

  it("rejects weak and mismatched passwords before calling the API", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => databaseStatus,
    } as Response);
    renderPage();
    await screen.findByText("App lock is enabled");
    const change = screen.getByRole("button", { name: "Change password" });
    const current = screen.getByLabelText("Current password");
    const next = screen.getByLabelText("New password");
    const confirm = screen.getByLabelText("Confirm new password");

    fireEvent.change(current, { target: { value: "current-password-1" } });
    fireEvent.change(next, { target: { value: "abc123" } });
    fireEvent.change(confirm, { target: { value: "abc123" } });
    expect(change).toBeDisabled();

    fireEvent.change(next, { target: { value: "new-password-2" } });
    expect(change).toBeDisabled();
    fireEvent.change(confirm, { target: { value: "new-password-2" } });
    expect(change).toBeEnabled();
  });

  it("announces success after changing the password", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce({ ok: true, json: async () => databaseStatus } as Response)
      .mockResolvedValue({ ok: true, json: async () => ({ changed: true }) } as Response);
    renderPage();
    await screen.findByText("App lock is enabled");
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "current-password-1" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password-2" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "new-password-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Password changed"));
  });

  it("explains environment-managed passwords without showing the form", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ ...databaseStatus, configured_source: "env" }),
    } as Response);
    renderPage();
    expect(await screen.findByText("In-app password change is disabled.")).toBeVisible();
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it("states exactly what local recovery preserves and removes", async () => {
    vi.mocked(global.fetch).mockResolvedValue({
      ok: true,
      json: async () => databaseStatus,
    } as Response);
    renderPage();
    expect(await screen.findByText(/removes the app-lock password and active sessions/i)).toBeVisible();
    expect(screen.getByText(/jobs, profile, CVs, and application data are preserved/i)).toBeVisible();
    expect(screen.getByText("bash scripts/reset-app-lock.sh")).toBeVisible();
  });
});
