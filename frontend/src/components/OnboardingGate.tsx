"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchProfileStatus } from "@/lib/api";

export function OnboardingGate() {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (pathname.startsWith("/onboarding")) return;
    let cancelled = false;
    fetchProfileStatus()
      .then((s) => { if (!cancelled && s.onboarding_required) router.replace("/onboarding"); })
      .catch(() => {/* offline / backend down: stay put */});
    return () => { cancelled = true; };
  }, [pathname, router]);

  return null;
}
