"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getAppLockStatus } from "@/lib/api";
import { HatchNavShell } from "@/components/hatch/HatchNavShell";
import { HatchTopBarSlot } from "@/components/hatch/HatchTopBarSlot";
import { HatchMobileBar } from "@/components/hatch/HatchMobileBar";
import { OnboardingGate } from "@/components/OnboardingGate";
import { OfflineIndicator } from "@/components/OfflineIndicator";
import { InstallPrompt } from "@/components/InstallPrompt";
import { CommandPalette } from "@/components/CommandPalette";

export const APP_LOCK_QUERY_KEY = ["app-lock-status"] as const;

export function AppLockGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const isUnlockRoute = pathname === "/unlock";
  const { data, isLoading, isError } = useQuery({
    queryKey: APP_LOCK_QUERY_KEY,
    queryFn: getAppLockStatus,
    retry: 1,
  });
  const [slowCheck, setSlowCheck] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      setSlowCheck(false);
      return;
    }
    const timer = window.setTimeout(() => setSlowCheck(true), 4000);
    return () => window.clearTimeout(timer);
  }, [isLoading]);

  useEffect(() => {
    if (!isUnlockRoute && data?.enabled && !data.is_unlocked) {
      const next = encodeURIComponent(pathname || "/today");
      router.replace(`/unlock?next=${next}`);
    }
    if (isUnlockRoute && data && (!data.enabled || data.is_unlocked)) {
      router.replace("/today");
    }
  }, [data, isUnlockRoute, pathname, router]);

  if (isUnlockRoute) {
    return <main className="min-h-screen">{children}</main>;
  }
  if (isLoading || (data?.enabled && !data.is_unlocked)) {
    return (
      <div className="grid min-h-screen place-items-center" style={{ background: "var(--bg)" }}>
        <div className="max-w-sm px-6 text-center text-sm text-[var(--text-muted)]" role="status">
          {slowCheck
            ? "Still checking the local backend. Make sure Hatch is running."
            : "Checking app lock..."}
        </div>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="grid min-h-screen place-items-center p-6" style={{ background: "var(--bg)" }}>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Hatch could not verify the lock state. Check the backend is running, then reload this page.
        </p>
      </div>
    );
  }

  return (
    <>
      <a
        className="fixed left-4 top-4 z-[300] -translate-y-24 rounded-[var(--radius-control)] bg-[var(--accent)] px-4 py-2 font-semibold text-[var(--on-accent)] transition-transform focus:translate-y-0"
        href="#main-content"
      >
        Skip to main content
      </a>
      <OnboardingGate />
      <OfflineIndicator />
      <div className="flex" style={{ minHeight: "100vh" }}>
        <HatchNavShell />
        <div className="flex flex-col flex-1 min-w-0">
          <HatchMobileBar />
          <HatchTopBarSlot />
          <main
            className="flex-1 px-4 py-6 pb-24 md:px-8 md:py-6 md:pb-8"
            id="main-content"
            tabIndex={-1}
          >
            {children}
          </main>
        </div>
      </div>
      <InstallPrompt />
      <CommandPalette />
    </>
  );
}
