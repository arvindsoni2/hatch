import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { InstallPrompt } from "@/components/InstallPrompt";

describe("InstallPrompt", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("does not render without beforeinstallprompt event", () => {
    const { container } = render(<InstallPrompt />);
    expect(container.firstChild).toBeNull();
  });

  it("renders when beforeinstallprompt fires", () => {
    render(<InstallPrompt />);
    act(() => {
      const event = new Event("beforeinstallprompt");
      (event as Event & { preventDefault: () => void }).preventDefault = vi.fn();
      window.dispatchEvent(event);
    });
    expect(screen.getByText(/install jobpilot/i)).toBeInTheDocument();
  });

  it("dismisses and remembers in localStorage", () => {
    render(<InstallPrompt />);
    act(() => {
      const event = new Event("beforeinstallprompt");
      (event as Event & { preventDefault: () => void }).preventDefault = vi.fn();
      window.dispatchEvent(event);
    });
    fireEvent.click(screen.getByText(/not now/i));
    expect(localStorage.getItem("pwa-install-dismissed")).toBe("1");
    expect(screen.queryByText(/install jobpilot/i)).not.toBeInTheDocument();
  });

  it("install button has minimum 44px touch target", () => {
    render(<InstallPrompt />);
    act(() => {
      const event = new Event("beforeinstallprompt");
      (event as Event & { preventDefault: () => void }).preventDefault = vi.fn();
      window.dispatchEvent(event);
    });
    const installButton = screen.getByText("Install");
    expect(installButton.className).toContain("min-h-[44px]");
  });
});
