"use client";
import { useEffect, useState } from "react";
import { fetchAgentPerformance, type AgentPerformance } from "@/lib/api";
import { AgentBadge } from "./AgentBadge";
import { AGENT_DEFS, PIPELINE } from "./agents";

function formatRelativeTime(lastRunAt: string | null): string {
  if (!lastRunAt) return "—";
  const dt = new Date(lastRunAt.endsWith("Z") ? lastRunAt : lastRunAt + "Z");
  const diffMs = Date.now() - dt.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return dt.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function AgentActivityPanel({ initialData }: { initialData: AgentPerformance | null }) {
  const [data, setData] = useState<AgentPerformance | null>(initialData);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const fresh = await fetchAgentPerformance();
        setData(fresh);
      } catch {
        // keep stale
      }
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  const agentMap = new Map(data?.agents.map((a) => [a.agent.toLowerCase(), a]));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 2,
      }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>Agent activity</span>
      </div>

      {PIPELINE.map((key) => {
        const def = AGENT_DEFS[key];
        const row = agentMap.get(key);

        return (
          <div
            key={key}
            style={{
              display: "flex",
              gap: 10,
              padding: "10px 12px",
              borderRadius: 10,
              background: "var(--surface)",
              border: "1px solid var(--border)",
            }}
          >
            <AgentBadge agent={key as never} size={30} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: def.color }}>{def.name}</span>
                {row?.last_run_at && (
                  <span style={{ fontSize: 11, color: "var(--text-muted)", flexShrink: 0 }}>
                    {formatRelativeTime(row.last_run_at)}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-muted)", marginTop: 1 }}>
                {def.role}
              </div>
              {row ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 5 }}>
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
                    {row.runs_today} run{row.runs_today !== 1 ? "s" : ""} today
                  </span>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 600,
                      padding: "1px 6px",
                      borderRadius: 999,
                      background: row.success_rate >= 95 ? "var(--success-soft)" : row.success_rate >= 80 ? "var(--warning-soft)" : "var(--danger-soft)",
                      color: row.success_rate >= 95 ? "var(--success)" : row.success_rate >= 80 ? "var(--warning)" : "var(--danger)",
                    }}
                  >
                    {row.success_rate.toFixed(0)}%
                  </span>
                  {row.last_error && (
                    <span style={{ fontSize: 10, color: "var(--danger)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                      ⚠ {row.last_error.slice(0, 40)}
                    </span>
                  )}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 5 }}>No runs recorded</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
