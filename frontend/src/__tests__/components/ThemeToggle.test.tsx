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
    localStorageMock.setItem.mockClear();
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

  it("toggles back to light mode on second click", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    fireEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    fireEvent.click(button);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("persists theme preference to localStorage", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button", { name: /toggle dark mode/i }));
    expect(localStorageMock.setItem).toHaveBeenCalledWith("theme", "dark");
  });

  it("persists light preference when toggling back", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(localStorageMock.setItem).toHaveBeenLastCalledWith("theme", "light");
  });

  it("respects stored dark preference on mount", () => {
    localStorageMock.getItem.mockReturnValue("dark");
    render(<ThemeToggle />);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("touch target is at least 44px", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button", { name: /toggle dark mode/i });
    expect(button.className).toContain("min-h-[44px]");
    expect(button.className).toContain("min-w-[44px]");
  });
});
