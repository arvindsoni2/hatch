"use client";

interface ScoreBreakdownProps {
  skillMatch: number | null;
  experienceMatch: number | null;
  rateMatch: number | null;
  locationMatch: number | null;
  overallScore: number | null;
  scoringMethod: "local" | "llm" | null;
  reasoning?: string | null;
  keywordMatches?: string[];
  keywordMisses?: string[];
}

function DimensionBar({
  label,
  value,
  isWeakest,
}: {
  label: string;
  value: number | null;
  isWeakest: boolean;
}) {
  if (value === null) return null;
  const pct = Math.round(value * 100);
  const fill =
    pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-amber-400" : "bg-red-400";

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span
          style={{ color: isWeakest ? "var(--warning)" : "var(--text-dim)" }}
          className="font-medium"
        >
          {label}
          {isWeakest && (
            <span
              data-testid="weakest-dimension"
              className="ml-1 text-[10px] font-normal"
              style={{ color: "var(--warning)" }}
            >
              ↑ weakest
            </span>
          )}
        </span>
        <span className="font-semibold tabular-nums" style={{ color: "var(--text)" }}>
          {pct}%
        </span>
      </div>
      <div
        className="h-2 w-full rounded-full overflow-hidden"
        style={{ background: "var(--surface-2)" }}
      >
        <div
          className={`h-full rounded-full transition-all ${fill}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function ScoreBreakdown({
  skillMatch,
  experienceMatch,
  rateMatch,
  locationMatch,
  overallScore,
  scoringMethod,
  reasoning,
  keywordMatches = [],
  keywordMisses = [],
}: ScoreBreakdownProps) {
  const dimensions = [
    { label: "Skill match", value: skillMatch },
    { label: "Experience", value: experienceMatch },
    { label: "Compensation", value: rateMatch },
    { label: "Location", value: locationMatch },
  ];

  const defined = dimensions.filter((d) => d.value !== null);
  const minValue = defined.length > 0 ? Math.min(...defined.map((d) => d.value!)) : null;

  const isLocal = scoringMethod === "local";
  const overallPct = overallScore !== null ? Math.round(overallScore * 100) : null;

  const showReasoning =
    reasoning && reasoning !== "local-keyword" && !isLocal;

  return (
    <div className="space-y-4">
      {/* Method badge + overall */}
      <div className="flex items-center justify-between gap-3">
        <div>
          {overallPct !== null && (
            <span
              className="text-3xl font-bold tabular-nums"
              style={{ color: "var(--text)" }}
            >
              {overallPct}%
            </span>
          )}
          <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
            overall match
          </p>
        </div>
        <span
          className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium"
          style={
            isLocal
              ? { background: "var(--surface-2)", color: "var(--text-muted)" }
              : { background: "var(--accent-soft)", color: "var(--accent)" }
          }
        >
          {isLocal ? "Quick estimate" : "AI assessment"}
        </span>
      </div>

      {/* Dimension bars */}
      <div className="space-y-3">
        {dimensions.map(({ label, value }) => (
          <DimensionBar
            key={label}
            label={label}
            value={value}
            isWeakest={value !== null && value === minValue}
          />
        ))}
      </div>

      {/* Reasoning */}
      {showReasoning && (
        <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
          {reasoning}
        </p>
      )}

      {/* Local-only note */}
      {isLocal && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Quick keyword estimate — this job hasn&apos;t had a full AI review yet.
        </p>
      )}
    </div>
  );
}
