import { notFound } from "next/navigation";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft, ExternalLink, Search, Brain, FileText,
  CheckCircle2, AlertTriangle, Clock, DollarSign,
} from "lucide-react";
import { fetchJob, fetchJobDecisions, type DecisionStep } from "@/lib/api";
import { ScoreRationale } from "@/components/ScoreRationale";

export const revalidate = 60;

// ── Score bar (used in decision trail) ────────────────────────────────────────

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-green-500" : pct >= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <span className="w-36 text-xs text-slate-500 shrink-0">{label}</span>
      <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-xs font-medium text-slate-700 text-right">{pct}%</span>
    </div>
  );
}

// ── Agent icon mapping ────────────────────────────────────────────────────────

const AGENT_ICONS: Record<string, React.ReactNode> = {
  scout: <Search className="h-4 w-4 text-slate-500" />,
  scorer: <Brain className="h-4 w-4 text-blue-500" />,
  tailor: <FileText className="h-4 w-4 text-indigo-500" />,
  human: <CheckCircle2 className="h-4 w-4 text-green-500" />,
};

const STATUS_RING: Record<string, string> = {
  completed: "ring-green-200 bg-green-50",
  failed: "ring-red-200 bg-red-50",
  processing: "ring-blue-200 bg-blue-50",
  pending: "ring-amber-200 bg-amber-50",
};

// ── Decision step card ────────────────────────────────────────────────────────

function StepCard({ step }: { step: DecisionStep }) {
  const ringClass = STATUS_RING[step.status] ?? "ring-slate-200 bg-white";
  const icon = AGENT_ICONS[step.agent] ?? <Clock className="h-4 w-4 text-slate-400" />;
  const hasCost = step.cost_estimate != null && step.cost_estimate > 0;

  return (
    <div className={`rounded-xl border ring-1 p-4 ${ringClass}`}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-slate-200">
            {icon}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                Step {step.step}
              </span>
              <span className="text-xs text-slate-400">·</span>
              <span className="text-xs text-slate-500 capitalize">{step.agent}</span>
            </div>
            <p className="text-sm font-medium text-slate-800 mt-0.5">{step.summary}</p>
          </div>
        </div>
        <span className="text-xs text-slate-400 shrink-0">
          {formatDistanceToNow(new Date(step.timestamp), { addSuffix: true })}
        </span>
      </div>

      {/* Score breakdown */}
      {step.event_type === "job_scored" && (
        <div className="space-y-1.5 mt-2 mb-3">
          <ScoreBar label="Skill match" value={step.skill_match} />
          <ScoreBar label="Experience match" value={step.experience_match} />
          <ScoreBar label="Rate match" value={step.rate_match} />
          <ScoreBar label="Location match" value={step.location_match} />
        </div>
      )}

      {/* Reasoning */}
      {step.reasoning && (
        <p className="text-xs text-slate-600 bg-white/70 rounded px-2.5 py-2 leading-relaxed mb-2">
          &ldquo;{step.reasoning}&rdquo;
        </p>
      )}

      {/* ATS score */}
      {step.ats_score != null && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-slate-500">ATS score:</span>
          <span className="text-sm font-semibold text-green-700">{step.ats_score}%</span>
        </div>
      )}

      {/* LLM metadata footer */}
      {(step.model_used || hasCost) && (
        <div className="flex items-center gap-3 mt-2 pt-2 border-t border-white/60 text-xs text-slate-400">
          {step.model_used && <span>{step.model_used}</span>}
          {step.tokens_in && <span>{step.tokens_in.toLocaleString()} in / {step.tokens_out?.toLocaleString()} out tokens</span>}
          {hasCost && (
            <span className="flex items-center gap-0.5">
              <DollarSign className="h-3 w-3" />
              ~${(step.cost_estimate! * 100).toFixed(3)}¢
            </span>
          )}
          {step.duration_ms && <span>{step.duration_ms}ms</span>}
        </div>
      )}

      {/* Error */}
      {step.status === "failed" && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-red-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          Step failed
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function JobDetailPage({ params }: { params: { id: string } }) {
  const [job, decisions] = await Promise.all([
    fetchJob(params.id).catch(() => null),
    fetchJobDecisions(params.id).catch(() => null),
  ]);

  if (!job) notFound();

  const matchPct = job.match_score != null ? Math.round(job.match_score * 100) : null;
  const scoreColor =
    matchPct == null
      ? "text-slate-400"
      : matchPct >= 80
      ? "text-green-700"
      : matchPct >= 60
      ? "text-amber-600"
      : "text-red-600";

  return (
    <div className="space-y-6">
      {/* Back navigation */}
      <Link
        href="/jobs"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="h-4 w-4" /> Back to jobs
      </Link>

      {/* Job header */}
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">{job.title}</h1>
            <p className="mt-1 text-slate-600">{job.company}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-slate-500">
              {job.location && <span>{job.location}</span>}
              {job.rate_text && (
                <>
                  <span className="text-slate-300">·</span>
                  <span>{job.rate_text}</span>
                </>
              )}
              {(() => {
                const legalVal = Object.values(job.legal_fields ?? {})[0] ?? job.ir35_status;
                return legalVal ? (
                  <>
                    <span className="text-slate-300">·</span>
                    <span className="capitalize">{legalVal.replace(/_/g, " ")}</span>
                  </>
                ) : null;
              })()}
              {job.source && (
                <>
                  <span className="text-slate-300">·</span>
                  <span className="capitalize">{job.source}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            {matchPct != null && (
              <span className={`text-3xl font-bold tabular-nums ${scoreColor}`}>
                {matchPct}%
              </span>
            )}
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
              >
                View original <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>

        {job.description && (
          <div className="mt-4 border-t border-slate-100 pt-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Description</h2>
            <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap line-clamp-[12]">
              {job.description}
            </p>
          </div>
        )}
      </div>

      {/* Score rationale */}
      <ScoreRationale job={job} />

      {/* Decision trail */}
      {decisions && decisions.steps.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700">Decision trail</h2>
            {decisions.total_cost_usd > 0 && (
              <span className="text-xs text-slate-400">
                Total LLM cost: ~${(decisions.total_cost_usd * 100).toFixed(3)}¢
              </span>
            )}
          </div>
          <div className="space-y-3">
            {decisions.steps.map((step) => (
              <StepCard key={`${step.step}-${step.event_type}`} step={step} />
            ))}
          </div>
        </div>
      )}

      {(!decisions || decisions.steps.length === 0) && (
        <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
          No agent decisions recorded for this job yet.
        </div>
      )}
    </div>
  );
}
