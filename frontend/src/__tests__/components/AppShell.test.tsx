import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  usePathname: () => "/today",
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: { enabled: true, is_unlocked: true },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/components/hatch/HatchNavShell", () => ({
  HatchNavShell: () => <nav aria-label="Primary" />,
}));
vi.mock("@/components/hatch/HatchTopBarSlot", () => ({
  HatchTopBarSlot: () => <header />,
}));
vi.mock("@/components/hatch/HatchMobileBar", () => ({
  HatchMobileBar: () => null,
}));
vi.mock("@/components/OnboardingGate", () => ({ OnboardingGate: () => null }));
vi.mock("@/components/OfflineIndicator", () => ({ OfflineIndicator: () => null }));
vi.mock("@/components/InstallPrompt", () => ({ InstallPrompt: () => null }));
vi.mock("@/components/CommandPalette", () => ({ CommandPalette: () => null }));

describe("authenticated application shell", () => {
  it("owns one main landmark and leaves one H1 to route content", async () => {
    const { AppLockGate } = await import("@/components/AppLockGate");
    render(
      <AppLockGate>
        <section>
          <h1>Today</h1>
        </section>
      </AppLockGate>,
    );

    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });
});
