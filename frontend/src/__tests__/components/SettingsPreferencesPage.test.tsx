import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import JobPreferencesPage from "@/app/settings/preferences/page";

const profile = {
  candidate: { name: "Avery Morgan", title: "Transformation Director" },
  locale: "uk",
  search: {
    target_roles: ["Delivery Lead"],
    contract_type: "contract",
    locations: [{ city: "London", country: "GB", remote_preference: "hybrid" }],
  },
  job_boards: [
    { name: "LinkedIn", scraper: "linkedin", enabled: true },
    { name: "Indeed", scraper: "indeed", enabled: false },
  ],
  compensation: { min_rate: 650, max_rate: 800, currency: "GBP", rate_type: "daily" },
  skills: { primary: ["Agile delivery"], secondary: ["Stakeholder management"] },
  scoring: { shortlist_threshold: 0.75, weights: { skill_match: 0.35 } },
  perception: { face: { enabled: false } },
  outcome_learning: {
    enabled: true,
    minimum_total_applications: 15,
    no_response_after_days: 35,
    recency_half_life_days: 120,
    maximum_score_adjustment: 0.1,
    enabled_signals: ["source", "role_family"],
  },
};

function mockProfileFetch() {
  vi.mocked(global.fetch).mockImplementation(async (_input, init) => {
    if (init?.method === "PUT") {
      return { ok: true, json: async () => ({}) } as Response;
    }
    return { ok: true, json: async () => structuredClone(profile) } as Response;
  });
}

describe("Job preferences settings page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    localStorage.clear();
    mockProfileFetch();
  });

  it("renders Settings navigation with Job Preferences active", async () => {
    render(<JobPreferencesPage />);

    expect(await screen.findByRole("heading", { name: "Job Preferences" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Job Preferences" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Settings section")).toHaveValue("/settings/preferences");
  });

  it("owns job-search sections without exposing identity or AI provider controls", async () => {
    render(<JobPreferencesPage />);

    expect(await screen.findByText("Target roles")).toBeVisible();
    expect(screen.getByText("Location")).toBeVisible();
    expect(screen.getByText("Compensation")).toBeVisible();
    expect(screen.getByText("Skills")).toBeVisible();
    expect(screen.queryByLabelText("Full name")).not.toBeInTheDocument();
    expect(screen.queryByText("LLM Provider")).not.toBeInTheDocument();
  });

  it("validates required target roles and focuses the tag entry", async () => {
    render(<JobPreferencesPage />);

    await screen.findByText("Target roles");
    const rolesRegion = screen.getByRole("group", { name: "Target roles" });
    fireEvent.click(within(rolesRegion).getByRole("button", { name: "Remove Delivery Lead" }));
    fireEvent.click(screen.getByRole("button", { name: "Save job preferences" }));

    expect(await screen.findByText("Add at least one target role.")).toBeVisible();
    expect(within(rolesRegion).getByRole("textbox", { name: "Add target role" })).toHaveFocus();
  });

  it("only mutates preference-owned fields in the full profile payload", async () => {
    render(<JobPreferencesPage />);

    const city = await screen.findByLabelText("City");
    fireEvent.change(city, { target: { value: "Manchester" } });
    fireEvent.click(screen.getByRole("button", { name: "Save job preferences" }));

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      "/api/v2/profile",
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining('"search"'),
      }),
    ));
    const put = vi.mocked(global.fetch).mock.calls.find(([, init]) => init?.method === "PUT");
    const payload = JSON.parse(String(put?.[1]?.body));
    expect(payload.candidate).toEqual(profile.candidate);
    expect(payload.llm).toBeUndefined();
    expect(payload.search.locations[0].city).toBe("Manchester");
  });

  it("revokes saved camera consent when Coach privacy action is used", async () => {
    localStorage.setItem("face_consent_given", "true");
    render(<JobPreferencesPage />);

    await screen.findByText("Coach privacy");
    fireEvent.click(screen.getByRole("button", { name: "Revoke saved camera-analysis consent" }));

    expect(localStorage.getItem("face_consent_given")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Camera-analysis consent revoked");
  });
});
