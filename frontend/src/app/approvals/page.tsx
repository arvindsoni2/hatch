"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  fetchPendingApprovals,
  approveApplication,
  rejectApplication,
  PendingApproval,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { TriggerScrapeButton } from "@/components/TriggerScrapeButton";
import { AssistedApplyCard } from "@/components/AssistedApplyCard";
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  RefreshCw,
  Sparkles,
  XCircle,
} from "lucide-react";

function ScoreBar({ value, label }: { value: number | null; label: string }) {
  if (value === null) return null;
  const pct = Math.round(value * 100);
  const colour =
    pct >= 85 ? "bg-green-500" : pct >= 70 ? "bg-amber-500" : "bg-red-400";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24" style={{ color: "var(--text-muted)" }}>{label}</span>
      <div className="flex-1 h-2 rounded overflow-hidden" style={{ background: "var(--surface-2)" }}>
        <div className={`h-full ${colour}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right font-medium">{pct}%</span>
    </div>
  );
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <Badge variant="secondary">Unscored</Badge>;
  const pct = Math.round(score * 100);
  if (pct >= 85) return <Badge className="bg-green-100 text-green-700 border-green-200">{pct}%</Badge>;
  if (pct >= 75) return <Badge className="bg-amber-100 text-amber-700 border-amber-200">{pct}%</Badge>;
  return <Badge className="bg-red-100 text-red-700 border-red-200">{pct}%</Badge>;
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<Record<string, "approving" | "rejecting">>({});
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchPendingApprovals();
      setApprovals(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleApprove = async (id: string) => {
    setActing((a) => ({ ...a, [id]: "approving" }));
    setActionError(null);
    try {
      await approveApplication(id);
      setApprovals((prev) => prev.filter((a) => a.application_id !== id));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to approve. The database may be busy — please try again in a moment.");
    } finally {
      setActing((a) => { const n = { ...a }; delete n[id]; return n; });
    }
  };

  const handleReject = async (id: string) => {
    setActing((a) => ({ ...a, [id]: "rejecting" }));
    setActionError(null);
    try {
      await rejectApplication(id);
      setApprovals((prev) => prev.filter((a) => a.application_id !== id));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject. Please try again.");
    } finally {
      setActing((a) => { const n = { ...a }; delete n[id]; return n; });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-500">
        <RefreshCw className="animate-spin mr-2 h-5 w-5" /> Loading approvals…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[28px] font-semibold flex items-center gap-2" style={{ color: "var(--text)", letterSpacing: "-0.025em" }}>
            <Sparkles className="h-6 w-6" style={{ color: "var(--accent)" }} />
            Approval queue
          </h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
            {approvals.length} application{approvals.length !== 1 ? "s" : ""} awaiting your review
          </p>
        </div>
        <button onClick={refresh} className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0" style={{ background: "var(--surface-2)", color: "var(--text-dim)", border: "1px solid var(--border)" }}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      {actionError && (
        <div className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm" style={{ background: "var(--danger-soft)", border: "1px solid var(--danger)", color: "var(--danger)" }}>
          <XCircle className="h-4 w-4 shrink-0" />
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="ml-auto text-xs underline">Dismiss</button>
        </div>
      )}

      {approvals.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl py-14 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="w-12 h-12 rounded-xl flex items-center justify-center mb-4" style={{ background: "var(--success-soft)", color: "var(--success)" }}>
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <p className="text-base font-semibold" style={{ color: "var(--text)" }}>{"You're all caught up"}</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>Every AI-sourced application has been reviewed.</p>
          <div className="mt-5">
            <TriggerScrapeButton variant="primary" />
          </div>
        </div>
      )}

      {approvals.map((app) => (
        <div key={app.application_id} className="rounded-xl overflow-hidden" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="px-5 py-4" style={{ borderBottom: "1px solid var(--border)" }}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-base font-semibold" style={{ color: "var(--text)" }}>{app.job_title ?? "Untitled Role"}</h3>
                <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {app.company ?? "Unknown Company"}
                  {app.rate_text && (
                    <span className="ml-2 font-medium" style={{ color: "var(--text-dim)" }}>{app.rate_text}</span>
                  )}
                </p>
              </div>
              <ScoreBadge score={app.overall_score} />
            </div>
          </div>
          <div className="px-5 py-4 space-y-4">
            {/* Score breakdown */}
            <div className="space-y-1.5">
              <ScoreBar value={app.skill_match} label="Skill match" />
              <ScoreBar value={app.experience_match} label="Experience" />
              <ScoreBar value={app.rate_match} label="Rate" />
              <ScoreBar value={app.location_match} label="Location" />
            </div>

            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
              <Clock className="h-3 w-3" />
              {app.created_at
                ? new Date(app.created_at).toLocaleString("en-GB")
                : "Unknown time"}
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1">
              <button
                className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0 transition-colors"
                style={{ background: "var(--success-soft)", color: "var(--success)" }}
                onClick={() => handleApprove(app.application_id)}
                disabled={!!acting[app.application_id]}
              >
                {acting[app.application_id] === "approving" ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Approve
              </button>
              <button
                className="flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-[44px] sm:min-h-0 transition-colors"
                style={{ background: "var(--danger-soft)", color: "var(--danger)" }}
                onClick={() => handleReject(app.application_id)}
                disabled={!!acting[app.application_id]}
              >
                {acting[app.application_id] === "rejecting" ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                Reject
              </button>
              <Link href={`/approvals/${app.application_id}`} className="ml-auto">
                <button className="flex items-center gap-1 text-sm px-3 py-2 rounded-lg min-h-[44px] sm:min-h-0" style={{ color: "var(--text-muted)" }}>
                  Full review <ChevronRight className="h-4 w-4" />
                </button>
              </Link>
            </div>

            {/* Assisted apply — shown once status is approved or later */}
            {(app.status === "approved" || app.status === "preparing" || app.status === "ready_to_apply") && (
              <AssistedApplyCard application={app} onStatusChange={refresh} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
