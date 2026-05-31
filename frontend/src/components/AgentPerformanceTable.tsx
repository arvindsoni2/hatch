"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { fetchAgentPerformance, type AgentPerformance } from "@/lib/api";

function formatLastRun(lastRunAt: string | null): string {
  if (!lastRunAt) return "—";
  const dt = new Date(lastRunAt.endsWith("Z") ? lastRunAt : lastRunAt + "Z");
  return dt.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function AgentPerformanceTable({ initialData }: { initialData: AgentPerformance | null }) {
  const [data, setData] = useState<AgentPerformance | null>(initialData);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  const refresh = async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const fresh = await fetchAgentPerformance();
      setData(fresh);
      setLastUpdated(new Date());
    } catch {
      // keep stale data
    } finally {
      if (showSpinner) setRefreshing(false);
    }
  };

  useEffect(() => {
    const interval = setInterval(() => refresh(false), 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Agent Performance</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Updated {lastUpdated.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
          </span>
          <button
            onClick={() => refresh(true)}
            disabled={refreshing}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs"
            style={{ background: "var(--surface-2)", color: "var(--text-dim)", border: "1px solid var(--border)" }}
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>
      {(!data || data.agents.length === 0) ? (
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>No agent activity recorded yet.</p>
      ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs border-b" style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}>
              <th className="text-left py-2 pr-4 font-medium">Agent</th>
              <th className="text-right py-2 px-4 font-medium">Today</th>
              <th className="text-right py-2 px-4 font-medium">This week</th>
              <th className="text-right py-2 px-4 font-medium">Success rate</th>
              <th className="text-left py-2 pl-4 font-medium">Last run</th>
              <th className="text-left py-2 pl-4 font-medium">Last error</th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((a) => (
              <tr key={a.agent} style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-dim)" }}>
                <td className="py-2 pr-4 font-medium capitalize">{a.agent}</td>
                <td className="py-2 px-4 text-right tabular-nums">{a.runs_today}</td>
                <td className="py-2 px-4 text-right tabular-nums">{a.runs_this_week}</td>
                <td className="py-2 px-4 text-right">
                  <span
                    className="font-medium"
                    style={{ color: a.success_rate >= 95 ? "var(--success)" : a.success_rate >= 80 ? "var(--warning)" : "var(--danger)" }}
                  >
                    {a.success_rate.toFixed(1)}%
                  </span>
                </td>
                <td className="py-2 pl-4 text-xs" style={{ color: "var(--text-muted)" }}>
                  {formatLastRun(a.last_run_at)}
                </td>
                <td className="py-2 pl-4 text-xs max-w-xs truncate" style={{ color: "var(--danger)" }}>
                  {a.last_error ? a.last_error.slice(0, 80) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
    </div>
  );
}
