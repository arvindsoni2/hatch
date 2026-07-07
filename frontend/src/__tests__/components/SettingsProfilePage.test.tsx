import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProfileSettingsPage from "@/app/settings/profile/page";

const profile = {
  candidate: {
    name: "Avery Morgan",
    title: "Transformation Director",
    years_experience: 14,
    summary: "Delivery leader.",
  },
  search: {
    target_roles: ["Delivery Lead"],
    locations: [{ city: "London", country: "GB", remote_preference: "hybrid" }],
  },
  compensation: { min_rate: 650, max_rate: 800, currency: "GBP" },
  skills: { primary: ["Agile delivery"], secondary: ["Stakeholder management"] },
  llm: { provider: "llamacpp" },
};

function mockProfileFetch() {
  vi.mocked(global.fetch).mockImplementation(async (_input, init) => {
    if (init?.method === "PUT") {
      return { ok: true, json: async () => ({}) } as Response;
    }
    return { ok: true, json: async () => structuredClone(profile) } as Response;
  });
}

describe("Profile settings page", () => {
  beforeEach(() => {
    vi.mocked(global.fetch).mockReset();
    mockProfileFetch();
  });

  it("renders the settings shell navigation with Profile active", async () => {
    render(<ProfileSettingsPage />);

    expect(await screen.findByRole("heading", { name: "Profile" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Settings" });
    expect(nav).toBeVisible();
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Job Preferences" })).toHaveAttribute("href", "/settings/preferences");
    expect(screen.getByLabelText("Settings section")).toHaveValue("/settings/profile");
  });

  it("keeps Profile scoped to identity and removes job and AI controls", async () => {
    render(<ProfileSettingsPage />);

    await screen.findByDisplayValue("Avery Morgan");
    expect(screen.getByLabelText("Full name")).toBeVisible();
    expect(screen.getByLabelText("Current or target title")).toBeVisible();
    expect(screen.queryByText("Target Roles")).not.toBeInTheDocument();
    expect(screen.queryByText("Compensation")).not.toBeInTheDocument();
    expect(screen.queryByText("LLM Provider")).not.toBeInTheDocument();
  });

  it("shows dirty save actions, can discard, and only mutates candidate-owned fields", async () => {
    render(<ProfileSettingsPage />);

    const name = await screen.findByLabelText("Full name");
    fireEvent.change(name, { target: { value: "Avery Stone" } });

    expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    await waitFor(() => expect(screen.getByDisplayValue("Avery Morgan")).toBeVisible());

    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Avery Stone" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      "/api/v2/profile",
      expect.objectContaining({
        method: "PUT",
        body: expect.stringContaining('"candidate"'),
      }),
    ));
    const put = vi.mocked(global.fetch).mock.calls.find(([, init]) => init?.method === "PUT");
    const payload = JSON.parse(String(put?.[1]?.body));
    expect(payload.candidate.name).toBe("Avery Stone");
    expect(payload.search).toEqual(profile.search);
    expect(payload.compensation).toEqual(profile.compensation);
    expect(payload.skills).toEqual(profile.skills);
    expect(payload.llm).toEqual(profile.llm);
  });
});
