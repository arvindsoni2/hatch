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
  const gaugeColor = match_pct >= 70 ? "var(--success)" : match_pct >= 50 ? "var(--warning)" : "var(--danger)";

  return (
    <div className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
        Skill Match
      </h3>

      <div className="mb-4 flex items-center gap-5">
        <svg width="72" height="72" viewBox="0 0 72 72">
          <circle cx="36" cy="36" r={radius} fill="none" stroke="var(--surface-3)" strokeWidth="6" />
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
          <text x="36" y="40" textAnchor="middle" fill="var(--text)" fontSize="13" fontWeight="bold">
            {match_pct.toFixed(0)}%
          </text>
        </svg>

        <div className="flex-1">
          <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
            {matched.length} of {matched.length + missing.length} keywords matched
          </p>
          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            Domain match:{" "}
            <span style={{ color: domain_match ? "var(--success)" : "var(--danger)" }}>
              {domain_match ? "Yes" : "No"}
            </span>
          </p>
        </div>
      </div>

      {matched.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-semibold" style={{ color: "var(--success)" }}>Matched</p>
          <div className="flex flex-wrap gap-1">
            {matched.slice(0, 12).map((kw) => (
              <span
                key={kw}
                className="rounded-full px-2 py-0.5 text-xs"
                style={{ background: "var(--success-soft)", color: "var(--success)" }}
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {missing.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-xs font-semibold" style={{ color: "var(--warning)" }}>Gap</p>
          <div className="flex flex-wrap gap-1">
            {missing.slice(0, 8).map((kw) => (
              <span
                key={kw}
                className="rounded-full px-2 py-0.5 text-xs"
                style={{ background: "var(--warning-soft)", color: "var(--warning)" }}
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="mt-3 rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
          <p className="mb-1 text-xs font-semibold" style={{ color: "var(--text-muted)" }}>Recommendations</p>
          {recommendations.map((rec, i) => (
            <p key={i} className="text-xs" style={{ color: "var(--text-dim)" }}>
              • {rec}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
