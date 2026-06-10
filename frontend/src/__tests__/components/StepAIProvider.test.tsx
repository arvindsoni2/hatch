import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StepAIProvider, type LLMData } from "@/components/onboarding/StepAIProvider";
import * as api from "@/lib/api";

const defaultLlm: LLMData = {
  provider: "google",
  triage_model: "gemini-2.5-flash-lite",
  primary_model: "gemini-2.5-flash",
  api_key_env: "GOOGLE_API_KEY",
  base_url: null,
  temperature: 0.3,
  max_retries: 3,
  track_costs: true,
  monthly_budget: 15,
  currency: "USD",
};

const ollamaLlm: LLMData = {
  ...{ provider: "ollama", triage_model: "", primary_model: "", api_key_env: "", base_url: null },
  temperature: 0.3, max_retries: 3, track_costs: false, monthly_budget: 0, currency: "GBP",
};

const baseProps = {
  onLlmChange: vi.fn(),
  testApiKey: "",
  onTestApiKeyChange: vi.fn(),
  testingConnection: false,
  connectionResult: null as null,
  onTestConnection: vi.fn(),
  boards: [] as import("@/lib/api").LocaleBoard[],
  enabledBoards: new Set<string>(),
  onEnabledBoardsChange: vi.fn(),
  scrapeIntervalHours: 4,
  onScrapeIntervalChange: vi.fn(),
};

beforeEach(() => {
  vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({ status: "ok", timestamp: "", ram_gb: 16 }),
  } as Response);
});

describe("StepAIProvider", () => {
  it("renders all LLM provider cards", () => {
    render(
      <StepAIProvider
        llm={defaultLlm}
        onLlmChange={vi.fn()}
        testApiKey=""
        onTestApiKeyChange={vi.fn()}
        testingConnection={false}
        connectionResult={null}
        onTestConnection={vi.fn()}
        boards={[]}
        enabledBoards={new Set()}
        onEnabledBoardsChange={vi.fn()}
        scrapeIntervalHours={4}
        onScrapeIntervalChange={vi.fn()}
      />
    );
    expect(screen.getByText(/anthropic/i)).toBeInTheDocument();
    expect(screen.getByText(/openai/i)).toBeInTheDocument();
    expect(screen.getByText(/gemini/i)).toBeInTheDocument();
    expect(screen.getByText(/ollama/i)).toBeInTheDocument();
  });

  it("shows API key input when non-ollama provider selected", () => {
    render(
      <StepAIProvider
        llm={defaultLlm}
        onLlmChange={vi.fn()}
        testApiKey=""
        onTestApiKeyChange={vi.fn()}
        testingConnection={false}
        connectionResult={null}
        onTestConnection={vi.fn()}
        boards={[]}
        enabledBoards={new Set()}
        onEnabledBoardsChange={vi.fn()}
        scrapeIntervalHours={4}
        onScrapeIntervalChange={vi.fn()}
      />
    );
    expect(screen.getByPlaceholderText(/GOOGLE_API_KEY/i)).toBeInTheDocument();
  });

  it("hides API key input for ollama provider", () => {
    render(
      <StepAIProvider
        llm={{ ...defaultLlm, provider: "ollama", api_key_env: "" }}
        onLlmChange={vi.fn()}
        testApiKey=""
        onTestApiKeyChange={vi.fn()}
        testingConnection={false}
        connectionResult={null}
        onTestConnection={vi.fn()}
        boards={[]}
        enabledBoards={new Set()}
        onEnabledBoardsChange={vi.fn()}
        scrapeIntervalHours={4}
        onScrapeIntervalChange={vi.fn()}
      />
    );
    expect(screen.queryByPlaceholderText(/GOOGLE_API_KEY/i)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/http:\/\/host\.containers/i)).toBeInTheDocument();
  });

  it("calls onTestConnection when Test button is clicked", () => {
    const onTestConnection = vi.fn();
    render(
      <StepAIProvider
        llm={defaultLlm}
        onLlmChange={vi.fn()}
        testApiKey="test-key-123"
        onTestApiKeyChange={vi.fn()}
        testingConnection={false}
        connectionResult={null}
        onTestConnection={onTestConnection}
        boards={[]}
        enabledBoards={new Set()}
        onEnabledBoardsChange={vi.fn()}
        scrapeIntervalHours={4}
        onScrapeIntervalChange={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText("Test"));
    expect(onTestConnection).toHaveBeenCalled();
  });

  it("shows pull command and refresh button when Ollama has no models (LLM-3)", async () => {
    vi.spyOn(api, "fetchOllamaModels").mockResolvedValue({ models: [], base_url: "" });
    render(
      <StepAIProvider
        llm={ollamaLlm}
        {...baseProps}
      />
    );
    await waitFor(() => {
      expect(screen.getByTestId("ollama-pull-cmd")).toBeInTheDocument();
    });
    expect(screen.getByTestId("ollama-pull-cmd")).toHaveTextContent("ollama pull qwen3:4b");
    expect(screen.getByText(/refresh model list/i)).toBeInTheDocument();
  });

  it("pre-selects recommended model when user switches to Ollama and models are available (LLM-3)", async () => {
    const onLlmChange = vi.fn();
    vi.spyOn(api, "fetchOllamaModels").mockResolvedValue({
      models: ["gemma4:e2b", "qwen3:4b", "llama3:8b"],
      base_url: "",
    });
    render(
      <StepAIProvider
        llm={defaultLlm}
        {...baseProps}
        onLlmChange={onLlmChange}
      />
    );
    // Click the Ollama provider card to trigger handleProviderChange
    fireEvent.click(screen.getByText(/ollama/i));
    await waitFor(() => {
      expect(onLlmChange).toHaveBeenCalled();
    });
    const call = onLlmChange.mock.calls[0][0] as LLMData;
    // qwen3:4b ranks higher than gemma4:e2b in OLLAMA_RECOMMENDED_ORDER
    expect(call.primary_model).toBe("qwen3:4b");
    // gemma4:e2b is preferred for triage (edge/smallest model)
    expect(call.triage_model).toBe("gemma4:e2b");
  });
});
