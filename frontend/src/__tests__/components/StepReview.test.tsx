import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepReview } from "@/components/onboarding/StepReview";

const props = {
  candidate: { name: "Alex Smith", title: "CTO", years_experience: 10, summary: "" },
  selectedLocale: "uk",
  locales: [{ id: "uk", name: "United Kingdom", flag: "🇬🇧", currency: "GBP", currency_symbol: "£", default_rate_type: "daily" }],
  search: { target_roles: ["CTO", "VP Engineering"], contract_type: "contract" },
  compensation: { min_rate: 600, max_rate: 900, rate_type: "daily", currency: "GBP", legal_preferences: {} },
  skills: { primary: ["leadership", "cloud", "agile"], secondary: [], certifications: [] },
  llm: {
    provider: "google", triage_model: "gemini-2.5-flash-lite", primary_model: "gemini-2.5-flash",
    api_key_env: "GOOGLE_API_KEY", base_url: null, triage_base_url: "", temperature: 0.3, max_retries: 3,
    track_costs: true, monthly_budget: 15, currency: "USD",
  },
  enabledBoardsCount: 3,
  totalBoardsCount: 5,
  locations: [{ city: "London", country: "", radius_miles: 20, remote_preference: "hybrid" }],
  domains: { preferred: ["Financial services"], excluded: [] },
  legalPreferences: { work_authorization: "permanent_resident" },
  warnings: [] as string[],
  error: "",
  saving: false,
  onFinish: vi.fn(),
};

describe("StepReview", () => {
  it("renders candidate name and locale", () => {
    render(<StepReview {...props} />);
    expect(screen.getByText(/Alex Smith - CTO/)).toBeInTheDocument();
    expect(screen.getByText("United Kingdom")).toBeInTheDocument();
  });

  it("renders target roles", () => {
    render(<StepReview {...props} />);
    expect(screen.getByText(/CTO, VP Engineering/)).toBeInTheDocument();
  });

  it("renders Start Hatch button and calls onFinish when clicked", () => {
    render(<StepReview {...props} />);
    const button = screen.getByRole("button", { name: /start hatch/i });
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(props.onFinish).toHaveBeenCalled();
  });

  it("shows error message when error prop is set", () => {
    render(<StepReview {...props} error="Something went wrong" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
  });

  it("shows skipped setup warnings before saving", () => {
    render(
      <StepReview
        {...props}
        warnings={[
          "No target roles yet. Job discovery will be broad until you add them.",
          "AI-assisted tailoring and coaching will be limited until a provider is configured.",
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Before you save" })).toBeInTheDocument();
    expect(screen.getByText(/job discovery will be broad/i)).toBeInTheDocument();
    expect(screen.getByText(/AI-assisted tailoring/i)).toBeInTheDocument();
  });
});
