"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  fetchAllAgentStatus,
  fetchAgentEvents,
  fetchPipelineStats,
  triggerAgent,
  type AgentEvent,
  type AllAgentStatus,
  type PipelineStats,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { StatusBadge } from "@/components/ui/status-badge";
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

function agentStatusBadge(status: string) {
  switch (status) {
    case "running":
      return <StatusBadge tone="info">Running</StatusBadge>;
    case "waiting_approval":
      return <StatusBadge tone="warning">Waiting</StatusBadge>;
    case "error":
      return <StatusBadge tone="danger">Failed</StatusBadge>;
    case "idle":
      return <StatusBadge tone="success">Idle</StatusBadge>;
    case "never_run":
      return <StatusBadge tone="neutral">Never run</StatusBadge>;
    default:
      return <StatusBadge tone="neutral">Unknown</StatusBadge>;
  }
}

function eventStatusBadge(status: AgentEvent["status"]) {
  switch (status) {
    case "completed":
      return <StatusBadge tone="success">Completed</StatusBadge>;
    case "failed":
      return <StatusBadge tone="danger">Failed</StatusBadge>;
    case "processing":
      return <StatusBadge tone="info">Processing</StatusBadge>;
    case "pending":
      return <StatusBadge tone="warning">Pending</StatusBadge>;
    default:
      return <StatusBadge tone="neutral">Unknown</StatusBadge>;
  }
}

function eventTypeBadge(type: string) {
  return <StatusBadge tone="neutral">{type.replace(/_/g, " ")}</StatusBadge>;
}

function formatDateTime(value: string | null) {
  if (!value) return "Never run";
  return new Date(value).toLocaleString("en-GB");
}

function formatRefreshTime(value: Date | null) {
  if (!value) return "Last updated --";
  return `Last updated ${value.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

function PipelineFunnel({ stats }: { stats: PipelineStats }) {
  const steps = [
    { label: "Discovered", count: stats.discovered, colour: "var(--accent)" },
    { label: "Scored", count: stats.scored, colour: "var(--text-dim)" },
    { label: "Shortlisted", count: stats.shortlisted, colour: "var(--warning)" },
    { label: "Tailored", count: stats.tailored, colour: "var(--success)" },
    { label: "Approved", count: stats.approved, colour: "var(--text-muted)" },
  ];
  const max = Math.max(...steps.map((s) => s.count), 1);

  return (
    <div className="space-y-3">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center gap-3">
          <span className="w-24 text-right text-sm text-[var(--text-dim)]">{step.label}</span>
          <div className="relative h-6 flex-1 overflow-hidden rounded bg-[var(--surface-2)]">
            <div
              className="h-full transition-all duration-500"
              style={{ width: `${(step.count / max) * 100}%`, background: step.colour }}
            />
          </div>
          <span className="w-10 text-right text-sm font-semibold text-[var(--text)]">{step.count}</span>
          {i < steps.length - 1 ? (
            <ChevronRight className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default function AgentDashboardPage() {
  const [agentStatus, setAgentStatus] = useState<AllAgentStatus | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [pipeline, setPipeline] = useState<PipelineStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

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
      setLastUpdated(new Date());
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
      <div className="flex items-center justify-center py-24 text-[var(--text-dim)]">
        <RefreshCw className="mr-2 h-5 w-5 animate-spin" /> Loading agent status...
      </div>
    );
  }

  return (
    <PageContainer width="wide" className="space-y-8">
      <PageHeader
        title="Agent Dashboard"
        description={`Uptime: ${agentStatus ? Math.round(agentStatus.uptime_seconds / 60) : 0}min | DB: ${agentStatus?.database ?? "--"} | ${formatRefreshTime(lastUpdated)} | Refreshes every 30 seconds`}
        actions={(
          <Button variant="outline" size="sm" onClick={refresh}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        )}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {(agentStatus?.agents ?? []).map((agent) => (
          <Card key={agent.agent_name} className="relative overflow-hidden" data-testid="agent-status-card">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between text-sm font-semibold capitalize">
                <span className="flex min-w-0 items-center gap-2">
                  <Bot className="h-4 w-4 shrink-0 text-[var(--accent)]" />
                  <span className="truncate">{agent.agent_name}</span>
                </span>
                {agentStatusBadge(agent.status)}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-1 text-xs text-[var(--text-dim)]">
                <Clock className="h-3 w-3" />
                {formatDateTime(agent.last_run_at)}
              </div>
              <Button
                size="sm"
                variant="outline"
                className="w-full text-xs"
                onClick={() => handleTrigger(agent.agent_name)}
                disabled={triggering === agent.agent_name}
              >
                {triggering === agent.agent_name ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <Zap className="h-3 w-3" />
                )}
                Trigger
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="h-4 w-4 text-[var(--accent)]" />
              Pipeline Funnel
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pipeline ? (
              <PipelineFunnel stats={pipeline} />
            ) : (
              <p className="text-sm text-[var(--text-muted)]">No data</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-4 w-4 text-[var(--accent)]" />
              Recent Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {events.length === 0 ? (
                <p className="text-sm text-[var(--text-muted)]">No events yet</p>
              ) : null}
              {events.map((ev) => (
                <div
                  key={ev.id}
                  className="flex items-start gap-3 border-b border-[var(--border)] py-1.5 last:border-0"
                >
                  <div className="mt-0.5 shrink-0">
                    {ev.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
                    ) : ev.status === "failed" ? (
                      <XCircle className="h-4 w-4 text-[var(--danger)]" />
                    ) : ev.status === "processing" ? (
                      <RefreshCw className="h-4 w-4 animate-spin text-[var(--accent)]" />
                    ) : (
                      <Clock className="h-4 w-4 text-[var(--warning)]" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {eventTypeBadge(ev.event_type)}
                      {eventStatusBadge(ev.status)}
                      <span className="text-xs text-[var(--text-muted)]">{ev.source_agent}</span>
                    </div>
                    {ev.error_message ? (
                      <p className="mt-0.5 truncate text-xs text-[var(--danger)]">{ev.error_message}</p>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-xs text-[var(--text-muted)]">
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

      <Card className="border-[var(--warning)] bg-[var(--warning-soft)]">
        <CardContent className="flex items-center justify-between py-4">
          <div>
            <p className="font-semibold text-[var(--text)]">Shortlist</p>
            <p className="mt-0.5 text-sm text-[var(--text-dim)]">
              Review AI-generated CVs before they go out
            </p>
          </div>
          <Link href="/approvals">
            <Button>
              Review <ChevronRight className="h-4 w-4" />
            </Button>
          </Link>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
