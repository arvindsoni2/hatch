import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AnalysingBanner } from "@/components/coach/AnalysingBanner";

describe("AnalysingBanner", () => {
  it("renders processing message when visible", () => {
    render(<AnalysingBanner visible />);
    expect(screen.getByText(/analysing your answer/i)).toBeInTheDocument();
    expect(screen.getByText(/take a little while on local hardware/i)).toBeInTheDocument();
  });

  it("renders nothing when not visible", () => {
    const { container } = render(<AnalysingBanner visible={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("clears when toggled from visible to hidden", () => {
    const { rerender } = render(<AnalysingBanner visible />);
    expect(screen.getByText(/analysing your answer/i)).toBeInTheDocument();
    rerender(<AnalysingBanner visible={false} />);
    expect(screen.queryByText(/analysing your answer/i)).not.toBeInTheDocument();
  });
});
