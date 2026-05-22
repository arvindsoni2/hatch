"use client";

import { SkillMatch } from "@/lib/api";

interface SkillMatchMatrixProps {
  skillMatch: SkillMatch;
}

export function SkillMatchMatrix({ skillMatch }: SkillMatchMatrixProps) {
  const { matched, missing, match_pct, domain_match, recommendations } = skillMatch;
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const dash = (match_pct / 100) * circumference;
  const gaugeColor = match_pct >= 70 ? "#10b981" : match_pct >= 50 ? "#f59e0b" : "#ef4444";

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-800 p-5">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-400">
        Skill Match
      </h3>

      <div className="mb-4 flex items-center gap-5">
        {/* Mini gauge */}
        <svg width="72" height="72" viewBox="0 0 72 72">
          <circle cx="36" cy="36" r={radius} fill="none" stroke="#334155" strokeWidth="6" />
          <circle
            cx="36"
            cy="36"
            r={radius}
            fill="none"
            stroke={gaugeColor}
            strokeWidth="6"
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeLinecap="round"
            transform="rotate(-90 36 36)"
          />
          <text x="36" y="40" textAnchor="middle" fill="white" fontSize="13" fontWeight="bold">
            {match_pct.toFixed(0)}%
          </text>
        </svg>

        <div className="flex-1">
          <p className="text-sm font-medium text-slate-200">
            {matched.length} of {matched.length + missing.length} keywords matched
          </p>
          <p className="text-xs text-slate-500">
            Domain match:{" "}
            <span className={domain_match ? "text-emerald-400" : "text-red-400"}>
              {domain_match ? "Yes" : "No"}
            </span>
          </p>
        </div>
      </div>

      {/* Matched keywords */}
      {matched.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-semibold text-emerald-400">Matched</p>
          <div className="flex flex-wrap gap-1">
            {matched.slice(0, 12).map((kw) => (
              <span
                key={kw}
                className="rounded-full bg-emerald-900/40 px-2 py-0.5 text-xs text-emerald-300"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Missing keywords */}
      {missing.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-semibold text-amber-400">Gap</p>
          <div className="flex flex-wrap gap-1">
            {missing.slice(0, 8).map((kw) => (
              <span
                key={kw}
                className="rounded-full bg-amber-900/30 px-2 py-0.5 text-xs text-amber-300"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="mt-3 rounded-lg bg-slate-700/50 p-3">
          <p className="mb-1 text-xs font-semibold text-slate-400">Recommendations</p>
          {recommendations.map((rec, i) => (
            <p key={i} className="text-xs text-slate-400">
              • {rec}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
