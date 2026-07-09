"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft, RefreshCw, Download, RotateCcw,
  Loader2, Trash2, Zap, Server, Activity, Cpu, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_BASE, getSystemCapabilities } from "@/lib/api";
import type { BackendCapabilityStatus, SystemCapabilities } from "@/lib/api";
import {
  LEGACY_ONBOARDING_STORAGE_KEY,
  ONBOARDING_STORAGE_KEY,
} from "@/lib/onboardingDraft";

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

interface RuntimeService {
  name: string;
  status: "online" | "degraded" | "offline";
  detail: string;
  latency_ms: number;
}

interface RuntimeStatus {
  services: RuntimeService[];
  checked_at: number;
}

interface SetupResetPreview {
  mode: "onboarding" | "demo" | "factory";
  can_apply: boolean;
  deletes: string[];
  preserves: string[];
  counts: {
    database: Record<string, number>;
    files: Record<string, number>;
  };
  requires_confirmation: boolean;
  fallback_command?: string | null;
  warning?: string;
}

const STATUS_BADGE: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
  processing: "bg-blue-100 text-blue-700",
  pending: "bg-amber-100 text-amber-700",
};

const AGENT_COLORS: Record<string, string> = {
  scout: "bg-surface-2 text-fg",
  scorer: "bg-blue-100 text-blue-700",
  tailor: "bg-indigo-100 text-indigo-700",
  coach: "bg-purple-100 text-purple-700",
};

const SERVICE_LABELS: Record<string, { label: string; icon: ReactNode }> = {
  backend: { label: "Backend API", icon: <Server className="h-4 w-4" aria-hidden="true" /> },
  "llm-primary": { label: "Primary LLM", icon: <Cpu className="h-4 w-4" aria-hidden="true" /> },
  "llm-triage": { label: "Triage LLM", icon: <Zap className="h-4 w-4" aria-hidden="true" /> },
};

const CAPABILITY_ROWS: Array<{
  key: keyof SystemCapabilities["capabilities"];
  label: string;
  action?: string;
}> = [
  { key: "core_backend", label: "Core backend" },
  {
    key: "browser_automation",
    label: "Browser automation",
    action: "Enable browser automation from your terminal:",
  },
  {
    key: "local_embeddings",
    label: "Local embeddings",
    action: "Enable local embeddings from your terminal:",
  },
  {
    key: "perception_advanced_coach",
    label: "Perception/advanced coach extras",
    action: "Enable all optional backend capabilities from your terminal:",
  },
];

function money(amount: number): string {
  if (amount === 0) return "$0.00";
  if (amount < 0.01) return `$${amount.toFixed(5)}`;
  return `$${amount.toFixed(2)}`;
}

function serviceTone(status: RuntimeService["status"]) {
  if (status === "online") return { text: "var(--success)", bg: "var(--success-soft)", label: "Online" };
  if (status === "degraded") return { text: "var(--warning)", bg: "var(--warning-soft)", label: "Degraded" };
  return { text: "var(--danger)", bg: "var(--danger-soft)", label: "Offline" };
}

function capabilityTone(capability: BackendCapabilityStatus) {
  if (capability.available) {
    return { text: "var(--success)", bg: "var(--success-soft)", label: "Installed" };
  }
  if (capability.configured) {
    return { text: "var(--warning)", bg: "var(--warning-soft)", label: "Configured, not installed" };
  }
  return { text: "var(--text-dim)", bg: "var(--surface-2)", label: "Not installed" };
}

