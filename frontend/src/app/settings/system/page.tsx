"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft, RefreshCw, Download, RotateCcw, CheckCircle2,
  AlertTriangle, Clock, Loader2, Trash2, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_BASE } from "@/lib/api";

interface LLMTrace {
  id: number;
  ts: string;
  model: string;
  duration_ms: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  response_preview: string;
}

interface AgentEvent {
  id: string;
  event_type: string;
  source_agent: string | null;
  status: string;
  created_at: string;
  processed_at: string | null;
  error_message: string | null;
  payload: Record<string, unknown> | null;
}

interface EventPage {
  items: AgentEvent[];
  total: number;
}

interface CostSummary {
  total_cost_usd: number;
  by_agent: Record<string, number>;
  total_calls: number;
}

const STATUS_BADGE: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  processing: "bg-blue-100 text-blue-700",
  pending: "bg-amber-100 text-amber-700",
};

const AGENT_COLORS: Record<string, string> = {
  scout: "bg-slate-100 text-slate-700",
  scorer: "bg-blue-100 text-blue-700",
  tailor: "bg-indigo-100 text-indigo-700",
  coach: "bg-purple-100 text-purple-700",
};

export default function SystemLogPage() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState({ agent: "", status: "", type: "" });
  const [costs, setCosts] = useState<CostSummary | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [traces, setTraces] = useState<LLMTrace[]>([]);
  const [expandedTrace, setExpandedTrace] = useState<number | null>(null);
  const traceTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const LIMIT = 50;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: String(LIMIT),
        offset: String(offset),
      });
      if (filter.agent) params.set("source_agent", filter.agent);
      if (filter.status) params.set("status", filter.status);
      if (filter.type) params.set("event_type", filter.type);
      const res = await fetch(`${API_BASE}/api/events?${params}`);
      const data: EventPage = await res.json();
      setEvents(data.items);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [offset, filter]);

  const loadCosts = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/events/costs?days=30`);
      setCosts(await res.json());
    } catch {
      // cost endpoint not critical
    }
  }, []);

  const loadTraces = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/debug/llm-traces`);
      if (res.ok) setTraces(await res.json());
    } catch {
      // non-critical
    }
  }, []);

  const clearTraces = async () => {
    await fetch(`${API_BASE}/api/debug/llm-traces`, { method: "DELETE" });
    setTraces([]);
    setExpandedTrace(null);
  };

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void loadCosts(); }, [loadCosts]);
  useEffect(() => {
    void loadTraces();
    traceTimerRef.current = setInterval(() => { void loadTraces(); }, 10_000);
    return () => { if (traceTimerRef.current) clearInterval(traceTimerRef.current); };
  }, [loadTraces]);

  const retryEvent = async (id: string) => {
    setRetrying(id);
    try {
      await fetch(`${API_BASE}/api/events/${id}/retry`, { method: "POST" });
      await load();
    } finally {
      setRetrying(null);
    }
  };

  const exportCsv = () => {
    const rows = [
      ["id", "timestamp", "agent", "event_type", "status", "error"].join(","),
      ...events.map((e) =>
        [e.id, e.created_at, e.source_agent ?? "", e.event_type, e.status, (e.error_message ?? "").replace(/,/g, ";")].join(",")
      ),
    ].join("\n");
    const blob = new Blob([rows], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `jobpilot-events-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
  };

  return (
    <div className="space-y-6">
      {/* Back nav */}
      <div className="flex items-center justify-between">
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700"
        >
          <ArrowLeft className="h-4 w-4" /> Settings
        </Link>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download className="h-3.5 w-3.5 mr-1" /> Export CSV
          </Button>
        </div>
      </div>

      <h1 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>System Event Log</h1>

      {/* Cost summary */}
      {costs && costs.total_calls > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
            <p className="text-xs text-slate-500">Total LLM cost (30d)</p>
            <p className="text-xl font-bold" style={{ color: 'var(--text)' }}>${costs.total_cost_usd.toFixed(4)}</p>
            <p className="text-xs text-slate-400">USD</p>
          </div>
          <div className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
            <p className="text-xs text-slate-500">LLM calls (30d)</p>
            <p className="text-xl font-bold" style={{ color: 'var(--text)' }}>{costs.total_calls.toLocaleString()}</p>
          </div>
          {Object.entries(costs.by_agent).map(([agent, cost]) => (
            <div key={agent} className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
              <p className="text-xs text-slate-500 capitalize">{agent} agent cost</p>
              <p className="text-xl font-bold" style={{ color: 'var(--text)' }}>${cost.toFixed(4)}</p>
            </div>
          ))}
        </div>
      )}

      {/* LLM Traces */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-slate-700">LLM Call Traces</h2>
            <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-500">
              last {traces.length} / 100 · auto-refreshes every 10s
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void loadTraces()}>
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
            <Button variant="outline" size="sm" onClick={() => void clearTraces()} disabled={traces.length === 0}>
              <Trash2 className="h-3.5 w-3.5 mr-1" /> Clear
            </Button>
          </div>
        </div>

        {traces.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-400">
            No traces yet — LLM calls will appear here as agents run.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-500">
                <th className="px-4 py-2 text-left font-medium">Time</th>
                <th className="px-4 py-2 text-left font-medium">Model</th>
                <th className="px-4 py-2 text-right font-medium">Latency</th>
                <th className="px-4 py-2 text-right font-medium">Tokens in</th>
                <th className="px-4 py-2 text-right font-medium">Tokens out</th>
                <th className="px-4 py-2 text-right font-medium">Cost</th>
                <th className="px-4 py-2 text-left font-medium">Preview</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => {
                const latencyBadge =
                  t.duration_ms < 2_000
                    ? "bg-green-100 text-green-700"
                    : t.duration_ms < 10_000
                    ? "bg-amber-100 text-amber-700"
                    : "bg-red-100 text-red-700";
                const isExpanded = expandedTrace === t.id;
                return (
                  <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50/60">
                    <td className="px-4 py-2 text-xs text-slate-400 whitespace-nowrap">
                      {formatDistanceToNow(new Date(t.ts), { addSuffix: true })}
                    </td>
                    <td className="px-4 py-2">
                      <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-xs font-medium text-indigo-700">
                        {t.model}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold tabular-nums ${latencyBadge}`}>
                        {t.duration_ms >= 1_000
                          ? `${(t.duration_ms / 1_000).toFixed(1)}s`
                          : `${t.duration_ms}ms`}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right text-xs tabular-nums text-slate-500">
                      {t.tokens_in.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right text-xs tabular-nums text-slate-500">
                      {t.tokens_out.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right text-xs tabular-nums text-slate-400">
                      {t.cost_usd > 0 ? `$${t.cost_usd.toFixed(5)}` : "—"}
                    </td>
                    <td className="px-4 py-2 max-w-xs">
                      {t.response_preview ? (
                        <button
                          onClick={() => setExpandedTrace(isExpanded ? null : t.id)}
                          className="text-left text-xs text-slate-500 hover:text-slate-700"
                        >
                          {isExpanded
                            ? t.response_preview
                            : t.response_preview.slice(0, 80) + (t.response_preview.length > 80 ? "…" : "")}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-300">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {[
          { key: "agent", label: "Agent", options: ["", "scout", "scorer", "tailor", "coach"] },
          { key: "status", label: "Status", options: ["", "completed", "failed", "pending", "processing"] },
        ].map(({ key, label, options }) => (
          <select
            key={key}
            value={filter[key as keyof typeof filter]}
            onChange={(e) => { setOffset(0); setFilter((f) => ({ ...f, [key]: e.target.value })); }}
            className="rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500" style={{ borderColor: 'var(--border)', background: 'var(--surface-2)', color: 'var(--text-dim)' }}
          >
            {options.map((o) => (
              <option key={o} value={o}>
                {o ? `${label}: ${o}` : `All ${label.toLowerCase()}s`}
              </option>
            ))}
          </select>
        ))}
        <p className="ml-auto self-center text-xs text-slate-400">{total.toLocaleString()} total events</p>
      </div>

      {/* Table */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        ) : events.length === 0 ? (
          <p className="py-16 text-center text-sm text-slate-400">No events found.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500">
                <th className="px-4 py-3 text-left font-medium">Timestamp</th>
                <th className="px-4 py-3 text-left font-medium">Agent</th>
                <th className="px-4 py-3 text-left font-medium">Event</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Error</th>
                <th className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">
                    {formatDistanceToNow(new Date(e.created_at), { addSuffix: true })}
                  </td>
                  <td className="px-4 py-2.5">
                    {e.source_agent && (
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${AGENT_COLORS[e.source_agent] ?? "bg-slate-100 text-slate-600"}`}>
                        {e.source_agent}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-slate-700 font-mono">{e.event_type}</td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_BADGE[e.status] ?? "bg-slate-100 text-slate-600"}`}>
                      {e.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 max-w-xs">
                    {e.error_message && (
                      <span className="text-xs text-red-600 truncate block" title={e.error_message}>
                        {e.error_message.slice(0, 80)}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {e.status === "failed" && (
                      <button
                        onClick={() => void retryEvent(e.id)}
                        disabled={retrying === e.id}
                        className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline disabled:opacity-50"
                      >
                        {retrying === e.id ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <RotateCcw className="h-3 w-3" />
                        )}
                        Retry
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > LIMIT && (
        <div className="flex items-center justify-between text-sm text-slate-500">
          <span>
            Showing {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + LIMIT >= total}
              onClick={() => setOffset((o) => o + LIMIT)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
