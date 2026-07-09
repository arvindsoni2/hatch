import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SystemSettingsPage from "@/app/settings/system/page";

const capabilities = {
  backend_profile: "core",
  ai_mode: "local",
  capabilities: {
    core_backend: {
      configured: true,
      installed: true,
      available: true,
      reason: null,
      enable_command: null,
    },
    browser_automation: {
      configured: false,
      installed: false,
      available: false,
      reason: "Browser automation profile is not enabled.",
      enable_command: "hatch capabilities enable browser",
    },
    local_embeddings: {
      configured: false,
      installed: false,
      available: false,
      reason: "Local embeddings profile is not enabled.",
      enable_command: "hatch capabilities enable local-embeddings",
    },
    perception_advanced_coach: {
      configured: false,
      installed: false,
      available: false,
      reason: "Full backend capability profile is not enabled.",
      enable_command: "hatch capabilities enable full",
    },
  },
};

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

function mockSystemFetch({ capabilitiesOk = true } = {}) {
  vi.mocked(global.fetch).mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/api/system/capabilities")) {
      if (!capabilitiesOk) {
        return { ok: false, status: 503, text: async () => "unavailable" } as Response;
      }
      return jsonResponse(capabilities);
    }
    if (url.includes("/api/events/costs")) return jsonResponse({ total_cost_usd: 0, by_agent: {}, total_calls: 0 });
    if (url.includes("/api/debug/llm-traces")) return jsonResponse([]);
    if (url.includes("/api/debug/runtime-status")) return jsonResponse({ services: [], checked_at: Date.now() });
    if (url.includes("/api/events?")) return jsonResponse({ items: [], total: 0 });
    if (url.endsWith("/api/setup/reset/preview?mode=onboarding")) {
      return jsonResponse({
        mode: "onboarding",
        can_apply: true,
        deletes: ["job_postings", "applications", "master_cv.json"],
        preserves: ["api_keys.env", "app_lock_config"],
        counts: { database: { job_postings: 2, applications: 1 }, files: { "master_cv.json": 1 } },
        requires_confirmation: true,
      });
    }
    if (url.endsWith("/api/setup/reset/apply")) return jsonResponse({ applied: true, mode: "onboarding" });
    return jsonResponse({});
  });
}

describe("Settings System backend capabilities", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    mockSystemFetch();
  });

  it("renders the read-only backend capability panel", async () => {
    render(<SystemSettingsPage />);

    expect(await screen.findByRole("heading", { name: "Backend capabilities" })).toBeVisible();
    expect(screen.getByText("Backend profile")).toBeVisible();
    expect(screen.getByText("core")).toBeVisible();
    expect(screen.getByText("AI mode")).toBeVisible();
    expect(screen.getByText("local")).toBeVisible();
    expect(screen.getByText("Core backend")).toBeVisible();
    expect(screen.getByText("Installed")).toBeVisible();
  });

  it("shows exact terminal commands for missing optional capabilities", async () => {
    render(<SystemSettingsPage />);

    expect(await screen.findByText("hatch capabilities enable browser")).toBeVisible();
    expect(screen.getByText("hatch capabilities enable local-embeddings")).toBeVisible();
    expect(screen.getByText("hatch capabilities enable full")).toBeVisible();
    expect(screen.queryByRole("button", { name: /enable browser/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /rebuild/i })).not.toBeInTheDocument();
  });

  it("shows a soft warning when the capability status endpoint fails", async () => {
    vi.mocked(global.fetch).mockReset();
    mockSystemFetch({ capabilitiesOk: false });

    render(<SystemSettingsPage />);

    expect(await screen.findByText("Capability status is temporarily unavailable.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "System Logs" })).toBeVisible();
  });

  it("previews and applies onboarding reset without deleting host secrets", async () => {
    render(<SystemSettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Preview onboarding reset" }));

    expect(await screen.findByText("job_postings")).toBeVisible();
    expect(screen.getAllByText("api_keys.env").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Reset onboarding data" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/setup/reset/apply",
        expect.objectContaining({
          body: JSON.stringify({ mode: "onboarding", confirmation: "RESET" }),
          method: "POST",
        }),
      );
    });
    expect(await screen.findByText("Onboarding reset complete.")).toBeVisible();
  });
});
