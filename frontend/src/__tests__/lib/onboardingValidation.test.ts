import { describe, expect, it } from "vitest";
import {
  getOnboardingStepErrors,
  getOnboardingWarnings,
} from "@/lib/onboardingValidation";

const validState = {
  candidate: {
    name: "Alex Smith",
    title: "Programme Director",
    years_experience: 12,
    summary: "",
  },
  search: {
    target_roles: ["Delivery Director"],
    contract_type: "contract",
  },
  locations: [{
    city: "London",
    country: "",
    radius_miles: 20,
    remote_preference: "hybrid",
  }],
  compensation: {
    min_rate: 700,
    max_rate: 900,
    rate_type: "daily",
    currency: "GBP",
    legal_preferences: { work_authorization: "permanent_resident" },
  },
  skills: {
    primary: ["Programme delivery", "Agile", "Leadership", "Risk", "Budget"],
    secondary: [],
    certifications: [],
  },
  rolesSkipped: false,
  skillsSkipped: false,
  aiSetupLater: false,
};

describe("onboarding step validation", () => {
  it("rejects a maximum rate below the minimum", () => {
    const errors = getOnboardingStepErrors(3, {
      ...validState,
      compensation: { ...validState.compensation, min_rate: 900, max_rate: 700 },
    });

    expect(errors).toContain("Maximum rate must be greater than or equal to minimum rate.");
  });

  it("requires a target role unless the user explicitly defers it", () => {
    expect(getOnboardingStepErrors(2, {
      ...validState,
      search: { ...validState.search, target_roles: [] },
    })).toContain("Add at least one target role or choose to add roles later.");

    expect(getOnboardingStepErrors(2, {
      ...validState,
      search: { ...validState.search, target_roles: [] },
      rolesSkipped: true,
    })).toEqual([]);
  });

  it("summarises reversible omissions before save", () => {
    const warnings = getOnboardingWarnings({
      ...validState,
      search: { ...validState.search, target_roles: [] },
      skills: { ...validState.skills, primary: [] },
      rolesSkipped: true,
      skillsSkipped: true,
      aiSetupLater: true,
    });

    expect(warnings).toEqual(expect.arrayContaining([
      expect.stringMatching(/target roles/i),
      expect.stringMatching(/skills/i),
      expect.stringMatching(/AI-assisted/i),
    ]));
  });
});
