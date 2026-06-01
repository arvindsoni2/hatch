import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Field, Help, Why, TagInput, Choice, Seg, ToggleRow, ChipInfo } from "@/components/onboarding/OnboardingPrimitives";

describe("Field", () => {
  it("renders label and children", () => {
    render(<Field label="Test label"><input data-testid="child" /></Field>);
    expect(screen.getByText("Test label")).toBeTruthy();
    expect(screen.getByTestId("child")).toBeTruthy();
  });

  it("shows required asterisk when req=true", () => {
    render(<Field label="Name" req><input /></Field>);
    expect(screen.getByText("*")).toBeTruthy();
  });

  it("shows Optional badge when optional=true", () => {
    render(<Field label="Summary" optional><input /></Field>);
    expect(screen.getByText("Optional")).toBeTruthy();
  });

  it("renders hint text", () => {
    render(<Field label="Field" hint="Helper text here"><input /></Field>);
    expect(screen.getByText("Helper text here")).toBeTruthy();
  });
});

describe("Help", () => {
  it("renders helper text", () => {
    render(<Help>Some hint</Help>);
    expect(screen.getByText("Some hint")).toBeTruthy();
  });
});

describe("Why", () => {
  it("renders callout text", () => {
    render(<Why>Why we ask this.</Why>);
    expect(screen.getByText("Why we ask this.")).toBeTruthy();
  });
});

describe("TagInput", () => {
  it("renders existing tags", () => {
    const onChange = vi.fn();
    render(<TagInput tags={["React", "TypeScript"]} onChange={onChange} placeholder="Add skill" />);
    expect(screen.getByText("React")).toBeTruthy();
    expect(screen.getByText("TypeScript")).toBeTruthy();
  });

  it("adds a tag on Enter", () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} placeholder="Add skill" />);
    const input = screen.getByPlaceholderText("Add skill");
    fireEvent.change(input, { target: { value: "Python" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith(["Python"]);
  });

  it("removes a tag when × clicked", () => {
    const onChange = vi.fn();
    render(<TagInput tags={["React"]} onChange={onChange} placeholder="Add" />);
    fireEvent.click(screen.getByLabelText("Remove React"));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

describe("Choice", () => {
  it("shows selected state", () => {
    render(<Choice on title="Option A" onClick={() => {}} />);
    const btn = screen.getByRole("button");
    expect(btn.className).toContain("on");
  });

  it("calls onClick", () => {
    const onClick = vi.fn();
    render(<Choice on={false} title="Option B" onClick={onClick} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalled();
  });
});

describe("Seg", () => {
  it("marks the active segment", () => {
    render(
      <Seg value="b" onChange={() => {}} options={[{ v: "a", l: "A" }, { v: "b", l: "B" }]} />
    );
    const bBtn = screen.getByText("B").closest("button")!;
    expect(bBtn.className).toContain("on");
  });

  it("calls onChange when non-active segment clicked", () => {
    const onChange = vi.fn();
    render(
      <Seg value="b" onChange={onChange} options={[{ v: "a", l: "A" }, { v: "b", l: "B" }]} />
    );
    fireEvent.click(screen.getByText("A"));
    expect(onChange).toHaveBeenCalledWith("a");
  });
});

describe("ToggleRow", () => {
  it("renders title and sub", () => {
    render(<ToggleRow on title="Reed" sub="Active" onToggle={() => {}} />);
    expect(screen.getByText("Reed")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });

  it("calls onToggle", () => {
    const onToggle = vi.fn();
    render(<ToggleRow on={false} title="LinkedIn" onToggle={onToggle} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalled();
  });
});

describe("ChipInfo", () => {
  it("renders label", () => {
    render(<ChipInfo>GBP · daily</ChipInfo>);
    expect(screen.getByText("GBP · daily")).toBeTruthy();
  });
});
