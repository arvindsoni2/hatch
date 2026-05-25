import Link from "next/link";
import { redirect } from "next/navigation";
import {
  fetchProfileStatus,
  fetchRawProfile,
  fetchAllAgentStatus,
  fetchPipelineStats,
  fetchPendingApprovals,
  fetchJobs,
  getUpcomingInterviews,
  fetchFollowUpReminders,
  type AllAgentStatus,
  type PipelineStats,
  type PendingApproval,
  type RawProfile,
  type FollowUpReminder,
} from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { Button } from "@/components/ui/button";
import { TriggerScrapeButton } from "@/components/TriggerScrapeButton";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import { ArrowRight, CheckCircle2, AlertTriangle, XCircle, Zap, ClipboardCheck, Briefcase, Stars, Bell } from "lucide-react";
import { formatDistanceToNow, addHours } from "date-fns";

export const revalidate = 60;

// ── Agent status strip ────────────────────────────────────────────────────────

function getSystemHealth(agentStatus: AllAgentStatus | null): "green" | "amber" | "red" {
  if (!agentStatus) return "amber";
  const statuses = agentStatus.agents.map((a) => a.status);
  if (statuses.includes("error")) return "red";
  if (statuses.includes("running")) return "green";
  if (statuses.every((s) => s === "never_run")) return "amber";
  return "green";
}

function AgentStatusStrip({
  agentStatus,
  scrapeIntervalHours,
}: {
  agentStatus: AllAgentStatus | null;
  scrapeIntervalHours: number;
}) {
  const health = getSystemHealth(agentStatus);
  const scout = agentStatus?.agents.find((a) => a.agent_name === "scout");
  const lastRunAt = scout?.last_run_at ? new Date(scout.last_run_at) : null;
  const nextRunAt = lastRunAt ? addHours(lastRunAt, scrapeIntervalHours) : null;
  const hoursSinceLastRun = lastRunAt
    ? (Date.now() - lastRunAt.getTime()) / (1000 * 60 * 60)
    : null;
  const isStale = hoursSinceLastRun != null && hoursSinceLastRun > scrapeIntervalHours * 2;

  if (isStale) {
    return (
      <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
          <span>No scrapes in the last {Math.round(hoursSinceLastRun!)} hours.</span>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/settings" className="text-xs font-medium underline underline-offset-2">
            Check agent status
          </Link>
          <TriggerScrapeButton variant="link" />
        </div>
      </div>
    );
  }

  const dotColor =
    health === "green" ? "bg-green-500" : health === "amber" ? "bg-amber-400" : "bg-red-500";
  const statusText =
    health === "green"
      ? "All agents running"
      : health === "amber"
      ? "Agents idle"
      : "Agent error — check settings";

  return (
    <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-xs text-slate-500 shadow-sm">
      <span className={`h-2 w-2 shrink-0 rounded-full ${dotColor}`} />
      <span className="font-medium text-slate-700">{statusText}</span>
      {lastRunAt && (
        <>
          <span className="text-slate-300">·</span>
          <span>Last scrape: {formatDistanceToNow(lastRunAt, { addSuffix: true })}</span>
        </>
      )}
      {nextRunAt && nextRunAt > new Date() && (
        <>
          <span className="text-slate-300">·</span>
          <span>Next: {formatDistanceToNow(nextRunAt)}</span>
        </>
      )}
      {health === "red" && (
        <>
          <span className="text-slate-300">·</span>
          <Link href="/settings" className="font-medium text-red-600 hover:underline">
            View details
          </Link>
        </>
      )}
    </div>
  );
}

// ── Action cards ──────────────────────────────────────────────────────────────

function ActionCard({
  icon,
  count,
  label,
  subtitle,
  href,
  featured,
}: {
  icon: React.ReactNode;
  count: number;
  label: string;
  subtitle: string;
  href: string;
  featured?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`flex flex-col gap-2 rounded-xl border bg-white p-5 shadow-sm transition-all hover:shadow-md ${
        featured ? "border-brand-300 ring-1 ring-brand-200" : "border-slate-200 hover:border-brand-200"
      }`}
    >
      <div className="flex items-center gap-2 text-sm font-medium text-slate-500">
        {icon}
        {label}
      </div>
      <p className="text-4xl font-bold tabular-nums text-slate-900">{count}</p>
      <p className="text-xs text-slate-400">{subtitle}</p>
    </Link>
  );
}

// ── Pipeline bar ──────────────────────────────────────────────────────────────

