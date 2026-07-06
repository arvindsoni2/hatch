import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const queryState = vi.hoisted(() => ({
  data: undefined as { enabled: boolean; is_unlocked: boolean } | undefined,
  isLoading: true,
  isError: false,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/today",
  useRouter: () => ({ replace: vi.fn() }),
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
});