export default function SystemLogPage() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState({ agent: "", status: "", type: "" });
  const [costs, setCosts] = useState<CostSummary | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null);
  const [capabilitiesError, setCapabilitiesError] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [traces, setTraces] = useState<LLMTrace[]>([]);
  const [expandedTrace, setExpandedTrace] = useState<number | null>(null);
  const [resetPreview, setResetPreview] = useState<SetupResetPreview | null>(null);
  const [resetStatus, setResetStatus] = useState("");
  const [resetBusy, setResetBusy] = useState(false);
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

  const loadRuntime = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/debug/runtime-status`);
      if (res.ok) setRuntime(await res.json());
    } catch {
      // runtime status is advisory
    }
  }, []);

  const loadCapabilities = useCallback(async () => {
    try {
      const data = await getSystemCapabilities();
      setCapabilities(data);
      setCapabilitiesError(false);
    } catch {
      setCapabilitiesError(true);
    }
  }, []);

  const clearTraces = async () => {
    await fetch(`${API_BASE}/api/debug/llm-traces`, { method: "DELETE" });
    setTraces([]);
    setExpandedTrace(null);
  };

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void loadCosts(); }, [loadCosts]);
  useEffect(() => { void loadRuntime(); }, [loadRuntime]);
  useEffect(() => { void loadCapabilities(); }, [loadCapabilities]);
  useEffect(() => {
    void loadTraces();
    traceTimerRef.current = setInterval(() => {
      void loadTraces();
      void loadRuntime();
    }, 10_000);
    return () => { if (traceTimerRef.current) clearInterval(traceTimerRef.current); };
  }, [loadRuntime, loadTraces]);

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

  const previewOnboardingReset = async () => {
    setResetBusy(true);
    setResetStatus("");
    try {
      const response = await fetch(`${API_BASE}/api/setup/reset/preview?mode=onboarding`);
      if (!response.ok) throw new Error(await response.text());
      setResetPreview(await response.json());
    } catch {
      setResetStatus("Could not load reset preview.");
    } finally {
      setResetBusy(false);
    }
  };

  const applyOnboardingReset = async () => {
    setResetBusy(true);
    setResetStatus("");
    try {
      const response = await fetch(`${API_BASE}/api/setup/reset/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "onboarding", confirmation: "RESET" }),
      });
      if (!response.ok) throw new Error(await response.text());
      try {
        window.localStorage.removeItem(ONBOARDING_STORAGE_KEY);
        window.localStorage.removeItem(LEGACY_ONBOARDING_STORAGE_KEY);
        window.sessionStorage.clear();
      } catch {
        // Browser storage cleanup is best-effort; backend reset is authoritative.
      }
      setResetStatus("Onboarding reset complete.");
      setResetPreview(null);
      await Promise.allSettled([load(), loadTraces(), loadRuntime(), loadCapabilities()]);
    } catch {
      setResetStatus("Could not apply onboarding reset.");
    } finally {
      setResetBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Back nav */}
      <div className="flex items-center justify-between">
        <Link
          href="/today"
          className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"
        >
          <ArrowLeft className="h-4 w-4" /> Today
        </Link>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { void load(); void loadRuntime(); void loadTraces(); void loadCapabilities(); }}>
            <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download className="h-3.5 w-3.5 mr-1" /> Export CSV
          </Button>
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--text)' }}>System Logs</h1>
        <p className="mt-1 text-sm text-muted">
          Runtime health, LLM calls, and agent events from the local Hatch stack.
        </p>
      </div>

      {/* Backend capabilities */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
        <div className="flex flex-col gap-3 border-b border-border bg-surface-2 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-fg">Backend capabilities</h2>
            <p className="mt-1 text-xs text-muted">
              Hatch installs the lightweight backend by default. Some advanced features need optional backend capabilities.
            </p>
          </div>
          {capabilities && (
            <div className="grid grid-cols-2 gap-2 text-xs sm:min-w-64">
              <div className="rounded-lg px-3 py-2" style={{ background: "var(--surface)" }}>
                <p className="text-muted">Backend profile</p>
                <p className="mt-0.5 font-semibold text-fg">{capabilities.backend_profile}</p>
              </div>
              <div className="rounded-lg px-3 py-2" style={{ background: "var(--surface)" }}>
                <p className="text-muted">AI mode</p>
                <p className="mt-0.5 font-semibold text-fg">{capabilities.ai_mode}</p>
              </div>
            </div>
          )}
        </div>

        {capabilitiesError ? (
          <div className="flex items-start gap-2 px-4 py-4">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-500" aria-hidden="true" />
            <div>
              <p className="text-sm font-medium text-fg">Capability status is temporarily unavailable.</p>
              <p className="mt-1 text-xs text-muted">System logs and runtime diagnostics are still available.</p>
            </div>
          </div>
        ) : capabilities ? (
          <div className="divide-y divide-border">
            {CAPABILITY_ROWS.map((row) => {
              const capability = capabilities.capabilities[row.key];
              const tone = capabilityTone(capability);
              return (
                <div key={row.key} className="grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-fg">{row.label}</p>
                      <span className="rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: tone.bg, color: tone.text }}>
                        {tone.label}
                      </span>
                    </div>
                    {capability.reason && (
                      <p className="mt-1 text-xs text-muted">{capability.reason}</p>
                    )}
                  </div>
                  {row.action && capability.enable_command && (
                    <div className="min-w-0 rounded-lg px-3 py-2 text-xs" style={{ background: "var(--surface-2)" }}>
                      <p className="text-muted">{row.action}</p>
                      <code className="mt-1 block whitespace-normal break-words font-mono font-semibold text-fg">
                        {capability.enable_command}
                      </code>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 px-4 py-4 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Checking backend capabilities...
          </div>
        )}
      </div>

      {/* Setup reset */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
        <div className="flex flex-col gap-3 border-b border-border bg-surface-2 px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-sm font-semibold text-fg">Workspace reset</h2>
            <p className="mt-1 text-xs text-muted">
              Restart onboarding and clear stale workspace data while preserving app-lock and host-owned secrets.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void previewOnboardingReset()} disabled={resetBusy}>
            <RotateCcw className="h-3.5 w-3.5 mr-1" /> Preview onboarding reset
          </Button>
        </div>
        <div className="grid gap-4 px-4 py-4 md:grid-cols-[minmax(0,1fr)_auto]">
          <div>
            <p className="text-sm font-medium text-fg">Safe local reset</p>
            <p className="mt-1 text-xs text-muted">
              This clears roles, applications, agent activity, generated files, uploads, and Master CV/profile data. It keeps <code>api_keys.env</code> unless you use the host CLI with an explicit secret-delete option.
            </p>
            {resetStatus ? <p className="mt-3 text-sm font-medium text-fg" role="status">{resetStatus}</p> : null}
            {resetPreview ? (
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
                  <p className="text-xs font-semibold text-fg">Will delete</p>
                  <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-xs text-muted">
                    {resetPreview.deletes.slice(0, 16).map((item) => <li key={`delete-${item}`}>{item}</li>)}
                  </ul>
                </div>
                <div className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}>
                  <p className="text-xs font-semibold text-fg">Will preserve</p>
                  <ul className="mt-2 space-y-1 text-xs text-muted">
                    {resetPreview.preserves.map((item) => <li key={`preserve-${item}`}>{item}</li>)}
                  </ul>
                </div>
              </div>
            ) : null}
          </div>
          <div className="flex flex-col gap-2 md:w-56">
            <Button
              variant="destructive"
              disabled={resetBusy || !resetPreview?.can_apply}
              onClick={() => void applyOnboardingReset()}
            >
              <Trash2 className="h-4 w-4" /> Reset onboarding data
            </Button>
            <Link className="text-center text-xs font-medium text-muted hover:text-fg" href="/onboarding">
              Open onboarding
            </Link>
          </div>
        </div>
      </div>

      {/* Runtime health */}
      <div className="grid gap-3 md:grid-cols-3">
        {(runtime?.services ?? [
          { name: "backend", status: "degraded" as const, detail: "Checking…", latency_ms: 0 },
          { name: "llm-primary", status: "degraded" as const, detail: "Checking…", latency_ms: 0 },
          { name: "llm-triage", status: "degraded" as const, detail: "Checking…", latency_ms: 0 },
        ]).map((service) => {
          const meta = SERVICE_LABELS[service.name] ?? { label: service.name, icon: <Activity className="h-4 w-4" aria-hidden="true" /> };
          const tone = serviceTone(service.status);
          return (
            <div key={service.name} className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="grid h-8 w-8 place-items-center rounded-lg" style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}>
                    {meta.icon}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold truncate" style={{ color: "var(--text)" }}>{meta.label}</p>
                    <p className="text-xs text-muted truncate">{service.detail}</p>
                  </div>
                </div>
                <span className="rounded-full px-2 py-0.5 text-xs font-semibold" style={{ background: tone.bg, color: tone.text }}>
                  {tone.label}
                </span>
              </div>
              <div className="mt-3 flex items-center gap-1 text-xs text-muted tabular-nums">
                <Activity className="h-3.5 w-3.5" aria-hidden="true" />
                {service.latency_ms > 0 ? `${service.latency_ms} ms probe` : "local process"}
              </div>
            </div>
          );
        })}
      </div>

      {/* Cost summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
            <p className="text-xs text-muted">Total LLM cost (30d)</p>
            <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--text)' }}>{money(costs?.total_cost_usd ?? 0)}</p>
            <p className="text-xs text-muted">USD</p>
          </div>
          <div className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
            <p className="text-xs text-muted">LLM calls (30d)</p>
            <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--text)' }}>{(costs?.total_calls ?? traces.length).toLocaleString()}</p>
            <p className="text-xs text-muted">{costs ? "tracked costs" : "recent trace buffer"}</p>
          </div>
          {Object.entries(costs?.by_agent ?? {}).slice(0, 2).map(([agent, cost]) => (
            <div key={agent} className="rounded-xl p-4 shadow-sm" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
              <p className="text-xs text-muted capitalize">{agent} agent cost</p>
              <p className="text-xl font-bold tabular-nums" style={{ color: 'var(--text)' }}>{money(cost)}</p>
            </div>
          ))}
          {(!costs || Object.keys(costs.by_agent).length === 0) && (
            <div className="rounded-xl p-4 shadow-sm sm:col-span-2" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
              <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-500" aria-hidden="true" />
                <div>
                  <p className="text-xs font-medium" style={{ color: "var(--text)" }}>No cost breakdown yet</p>
                  <p className="mt-1 text-xs text-muted">Costs and per-agent spend populate after LLM-backed agent runs.</p>
                </div>
              </div>
            </div>
          )}
      </div>

      {/* LLM Traces */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-2">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-500" />
            <h2 className="text-sm font-semibold text-fg">LLM Call Traces</h2>
            <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">
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

        {traces.length > 0 && (() => {
          const byModel: Record<string, { durations: number[]; tokensOut: number[]; cost: number }> = {};
          for (const t of traces) {
            if (!byModel[t.model]) byModel[t.model] = { durations: [], tokensOut: [], cost: 0 };
            byModel[t.model].durations.push(t.duration_ms);
            byModel[t.model].tokensOut.push(t.tokens_out);
            byModel[t.model].cost += t.cost_usd;
          }
          const rows = Object.entries(byModel).map(([model, d]) => {
            const sorted = [...d.durations].sort((a, b) => a - b);
            const avg = sorted.reduce((s, v) => s + v, 0) / sorted.length;
            const median = sorted[Math.floor(sorted.length / 2)];
            const avgToksOut = d.tokensOut.reduce((s, v) => s + v, 0) / d.tokensOut.length;
            const tps = avg > 0 ? (avgToksOut / avg) * 1000 : 0;
            return { model, calls: sorted.length, avg, median, tps, cost: d.cost };
          });
          return (
            <div className="border-b border-border px-4 py-3">
              <p className="text-xs font-semibold text-muted mb-2 uppercase tracking-wide">Per-model summary</p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-muted">
                    <th className="text-left font-medium pb-1.5">Model</th>
                    <th className="text-right font-medium pb-1.5">Calls</th>
                    <th className="text-right font-medium pb-1.5">Avg latency</th>
                    <th className="text-right font-medium pb-1.5">Median latency</th>
                    <th className="text-right font-medium pb-1.5">Tokens/sec</th>
                    <th className="text-right font-medium pb-1.5">Total cost</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map(r => (
                    <tr key={r.model} className="border-t border-border/50">
                      <td className="py-1.5 pr-4 font-mono font-medium" style={{ color: 'var(--text)' }}>{r.model}</td>
                      <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--text-dim)' }}>{r.calls}</td>
                      <td className="py-1.5 text-right tabular-nums">
                        <span className={`rounded px-1.5 py-0.5 font-semibold ${r.avg < 2000 ? 'bg-green-100 text-green-700' : r.avg < 10000 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                          {r.avg >= 1000 ? `${(r.avg / 1000).toFixed(1)}s` : `${Math.round(r.avg)}ms`}
                        </span>
                      </td>
                      <td className="py-1.5 text-right tabular-nums">
                        <span className={`rounded px-1.5 py-0.5 font-semibold ${r.median < 2000 ? 'bg-green-100 text-green-700' : r.median < 10000 ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                          {r.median >= 1000 ? `${(r.median / 1000).toFixed(1)}s` : `${Math.round(r.median)}ms`}
                        </span>
                      </td>
                      <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--text-dim)' }}>{r.tps.toFixed(1)} tok/s</td>
                      <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--text-dim)' }}>{r.cost > 0 ? `$${r.cost.toFixed(5)}` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })()}

        {traces.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted">
            No traces yet — LLM calls will appear here as agents run.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted">
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
                  <tr key={t.id} className="border-b border-border hover:bg-surface-2/60">
                    <td className="px-4 py-2 text-xs text-muted whitespace-nowrap">
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
                    <td className="px-4 py-2 text-right text-xs tabular-nums text-muted">
                      {t.tokens_in.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right text-xs tabular-nums text-muted">
                      {t.tokens_out.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right text-xs tabular-nums text-muted">
                      {t.cost_usd > 0 ? `$${t.cost_usd.toFixed(5)}` : "—"}
                    </td>
                    <td className="px-4 py-2 max-w-xs">
                      {t.response_preview ? (
                        <button
                          onClick={() => setExpandedTrace(isExpanded ? null : t.id)}
                          className="text-left text-xs text-muted hover:text-fg"
                        >
                          {isExpanded
                            ? t.response_preview
                            : t.response_preview.slice(0, 80) + (t.response_preview.length > 80 ? "…" : "")}
                        </button>
                      ) : (
                        <span className="text-xs text-muted">—</span>
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
        <p className="ml-auto self-center text-xs text-muted">{total.toLocaleString()} total events</p>
      </div>

      {/* Table */}
      <div className="rounded-xl shadow-sm overflow-hidden" style={{ border: '1px solid var(--border)', background: 'var(--surface)' }}>
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-6 w-6 animate-spin text-muted" />
          </div>
        ) : events.length === 0 ? (
          <p className="py-16 text-center text-sm text-muted">No events found.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-2 text-xs text-muted">
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
                <tr key={e.id} className="border-b border-border hover:bg-surface-2/50">
                  <td className="px-4 py-2.5 text-xs text-muted whitespace-nowrap">
                    {formatDistanceToNow(new Date(e.created_at), { addSuffix: true })}
                  </td>
                  <td className="px-4 py-2.5">
                    {e.source_agent && (
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${AGENT_COLORS[e.source_agent] ?? "bg-surface-2 text-dim"}`}>
                        {e.source_agent}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-fg font-mono">{e.event_type}</td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_BADGE[e.status] ?? "bg-surface-2 text-dim"}`}>
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
        <div className="flex items-center justify-between text-sm text-muted">
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
