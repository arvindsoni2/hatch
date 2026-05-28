import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useMediaQuery, useIsMobile, useIsDesktop } from "@/hooks/useMediaQuery";

describe("useMediaQuery", () => {
  it("returns false when no match", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { result } = renderHook(() => useMediaQuery("(max-width: 767px)"));
    expect(result.current).toBe(false);
  });

  it("returns true when matches", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
  });

  it("useIsDesktop returns true for wide viewport", () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("min-width: 1024px"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const { result } = renderHook(() => useIsDesktop());
    expect(result.current).toBe(true);
  });
});
