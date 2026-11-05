import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchDisplayTimeZone } from "@/lib/coachReadinessApi";
import { browserTimeZone } from "@/lib/formatInterviewTime";
import { useDisplayTimeZone } from "../useDisplayTimeZone";

vi.mock("@/lib/coachReadinessApi", () => ({
  fetchDisplayTimeZone: vi.fn(),
}));

describe("useDisplayTimeZone", () => {
  beforeEach(() => {
    vi.mocked(fetchDisplayTimeZone).mockReset();
  });

  it("uses the configured zone", async () => {
    vi.mocked(fetchDisplayTimeZone).mockResolvedValue("Asia/Kolkata");

    const { result } = renderHook(() => useDisplayTimeZone());

    await waitFor(() => expect(result.current).toBe("Asia/Kolkata"));
  });

  it("falls back to the browser zone when the API returns null", async () => {
    vi.mocked(fetchDisplayTimeZone).mockResolvedValue(null);

    const { result } = renderHook(() => useDisplayTimeZone());

    await waitFor(() => expect(result.current).toBe(browserTimeZone()));
  });
});
