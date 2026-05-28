import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ThemeToggle } from "@/components/ThemeToggle";

const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  clear: vi.fn(),
  removeItem: vi.fn(),
};
Object.defineProperty(window, "localStorage", { value: localStorageMock, configurable: true });

describe("ThemeToggle", () => {
  beforeEach(() => {
    localStorageMock.getItem.mockReturnValue(null);
    document.documentElement.classList.remove("dark");
  });

  it("renders a button with accessible label", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /toggle dark mode/i })).toBeInTheDocument();
  });

  it("toggles dark class on documentElement when clicked", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    fireEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("persists theme preference to localStorage", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: /toggle dark mode/i }));
    expect(localStorageMock.setItem).toHaveBeenCalledWith("theme", "dark");
  });
});
