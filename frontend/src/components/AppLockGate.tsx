"use client";

import { useEffect } from "react";
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
        <div className="text-sm" style={{ color: "var(--text-muted)" }}>Securing Hatch…</div>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="grid min-h-screen place-items-center p-6" style={{ background: "var(--bg)" }}>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Hatch could not verify the lock state. Check that the backend is online.
        </p>
      </div>
    );
  }

  return (
    <>
      <OnboardingGate />
      <OfflineIndicator />
      <div className="flex" style={{ minHeight: "100vh" }}>
        <HatchNavShell />
        <div className="flex flex-col flex-1 min-w-0">
          <HatchMobileBar />
          <HatchTopBarSlot />
          <main className="flex-1 px-4 py-6 pb-24 md:px-8 md:py-6 md:pb-8">
            {children}
          </main>
        </div>
      </div>
      <InstallPrompt />
      <CommandPalette />
    </>
  );
}
