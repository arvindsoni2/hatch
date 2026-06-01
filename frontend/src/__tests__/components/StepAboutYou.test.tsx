import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StepAboutYou } from "@/components/onboarding/StepAboutYou";

const defaultCandidate = { name: "", title: "", years_experience: 0, summary: "" };

describe("StepAboutYou", () => {
  it("renders all required fields", () => {
    render(<StepAboutYou candidate={defaultCandidate} onChange={vi.fn()} tried={false} />);
    expect(screen.getByPlaceholderText(/arvind soni/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Delivery Lead")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("12")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/senior delivery lead with 12 years/i)).toBeInTheDocument();
  });

  it("calls onChange with updated name when input changes", () => {
    const onChange = vi.fn();
    render(<StepAboutYou candidate={defaultCandidate} onChange={onChange} tried={false} />);
    fireEvent.change(screen.getByPlaceholderText(/arvind soni/i), { target: { value: "Jane Doe" } });
    expect(onChange).toHaveBeenCalledWith({ ...defaultCandidate, name: "Jane Doe" });
  });

  it("displays existing candidate data", () => {
    const candidate = { name: "Alex Smith", title: "CTO", years_experience: 15, summary: "Tech leader" };
    render(<StepAboutYou candidate={candidate} onChange={vi.fn()} tried={false} />);
    expect(screen.getByDisplayValue("Alex Smith")).toBeInTheDocument();
    expect(screen.getByDisplayValue("CTO")).toBeInTheDocument();
  });

  it("shows validation error when tried=true and name is empty", () => {
    render(<StepAboutYou candidate={defaultCandidate} onChange={vi.fn()} tried={true} />);
    expect(screen.getByText(/name is required/i)).toBeInTheDocument();
  });
});
