"use client";

import type { OutcomeReason } from "@/lib/api";

interface Props {
  score: number;
  adjustment: number;
  confidence: string;
  sampleSize: number;
  reasons: OutcomeReason[];
}

export function OpportunityScoreBadge({ score, adjustment, confidence, sampleSize, reasons }: Props) {
  return (
    <details className="group relative">
      <summary className="cursor-pointer list-none rounded-lg border border-indigo-200 bg-indigo-50 px-2 py-1 text-center text-xs text-indigo-800 focus:outline-none focus:ring-2 focus:ring-indigo-500">
        <span className="block font-semibold">Opportunity {Math.round(score * 100)}%</span>
        <span className="capitalize text-indigo-600">{confidence} confidence</span>
      </summary>
      <div className="absolute right-0 z-20 mt-2 w-72 rounded-lg border border-slate-200 bg-white p-3 text-left shadow-xl">
        <p className="text-xs font-medium text-slate-800">Outcome adjustment {adjustment >= 0 ? "+" : ""}{Math.round(adjustment * 100)} points</p>
        <p className="mt-1 text-xs text-slate-500">Based on {sampleSize} resolved applications. This is a ranking aid, not a response probability.</p>
        {reasons.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {reasons.map((reason) => (
              <li key={`${reason.signal}-${reason.value}`} className="text-xs text-slate-600">
                <span className={reason.direction === "positive" ? "text-emerald-700" : "text-amber-700"}>{reason.direction === "positive" ? "+" : "-"}</span>{" "}{reason.message} ({reason.sample_size} samples)
              </li>
            ))}
          </ul>
        ) : <p className="mt-2 text-xs text-slate-500">No individual signal met the explanation threshold.</p>}
      </div>
    </details>
  );
}
