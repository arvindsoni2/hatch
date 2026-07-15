import { beforeEach, describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn();
const serverApiFetchMock = vi.fn();

vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/server-api", () => ({ serverApiFetch: serverApiFetchMock }));

describe("root first-run routing", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    redirectMock.mockImplementation((destination: string) => {
      throw new Error(`NEXT_REDIRECT:${destination}`);
    });
  });

  it("redirects an unconfigured incomplete workspace to onboarding", async () => {
    serverApiFetchMock.mockResolvedValue({
      enabled: true,
      configured_source: "none",
      onboarding: { status: "not_started", last_completed_step: null },
    });
    const { default: RootPage } = await import("@/app/page");

    await expect(RootPage()).rejects.toThrow("NEXT_REDIRECT:/onboarding");
    expect(serverApiFetchMock).toHaveBeenCalledWith("/api/app-lock/status");
    expect(redirectMock).toHaveBeenCalledWith("/onboarding");
  });

  it("redirects a configured workspace to today", async () => {
    serverApiFetchMock.mockResolvedValue({
      enabled: true,
      configured_source: "database",
      onboarding: { status: "complete", last_completed_step: "protect-workspace" },
    });
    const { default: RootPage } = await import("@/app/page");

    await expect(RootPage()).rejects.toThrow("NEXT_REDIRECT:/today");
    expect(redirectMock).toHaveBeenCalledWith("/today");
  });

  it("falls back to today when lock status is unavailable", async () => {
    serverApiFetchMock.mockRejectedValue(new Error("backend unavailable"));
    const { default: RootPage } = await import("@/app/page");

    await expect(RootPage()).rejects.toThrow("NEXT_REDIRECT:/today");
    expect(redirectMock).toHaveBeenCalledWith("/today");
  });
});
