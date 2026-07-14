import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AiCapabilitiesForm } from "@/components/setup/AiCapabilitiesForm";

const status = {
  schema_version: 2,
  overall_status: "needs_user_input",
  onboarding: { status: "in_progress", last_completed_step: "skills" },
  intent: {
    schema_version: 2,
    ai_mode: "none",
    backend_profile: "core",
    experience: "essential",
  },
  ai: { mode: "none", status: "ready", healthy: true },
  capabilities: { profile: "core", selected_profile: "core", enabled: [], operation: null },
  next_actions: [],
};

const providers = {
  providers: [{
    id: "anthropic",
    label: "Anthropic",
    primary_model: "claude-sonnet-5",
    triage_model: "claude-haiku-4-5",
    models: ["claude-sonnet-5", "claude-haiku-4-5"],
    privacy: "Prompts are sent to Anthropic.",
    cost: "External API charges apply.",
    configured: false,
  }],
};

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("AiCapabilitiesForm", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/setup/status")) return response(status);
      if (url.endsWith("/api/setup/providers")) return response(providers);
      if (url.includes("/api/setup/models/discovery")) {
        return response({ source: "live", compatible: [], models: [] });
      }
      return response({ intent: status.intent });
    });
  });

  it("routes cloud models without rendering local discovery", async () => {
    const user = userEvent.setup();
    render(<AiCapabilitiesForm context="onboarding" />);

    await user.click(await screen.findByRole("radio", { name: "Cloud" }));

    expect(await screen.findByLabelText("Primary cloud model")).toBeVisible();
    expect(screen.queryByText("Hugging Face recommendations")).not.toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/models/discovery"),
      expect.anything(),
    );
  });

  it("labels core as Standard Hatch and discloses advanced capabilities", async () => {
    const user = userEvent.setup();
    render(<AiCapabilitiesForm context="settings" />);

    expect(await screen.findByRole("radio", { name: "Standard Hatch" })).toBeChecked();
    expect(screen.queryByRole("radio", { name: "Full capabilities" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advanced capabilities" }));
    expect(screen.getByRole("radio", { name: "Full capabilities" })).toBeVisible();
  });

  it("loads curated discovery only after Local is selected", async () => {
    const user = userEvent.setup();
    render(<AiCapabilitiesForm context="settings" />);

    await user.click(await screen.findByRole("radio", { name: "Local" }));

    expect(await screen.findByText("Hugging Face recommendations")).toBeVisible();
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/setup/models/discovery"),
        expect.anything(),
      );
    });
    expect(screen.queryByLabelText("Primary cloud model")).not.toBeInTheDocument();
  });
});
