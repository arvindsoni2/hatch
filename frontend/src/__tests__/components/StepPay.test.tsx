import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StepPay } from "@/components/onboarding/StepPay";

describe("StepPay", () => {
  it("links an invalid maximum rate to an inline error", () => {
    render(
      <StepPay
        locale={{
          id: "uk",
          name: "United Kingdom",
          flag: "🇬🇧",
          currency: "GBP",
          currency_symbol: "£",
          default_rate_type: "daily",
        }}
        locations={[{
          city: "London",
          country: "",
          radius_miles: 30,
          remote_preference: "hybrid",
        }]}
        onLocationsChange={vi.fn()}
        compensation={{
          min_rate: 900,
          max_rate: 700,
          rate_type: "daily",
          currency: "GBP",
          legal_preferences: {},
        }}
        onCompensationChange={vi.fn()}
        tried
      />,
    );

    const maximum = screen.getByLabelText("Maximum expected rate");
    expect(maximum).toHaveAttribute("aria-invalid", "true");
    expect(maximum).toHaveAccessibleDescription(
      "Maximum rate must be greater than or equal to minimum rate.",
    );
  });
});
