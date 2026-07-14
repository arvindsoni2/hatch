import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiSettingsPage from "@/app/settings/ai/page";

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("AI & Capabilities settings page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      if (String(input).endsWith("/api/setup/status")) return response({
        overall_status: "ready",
        onboarding: { status: "complete", last_completed_step: "protect-workspace" },
        intent: { schema_version: 2, ai_mode: "none", backend_profile: "core", experience: "essential" },
        ai: { mode: "none", status: "ready", healthy: true },
        capabilities: { profile: "core", selected_profile: "core", enabled: [], operation: null },
        next_actions: [],
      });
      if (String(input).endsWith("/api/setup/providers")) return response({ providers: [] });
      return response({});
    });
  });

  it("uses the shared setup form and never collects provider secrets", async () => {
    render(<AiSettingsPage />);

    expect(await screen.findByRole("heading", { name: "AI & Capabilities" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Choose an AI engine" })).toBeVisible();
    expect(screen.getByRole("radio", { name: "Standard Hatch" })).toBeChecked();
    expect(screen.queryByPlaceholderText(/api key/i)).not.toBeInTheDocument();
  });
});
