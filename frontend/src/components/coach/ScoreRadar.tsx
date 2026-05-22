"use client";

interface ScoreRadarProps {
  scores: Record<string, number>;
  size?: number;
}

const LABEL_MAP: Record<string, string> = {
  relevance: "Relevance",
  star_structure: "STAR",
  technical_depth: "Technical",
  conciseness: "Conciseness",
  communication: "Comms",
  impact_metrics: "Impact",
};

export function ScoreRadar({ scores, size = 220 }: ScoreRadarProps) {
  const keys = Object.keys(LABEL_MAP).filter((k) => k in scores);
  const n = keys.length;
  if (n === 0) return null;

  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.35;
  const labelRadius = size * 0.47;
  const maxScore = 10;

  const toXY = (i: number, r: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  };

  // Grid levels
  const gridLevels = [2, 4, 6, 8, 10];

  // Data polygon
  const dataPoints = keys.map((k, i) =>
    toXY(i, (scores[k] / maxScore) * radius)
  );
  const dataPath = dataPoints
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ") + " Z";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* Grid */}
      {gridLevels.map((level) => {
        const pts = keys.map((_, i) => toXY(i, (level / maxScore) * radius));
        const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z";
        return (
          <path
            key={level}
            d={path}
            fill="none"
            stroke="#334155"
            strokeWidth="1"
          />
        );
      })}

      {/* Spokes */}
      {keys.map((_, i) => {
        const outer = toXY(i, radius);
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={outer.x.toFixed(1)}
            y2={outer.y.toFixed(1)}
            stroke="#334155"
            strokeWidth="1"
          />
        );
      })}

      {/* Data polygon */}
      <path d={dataPath} fill="#6366f133" stroke="#6366f1" strokeWidth="2" />

      {/* Data points */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#6366f1" />
      ))}

      {/* Labels */}
      {keys.map((k, i) => {
        const pos = toXY(i, labelRadius);
        return (
          <text
            key={k}
            x={pos.x.toFixed(1)}
            y={pos.y.toFixed(1)}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="10"
            fill="#94a3b8"
          >
            {LABEL_MAP[k]}
          </text>
        );
      })}
    </svg>
  );
}
