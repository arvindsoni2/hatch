"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  fetchApprovalDetail,
  approveApplication,
  rejectApplication,
  API_BASE,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ArrowLeft, Building2, CheckCircle2, Clock, FileText,
  MapPin, RefreshCw, XCircle, ChevronDown, ChevronUp,
  AlertTriangle, Save,
} from "lucide-react";

interface AtsDetails {
  overall_score?: number;
  keyword_matches?: string[];
  keyword_misses?: string[];
  format_warnings?: string[];
  improvements?: string[];
  ats_analysis?: {
    matched_keywords?: string[];
    missing_keywords?: string[];
    score?: number;
  };
}

interface JdAnalysis {
  requirements?: { must_have?: string[]; nice_to_have?: string[] };
  ats_keywords?: { technical?: string[]; methodologies?: string[]; soft_skills?: string[]; domain?: string[]; certifications?: string[] };
  tone_analysis?: { red_flags?: string[] };
  responsibilities?: string[];
  skill_match?: { matched?: string[]; missing?: string[]; recommendations?: string[] };
}

interface ApprovalDetail {
  application: {
    id: string;
    status: string;
    approval_status: string;
    agent_created: boolean;
    created_at: string | null;
  };
  job: {
    id: string | null;
    title: string | null;
    company: string | null;
    location: string | null;
    rate_text: string | null;
    ir35_status: string | null;
    legal_fields?: Record<string, string> | null;
    description: string | null;
  } | null;
  score: {
    overall_score: number | null;
    skill_match: number | null;
    experience_match: number | null;
    rate_match: number | null;
    location_match: number | null;
    reasoning: string | null;
  } | null;
  documents: {
    id: string;
    document_type: string;
    version: number;
    file_path: string;
    ats_score: number | null;
    ats_details: AtsDetails | null;
    jd_analysis: JdAnalysis | null;
    content_text: string | null;
    created_at: string | null;
  }[];
  notes: string | null;
}

// ── Score radar ───────────────────────────────────────────────────────────────

