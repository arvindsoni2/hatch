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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      <span className="w-24 text-slate-500">{label}</span>
      <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
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
    try {
      await approveApplication(id);
      setApprovals((prev) => prev.filter((a) => a.application_id !== id));
    } finally {
      setActing((a) => { const n = { ...a }; delete n[id]; return n; });
    }
  };

  const handleReject = async (id: string) => {
    setActing((a) => ({ ...a, [id]: "rejecting" }));
    try {
      await rejectApplication(id);
      setApprovals((prev) => prev.filter((a) => a.application_id !== id));
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Sparkles className="h-6 w-6 text-amber-500" />
            Approval Queue
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {approvals.length} application{approvals.length !== 1 ? "s" : ""} awaiting your review
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh
        </Button>
      </div>

      {approvals.length === 0 && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="py-8 text-center text-green-700">
            <CheckCircle2 className="h-8 w-8 mx-auto mb-2 text-green-500" />
            <p className="font-medium">No pending approvals</p>
            <p className="text-sm mt-1 text-green-600">All AI-generated applications have been reviewed.</p>
          </CardContent>
        </Card>
      )}

      {approvals.map((app) => (
        <Card key={app.application_id} className="overflow-hidden">
          <CardHeader className="pb-3 border-b border-slate-100">
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-lg">{app.job_title ?? "Untitled Role"}</CardTitle>
                <p className="text-sm text-slate-500 mt-0.5">
                  {app.company ?? "Unknown Company"}
                  {app.rate_text && (
                    <span className="ml-2 font-medium text-slate-700">{app.rate_text}</span>
                  )}
                </p>
              </div>
              <ScoreBadge score={app.overall_score} />
            </div>
          </CardHeader>
          <CardContent className="py-4 space-y-4">
            {/* Score breakdown */}
            <div className="space-y-1.5">
              <ScoreBar value={app.skill_match} label="Skill match" />
              <ScoreBar value={app.experience_match} label="Experience" />
              <ScoreBar value={app.rate_match} label="Rate" />
              <ScoreBar value={app.location_match} label="Location" />
            </div>

            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Clock className="h-3 w-3" />
              {app.created_at
                ? new Date(app.created_at).toLocaleString("en-GB")
                : "Unknown time"}
            </div>

            {/* Actions */}
            <div className="flex items-center gap-3 pt-1">
              <Button
                size="sm"
                className="bg-green-600 hover:bg-green-700 text-white"
                onClick={() => handleApprove(app.application_id)}
                disabled={!!acting[app.application_id]}
              >
                {acting[app.application_id] === "approving" ? (
                  <RefreshCw className="h-4 w-4 animate-spin mr-1" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 mr-1" />
                )}
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-red-300 text-red-600 hover:bg-red-50"
                onClick={() => handleReject(app.application_id)}
                disabled={!!acting[app.application_id]}
              >
                {acting[app.application_id] === "rejecting" ? (
                  <RefreshCw className="h-4 w-4 animate-spin mr-1" />
                ) : (
                  <XCircle className="h-4 w-4 mr-1" />
                )}
                Reject
              </Button>
              <Link href={`/approvals/${app.application_id}`} className="ml-auto">
                <Button variant="ghost" size="sm" className="text-slate-500">
                  Full review <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
