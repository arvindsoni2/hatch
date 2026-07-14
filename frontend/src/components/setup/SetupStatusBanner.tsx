"use client";

import { useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { useSetupStatus } from "@/lib/setup";

const DISMISS_KEY = "hatch_setup_banner_dismissed";

export function SetupStatusBanner() {
  const [dismissed, setDismissed] = useState(() => {
    try { return sessionStorage.getItem(DISMISS_KEY) === "1"; } catch { return false; }
  });
  const { status } = useSetupStatus();
  if (dismissed || !status || status.onboarding.status !== "complete" || status.overall_status === "ready") return null;
  return (
    <aside className="flex items-center justify-between gap-3 border-b border-[var(--warning)]/30 bg-[var(--warning-soft)] px-4 py-2 text-sm text-[var(--text)]" role="status">
      <p>AI or capability setup still needs attention. <Link className="font-semibold underline" href="/settings/ai">Open AI & Capabilities</Link></p>
      <button aria-label="Dismiss setup reminder" onClick={() => {
        sessionStorage.setItem(DISMISS_KEY, "1");
        setDismissed(true);
      }} type="button"><X className="h-4 w-4" /></button>
    </aside>
  );
}
