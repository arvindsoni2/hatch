import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepJobSearch } from "@/components/onboarding/StepJobSearch";
import type { LocaleSummary } from "@/lib/api";

const MOCK_LOCALES: LocaleSummary[] = [
  { id: "uk", name: "United Kingdom", flag: "🇬🇧", currency: "GBP", currency_symbol: "£", default_rate_type: "daily" },
  { id: "in", name: "India", flag: "🇮🇳", currency: "INR", currency_symbol: "₹", default_rate_type: "annual" },
  { id: "ae", name: "United Arab Emirates", flag: "🇦🇪", currency: "AED", currency_symbol: "AED", default_rate_type: "monthly" },
  { id: "ie", name: "Ireland", flag: "🇮🇪", currency: "EUR", currency_symbol: "€", default_rate_type: "daily" },
  { id: "us", name: "United States", flag: "🇺🇸", currency: "USD", currency_symbol: "$", default_rate_type: "annual" },
];

const defaultSearch = { target_roles: [], contract_type: "permanent" };
const defaultLocation = { city: "", country: "", radius_miles: 30, remote_preference: "hybrid" };
const defaultCompensation = {
  min_rate: 0, max_rate: 0, rate_type: "daily", currency: "GBP", legal_preferences: {},
};

function renderStep(locales = MOCK_LOCALES, selectedLocale = "uk") {
  return render(
    <StepJobSearch
      selectedLocale={selectedLocale}
      locales={locales}
      loadingLocales={false}
      onLocaleChange={vi.fn()}
      search={defaultSearch}
      onSearchChange={vi.fn()}
      locations={[defaultLocation]}
      onLocationsChange={vi.fn()}
      compensation={defaultCompensation}
      onCompensationChange={vi.fn()}
      legalFields={[]}
      localeName="United Kingdom"
    />
  );
}

describe("StepJobSearch", () => {
  it("renders all locale cards including UAE and Ireland", () => {
    renderStep();
    expect(screen.getByText("United Kingdom")).toBeInTheDocument();
    expect(screen.getByText("India")).toBeInTheDocument();
    expect(screen.getByText("United Arab Emirates")).toBeInTheDocument();
    expect(screen.getByText("Ireland")).toBeInTheDocument();
  });

  it("shows flags for each locale card", () => {
    renderStep();
    expect(screen.getByText("🇦🇪")).toBeInTheDocument();
    expect(screen.getByText("🇮🇪")).toBeInTheDocument();
  });

  it("calls onLocaleChange when a locale card is clicked", () => {
    const onLocaleChange = vi.fn();
    render(
      <StepJobSearch
        selectedLocale="uk"
        locales={MOCK_LOCALES}
        loadingLocales={false}
        onLocaleChange={onLocaleChange}
        search={defaultSearch}
        onSearchChange={vi.fn()}
        locations={[defaultLocation]}
        onLocationsChange={vi.fn()}
        compensation={defaultCompensation}
        onCompensationChange={vi.fn()}
        legalFields={[]}
        localeName="United Kingdom"
      />
    );
    fireEvent.click(screen.getByText("United Arab Emirates").closest("button")!);
    expect(onLocaleChange).toHaveBeenCalledWith("ae");
  });

  it("renders Job type dropdown with expected options", () => {
    renderStep();
    const jobTypeSelect = screen.getByDisplayValue("Permanent");
    expect(jobTypeSelect).toBeInTheDocument();
    const opts = Array.from(jobTypeSelect.querySelectorAll("option")).map((o) => o.textContent);
    expect(opts).toContain("Temporary");
    expect(opts).toContain("Hybrid");
    expect(opts).toContain("Remote");
  });
});
