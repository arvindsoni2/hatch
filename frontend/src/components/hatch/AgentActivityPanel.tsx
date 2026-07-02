"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  fetchAgentPerformance,
  fetchAnalyticsDashboard,
  type AgentPerformance,
  type AgentPerformanceRow,
  type AnalyticsDashboard,
} from "@/lib/api";
import { AgentBadge } from "./AgentBadge";
import { AGENT_DEFS, PIPELINE } from "./agents";

interface FunnelCounts { scout: number; scorer: number; tailor: number; coach: number }
interface TransitCounts { scout_to_scorer: number; scorer_to_tailor: number; tailor_to_coach: number }

interface NarrativeResult {
  text: string;
  chip: string | null;
  chipColor: string;
  chipBg: string;
}

function narrativeFor(
  agent: string,
  row: AgentPerformanceRow | undefined,
  funnel: FunnelCounts,
  transit: TransitCounts | undefined,
  coachSessions: number,
): NarrativeResult {
  switch (agent) {
    case "scout": {
      const boards = row?.runs_today ?? 0;
      const found = funnel.scout;
      return {
        text: found > 0
          ? `${found} roles stored across ${boards} board run${boards !== 1 ? "s" : ""} today`
          : "Scanning job boards for new roles",
        chip: found > 0 ? `${found} total` : null,
        chipColor: "var(--accent)",
        chipBg: "var(--accent-soft)",
      };
    }
    case "scorer": {
      const total = transit?.scout_to_scorer ?? 0;
      const passed = transit?.scorer_to_tailor ?? 0;
      return {
        text: total > 0
          ? `${total} roles scored — ${passed} shortlist events recorded`
          : "Waiting for new roles to score",
        chip: passed > 0 ? `${passed} passed` : null,
        chipColor: "var(--success)",
        chipBg: "var(--success-soft)",
      };
    }
    case "tailor": {
      const count = funnel.tailor;
      const queued = transit?.scorer_to_tailor ?? 0;
      const ats = row?.success_rate;
      return {
        text: count > 0
          ? `${count} applications have a completed CV + cover letter package`
          : queued > 0
            ? `${queued} shortlisted role${queued !== 1 ? "s" : ""} awaiting a completed package`
            : "Waiting for shortlisted roles",
        chip: ats != null && ats > 0 ? `${ats.toFixed(0)}% ATS` : null,
        chipColor: "var(--warning)",
        chipBg: "var(--warning-soft)",
      };
    }
    case "coach": {
      return {
        text: coachSessions > 0
          ? `${coachSessions} active or completed interview prep session${coachSessions !== 1 ? "s" : ""}`
          : "No interview sessions yet",
        chip: coachSessions > 0 ? `${coachSessions} sessions` : null,
        chipColor: "var(--purple)",
        chipBg: "var(--purple-soft)",
      };
    }
    default:
      return { text: "Running…", chip: null, chipColor: "", chipBg: "" };
  }
}

function formatTimestamp(lastRunAt: string | null): string {
  if (!lastRunAt) return "—";
  const dt = new Date(lastRunAt.endsWith("Z") ? lastRunAt : lastRunAt + "Z");
  const diffMs = Date.now() - dt.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return dt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return dt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
  if (Math.floor(diffH / 24) === 1) return "Yesterday";
  return dt.toLocaleDateString([], { weekday: "short", timeZone: "UTC" });
}

interface AgentActivityPanelProps {
  initialData: AgentPerformance | null;
  funnel?: FunnelCounts;
  transit?: TransitCounts;
  avgMatch?: number;
}

