import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => ({ pathname: "/today" }));
const router = vi.hoisted(() => ({ replace: vi.fn() }));
const queryState = vi.hoisted(() => ({
  data: undefined as {
    enabled: boolean;
    configured_source?: "env" | "database" | "none";
    is_unlocked: boolean;
    onboarding?: { status: string; last_completed_step: string | null };
  } | undefined,
  isLoading: true,
  isError: false,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => router,
}));
vi.mock("@tanstack/react-query", () => ({ useQuery: () => queryState }));
vi.mock("@/components/hatch/HatchNavShell", () => ({ HatchNavShell: () => null }));
vi.mock("@/components/hatch/HatchTopBarSlot", () => ({ HatchTopBarSlot: () => null }));
vi.mock("@/components/hatch/HatchMobileBar", () => ({ HatchMobileBar: () => null }));
vi.mock("@/components/OnboardingGate", () => ({ OnboardingGate: () => null }));
vi.mock("@/components/OfflineIndicator", () => ({ OfflineIndicator: () => null }));
vi.mock("@/components/InstallPrompt", () => ({ InstallPrompt: () => null }));
vi.mock("@/components/CommandPalette", () => ({ CommandPalette: () => null }));

describe("AppLockGate verification states", () => {
  afterEach(() => {
    vi.useRealTimers();
    navigation.pathname = "/today";
    router.replace.mockReset();
    queryState.data = undefined;
    queryState.isLoading = true;
    queryState.isError = false;
  });

  it("keeps protected content hidden and explains a slow local check", async () => {
    vi.useFakeTimers();
    const { AppLockGate } = await import("@/components/AppLockGate");
    render(<AppLockGate><h1>Private content</h1></AppLockGate>);

    expect(screen.queryByText("Private content")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Checking app lock");
    act(() => vi.advanceTimersByTime(4000));
    expect(screen.getByRole("status")).toHaveTextContent("Still checking the local backend");
  });

  it("keeps protected content hidden when verification fails", async () => {
    queryState.isLoading = false;
    queryState.isError = true;
    const { AppLockGate } = await import("@/components/AppLockGate");
    render(<AppLockGate><h1>Private content</h1></AppLockGate>);

    expect(screen.queryByText("Private content")).not.toBeInTheDocument();
    expect(screen.getByText(/Check the backend is running/)).toBeVisible();
  });

  it("does not expose locked onboarding after authoritative completion", async () => {
    navigation.pathname = "/onboarding";
    queryState.data = {
      enabled: true,
      configured_source: "none",
      is_unlocked: false,
      onboarding: { status: "complete", last_completed_step: "protect-workspace" },
    };
    queryState.isLoading = false;
    const { AppLockGate } = await import("@/components/AppLockGate");

    render(<AppLockGate><h1>Onboarding</h1></AppLockGate>);

    await waitFor(() => {
      expect(router.replace).toHaveBeenCalledWith("/unlock?next=%2Fonboarding");
    });
    expect(screen.queryByRole("heading", { name: "Onboarding" })).not.toBeInTheDocument();
  });
});
