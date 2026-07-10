import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => ({ pathname: "/today" }));
const router = vi.hoisted(() => ({ replace: vi.fn() }));
const query = vi.hoisted(() => ({
  data: { enabled: true, configured_source: "database", is_unlocked: true },
  isLoading: false,
  isError: false,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useRouter: () => router,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => query,
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
  beforeEach(() => {
    navigation.pathname = "/today";
    router.replace.mockReset();
    query.data = { enabled: true, configured_source: "database", is_unlocked: true };
    query.isLoading = false;
    query.isError = false;
  });

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

  it("renders onboarding as a dedicated workflow without application chrome", async () => {
    navigation.pathname = "/onboarding";
    const { AppLockGate } = await import("@/components/AppLockGate");
    render(
      <AppLockGate>
        <h1>Welcome to Hatch</h1>
      </AppLockGate>,
    );

    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Welcome to Hatch");
    expect(screen.queryByRole("navigation", { name: "Primary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Skip to main content" })).not.toBeInTheDocument();
  });

  it("does not redirect first-run onboarding to unlock", async () => {
    navigation.pathname = "/onboarding";
    query.data = { enabled: true, configured_source: "none", is_unlocked: false };
    const { AppLockGate } = await import("@/components/AppLockGate");
    render(
      <AppLockGate>
        <h1>Protect your Hatch workspace</h1>
      </AppLockGate>,
    );

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Protect your Hatch workspace");
    expect(router.replace).not.toHaveBeenCalledWith(expect.stringContaining("/unlock"));
    expect(screen.queryByText(/Checking app lock/i)).not.toBeInTheDocument();
  });

  it("redirects configured locked onboarding to unlock", async () => {
    navigation.pathname = "/onboarding";
    query.data = { enabled: true, configured_source: "database", is_unlocked: false };
    const { AppLockGate } = await import("@/components/AppLockGate");
    render(
      <AppLockGate>
        <h1>Protect your Hatch workspace</h1>
      </AppLockGate>,
    );

    expect(router.replace).toHaveBeenCalledWith("/unlock?next=%2Fonboarding");
    expect(screen.getByText(/Checking app lock/i)).toBeInTheDocument();
  });
});
