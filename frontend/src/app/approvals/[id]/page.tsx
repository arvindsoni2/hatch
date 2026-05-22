"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  fetchApprovalDetail,
  approveApplication,
  rejectApplication,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowLeft,
  Building2,
  CheckCircle2,
  Clock,
  FileText,
  MapPin,
  RefreshCw,
  XCircle,
} from "lucide-react";

interface ApprovalDetail {
  application: {
    id: string
    status: string
    approval_status: string
    agent_created: boolean
    created_at: string | null
  }
  job: {
    id: string | null
    title: string | null
    company: string | null
    location: string | null
    rate_text: string | null
    ir35_status: string | null
    description: string | null
  } | null
  score: {
    overall_score: number | null
    skill_match: number | null
    experience_match: number | null
    rate_match: number | null
    location_match: number | null
    reasoning: string | null
  } | null
  documents: {
    id: string
    document_type: string
    version: number
    file_path: string
    ats_score: number | null
    created_at: string | null
  }[]
}

function ScoreRadar({
  skill, experience, rate, location,
}: {
  skill: number | null; experience: number | null;
  rate: number | null; location: number | null;
}) {
  const bars = [
    { label: "Skills", value: skill },
    { label: "Experience", value: experience },
    { label: "Rate", value: rate },
    { label: "Location", value: location },
  ];
  return (
    <div className="grid grid-cols-2 gap-3">
      {bars.map(({ label, value }) => {
        const pct = value !== null ? Math.round(value * 100) : null;
        const colour = pct === null ? "bg-slate-200"
          : pct >= 85 ? "bg-green-500"
          : pct >= 70 ? "bg-amber-500"
          : "bg-red-400";
        return (
          <div key={label} className="text-center">
            <div className="relative h-16 w-16 mx-auto mb-1">
              <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90">
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#e2e8f0" strokeWidth="3" />
                <circle
                  cx="18" cy="18" r="15.9155"
                  fill="none"
                  stroke={pct === null ? "#cbd5e1" : pct >= 85 ? "#22c55e" : pct >= 70 ? "#f59e0b" : "#f87171"}
                  strokeWidth="3"
                  strokeDasharray={`${pct ?? 0} 100`}
                  strokeLinecap="round"
                />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-slate-700">
                {pct !== null ? `${pct}%` : "—"}
              </span>
            </div>
            <span className="text-xs text-slate-500">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function ApprovalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<ApprovalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<"approving" | "rejecting" | null>(null);

  useEffect(() => {
    fetchApprovalDetail(id)
      .then((d) => setDetail(d as ApprovalDetail))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const handleApprove = async () => {
    setActing("approving");
    try {
      await approveApplication(id);
      router.push("/approvals");
    } finally {
      setActing(null);
    }
  };

  const handleReject = async () => {
    setActing("rejecting");
    try {
      await rejectApplication(id);
      router.push("/approvals");
    } finally {
      setActing(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-500">
        <RefreshCw className="animate-spin mr-2 h-5 w-5" /> Loading…
      </div>
    );
  }

  if (!detail) {
    return <p className="text-center text-red-500 py-12">Application not found.</p>;
  }

  const { application, job, score, documents } = detail;
  const cv = documents.find((d) => d.document_type === "cv");
  const cl = documents.find((d) => d.document_type === "cover_letter");
  const isDecided = application.approval_status !== "pending";

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Back button */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="h-4 w-4" /> Back to queue
      </button>

      {/* Job summary */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <CardTitle className="text-xl">{job?.title ?? "Untitled Role"}</CardTitle>
              <div className="flex items-center gap-3 mt-1.5 text-sm text-slate-500 flex-wrap">
                {job?.company && (
                  <span className="flex items-center gap-1">
                    <Building2 className="h-3.5 w-3.5" /> {job.company}
                  </span>
                )}
                {job?.location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" /> {job.location}
                  </span>
                )}
                {job?.rate_text && (
                  <span className="font-semibold text-slate-700">{job.rate_text}</span>
                )}
                {job?.ir35_status && (
                  <Badge variant="outline" className="text-xs">{job.ir35_status} IR35</Badge>
                )}
              </div>
            </div>
            <Badge
              className={
                application.approval_status === "approved"
                  ? "bg-green-100 text-green-700"
                  : application.approval_status === "rejected"
                  ? "bg-red-100 text-red-700"
                  : "bg-amber-100 text-amber-700"
              }
            >
              {application.approval_status}
            </Badge>
          </div>
        </CardHeader>
        {job?.description && (
          <CardContent>
            <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap line-clamp-6">
              {job.description}
            </p>
          </CardContent>
        )}
      </Card>

      {/* Score breakdown */}
      {score && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Score Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <ScoreRadar
              skill={score.skill_match}
              experience={score.experience_match}
              rate={score.rate_match}
              location={score.location_match}
            />
            {score.reasoning && (
              <p className="text-sm text-slate-600 bg-slate-50 rounded p-3 mt-2">
                {score.reasoning}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Documents */}
      <div className="grid gap-4 sm:grid-cols-2">
        {[{ doc: cv, label: "Tailored CV" }, { doc: cl, label: "Cover Letter" }].map(({ doc, label }) => (
          <Card key={label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="h-4 w-4 text-brand-600" />
                {label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {doc ? (
                <div className="space-y-1">
                  <p className="text-xs text-slate-500">Version {doc.version}</p>
                  {doc.ats_score !== null && (
                    <p className="text-xs">
                      ATS score:{" "}
                      <span
                        className={
                          doc.ats_score >= 80
                            ? "text-green-600 font-semibold"
                            : doc.ats_score >= 60
                            ? "text-amber-600 font-semibold"
                            : "text-red-500 font-semibold"
                        }
                      >
                        {doc.ats_score}
                      </span>
                    </p>
                  )}
                  <p className="text-xs text-slate-400 truncate">{doc.file_path}</p>
                </div>
              ) : (
                <p className="text-xs text-slate-400">Not generated yet</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Approval actions */}
      {!isDecided && (
        <div className="flex items-center gap-4 pt-2">
          <Button
            className="bg-green-600 hover:bg-green-700 text-white flex-1 sm:flex-none"
            onClick={handleApprove}
            disabled={!!acting}
          >
            {acting === "approving" ? (
              <RefreshCw className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <CheckCircle2 className="h-4 w-4 mr-2" />
            )}
            Approve Application
          </Button>
          <Button
            variant="outline"
            className="border-red-300 text-red-600 hover:bg-red-50 flex-1 sm:flex-none"
            onClick={handleReject}
            disabled={!!acting}
          >
            {acting === "rejecting" ? (
              <RefreshCw className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <XCircle className="h-4 w-4 mr-2" />
            )}
            Reject
          </Button>
        </div>
      )}

      {isDecided && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Clock className="h-4 w-4" />
          This application was {application.approval_status}.
        </div>
      )}
    </div>
  );
}
