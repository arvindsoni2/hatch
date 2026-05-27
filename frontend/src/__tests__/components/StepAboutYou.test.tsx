import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepAboutYou } from "@/components/onboarding/StepAboutYou";

const defaultCandidate = { name: "", title: "", years_experience: 0, summary: "" };

describe("StepAboutYou", () => {
  it("renders all required fields", () => {
    render(<StepAboutYou candidate={defaultCandidate} onChange={vi.fn()} />);
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/current \/ target title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/years of experience/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/professional summary/i)).toBeInTheDocument();
  });

  it("calls onChange with updated name when input changes", () => {
    const onChange = vi.fn();
    render(<StepAboutYou candidate={defaultCandidate} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Jane Doe" } });
    expect(onChange).toHaveBeenCalledWith({ ...defaultCandidate, name: "Jane Doe" });
  });

  it("displays existing candidate data", () => {
    const candidate = { name: "Alex Smith", title: "CTO", years_experience: 15, summary: "Tech leader" };
    render(<StepAboutYou candidate={candidate} onChange={vi.fn()} />);
    expect(screen.getByDisplayValue("Alex Smith")).toBeInTheDocument();
    expect(screen.getByDisplayValue("CTO")).toBeInTheDocument();
  });
});
