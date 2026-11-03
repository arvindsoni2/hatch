import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CoverageMap as CoverageMapData } from "@/lib/coachReadinessApi";
import { CoverageMap } from "../CoverageMap";

const coverage: CoverageMapData = {
  application_id: "app-1",
  covered_count: 1,
  thin_count: 1,
  gap_count: 1,
  competencies: [
    {
      competency: "Budget ownership",
      status: "covered",
      action: "use",
      stories: [
        { story_id: "story-1", title: "Budget story", score: 1, has_metric: true },
      ],
    },
    {
      competency: "Stakeholder management",
      status: "thin",
      action: "strengthen",
      stories: [
        { story_id: "story-2", title: "Stakeholder story", score: 0.5, has_metric: false },
      ],
    },
    {
      competency: "Data migration",
      status: "gap",
      action: "draft",
      stories: [],
    },
  ],
};

describe("CoverageMap", () => {
  it("renders every status with icon and text", () => {
    render(<CoverageMap coverage={coverage} />);

    expect(screen.getByText("Ready story")).toBeVisible();
    expect(screen.getByText("Could be stronger")).toBeVisible();
    expect(screen.getByText("No story yet")).toBeVisible();
    expect(screen.getByText("Budget ownership")).toBeVisible();
    expect(screen.getByText("Stakeholder management")).toBeVisible();
    expect(screen.getByText("Data migration")).toBeVisible();
  });

  it("links a gap to a prefilled story draft and is keyboard reachable", () => {
    render(<CoverageMap coverage={coverage} />);

    const draft = screen.getByRole("link", { name: "Draft a story" });
    expect(draft.getAttribute("href")).toBe(
      "/coach/stories/new?competency=Data%20migration",
    );
    draft.focus();
    expect(draft).toHaveFocus();
  });
});
