"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import {
  Search, Brain, FileText, CheckCircle2, XCircle,
  AlertTriangle, ChevronDown, ChevronUp, ArrowRight, Loader2,
} from "lucide-react";
import { fetchActivity, type ActivityItem } from "@/lib/api";

const AGENT_ICONS: Record<string, React.ReactNode> = {
  scout: <Search className="h-3.5 w-3.5" />,
  scorer: <Brain className="h-3.5 w-3.5" />,
  tailor: <FileText className="h-3.5 w-3.5" />,
  human: <CheckCircle2 className="h-3.5 w-3.5" />,
};

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-500",
  failed: "bg-red-500",
  processing: "bg-blue-500",
  pending: "bg-amber-400",
};

function ActivityRow({ item }: { item: ActivityItem }) {
  const [expanded, setExpanded] = useState(false);
  const dotColor = STATUS_COLORS[item.status] ?? "bg-slate-300";
  const icon = AGENT_ICONS[item.agent] ?? <AlertTriangle className="h-3.5 w-3.5" />;
  const hasCost = item.cost_estimate != null && item.cost_estimate > 0;
  const hasDetail = !!item.detail;

  return (
    <div className="flex gap-3 py-2.5 border-b border-slate-100 last:border-0">
      {/* Timeline dot */}
      <div className="relative flex flex-col items-center pt-1">
        <span className={`h-2 w-2 rounded-full shrink-0 ${dotColor}`} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-600">
              {icon}
              {item.agent}
            </span>
            {item.job_id ? (
              <Link
                href={`/jobs/${item.job_id}`}
                className="text-sm text-slate-800 hover:text-brand-600 hover:underline font-medium line-clamp-1"
              >
                {item.title}
              </Link>
            ) : (
              <span className="text-sm text-slate-800 font-medium line-clamp-1">{item.title}</span>
            )}
          </div>
          <span className="text-xs text-slate-400 shrink-0">
            {formatDistanceToNow(new Date(item.timestamp), { addSuffix: true })}
          </span>
        </div>

        {/* Cost + expand button */}
        <div className="mt-0.5 flex items-center gap-2">
          {hasCost && (
            <span className="text-xs text-slate-400">
              ~${(item.cost_estimate! * 100).toFixed(3)}¢
              {item.model_used && <> · {item.model_used}</>}
            </span>
          )}
          {item.status === "failed" && (
            <span className="text-xs text-red-500 font-medium">Failed</span>
          )}
          {hasDetail && (
            <button
              onClick={() => setExpanded((p) => !p)}
              className="text-xs text-brand-600 hover:underline flex items-center gap-0.5"
            >
              {expanded ? (
                <><ChevronUp className="h-3 w-3" /> hide</>
              ) : (
                <><ChevronDown className="h-3 w-3" /> reasoning</>
              )}
            </button>
          )}
        </div>

        {expanded && item.detail && (
          <p className="mt-1.5 text-xs text-slate-500 bg-slate-50 rounded px-2 py-1.5 leading-relaxed">
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
    } catch (e) {
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
      <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading activity…
      </div>
    );
  }

  if (error) return null;
  if (items.length === 0) {
    return (
      <p className="text-sm text-slate-400 py-3">
        No agent activity in the last {hours} hours.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Activity</h2>
        <Link
          href="/settings?tab=system"
          className="flex items-center gap-1 text-xs text-brand-600 hover:underline"
        >
          Full log <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white px-4 shadow-sm divide-y divide-slate-100">
        {items.map((item) => (
          <ActivityRow key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
