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
} from "recharts";
import type { AnalyticsDashboard } from "@/lib/api";

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
