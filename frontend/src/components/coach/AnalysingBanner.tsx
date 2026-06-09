"use client";

import { Loader2 } from "lucide-react";

interface AnalysingBannerProps {
  visible: boolean;
}

export function AnalysingBanner({ visible }: AnalysingBannerProps) {
  if (!visible) return null;

  return (
    <div className="rounded-xl border border-indigo-700 bg-indigo-900/20 p-4">
      <div className="flex items-center gap-3">
        <Loader2 className="h-5 w-5 shrink-0 animate-spin text-indigo-400" />
        <div>
          <p className="text-sm font-medium text-indigo-300">Analysing your answer…</p>
          <p className="text-xs text-slate-400">
            This may take a little while on local hardware.
          </p>
        </div>
      </div>
    </div>
  );
}
