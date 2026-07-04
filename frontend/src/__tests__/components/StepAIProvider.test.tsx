import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StepAIProvider, type LLMData } from "@/components/onboarding/StepAIProvider";

const defaultLlm: LLMData = {
  provider: "google_genai",
  triage_model: "gemini-2.5-flash-lite",
  primary_model: "gemini-2.5-flash",
  api_key_env: "GOOGLE_API_KEY",
  base_url: null,
  triage_base_url: "",
  temperature: 0.3,
  max_retries: 3,
  track_costs: true,
  monthly_budget: 15,
  currency: "USD",
};

const llamacppLlm: LLMData = {
  provider: "llamacpp",
  triage_model: "qwen3-0.6b-q8_0",
  primary_model: "qwen3-8b-q5_k_m",
  api_key_env: "",
  base_url: "http://llm-primary:8080/v1",
  triage_base_url: "http://llm-triage:8081/v1",
  temperature: 0.3,
  max_retries: 3,
  track_costs: false,
  monthly_budget: 0,
  currency: "GBP",
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
    expect(screen.getByText(/local ai/i)).toBeInTheDocument();
    expect(screen.queryByText(/ollama/i)).not.toBeInTheDocument();
  });

  it("shows the host CLI command instead of accepting an API key", () => {
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
    expect(screen.queryByPlaceholderText(/GOOGLE_API_KEY/i)).not.toBeInTheDocument();
    expect(screen.getByText(/hatch secrets set google_genai/i)).toBeInTheDocument();
  });

  it("hides API key input for llamacpp provider", () => {
    render(
      <StepAIProvider
        llm={llamacppLlm}
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
    expect(screen.queryByPlaceholderText(/API_KEY/i)).not.toBeInTheDocument();
  });

  it("does not render a browser-side cloud connection test", () => {
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
    expect(screen.queryByText("Test")).not.toBeInTheDocument();
    expect(onTestConnection).not.toHaveBeenCalled();
  });

  it("switches to llamacpp and sets correct defaults (LLM-local)", () => {
    const onLlmChange = vi.fn();
    render(
      <StepAIProvider
        llm={defaultLlm}
        {...baseProps}
        onLlmChange={onLlmChange}
      />
    );
    fireEvent.click(screen.getByText(/local ai/i));
    expect(onLlmChange).toHaveBeenCalled();
    const call = onLlmChange.mock.calls[0][0] as LLMData;
    expect(call.provider).toBe("llamacpp");
    expect(call.base_url).toBe("http://llm-primary:8080/v1");
    expect(call.triage_base_url).toBe("http://llm-triage:8081/v1");
    expect(call.primary_model).toBe("qwen3-8b-q5_k_m");
    expect(call.triage_model).toBe("qwen3-0.6b-q8_0");
  });
});
