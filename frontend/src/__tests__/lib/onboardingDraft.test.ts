import { describe, expect, it } from "vitest";
import {
  createOnboardingDraft,
  restoreOnboardingDraft,
} from "@/lib/onboardingDraft";

const state = {
  step: 5,
  candidate: {
    name: "Alex Smith",
    title: "Programme Director",
    years_experience: 12,
    summary: "Identifying career summary",
  },
  selectedLocale: "uk",
  search: {
    target_roles: ["Delivery Director"],
    contract_type: "contract",
  },
  locations: [{
    city: "London",
    country: "United Kingdom",
    radius_miles: 20,
    remote_preference: "hybrid",
  }],
  compensation: {
    min_rate: 700,
    max_rate: 900,
    rate_type: "daily",
    currency: "GBP",
    legal_preferences: { work_authorization: "visa_holder" },
  },
  skills: {
    primary: ["Programme delivery"],
    secondary: ["FinTech"],
    certifications: ["PMP"],
  },
  domains: { preferred: ["Banking"], excluded: ["Gambling"] },
  proofPoints: [{
    id: "proof-1",
    summary: "Saved a named client £2m",
    context: "Identifying employer details",
    metrics: "£2m",
    tags: ["Transformation"],
  }],
  llm: {
    provider: "llamacpp",
    triage_model: "qwen3.5-0.8b-q8_0",
    primary_model: "qwen3.5-4b-q4_k_m",
    api_key_env: "",
    base_url: "http://llm-primary:8080/v1",
    triage_base_url: "http://llm-triage:8081/v1",
    temperature: 0.3,
    max_retries: 3,
    track_costs: false,
    monthly_budget: 0,
    currency: "USD",
  },
  rolesSkipped: false,
  skillsSkipped: false,
  aiSetupLater: false,
  enabledBoardIds: ["reed"],
  scrapeIntervalHours: 4,
};

describe("onboarding draft privacy", () => {
  it("persists progress and non-sensitive preferences only", () => {
    const draft = createOnboardingDraft(state);
    const serialized = JSON.stringify(draft);

    expect(draft).toMatchObject({
      version: 2,
      step: 5,
      selectedLocale: "uk",
      search: state.search,
      skills: state.skills,
      domains: state.domains,
    });
    expect(serialized).not.toContain("Alex Smith");
    expect(serialized).not.toContain("London");
    expect(serialized).not.toContain("700");
    expect(serialized).not.toContain("visa_holder");
    expect(serialized).not.toContain("Saved a named client");
    expect(draft).not.toHaveProperty("candidate");
    expect(draft).not.toHaveProperty("locations");
    expect(draft).not.toHaveProperty("compensation");
    expect(draft).not.toHaveProperty("proofPoints");
  });

  it("sanitises legacy drafts instead of restoring sensitive fields", () => {
    const restored = restoreOnboardingDraft({
      ...state,
      version: 1,
    });

    expect(restored).toMatchObject({
      selectedLocale: "uk",
      search: state.search,
      skills: state.skills,
    });
    expect(restored).not.toHaveProperty("candidate");
    expect(restored).not.toHaveProperty("locations");
    expect(restored).not.toHaveProperty("compensation");
    expect(restored).not.toHaveProperty("proofPoints");
  });
});
