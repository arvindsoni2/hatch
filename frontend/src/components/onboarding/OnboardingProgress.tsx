"use client";

import { CheckCircle2 } from "lucide-react";

const STEP_LABELS = ["About you", "Job search", "Skills", "AI provider", "Review"];

interface OnboardingProgressProps {
  current: number;
}

export function OnboardingProgress({ current }: OnboardingProgressProps) {
  return (
    <div className="flex items-center gap-1 mb-8 overflow-x-auto" role="progressbar" aria-valuenow={current} aria-valuemax={STEP_LABELS.length}>
      {STEP_LABELS.map((label, i) => (
        <div key={i} className="flex items-center min-w-0">
          <div className="flex flex-col items-center gap-1">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                i + 1 < current
                  ? "bg-green-500 text-white"
                  : i + 1 === current
                  ? "bg-brand-600 text-white"
                  : "bg-slate-200 text-slate-500"
              }`}
            >
              {i + 1 < current ? <CheckCircle2 className="w-4 h-4" /> : i + 1}
            </div>
            <span className={`text-xs whitespace-nowrap ${i + 1 === current ? "text-brand-700 font-medium" : "text-slate-400"}`}>
              {label}
            </span>
          </div>
          {i < STEP_LABELS.length - 1 && (
            <div className={`w-8 h-0.5 mx-1 mb-4 flex-shrink-0 ${i + 1 < current ? "bg-green-500" : "bg-slate-200"}`} />
          )}
        </div>
      ))}
    </div>
  );
}