function PipelineBar({ stats }: { stats: PipelineStats | null }) {
  if (!stats || stats.discovered === 0) return null;
  const total = stats.discovered;

  function Segment({
    count,
    label,
    color,
  }: {
    count: number;
    label: string;
    color: string;
  }) {
    if (count === 0) return null;
    const pct = Math.max(4, (count / total) * 100);
    return (
      <div className="flex flex-col items-center gap-1 min-w-0" style={{ flex: pct }}>
        <div className={`h-4 w-full rounded-sm ${color}`} />
        <span className="text-xs text-slate-500 truncate">
          {count.toLocaleString()} {label}
        </span>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className="text-sm font-semibold text-slate-700">Jobs pipeline</h2>
        <span className="text-xs text-slate-400">{total.toLocaleString()} jobs found by Scout</span>
      </div>
      <div className="flex items-end gap-1 overflow-hidden">
        <Segment count={stats.discovered} label="jobs found" color="bg-slate-200" />
        <Segment count={stats.scored} label="scored" color="bg-blue-200" />
        <Segment count={stats.shortlisted} label="shortlisted" color="bg-brand-300" />
        <Segment count={stats.tailored} label="tailored" color="bg-indigo-300" />
        <Segment count={stats.approved} label="approved" color="bg-green-400" />
      </div>
    </div>
  );
}

// ── Empty state (fresh profile, no jobs yet) ──────────────────────────────────

function EmptyState({ scrapeIntervalHours }: { scrapeIntervalHours: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-10 text-center shadow-sm">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-100">
        <Zap className="h-6 w-6 text-brand-600" />
      </div>
      <h3 className="text-lg font-semibold text-slate-900">Your agents are warming up</h3>
      <p className="mt-2 text-sm text-slate-500">
        First scrape runs in the next {scrapeIntervalHours} hours. Jobs will appear here automatically.
      </p>
      <div className="mt-6 flex flex-col items-center gap-3">
        <TriggerScrapeButton variant="primary" />
        <Link
          href="/settings"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
        >
          Edit profile
        </Link>
      </div>
    </div>
  );
}

// ── Follow-up reminders ───────────────────────────────────────────────────────

function FollowUpSection({ reminders }: { reminders: FollowUpReminder[] }) {
  if (reminders.length === 0) return null;
  const overdue = reminders.filter((r) => r.overdue);
  const upcoming = reminders.filter((r) => !r.overdue);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Bell className="h-4 w-4 text-amber-500" />
          Follow-up reminders
          {overdue.length > 0 && (
            <span className="rounded-full bg-red-100 text-red-700 text-xs px-2 py-0.5 font-medium">
              {overdue.length} overdue
            </span>
          )}
        </h2>
        <Link href="/applications" className="flex items-center gap-1 text-xs text-brand-600 hover:underline">
          View all <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm divide-y divide-slate-100 overflow-hidden">
        {reminders.slice(0, 5).map((r) => (
          <div key={r.application_id} className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-800 truncate">
                {r.job_title ?? "Untitled Role"}
              </p>
              {r.company && (
                <p className="text-xs text-slate-500 truncate">{r.company}</p>
              )}
            </div>
            <div className="flex items-center gap-3 shrink-0 text-right">
              <div>
                <p className="text-xs text-slate-500">
                  {r.days_since_applied}d since applied
                </p>
                <p className={`text-xs font-medium ${r.overdue ? "text-red-600" : "text-amber-600"}`}>
                  Follow-up #{r.follow_up_number} {r.overdue ? "overdue" : "due"}
                </p>
              </div>
              <span className={`h-2 w-2 rounded-full shrink-0 ${r.overdue ? "bg-red-400" : "bg-amber-400"}`} />
            </div>
          </div>
        ))}
        {reminders.length > 5 && (
          <div className="px-4 py-2 text-xs text-slate-400 text-center">
            +{reminders.length - 5} more — <Link href="/applications" className="text-brand-600 hover:underline">view all</Link>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function DashboardPage() {
  const profileStatus = await fetchProfileStatus().catch(() => null);
  if (profileStatus?.onboarding_required) {
    redirect("/onboarding");
  }

  const [rawProfile, agentStatus, pipelineStats, pendingApprovals, upcomingInterviews, followUpReminders] =
    await Promise.all([
      fetchRawProfile().catch((): RawProfile => ({})),
      fetchAllAgentStatus().catch((): AllAgentStatus | null => null),
      fetchPipelineStats().catch((): PipelineStats | null => null),
      fetchPendingApprovals().catch((): PendingApproval[] => []),
      getUpcomingInterviews(14).catch(() => []),
      fetchFollowUpReminders().catch((): FollowUpReminder[] => []),
    ]);

  const threshold = rawProfile.scoring?.shortlist_threshold ?? 0.75;
  const scrapeIntervalHours = rawProfile.preferences?.scrape_interval_hours ?? 4;

  const topJobs = await fetchJobs({ min_match_score: threshold, hide_ghosts: true }, 0, 5).catch(
    () => ({ items: [], total: 0 }),
  );

  // Dashboard subtitle from profile
  const roles = rawProfile.search?.target_roles?.join(", ") ?? "";
  const locationParts =
    rawProfile.search?.locations
      ?.map((l) => (l.remote_preference === "remote" ? "Remote" : l.city))
      .filter(Boolean) ?? [];
  const locations = locationParts.join(", ");
  const subtitle = roles ? [roles, locations].filter(Boolean).join(" — ") : null;

  // Action card counts
  const reviewCount = pendingApprovals.length;
  const prepCount = upcomingInterviews.filter(
    (i) => i.scheduled_at != null && new Date(i.scheduled_at) > new Date(),
  ).length;
  const newMatchCount = topJobs.total;
  const aboveThresholdCount = topJobs.items.filter(
    (j) => j.match_score != null && j.match_score >= threshold,
  ).length;

  const allCaughtUp = reviewCount === 0 && prepCount === 0 && newMatchCount === 0;
  const noJobsYet = (pipelineStats?.discovered ?? 0) === 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Home</h1>
        {subtitle && (
          <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
        )}
      </div>

      {/* Section A: Agent status strip */}
      <AgentStatusStrip agentStatus={agentStatus} scrapeIntervalHours={scrapeIntervalHours} />

      {/* Empty state for fresh setups */}
      {noJobsYet ? (
        <EmptyState scrapeIntervalHours={scrapeIntervalHours} />
      ) : (
        <>
          {/* Section B: Action cards */}
          {allCaughtUp ? (
            <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm font-medium text-green-800">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              {"You're all caught up."}
              {pipelineStats && (() => {
                const scoutLastRun = agentStatus?.agents.find((a) => a.agent_name === "scout")?.last_run_at;
                const nextRun = scoutLastRun ? addHours(new Date(scoutLastRun), scrapeIntervalHours) : null;
                const isFuture = nextRun && nextRun > new Date();
                return (
                  <span className="font-normal text-green-700">
                    {isFuture
                      ? `Next scrape ${formatDistanceToNow(nextRun!, { addSuffix: true })}.`
                      : `Scout runs every ${scrapeIntervalHours}h.`}
                  </span>
                );
              })()}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {reviewCount > 0 && (
                <ActionCard
                  featured
                  icon={<ClipboardCheck className="h-4 w-4 text-brand-500" />}
                  count={reviewCount}
                  label="Review needed"
                  subtitle="tailored applications ready"
                  href="/approvals"
                />
              )}
              {prepCount > 0 && (
                <ActionCard
                  icon={<Briefcase className="h-4 w-4 text-indigo-500" />}
                  count={prepCount}
                  label="Interview coming up"
                  subtitle={
                    upcomingInterviews[0]?.scheduled_at
                      ? formatDistanceToNow(new Date(upcomingInterviews[0].scheduled_at), { addSuffix: true })
                      : "upcoming interviews"
                  }
                  href="/applications"
                />
              )}
              {newMatchCount > 0 && (
                <ActionCard
                  icon={<Stars className="h-4 w-4 text-amber-500" />}
                  count={newMatchCount}
                  label="New matches"
                  subtitle={
                    aboveThresholdCount > 0
                      ? `${aboveThresholdCount} above ${Math.round(threshold * 100)}% threshold`
                      : "jobs discovered recently"
                  }
                  href={`/jobs?min_match_score=${threshold}`}
                />
              )}
            </div>
          )}

          {/* Section C: Top matches */}
          {topJobs.items.length > 0 && (
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">Top matches</h2>
                <Link href="/jobs" className="flex items-center gap-1 text-xs text-brand-600 hover:underline">
                  View all jobs <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
              <div className="space-y-2">
                {topJobs.items.map((job) => (
                  <JobCard key={job.id} job={job} threshold={threshold} />
                ))}
              </div>
            </div>
          )}

          {/* Section D: Pipeline bar */}
          <PipelineBar stats={pipelineStats} />

          {/* Section E: Follow-up reminders */}
          <FollowUpSection reminders={followUpReminders} />

          {/* Section F: Activity timeline */}
          <ActivityTimeline />
        </>
      )}
    </div>
  );
}
