import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiSettingsPage from "@/app/settings/ai/page";

const status = {
  runtime: {
    ai_mode: "not_configured",
    quality_mode: "not_configured",
    provider: null,
    warnings: [],
  },
  restart_required: false,
  next_command: "hatch apply-ai-config",
};

const hardware = {
  detected: true,
  snapshot: {
    platform: { os_family: "linux", arch: "x86_64" },
    memory: { total_gb: 32 },
    storage: { models_dir_free_gb: 184 },
  },
};

const catalog = {
  models: [
    {
      id: "qwen3-small",
      display_name: "Qwen3 Small",
      role: "triage",
      download_size_gb: 1.8,
      min_ram_gb: 8,
      recommended_ram_gb: 16,
    },
    {
      id: "qwen3-medium",
      display_name: "Qwen3 Medium",
      role: "combined_capable_primary",
      download_size_gb: 5.6,
      min_ram_gb: 16,
      recommended_ram_gb: 32,
    },
  ],
};

const recommendations = {
  recommended: [{ model_id: "qwen3-medium", already_downloaded: false }],
  compatible: [{ model_id: "qwen3-small", already_downloaded: true }],
  not_recommended: [],
};

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

function mockSetupFetch() {
  vi.mocked(global.fetch).mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/setup/status")) return jsonResponse(status);
    if (url.endsWith("/api/setup/hardware")) return jsonResponse(hardware);
    if (url.endsWith("/api/setup/models/catalog")) return jsonResponse(catalog);
    if (url.endsWith("/api/setup/models/recommendations")) return jsonResponse(recommendations);
    if (url.endsWith("/api/setup/cloud-provider") && init?.method === "POST") {
      return jsonResponse({ next_command: "hatch secrets set openai" });
    }
    if (url.endsWith("/api/setup/provider/test") && init?.method === "POST") {
      return jsonResponse({ ok: false, status: "missing_secret", error: "OPENROUTER_API_KEY is not configured." });
    }
    if (url.endsWith("/api/setup/skip-ai") && init?.method === "POST") {
      return jsonResponse({ next_command: "hatch apply-ai-config" });
    }
    if (url.endsWith("/api/setup/local-model-selection") && init?.method === "POST") {
      return jsonResponse({ next_command: "hatch models install" });
    }
    return jsonResponse({});
  });
}

describe("AI provider settings page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    mockSetupFetch();
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("uses the Settings shell and frames setup as three clear choices", async () => {
    render(<AiSettingsPage />);

    expect(await screen.findByRole("heading", { name: "AI Provider" })).toBeVisible();
    expect(screen.getByRole("link", { name: "AI Provider" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Settings section")).toHaveValue("/settings/ai");

    expect(screen.getByRole("heading", { name: "Current setup" })).toBeVisible();
    expect(screen.getByText("Use Hatch now, set up AI later.")).toBeVisible();
    expect(screen.getByText("Use Hatch now, set up AI later")).toBeVisible();
    expect(screen.getByText("Run AI locally")).toBeVisible();
    expect(screen.getByText("Use cloud AI provider")).toBeVisible();
    expect(screen.getAllByText(/Not tested yet/i).length).toBeGreaterThan(0);
  });

  it("summarizes the current AI setup by user outcome before technical provider details", async () => {
    render(<AiSettingsPage />);

    expect(await screen.findByText("Use Hatch now, set up AI later.")).toBeVisible();
    expect(screen.getByText("Manual tracking, profile editing, and settings are available. Tailoring and Coach unlock after AI setup.")).toBeVisible();
    expect(screen.getByRole("button", { name: "View technical setup details" })).toBeVisible();
    expect(screen.queryByText(/^Provider:/i)).not.toBeInTheDocument();
  });

  it("shows plain hardware details and selected model count", async () => {
    render(<AiSettingsPage />);

    expect(await screen.findByText("Detected RAM: 32 GB")).toBeVisible();
    expect(screen.getByText("Recommended local model tier: medium")).toBeVisible();
    expect(screen.getByText("Selected models: 0")).toBeVisible();

    fireEvent.click(screen.getByRole("checkbox", { name: /Qwen3 Medium/i }));
    expect(screen.getByText("Selected models: 1")).toBeVisible();
  });

  it("copies host CLI commands instead of collecting browser secrets", async () => {
    render(<AiSettingsPage />);

    await screen.findByText("Use cloud AI provider");
    fireEvent.click(screen.getByRole("button", { name: /Copy OpenAI secret command/i }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("hatch secrets set openai");
    });
    expect(screen.queryByPlaceholderText(/api key/i)).not.toBeInTheDocument();
  });

  it("shows OpenRouter with model slug input and host secret command", async () => {
    render(<AiSettingsPage />);

    expect(await screen.findByRole("heading", { name: "OpenRouter" })).toBeVisible();
    expect(screen.getByDisplayValue("openai/gpt-4o-mini")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: /Copy OpenRouter secret command/i }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("hatch secrets set openrouter");
    });

    fireEvent.click(screen.getByRole("button", { name: /Test OpenRouter/i }));
    expect(await screen.findByText(/Provider test: missing_secret/i)).toBeVisible();
  });
});
