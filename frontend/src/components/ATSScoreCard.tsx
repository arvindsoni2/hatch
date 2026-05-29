"use client";

import { ATSScore } from "@/lib/api";

interface ATSScoreCardProps {
  score: number;
  details?: ATSScore | null;
}

const SCORE_COLOR = {
  good:    "#3ddc97",
  warning: "#f5b950",
  poor:    "#ff6b6b",
} as const;

function scoreColor(score: number): string {
  if (score >= 80) return SCORE_COLOR.good;
  if (score >= 60) return SCORE_COLOR.warning;
  return SCORE_COLOR.poor;
}

function scoreLabel(score: number): string {
  if (score >= 80) return "Excellent";
  if (score >= 60) return "Good";
  if (score >= 40) return "Fair";
  return "Poor";
}

export function ATSScoreCard({ score, details }: ATSScoreCardProps) {
  const color = scoreColor(score);
  const radius = 36;
  const circumference = 2 * Math.PI * radius;
  const dash = (score / 100) * circumference;

  return (
    <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
        ATS Score
      </h3>

      <div className="mb-4 flex items-center gap-6">
        <svg width="96" height="96" viewBox="0 0 96 96">
          <circle cx="48" cy="48" r={radius} fill="none" stroke="var(--surface-3)" strokeWidth="8" />
          <circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeDasharray={`${dash} ${circumference - dash}`}
            strokeLinecap="round"
            transform="rotate(-90 48 48)"
            style={{ transition: "stroke-dasharray 0.6s ease" }}
          />
          <text x="48" y="52" textAnchor="middle" fill="var(--text)" fontSize="18" fontWeight="bold">
            {score}
          </text>
        </svg>

        <div>
          <p className="text-2xl font-bold" style={{ color }}>
            {scoreLabel(score)}
          </p>
          {details?.algorithmic_score != null && (
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Algorithmic: {details.algorithmic_score.toFixed(0)}% · Semantic:{" "}
              {details.semantic_score?.toFixed(0) ?? "—"}%
            </p>
          )}
        </div>
      </div>

      {details?.missing_critical && details.missing_critical.length > 0 && (
        <div className="mb-3">
          <p className="mb-1 text-xs font-semibold" style={{ color: "var(--danger)" }}>Missing Critical Keywords</p>
          <div className="flex flex-wrap gap-1">
            {details.missing_critical.map((kw) => (
              <span
                key={kw}
                className="rounded-full px-2 py-0.5 text-xs"
                style={{ background: "var(--danger-soft)", color: "var(--danger)" }}
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}

      {details?.improvement_suggestions && details.improvement_suggestions.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold" style={{ color: "var(--text-muted)" }}>Suggestions</p>
          <ul className="space-y-1">
            {details.improvement_suggestions.slice(0, 3).map((s, i) => (
              <li key={i} className="text-xs" style={{ color: "var(--text-dim)" }}>
                • {s}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
