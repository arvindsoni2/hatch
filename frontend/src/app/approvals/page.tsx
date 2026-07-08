"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  approveApplication,
  fetchPendingApprovals,
  rejectApplication,
  type PendingApproval,
} from "@/lib/api";
import { AssistedApplyCard } from "@/components/AssistedApplyCard";
import { TriggerScrapeButton } from "@/components/TriggerScrapeButton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  CheckCircle2,
  ChevronRight,
  Clock,
  RefreshCw,
  Search,
  Sparkles,
  XCircle,
} from "lucide-react";

function scoreTone(value: number | null) {
  if (value === null) return "var(--surface-3)";
  const pct = Math.round(value * 100);
  if (pct >= 85) return "var(--success)";
  if (pct >= 70) return "var(--warning)";
  return "var(--danger)";
}

function ScoreBar({ value, label }: { value: number | null; label: string }) {
  if (value === null) return null;
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 text-[var(--text-muted)]">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded bg-[var(--surface-2)]">
        <div className="h-full" style={{ width: `${pct}%`, background: scoreTone(value) }} />
      </div>
      <span className="w-8 text-right font-medium text-[var(--text)]">{pct}%</span>
    </div>
  );
}

function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <StatusBadge tone="neutral">Unscored</StatusBadge>;
  const pct = Math.round(score * 100);
  if (pct >= 85) return <StatusBadge tone="success">{pct}%</StatusBadge>;
  if (pct >= 75) return <StatusBadge tone="warning">{pct}%</StatusBadge>;
  return <StatusBadge tone="danger">{pct}%</StatusBadge>;
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<Record<string, "approving" | "rejecting">>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [pendingRejectId, setPendingRejectId] = useState<string | null>(null);

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
      setActionError(
        err instanceof Error
          ? err.message
          : "Failed to approve. The database may be busy - please try again in a moment.",
      );
    } finally {
      setActing((a) => {
        const n = { ...a };
        delete n[id];
        return n;
      });
    }
  };

  const handleReject = async (id: string) => {
    setActing((a) => ({ ...a, [id]: "rejecting" }));
    setActionError(null);
    try {
      await rejectApplication(id);
      setApprovals((prev) => prev.filter((a) => a.application_id !== id));
      setPendingRejectId(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to reject. Please try again.");
    } finally {
      setActing((a) => {
        const n = { ...a };
        delete n[id];
        return n;
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-[var(--text-dim)]">
        <RefreshCw className="mr-2 h-5 w-5 animate-spin" /> Loading approvals...
      </div>
    );
  }

  return (
    <PageContainer width="wide" className="space-y-6">
      <PageHeader
        title="Shortlist"
        description={
          approvals.length > 0
            ? `${approvals.length} application${approvals.length !== 1 ? "s" : ""} ready to review and approve`
            : "No pending approvals. Run Scout or open Jobs to find the next role to review."
        }
        actions={(
          <Button variant="outline" size="sm" onClick={refresh}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        )}
      />

      {actionError ? (
        <div
          className="flex items-center gap-2 rounded-[var(--radius-card)] border border-[var(--danger)] bg-[var(--danger-soft)] px-4 py-3 text-sm text-[var(--danger)]"
          role="alert"
        >
          <XCircle className="h-4 w-4 shrink-0" />
          <span>{actionError}</span>
          <button type="button" onClick={() => setActionError(null)} className="ml-auto text-xs underline">
            Dismiss
          </button>
        </div>
      ) : null}

      {approvals.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] px-6 py-14 text-center"
          role="status"
        >
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-[var(--radius-card)] bg-[var(--success-soft)] text-[var(--success)]">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <p className="text-base font-semibold text-[var(--text)]">No pending approvals</p>
          <p className="mt-1 max-w-md text-sm text-[var(--text-dim)]">
            Every AI-sourced application has been reviewed. Use Scout to find fresh matches or inspect Jobs for roles already in the pipeline.
          </p>
          <div className="mt-5 flex flex-col items-center gap-2 sm:flex-row">
            <TriggerScrapeButton variant="primary" />
            <Link
              href="/jobs"
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface)] px-4 py-2 text-sm font-semibold text-[var(--text)] hover:bg-[var(--surface-2)] sm:min-h-10"
            >
              <Search className="h-4 w-4" /> Open Jobs
            </Link>
          </div>
        </div>
      ) : null}

      {approvals.map((app) => (
        <div
          key={app.application_id}
          className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)]"
        >
          <div className="border-b border-[var(--border)] px-5 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="truncate text-base font-semibold text-[var(--text)]">
                  {app.job_title ?? "Untitled Role"}
                </h3>
                <p className="mt-0.5 text-sm text-[var(--text-muted)]">
                  {app.company ?? "Unknown Company"}
                  {app.rate_text ? (
                    <span className="ml-2 font-medium text-[var(--text-dim)]">{app.rate_text}</span>
                  ) : null}
                </p>
              </div>
              <ScoreBadge score={app.overall_score} />
            </div>
          </div>
          <div className="space-y-4 px-5 py-4">
            <div className="space-y-1.5">
              <ScoreBar value={app.skill_match} label="Skill match" />
              <ScoreBar value={app.experience_match} label="Experience" />
              <ScoreBar value={app.rate_match} label="Rate" />
              <ScoreBar value={app.location_match} label="Location" />
            </div>

            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
              <Clock className="h-3 w-3" />
              {app.created_at ? new Date(app.created_at).toLocaleString("en-GB") : "Unknown time"}
            </div>

            <div className="flex flex-col items-stretch gap-2 pt-1 sm:flex-row sm:items-center">
              <Button
                variant="success"
                size="sm"
                onClick={() => handleApprove(app.application_id)}
                disabled={!!acting[app.application_id]}
              >
                {acting[app.application_id] === "approving" ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
                Approve
              </Button>

              <AlertDialog
                open={pendingRejectId === app.application_id}
                onOpenChange={(open) => setPendingRejectId(open ? app.application_id : null)}
              >
                <Button
                  variant="destructive"
                  size="sm"
                  type="button"
                  onClick={() => setPendingRejectId(app.application_id)}
                  disabled={!!acting[app.application_id]}
                >
                  {acting[app.application_id] === "rejecting" ? (
                    <RefreshCw className="h-4 w-4 animate-spin" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  Reject
                </Button>
                <AlertDialogContent>
                  <AlertDialogTitle>Reject this application?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This removes it from your pending shortlist. You can still find the job record later, but it will not stay queued for approval.
                  </AlertDialogDescription>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Keep pending</AlertDialogCancel>
                    <AlertDialogAction onClick={() => handleReject(app.application_id)}>
                      Reject application
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>

              <Link
                href={`/approvals/${app.application_id}`}
                className="inline-flex min-h-11 items-center justify-center gap-1 rounded-[var(--radius-control)] px-3 py-2 text-sm font-semibold text-[var(--text-dim)] hover:bg-[var(--surface-2)] sm:ml-auto sm:min-h-9"
              >
                Full review <ChevronRight className="h-4 w-4" />
              </Link>
            </div>

            {app.status === "approved" || app.status === "preparing" || app.status === "ready_to_apply" ? (
              <AssistedApplyCard application={app} onStatusChange={refresh} />
            ) : null}
          </div>
        </div>
      ))}
    </PageContainer>
  );
}
