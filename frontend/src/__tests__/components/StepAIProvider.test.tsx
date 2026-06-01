import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepAIProvider, type LLMData } from "@/components/onboarding/StepAIProvider";

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
    expect(screen.getByPlaceholderText(/http:\/\/localhost/i)).toBeInTheDocument();
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
});
