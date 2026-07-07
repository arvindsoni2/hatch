import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CVStudioProgress } from "@/components/tailor/CVStudioProgress";

describe("CVStudioProgress", () => {
  it("names the CV Studio stages without decorative numbering", () => {
    render(<CVStudioProgress stage="idle" />);

    expect(screen.getByRole("list", { name: "CV Studio progress" })).toBeVisible();
    expect(screen.getByText("Add job")).toBeVisible();
    expect(screen.getByText("Analyse fit")).toBeVisible();
    expect(screen.getByText("Choose CV")).toBeVisible();
    expect(screen.getByText("Create pack")).toBeVisible();
    expect(screen.queryByText(/1\./)).not.toBeInTheDocument();
  });

  it("marks active and complete stages from current work state", () => {
    render(<CVStudioProgress stage="generating" />);

    expect(screen.getByText("Add job").closest("li")).toHaveAttribute("data-state", "complete");
    expect(screen.getByText("Analyse fit").closest("li")).toHaveAttribute("data-state", "complete");
    expect(screen.getByText("Choose CV").closest("li")).toHaveAttribute("data-state", "complete");
    expect(screen.getByText("Create pack").closest("li")).toHaveAttribute("data-state", "active");
  });
});
