"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  Legend,
  ReferenceLine,
  LineChart,
  Line,
} from "recharts";
import type { AnalyticsDashboard, ScoreDistributionBucket, DailyCostEntry } from "@/lib/api";

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

interface FunnelChartProps {
  stages: AnalyticsDashboard["funnel"]["stages"];
}

export function FunnelChart({ stages }: FunnelChartProps) {
  const data = stages.map((s) => ({ name: s.status, count: s.count }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} layout="vertical" margin={{ left: 60 }}>
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} />
        <Tooltip />
        <Bar dataKey="count" fill="#6366f1" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

interface TrendChartProps {
  weeks: AnalyticsDashboard["trends"]["weeks"];
}

export function TrendChart({ weeks }: TrendChartProps) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={weeks} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <XAxis
          dataKey="week_start"
          tick={{ fontSize: 10 }}
          tickFormatter={(v: string) => v.slice(5)}
        />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip />
        <Legend />
        <Area
          type="monotone"
          dataKey="new_applications"
          stroke="#6366f1"
          fill="#e0e7ff"
          name="New Applications"
        />
        <Area
          type="monotone"
          dataKey="reached_interview"
          stroke="#10b981"
          fill="#d1fae5"
          name="Reached Interview"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface SourceChartProps {
  sources: AnalyticsDashboard["sources"];
}

export function SourceBreakdownChart({ sources }: SourceChartProps) {
  if (!sources.length) {
    return (
      <p className="text-sm text-slate-400 text-center py-8">No source data yet.</p>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie
          data={sources}
          dataKey="total"
          nameKey="source"
          cx="50%"
          cy="50%"
          outerRadius={80}
          label={({ name, percent }: { name?: string; percent?: number }) =>
            `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
          labelLine
        >
          {sources.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function ScoreDistributionChart({
  buckets,
  threshold,
}: {
  buckets: ScoreDistributionBucket[];
  threshold: number;
}) {
  const data = buckets.map((b) => ({
    bucket: b.bucket,
    count: b.count,
    aboveThreshold: b.min >= threshold,
  }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip formatter={(v: number) => [v, "Jobs"]} />
        <ReferenceLine
          x={`${Math.round(threshold * 10) * 10}–${Math.round(threshold * 10) * 10 + 10}%`}
          stroke="#6366f1"
          strokeDasharray="4 2"
          label={{ value: "Threshold", fontSize: 10, fill: "#6366f1" }}
        />
        <Bar dataKey="count" radius={[3, 3, 0, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.aboveThreshold ? "#10b981" : "#cbd5e1"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

const AGENT_COLORS: Record<string, string> = {
  scout: "#6366f1",
  scorer: "#10b981",
  tailor: "#f59e0b",
  coach: "#8b5cf6",
  unknown: "#94a3b8",
};

export function DailyCostChart({ days }: { days: DailyCostEntry[] }) {
  const agents = Array.from(
    new Set(days.flatMap((d) => Object.keys(d.by_agent)))
  );
  // Recharts can't access nested keys — flatten by_agent into top-level fields
  const flatDays = days.map((d) => {
    const row: Record<string, string | number> = { date: d.date, total: d.total };
    for (const agent of agents) {
      row[agent] = d.by_agent[agent] ?? 0;
    }
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={flatDays} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `£${v.toFixed(2)}`} />
        <Tooltip formatter={(v: number, name: string) => [`£${v.toFixed(4)}`, name]} />
        <Legend />
        {agents.map((agent) => (
          <Line
            key={agent}
            type="monotone"
            dataKey={agent}
            name={agent}
            stroke={AGENT_COLORS[agent] ?? "#94a3b8"}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
