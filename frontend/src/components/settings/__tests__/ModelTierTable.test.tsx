import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ModelTierTable } from "@/components/settings/ModelTierTable";

const tiers = {
  tiers: [
    {
      tier: "T", route: "llm-triage", model_id: "qwen3.5-0.8b-q8-triage",
      display_name: "Qwen3.5 0.8B Q8_0 - fast triage", status: "promoted",
      deadline_s: 30, max_output_tokens: 512,
    },
    {
      tier: "S", route: "llm-primary", model_id: "qwen3.5-4b-q4km-primary",
      display_name: "Qwen3.5 4B Q4_K_M - compact primary", status: "promoted",
      deadline_s: 90, max_output_tokens: 600,
    },
  ],
  tier_l: { available: false, enabled: false, min_ram_gb: 24 },
};

function response(body: unknown): Response {
  return { ok: true, json: async () => structuredClone(body), text: async () => "" } as Response;
}

describe("ModelTierTable", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/setup/model-tiers")) return response(tiers);
      if (url.endsWith("/api/setup/intent") && init?.method === "PATCH") {
        return response({ intent: { tier_l_enabled: true } });
      }
      return response({});
    });
  });

  it("shows the promoted tier routes", async () => {
    render(<ModelTierTable />);

    expect(await screen.findByText("llm-triage")).toBeVisible();
    expect(screen.getByText("llm-primary")).toBeVisible();
    expect(screen.getByText("Qwen3.5 4B Q4_K_M - compact primary")).toBeVisible();
  });

  it("hides the Tier L opt-in when the probe has less than 24 GB", async () => {
    render(<ModelTierTable />);

    await screen.findByText("llm-triage");
    expect(screen.queryByLabelText("Enable the large model (Tier L)")).not.toBeInTheDocument();
  });

  it("offers the Tier L opt-in on a large machine and stores the choice", async () => {
    const user = userEvent.setup();
    vi.mocked(global.fetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/setup/model-tiers")) {
        return response({ ...tiers, tier_l: { available: true, enabled: false, min_ram_gb: 24 } });
      }
      if (url.endsWith("/api/setup/intent") && init?.method === "PATCH") {
        return response({ intent: { tier_l_enabled: true } });
      }
      return response({});
    });

    render(<ModelTierTable />);
    const toggle = await screen.findByLabelText("Enable the large model (Tier L)");
    await user.click(toggle);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/setup/intent"),
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({ tier_l_enabled: true }),
        }),
      );
    });
  });
});
