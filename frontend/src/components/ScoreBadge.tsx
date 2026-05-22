"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

export interface ScoreDimensions {
  skill_match?: number | null;
  experience_match?: number | null;
  rate_match?: number | null;
  location_match?: number | null;
}

interface ScoreBadgeProps {
  score: number | null;
  threshold?: number;
  dimensions?: ScoreDimensions;
  size?: "sm" | "md";
  className?: string;
}

function getScoreBand(score: number, threshold: number): "high" | "mid" | "low" {
  if (score >= threshold) return "high";
  if (score >= 0.5) return "mid";
  return "low";
}

const BAND_STYLES = {
  high: "bg-green-100 text-green-800 border-green-200",
  mid: "bg-amber-100 text-amber-800 border-amber-200",
  low: "bg-slate-100 text-slate-500 border-slate-200",
};

function DimensionRow({ label, value }: { label: string; value: number | null | undefined }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const filled = Math.round((pct / 100) * 14);
  const bar = "█".repeat(filled) + "░".repeat(14 - filled);
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="w-32 shrink-0 text-slate-500">{label}</span>
      <span className="w-8 text-right font-semibold tabular-nums text-slate-800">{pct}%</span>
      <span className="font-mono text-[10px] tracking-tighter text-slate-400">{bar}</span>
    </div>
  );
}

export function ScoreBadge({ score, threshold = 0.75, dimensions, size = "md", className }: ScoreBadgeProps) {
  const [open, setOpen] = useState(false);

  if (score == null) return <span className="text-slate-400 text-sm">—</span>;

  const pct = Math.round(score * 100);
  const band = getScoreBand(score, threshold);
  const hasDimensions = dimensions != null && Object.values(dimensions).some((v) => v != null);

  const sizeStyles = size === "sm"
    ? "h-6 w-10 text-[11px]"
    : "h-7 w-12 text-xs";

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => hasDimensions && setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span
        className={cn(
          "inline-flex items-center justify-center rounded-full border font-semibold",
          sizeStyles,
          BAND_STYLES[band],
          hasDimensions && "cursor-default",
          className,
        )}
      >
        {pct}%
      </span>

      {open && hasDimensions && dimensions && (
        <div className="absolute left-1/2 top-full z-50 mt-2 -translate-x-1/2 w-72 rounded-lg border border-slate-200 bg-white p-3 shadow-xl">
          <div className="space-y-1.5">
            <DimensionRow label="Skill match" value={dimensions.skill_match} />
            <DimensionRow label="Experience match" value={dimensions.experience_match} />
            <DimensionRow label="Rate match" value={dimensions.rate_match} />
            <DimensionRow label="Location match" value={dimensions.location_match} />
            <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 text-xs font-semibold">
              <span className="text-slate-500">Overall</span>
              <span className={cn(
                "rounded-full px-2 py-0.5",
                band === "high" ? "bg-green-100 text-green-800"
                  : band === "mid" ? "bg-amber-100 text-amber-800"
                  : "bg-slate-100 text-slate-600",
              )}>
                {pct}%
              </span>
            </div>
          </div>
          {/* Arrow */}
          <div className="absolute -top-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 border-l border-t border-slate-200 bg-white" />
        </div>
      )}
    </div>
  );
}
