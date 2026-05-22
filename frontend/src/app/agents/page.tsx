"use client";

import { useEffect, useState, useCallback } from "react";
import {
  fetchAllAgentStatus,
  fetchAgentEvents,
  fetchPipelineStats,
  triggerAgent,
  AllAgentStatus,
  AgentEvent,
  PipelineStats,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock,
  RefreshCw,
  XCircle,
  Zap,
} from "lucide-react";

// ── Status colour map ──────────────────────────────────────────────────────

function statusBadge(status: string) {
  switch (status) {
    case "running":
      return <Badge className="bg-blue-100 text-blue-700 border-blue-200">Running</Badge>;
    case "waiting_approval":
      return <Badge className="bg-amber-100 text-amber-700 border-amber-200">Waiting</Badge>;
    case "error":
      return <Badge className="bg-red-100 text-red-700 border-red-200">Error</Badge>;
    case "idle":
      return <Badge className="bg-green-100 text-green-700 border-green-200">Idle</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function eventTypeBadge(type: string) {
  const colours: Record<string, string> = {
    job_discovered: "bg-sky-100 text-sky-700",
    job_scored: "bg-indigo-100 text-indigo-700",
    job_shortlisted: "bg-violet-100 text-violet-700",
    cv_tailored: "bg-teal-100 text-teal-700",
    application_ready: "bg-amber-100 text-amber-700",
    application_approved: "bg-green-100 text-green-700",
    interview_scheduled: "bg-orange-100 text-orange-700",
    prep_ready: "bg-emerald-100 text-emerald-700",
    scout_error: "bg-red-100 text-red-700",
  };
  const cls = colours[type] ?? "bg-slate-100 text-slate-600";
  return <Badge className={`${cls} text-xs`}>{type.replace(/_/g, " ")}</Badge>;
}

// ── Pipeline funnel ────────────────────────────────────────────────────────

function PipelineFunnel({ stats }: { stats: PipelineStats }) {
  const steps = [
    { label: "Discovered", count: stats.discovered, colour: "bg-sky-500" },
    { label: "Scored", count: stats.scored, colour: "bg-indigo-500" },
    { label: "Shortlisted", count: stats.shortlisted, colour: "bg-violet-500" },
    { label: "Tailored", count: stats.tailored, colour: "bg-teal-500" },
    { label: "Approved", count: stats.approved, colour: "bg-green-500" },
  ];
  const max = Math.max(...steps.map((s) => s.count), 1);

  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center gap-3">
          <span className="w-24 text-right text-sm text-slate-500">{step.label}</span>
          <div className="relative flex-1 h-6 bg-slate-100 rounded overflow-hidden">
            <div
              className={`h-full ${step.colour} transition-all duration-500`}
              style={{ width: `${(step.count / max) * 100}%` }}
            />
          </div>
          <span className="w-10 text-sm font-semibold text-slate-700 text-right">{step.count}</span>
          {i < steps.length - 1 && (
            <ChevronRight className="w-4 h-4 text-slate-300 shrink-0" />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Page component ─────────────────────────────────────────────────────────

export default function AgentDashboardPage() {
  const [agentStatus, setAgentStatus] = useState<AllAgentStatus | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [statusData, eventsData, pipelineData] = await Promise.all([
        fetchAllAgentStatus(),
        fetchAgentEvents({ limit: 30 }),
        fetchPipelineStats(),
      ]);
      setAgentStatus(statusData);
      setEvents(eventsData.items);
      setPipeline(pipelineData);
    } catch (err) {
      console.error("Failed to load agent data", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  }, [refresh]);

  const handleTrigger = async (name: string) => {
    setTriggering(name);
    try {
      await triggerAgent(name);
      await refresh();
    } finally {
      setTriggering(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-500">
        <RefreshCw className="animate-spin mr-2 h-5 w-5" /> Loading agent status…
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Bot className="h-6 w-6 text-brand-600" />
            Agent Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Uptime: {agentStatus ? Math.round(agentStatus.uptime_seconds / 60) : 0}min · DB:{" "}
            <span className="text-green-600">{agentStatus?.database ?? "—"}</span>
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh
        </Button>
      </div>

      {/* Agent status cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(agentStatus?.agents ?? []).map((agent) => (
          <Card key={agent.agent_name} className="relative overflow-hidden">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold capitalize flex items-center justify-between">
                {agent.agent_name}
                {statusBadge(agent.status)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-1 text-xs text-slate-500">
                <Clock className="h-3 w-3" />
                {agent.last_run_at
                  ? new Date(agent.last_run_at).toLocaleString("en-GB")
                  : "Never run"}
              </div>
              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs"
                onClick={() => handleTrigger(agent.agent_name)}
                disabled={triggering === agent.agent_name}
              >
                {triggering === agent.agent_name ? (
                  <RefreshCw className="h-3 w-3 animate-spin mr-1" />
                ) : (
                  <Zap className="h-3 w-3 mr-1" />
                )}
                Trigger
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Pipeline funnel + event timeline */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Pipeline funnel */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="h-4 w-4 text-brand-600" />
              Pipeline Funnel
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pipeline ? (
              <PipelineFunnel stats={pipeline} />
            ) : (
              <p className="text-sm text-slate-400">No data</p>
            )}
          </CardContent>
        </Card>

        {/* Event timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4 text-brand-600" />
              Recent Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {events.length === 0 && (
                <p className="text-sm text-slate-400">No events yet</p>
              )}
              {events.map((ev) => (
                <div
                  key={ev.id}
                  className="flex items-start gap-3 py-1.5 border-b border-slate-100 last:border-0"
                >
                  <div className="mt-0.5 shrink-0">
                    {ev.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    ) : ev.status === "failed" ? (
                      <XCircle className="h-4 w-4 text-red-500" />
                    ) : (
                      <RefreshCw className="h-4 w-4 text-blue-400 animate-spin" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {eventTypeBadge(ev.event_type)}
                      <span className="text-xs text-slate-400">{ev.source_agent}</span>
                    </div>
                    {ev.error_message && (
                      <p className="text-xs text-red-500 mt-0.5 truncate">{ev.error_message}</p>
                    )}
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">
                    {new Date(ev.created_at).toLocaleTimeString("en-GB", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Approval queue shortcut */}
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="py-4 flex items-center justify-between">
          <div>
            <p className="font-semibold text-amber-800">Human Approval Queue</p>
            <p className="text-sm text-amber-600 mt-0.5">
              Review AI-generated CVs before they go out
            </p>
          </div>
          <a href="/approvals">
            <Button className="bg-amber-600 hover:bg-amber-700 text-white">
              Review <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </a>
        </CardContent>
      </Card>
    </div>
  );
}