export function AgentActivityPanel({ initialData, funnel, transit, avgMatch }: AgentActivityPanelProps) {
  const router = useRouter();
  const [data, setData] = useState<AgentPerformance | null>(initialData);
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const coachSessions = funnel?.coach ?? 0;

  useEffect(() => {
    fetchAnalyticsDashboard().then(setAnalytics).catch(() => {});
    const id = setInterval(() => {
      fetchAgentPerformance().then(setData).catch(() => {});
    }, 30_000);
    return () => clearInterval(id);
  }, []);

  const [hoveredAgent, setHoveredAgent] = useState<string | null>(null);

  const agentRoutes: Record<string, string> = {
    scout: "/jobs?view=all",
    scorer: "/stream",
    tailor: "/tracker",
    coach: "/prep",
  };

  const agentMap = new Map((data?.agents ?? []).map((a) => [a.agent.toLowerCase(), a]));
  const defaultFunnel: FunnelCounts = funnel ?? { scout: 0, scorer: 0, tailor: 0, coach: 0 };

  const sorted = [...PIPELINE].sort((a, b) => {
    const ra = agentMap.get(a)?.last_run_at;
    const rb = agentMap.get(b)?.last_run_at;
    if (!ra && !rb) return 0;
    if (!ra) return 1;
    if (!rb) return -1;
    return new Date(rb).getTime() - new Date(ra).getTime();
  });

  const weeks = analytics?.trends?.weeks ?? [];
  const thisWeek = weeks.length > 0 ? weeks[weeks.length - 1] : null;
  const weekApplied = thisWeek?.new_applications ?? analytics?.stats?.applied_count ?? 0;
  const weekInterviews = thisWeek?.reached_interview ?? 0;
  const responseRate = analytics?.stats?.response_rate ?? 0;
  const responseDisplay = responseRate > 1
    ? `${responseRate.toFixed(0)}%`
    : `${(responseRate * 100).toFixed(0)}%`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>
        Agent activity · latest runs
      </span>

      {sorted.map((key) => {
        const def = AGENT_DEFS[key];
        const row = agentMap.get(key);
        const { text, chip, chipColor, chipBg } = narrativeFor(key, row, defaultFunnel, transit, coachSessions);
        const timeStr = formatTimestamp(row?.last_run_at ?? null);
        const route = agentRoutes[key];
        const isHovered = hoveredAgent === key;

        return (
          <button
            type="button"
            className="hatch-interactive"
            key={key}
            onClick={() => router.push(route)}
            onMouseEnter={() => setHoveredAgent(key)}
            onMouseLeave={() => setHoveredAgent(null)}
            style={{
              display: "flex",
              gap: 10,
              padding: "10px 12px",
              borderRadius: 10,
              background: isHovered ? "var(--surface-hover, var(--border))" : "var(--surface)",
              border: "1px solid var(--border)",
              cursor: "pointer",
              transition: "background 0.15s ease",
              width: "100%",
              textAlign: "left",
            }}
          >
            <AgentBadge agent={key as never} size={30} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 3 }}>
                <span style={{ fontSize: 12.5, fontWeight: 600, color: def.color }}>{def.name}</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{timeStr}</span>
              </div>
              <div style={{ fontSize: 12, lineHeight: 1.45, color: "var(--text-dim)" }}>{text}</div>
              {chip && (
                <span
                  style={{
                    display: "inline-block",
                    marginTop: 5,
                    fontSize: 10,
                    fontWeight: 600,
                    padding: "2px 7px",
                    borderRadius: 999,
                    color: chipColor,
                    background: chipBg,
                  }}
                >
                  {chip}
                </span>
              )}
            </div>
          </button>
        );
      })}

      {analytics && (
        <div
          style={{
            marginTop: 4,
            padding: "12px 14px",
            borderRadius: 10,
            background: "var(--surface)",
            border: "1px solid var(--border)",
          }}
        >
          <div
            style={{
              fontSize: 10.5,
              fontWeight: 700,
              color: "var(--text-muted)",
              letterSpacing: "0.05em",
              marginBottom: 10,
            }}
          >
            THIS WEEK
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 16px" }}>
            <div>
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: "var(--text)",
                  fontFamily: "var(--font-mono)",
                  lineHeight: 1,
                }}
              >
                {weekApplied}
              </div>
              <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 3 }}>Applied</div>
            </div>
            <div>
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: "var(--text)",
                  fontFamily: "var(--font-mono)",
                  lineHeight: 1,
                }}
              >
                {weekInterviews}
              </div>
              <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 3 }}>Interviews</div>
            </div>
            <div>
              <div
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: "var(--success)",
                  fontFamily: "var(--font-mono)",
                  lineHeight: 1,
                }}
              >
                {responseDisplay}
              </div>
              <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 3 }}>Response rate</div>
            </div>
            {avgMatch != null && (
              <div>
                <div
                  style={{
                    fontSize: 22,
                    fontWeight: 700,
                    color: "var(--purple)",
                    fontFamily: "var(--font-mono)",
                    lineHeight: 1,
                  }}
                >
                  {avgMatch}%
                </div>
                <div style={{ fontSize: 10.5, color: "var(--text-muted)", marginTop: 3 }}>Avg match</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
