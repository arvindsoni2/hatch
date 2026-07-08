import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft, ExternalLink, Search, Brain, FileText,
  CheckCircle2, AlertTriangle, Clock, DollarSign,
} from "lucide-react";
import type { DecisionStep, DecisionTrail, Job, JobScoreRead } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { ScoreRationale } from "@/components/ScoreRationale";
import { PageContainer } from "@/components/ui/page-layout";
import { StatusBadge } from "@/components/ui/status-badge";

export const revalidate = 60;

// ── Score bar (used in decision trail) ────────────────────────────────────────

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "var(--success)" : pct >= 60 ? "var(--warning)" : "var(--danger)";
  return (
    <div className="flex items-center gap-2">
      <span className="w-36 shrink-0 text-xs text-[var(--text-dim)]">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-2)]">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-8 text-right text-xs font-medium text-[var(--text)]">{pct}%</span>
    </div>
  );
}

// ── Agent icon mapping ────────────────────────────────────────────────────────

const AGENT_ICONS: Record<string, React.ReactNode> = {
  scout: <Search className="h-4 w-4 text-[var(--text-dim)]" />,
  scorer: <Brain className="h-4 w-4 text-[var(--accent)]" />,
  tailor: <FileText className="h-4 w-4 text-[var(--accent)]" />,
  human: <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />,
};

function stepStatusBadge(status: string) {
  if (status === "completed") return <StatusBadge tone="success">Completed</StatusBadge>;
  if (status === "failed") return <StatusBadge tone="danger">Failed</StatusBadge>;
  if (status === "processing") return <StatusBadge tone="info">Processing</StatusBadge>;
  if (status === "pending") return <StatusBadge tone="warning">Pending</StatusBadge>;
  return <StatusBadge tone="neutral">{status || "Unknown"}</StatusBadge>;
}

// ── Decision step card ────────────────────────────────────────────────────────

function StepCard({ step }: { step: DecisionStep }) {
  const icon = AGENT_ICONS[step.agent] ?? <Clock className="h-4 w-4 text-[var(--text-muted)]" />;
  const hasCost = step.cost_estimate != null && step.cost_estimate > 0;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 ring-1 ring-[var(--border)]">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--surface-2)] shadow-sm ring-1 ring-[var(--border)]">
            {icon}
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--text-dim)]">
                Step {step.step}
              </span>
              <span className="text-xs text-[var(--text-muted)]">|</span>
              <span className="text-xs capitalize text-[var(--text-dim)]">{step.agent}</span>
              {stepStatusBadge(step.status)}
            </div>
            <p className="mt-0.5 text-sm font-medium text-[var(--text)]">{step.summary}</p>
          </div>
        </div>
        <span className="shrink-0 text-xs text-[var(--text-muted)]">
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
        <p className="mb-2 rounded bg-[var(--surface-2)] px-2.5 py-2 text-xs leading-relaxed text-[var(--text-dim)]">
          &ldquo;{step.reasoning}&rdquo;
        </p>
      )}

      {/* ATS score */}
      {step.ats_score != null && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-[var(--text-dim)]">ATS score:</span>
          <span className="text-sm font-semibold text-[var(--success)]">{step.ats_score}%</span>
        </div>
      )}

      {/* LLM metadata footer */}
      {(step.model_used || hasCost) && (
        <div className="mt-2 flex items-center gap-3 border-t border-[var(--border)] pt-2 text-xs text-[var(--text-muted)]">
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
        <div className="mt-2 flex items-center gap-1.5 text-xs text-[var(--danger)]">
          <AlertTriangle className="h-3.5 w-3.5" />
          Step failed
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const job = await serverApiFetch<Job>(`/api/jobs/${id}`);
  const [decisions, jobScore] = await Promise.all([
    serverApiFetch<DecisionTrail>(`/api/jobs/${id}/decisions`).catch(() => null),
    serverApiFetch<JobScoreRead>(`/api/v2/scoring/${id}`).catch(() => null),
  ]);

  const matchPct = job.match_score != null ? Math.round(job.match_score * 100) : null;
  const scoreColor =
    matchPct == null
      ? "var(--text-muted)"
      : matchPct >= 80
      ? "var(--success)"
      : matchPct >= 60
      ? "var(--warning)"
      : "var(--danger)";

  return (
    <PageContainer width="wide" className="space-y-6">
      <nav aria-label="Job detail breadcrumb">
        <Link
          href="/jobs"
          className="inline-flex items-center gap-1 text-sm font-medium text-[var(--text-dim)] hover:text-[var(--text)]"
        >
          <ArrowLeft className="h-4 w-4" /> Jobs
        </Link>
      </nav>

      {/* Job header */}
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-[var(--text)]">{job.title}</h1>
            <p className="mt-1 text-[var(--text-dim)]">{job.company}</p>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--text-dim)]">
              {job.location && <span>{job.location}</span>}
              {job.rate_text && (
                <>
                  <span className="text-[var(--text-muted)]">|</span>
                  <span>{job.rate_text}</span>
                </>
              )}
              {(() => {
                const legalVal = Object.values(job.legal_fields ?? {})[0] ?? job.ir35_status;
                return legalVal ? (
                  <>
                    <span className="text-[var(--text-muted)]">|</span>
                    <span className="capitalize">{legalVal.replace(/_/g, " ")}</span>
                  </>
                ) : null;
              })()}
              {job.source && (
                  <>
                    <span className="text-[var(--text-muted)]">|</span>
                    <span className="capitalize">{job.source}</span>
                  </>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            {matchPct != null && (
              <span className="text-3xl font-bold tabular-nums" style={{ color: scoreColor }}>
                {matchPct}%
              </span>
            )}
            {jobScore?.scored_at && (
              <span className="text-xs text-[var(--text-muted)]">
                Scored {formatDistanceToNow(new Date(jobScore.scored_at), { addSuffix: true })}
              </span>
            )}
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-[var(--accent)] hover:underline"
              >
                View original <ExternalLink className="h-3 w-3" />
              </a>
            )}
            <Link
              href={job.url ? `/tailor?jobUrl=${encodeURIComponent(job.url)}` : "/tailor"}
              className="hatch-interactive inline-flex min-h-10 items-center justify-center rounded-lg px-3 text-sm font-medium"
              style={{ background: "var(--accent)", color: "var(--on-accent)", textDecoration: "none" }}
            >
              <FileText className="mr-2 h-4 w-4" /> Create CV pack
            </Link>
          </div>
        </div>

        {job.description && (
          <div className="mt-4 border-t border-[var(--border)] pt-4">
            <h2 className="mb-2 text-sm font-semibold text-[var(--text)]">Description</h2>
            <p className="line-clamp-[12] whitespace-pre-wrap text-sm leading-relaxed text-[var(--text-dim)]">
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
            <h2 className="text-sm font-semibold text-[var(--text)]">Decision trail</h2>
            {decisions.total_cost_usd > 0 && (
              <span className="text-xs text-[var(--text-muted)]">
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
        <div className="rounded-xl border border-dashed p-8 text-center space-y-2" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
          {job.match_score == null ? (
            <>
              <p className="text-sm font-medium" style={{ color: "var(--text)" }}>Awaiting scoring</p>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                This job was stored before the scoring pipeline ran. Go to Inbox → Show all → Score now to queue it, or wait for the next scheduled scrape.
              </p>
            </>
          ) : (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>No agent decisions recorded for this job yet.</p>
          )}
        </div>
      )}
    </PageContainer>
  );
}
