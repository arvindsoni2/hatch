"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import {
  Search, Brain, FileText, CheckCircle2,
  AlertTriangle, ChevronDown, ChevronUp, ArrowRight, Loader2,
} from "lucide-react";
import { fetchActivity, type ActivityItem } from "@/lib/api";

const AGENT_ICONS: Record<string, React.ReactNode> = {
  scout:   <Search    className="h-3.5 w-3.5" />,
  scorer:  <Brain     className="h-3.5 w-3.5" />,
  tailor:  <FileText  className="h-3.5 w-3.5" />,
  human:   <CheckCircle2 className="h-3.5 w-3.5" />,
};

function statusDot(status: string): React.CSSProperties {
  const color =
    status === "completed"  ? "var(--success)"  :
    status === "failed"     ? "var(--danger)"   :
    status === "processing" ? "var(--accent)"   :
                              "var(--warning)";
  return { background: color };
}

function ActivityRow({ item }: { item: ActivityItem }) {
  const [expanded, setExpanded] = useState(false);
  const icon = AGENT_ICONS[item.agent] ?? <AlertTriangle className="h-3.5 w-3.5" />;
  const hasCost   = item.cost_estimate != null && item.cost_estimate > 0;
  const hasDetail = !!item.detail;

  return (
    <div
      className="flex gap-3 py-2.5"
      style={{ borderBottom: "1px solid var(--border)" }}
    >
      {/* Timeline dot */}
      <div className="flex flex-col items-center pt-1">
        <span className="h-2 w-2 rounded-full shrink-0" style={statusDot(item.status)} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            {/* Agent chip */}
            <span
              className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium"
              style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
            >
              {icon}
              {item.agent}
            </span>
            {/* Title — link if has job_id */}
            {item.job_id ? (
              <Link
                href={`/jobs/${item.job_id}`}
                className="text-sm font-medium line-clamp-1 hover:underline"
                style={{ color: "var(--text)" }}
              >
                {item.title}
              </Link>
            ) : (
              <span className="text-sm font-medium line-clamp-1" style={{ color: "var(--text)" }}>
                {item.title}
              </span>
            )}
          </div>
          <span className="text-xs shrink-0" style={{ color: "var(--text-muted)" }}>
            {formatDistanceToNow(new Date(item.timestamp), { addSuffix: true })}
          </span>
        </div>

        {/* Sub-row: cost / failed label / reasoning toggle */}
        <div className="mt-0.5 flex items-center gap-2">
          {hasCost && (
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              ~${(item.cost_estimate! * 100).toFixed(3)}¢
              {item.model_used && <> · {item.model_used}</>}
            </span>
          )}
          {item.status === "failed" && (
            <span className="text-xs font-medium" style={{ color: "var(--danger)" }}>
              Failed
            </span>
          )}
          {hasDetail && (
            <button
              onClick={() => setExpanded((p) => !p)}
              className="flex items-center gap-0.5 text-xs hover:underline"
              style={{ color: "var(--accent)" }}
            >
              {expanded ? (
                <><ChevronUp className="h-3 w-3" /> hide</>
              ) : (
                <><ChevronDown className="h-3 w-3" /> reasoning</>
              )}
            </button>
          )}
        </div>

        {/* Expanded detail */}
        {expanded && item.detail && (
          <p
            className="mt-1.5 text-xs rounded px-2 py-1.5 leading-relaxed"
            style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
          >
            {item.detail}
          </p>
        )}
      </div>
    </div>
  );
}

export function ActivityTimeline({ hours = 24 }: { hours?: number }) {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchActivity(20, hours);
      setItems(data.items);
      setError(null);
    } catch {
      setError("Could not load activity");
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), 30_000);
    return () => clearInterval(timer);
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm py-4" style={{ color: "var(--text-muted)" }}>
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading activity…
      </div>
    );
  }

  if (error) return null;

  if (items.length === 0) {
    return (
      <p className="text-sm py-3" style={{ color: "var(--text-muted)" }}>
        No agent activity in the last {hours} hours.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>Activity</h2>
        {/* "Full log" → analytics shows agent performance table + event history */}
        <Link
          href="/analytics"
          className="flex items-center gap-1 text-xs hover:underline"
          style={{ color: "var(--accent)" }}
        >
          Full log <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      <div
        className="rounded-xl px-4"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        {items.map((item, i) => (
          <div key={item.id} style={i === items.length - 1 ? { borderBottom: "none" } : {}}>
            <ActivityRow item={item} />
          </div>
        ))}
      </div>
    </div>
  );
}
