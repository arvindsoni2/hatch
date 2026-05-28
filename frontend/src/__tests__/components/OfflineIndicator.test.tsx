import { render, screen, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { OfflineIndicator } from "@/components/OfflineIndicator";

describe("OfflineIndicator", () => {
  const originalOnLine = navigator.onLine;

  beforeEach(() => {
    Object.defineProperty(navigator, "onLine", { value: true, writable: true, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(navigator, "onLine", { value: originalOnLine, writable: true, configurable: true });
  });

  it("does not render when online", () => {
    const { container } = render(<OfflineIndicator />);
    expect(container.firstChild).toBeNull();
  });

  it("renders banner when offline", () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    render(<OfflineIndicator />);
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
  });

  it("shows banner when offline event fires", () => {
    render(<OfflineIndicator />);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
  });

  it("hides banner when coming back online", () => {
    Object.defineProperty(navigator, "onLine", { value: false, configurable: true });
    render(<OfflineIndicator />);
    act(() => {
      Object.defineProperty(navigator, "onLine", { value: true, writable: true, configurable: true });
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument();
  });
});