function ScoreRadar({ skill, experience, rate, location }: {
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
        return (
          <div key={label} className="text-center">
            <div className="relative h-16 w-16 mx-auto mb-1">
              <svg viewBox="0 0 36 36" className="h-16 w-16 -rotate-90">
                <circle cx="18" cy="18" r="15.9155" fill="none" stroke="#e2e8f0" strokeWidth="3" />
                <circle
                  cx="18" cy="18" r="15.9155" fill="none"
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

// ── ATS rubric ────────────────────────────────────────────────────────────────

function AtsRubric({ atsScore, atsDetails }: { atsScore: number | null; atsDetails: AtsDetails | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!atsScore) return null;

  const matched = atsDetails?.keyword_matches
    ?? atsDetails?.ats_analysis?.matched_keywords ?? [];
  const missing = atsDetails?.keyword_misses
    ?? atsDetails?.ats_analysis?.missing_keywords ?? [];
  const improvements = atsDetails?.improvements ?? [];
  const formatWarnings = atsDetails?.format_warnings ?? [];

  const color = atsScore >= 80 ? "text-green-700 bg-green-50" : atsScore >= 60 ? "text-amber-700 bg-amber-50" : "text-red-700 bg-red-50";
  const barColor = atsScore >= 80 ? "bg-green-500" : atsScore >= 60 ? "bg-amber-400" : "bg-red-400";

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          <span className={`text-sm font-semibold px-2 py-0.5 rounded-full ${color}`}>
            ATS {atsScore}%
          </span>
          <div className="w-32 bg-slate-100 rounded-full h-2 overflow-hidden">
            <div className={`h-full rounded-full ${barColor}`} style={{ width: `${atsScore}%` }} />
          </div>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-slate-400" /> : <ChevronDown className="h-4 w-4 text-slate-400" />}
      </button>

      {expanded && (
        <div className="border-t border-slate-100 px-4 py-3 space-y-3 text-sm">
          {matched.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-green-700 mb-1.5">
                ✓ Matched keywords ({matched.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {matched.map((kw) => (
                  <span key={kw} className="rounded-full bg-green-100 text-green-700 px-2 py-0.5 text-xs">{kw}</span>
                ))}
              </div>
            </div>
          )}
          {missing.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-red-600 mb-1.5">
                ✗ Missing keywords ({missing.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {missing.map((kw) => (
                  <span key={kw} className="rounded-full bg-red-100 text-red-600 px-2 py-0.5 text-xs">{kw}</span>
                ))}
              </div>
            </div>
          )}
          {formatWarnings.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-amber-700 mb-1">Structure warnings</p>
              <ul className="space-y-0.5">
                {formatWarnings.map((w, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-amber-700">
                    <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" /> {w}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {improvements.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-600 mb-1">Recommendations</p>
              <ol className="space-y-0.5 list-decimal list-inside">
                {improvements.map((imp, i) => (
                  <li key={i} className="text-xs text-slate-600">{imp}</li>
                ))}
              </ol>
            </div>
          )}
          {matched.length === 0 && missing.length === 0 && improvements.length === 0 && (
            <p className="text-xs text-slate-400">Detailed ATS analysis not available for this version.</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tailoring context ────────────────────────────────────────────────────────

function TailoringContext({ jdAnalysis }: { jdAnalysis: JdAnalysis | null }) {
  const [expanded, setExpanded] = useState(false);
  if (!jdAnalysis) return null;

  const mustHave = jdAnalysis.requirements?.must_have ?? [];
  const niceToHave = jdAnalysis.requirements?.nice_to_have ?? [];
  const allKeywords = [
    ...(jdAnalysis.ats_keywords?.technical ?? []),
    ...(jdAnalysis.ats_keywords?.methodologies ?? []),
    ...(jdAnalysis.ats_keywords?.domain ?? []),
    ...(jdAnalysis.ats_keywords?.certifications ?? []),
  ];
  const redFlags = jdAnalysis.tone_analysis?.red_flags ?? [];
  const skillMissing = jdAnalysis.skill_match?.missing ?? [];
  const recommendations = jdAnalysis.skill_match?.recommendations ?? [];

  const hasData = mustHave.length > 0 || niceToHave.length > 0 || allKeywords.length > 0;
  if (!hasData) return null;

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/50">
      <button
        onClick={() => setExpanded((p) => !p)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-xs font-semibold text-indigo-700">What the tailor targeted</span>
        {expanded ? <ChevronUp className="h-4 w-4 text-indigo-400" /> : <ChevronDown className="h-4 w-4 text-indigo-400" />}
      </button>
      {expanded && (
        <div className="border-t border-indigo-100 px-4 py-3 space-y-3 text-xs">
          {mustHave.length > 0 && (
            <div>
              <p className="font-semibold text-slate-700 mb-1">Must-have requirements targeted</p>
              <ul className="space-y-0.5">
                {mustHave.slice(0, 6).map((r, i) => <li key={i} className="text-slate-600">• {r}</li>)}
              </ul>
            </div>
          )}
          {allKeywords.length > 0 && (
            <div>
              <p className="font-semibold text-slate-700 mb-1.5">ATS keywords inserted</p>
              <div className="flex flex-wrap gap-1">
                {allKeywords.slice(0, 20).map((kw) => (
                  <span key={kw} className="rounded-full bg-indigo-100 text-indigo-700 px-2 py-0.5">{kw}</span>
                ))}
              </div>
            </div>
          )}
          {skillMissing.length > 0 && (
            <div>
              <p className="font-semibold text-amber-700 mb-1">Skill gaps not covered</p>
              <div className="flex flex-wrap gap-1">
                {skillMissing.map((kw) => (
                  <span key={kw} className="rounded-full bg-amber-100 text-amber-700 px-2 py-0.5">{kw}</span>
                ))}
              </div>
            </div>
          )}
          {redFlags.length > 0 && (
            <div>
              <p className="font-semibold text-red-600 mb-1">Red flags identified</p>
              <ul className="space-y-0.5">
                {redFlags.map((f, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-red-600">
                    <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" /> {f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {recommendations.length > 0 && (
            <div>
              <p className="font-semibold text-slate-600 mb-1">Recommendations applied</p>
              <ol className="space-y-0.5 list-decimal list-inside">
                {recommendations.map((r, i) => <li key={i} className="text-slate-600">{r}</li>)}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ApprovalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [detail, setDetail] = useState<ApprovalDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<"approving" | "rejecting" | null>(null);
  const [notes, setNotes] = useState("");
  const [notesSaving, setNotesSaving] = useState(false);
  const [notesSaved, setNotesSaved] = useState(false);

  useEffect(() => {
    fetchApprovalDetail(id)
      .then((d) => {
        const typed = d as unknown as ApprovalDetail;
        setDetail(typed);
        setNotes(typed.notes ?? "");
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const saveNotes = async () => {
    setNotesSaving(true);
    try {
      await fetch(`${API_BASE}/api/agents/approvals/${id}/notes`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      setNotesSaved(true);
      setTimeout(() => setNotesSaved(false), 2000);
    } finally {
      setNotesSaving(false);
    }
  };

  const handleApprove = async () => {
    setActing("approving");
    try {
      if (notes !== (detail?.notes ?? "")) await saveNotes();
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
                  <span className="flex items-center gap-1"><Building2 className="h-3.5 w-3.5" /> {job.company}</span>
                )}
                {job?.location && (
                  <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {job.location}</span>
                )}
                {job?.rate_text && (
                  <span className="font-semibold text-slate-700">{job.rate_text}</span>
                )}
                {(() => {
                  const legalVal = Object.values(job?.legal_fields ?? {})[0] ?? job?.ir35_status;
                  return legalVal ? (
                    <Badge variant="outline" className="text-xs capitalize">{legalVal.replace(/_/g, " ")}</Badge>
                  ) : null;
                })()}
              </div>
            </div>
            <Badge
              className={
                application.approval_status === "approved" ? "bg-green-100 text-green-700"
                  : application.approval_status === "rejected" ? "bg-red-100 text-red-700"
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

      {/* Documents with ATS rubric */}
      <div className="grid gap-4 sm:grid-cols-2">
        {[{ doc: cv, label: "Tailored CV" }, { doc: cl, label: "Cover Letter" }].map(({ doc, label }) => (
          <Card key={label}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <FileText className="h-4 w-4 text-brand-600" />
                {label}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {doc ? (
                <>
                  <div className="space-y-1">
                    <p className="text-xs text-slate-500">Version {doc.version}</p>
                    <p className="text-xs text-slate-400 truncate">{doc.file_path}</p>
                  </div>
                  {doc.ats_score !== null && (
                    <AtsRubric atsScore={doc.ats_score} atsDetails={doc.ats_details} />
                  )}
                  {doc.document_type === "cv" && (
                    <TailoringContext jdAnalysis={doc.jd_analysis} />
                  )}
                </>
              ) : (
                <p className="text-xs text-slate-400">Not generated yet</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Reviewer notes / inline edit */}
      {!isDecided && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Reviewer notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-slate-500">
              Add any notes or edits before approving. These are saved with the application.
            </p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={5}
              placeholder="e.g. Adjusted summary to emphasise stakeholder management. Add SAFe experience if asked."
              className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-brand-500 resize-y"
            />
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void saveNotes()}
                disabled={notesSaving}
              >
                {notesSaving ? (
                  <RefreshCw className="h-3.5 w-3.5 mr-1 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5 mr-1" />
                )}
                {notesSaved ? "Saved!" : "Save notes"}
              </Button>
              {notesSaved && (
                <CheckCircle2 className="h-4 w-4 text-green-500" />
              )}
            </div>
          </CardContent>
        </Card>
      )}

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
            Save &amp; Approve
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
          {detail.notes && (
            <span className="ml-2 text-slate-400 italic">&ldquo;{detail.notes}&rdquo;</span>
          )}
        </div>
      )}
    </div>
  );
}
