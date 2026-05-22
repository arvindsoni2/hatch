"use client";

import { StoryMatchResult } from "@/lib/api";
import { Lightbulb } from "lucide-react";

interface Props {
  match: StoryMatchResult;
  compact?: boolean;
}

export function StoryMatchBadge({ match, compact = false }: Props) {
  const pct = Math.round(match.confidence * 100);
  const color =
    pct >= 70 ? "border-emerald-600 bg-emerald-900/30 text-emerald-300"
    : pct >= 40 ? "border-amber-600 bg-amber-900/30 text-amber-300"
    : "border-slate-600 bg-slate-800 text-slate-400";

  if (compact) {
    return (
      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${color}`}>
        <Lightbulb className="h-3 w-3" />
        {match.story.title.length > 30 ? match.story.title.slice(0, 30) + "…" : match.story.title}
        <span className="opacity-70">({pct}%)</span>
      </span>
    );
  }

  return (
    <div className={`rounded-lg border p-3 ${color}`}>
      <div className="flex items-start gap-2">
        <Lightbulb className="h-4 w-4 mt-0.5 shrink-0" />
        <div>
          <p className="text-xs font-semibold">Bank story match ({pct}% {match.match_stage})</p>
          <p className="text-sm font-medium mt-0.5">{match.story.title}</p>
          {match.story.summary && (
            <p className="text-xs opacity-75 mt-0.5">{match.story.summary}</p>
          )}
          {match.match_reason && (
            <p className="text-xs opacity-60 mt-1 italic">{match.match_reason}</p>
          )}
        </div>
      </div>
    </div>
  );
}
