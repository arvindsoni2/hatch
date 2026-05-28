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
  fetchRateLimitStatus,
  type AllAgentStatus,
  type PipelineStats,
  type PendingApproval,
  type RawProfile,
  type FollowUpReminder,
  type RateLimitStatus,
} from "@/lib/api";
import { TriggerScrapeButton } from "@/components/TriggerScrapeButton";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import {
  Inbox,
  Send,
  Target,
  Sparkles,
  ArrowUp,
  ArrowDown,
  AlertTriangle,
  CheckCircle2,
  Zap,
  Bell,
  ExternalLink,
} from "lucide-react";
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

function AgentStatusBanner({
  agentStatus,
  scrapeIntervalHours,
}: {
  agentStatus: AllAgentStatus | null;
  scrapeIntervalHours: number;
}) {
  const health = getSystemHealth(agentStatus);
  const scout = agentStatus?.agents.find((a) => a.agent_name === "scout");
  const lastRunAt = scout?.last_run_at ? new Date(scout.last_run_at) : null;
  const hoursSinceLastRun = lastRunAt
    ? (Date.now() - lastRunAt.getTime()) / (1000 * 60 * 60)
    : null;
  const isStale = hoursSinceLastRun != null && hoursSinceLastRun > scrapeIntervalHours * 2;

  if (isStale) {
    return (
      <div
        className="flex items-center justify-between rounded-xl px-4 py-3 text-sm"
        style={{
          background: "var(--warning-soft)",
          border: "1px solid var(--warning)",
          color: "var(--warning)",
        }}
      >
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} />
          <span>No scrapes in the last {Math.round(hoursSinceLastRun!)} hours.</span>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/settings" className="text-xs font-medium underline underline-offset-2">
            Check settings
          </Link>
          <TriggerScrapeButton variant="link" />
        </div>
      </div>
    );
  }

  if (health === "red") {
    return (
      <div
        className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm"
        style={{ background: "var(--danger-soft)", color: "var(--danger)", border: "1px solid var(--danger)" }}
      >
        <AlertTriangle size={14} />
        <span>Agent error —</span>
        <Link href="/settings" className="font-medium underline underline-offset-2">
          check settings
        </Link>
      </div>
    );
  }

  return null;
}

// ── KPI card ──────────────────────────────────────────────────────────────────

function KpiCard({
  icon,
  label,
  value,
  delta,
  deltaUp,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  delta?: string;
  deltaUp?: boolean;
}) {
  return (
    <div
      className="rounded-xl p-5"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <div
        className="flex items-center gap-1.5 text-xs font-medium mb-2"
        style={{ color: "var(--text-muted)" }}
      >
        {icon}
        {label}
      </div>
      <div
        className="text-3xl font-bold mb-1.5"
        style={{ letterSpacing: "-0.02em", color: "var(--text)" }}
      >
        {value}
      </div>
      {delta && (
        <div
          className="flex items-center gap-1 text-xs font-medium"
          style={{ color: deltaUp ? "var(--success)" : "var(--danger)" }}
        >
          {deltaUp ? <ArrowUp size={10} /> : <ArrowDown size={10} />}
          {delta}
        </div>
      )}
    </div>
  );
}

// ── Rate limit banner ─────────────────────────────────────────────────────────

function RateLimitBanner({ status }: { status: RateLimitStatus | null }) {
  if (!status) return null;
  if (!status.throttled && status.rpm_remaining > 3 && status.last_429_at === null) return null;

  const msg = status.last_429_at !== null
    ? `Provider returned 429. Backing off ${Math.round(status.wait_seconds)}s.`
    : status.throttled
    ? `Rate limited: waiting ${Math.round(status.wait_seconds)}s.`
    : `Rate limit close: ${status.rpm_remaining} of ${status.rpm_limit} req/min remaining.`;

  return (
    <div
      className="flex items-center gap-2 rounded-xl px-4 py-3 text-sm"
      style={{ background: "var(--warning-soft)", border: "1px solid var(--warning)", color: "var(--warning)" }}
    >
      <AlertTriangle size={14} />
      <span>{msg}</span>
      <Link href="/analytics" className="ml-auto text-xs font-medium underline underline-offset-2">
        View rate stats
      </Link>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ scrapeIntervalHours }: { scrapeIntervalHours: number }) {
  return (
    <div
      className="rounded-xl p-10 text-center"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <div
        className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full"
        style={{ background: "var(--accent-soft)", color: "var(--accent)" }}
      >
        <Zap size={24} />
      </div>
      <h3 className="text-lg font-semibold mb-2" style={{ color: "var(--text)" }}>
        Your agents are warming up
      </h3>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        First scrape runs in the next {scrapeIntervalHours} hours. Jobs will appear here automatically.
      </p>
      <div className="flex flex-col items-center gap-3">
        <TriggerScrapeButton variant="primary" />
        <Link href="/settings" className="text-sm" style={{ color: "var(--text-muted)" }}>
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

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--text)" }}>
          <Bell size={14} style={{ color: "var(--warning)" }} />
          Follow-up reminders
          {overdue.length > 0 && (
            <span
              className="text-xs px-2 py-0.5 rounded-full font-medium"
              style={{ background: "var(--danger-soft)", color: "var(--danger)" }}
            >
              {overdue.length} overdue
            </span>
          )}
        </div>
        <Link
          href="/applications"
          className="flex items-center gap-1 text-xs font-medium"
          style={{ color: "var(--accent)" }}
        >
          View all <ExternalLink size={10} />
        </Link>
      </div>
      <div
        className="rounded-xl divide-y overflow-hidden"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          "--tw-divide-opacity": 1,
        } as React.CSSProperties}
      >
        {reminders.slice(0, 5).map((r) => (
          <div key={r.application_id} className="flex items-center justify-between px-4 py-3 gap-4">
            <div className="min-w-0">
              <p className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>
                {r.job_title ?? "Untitled Role"}
              </p>
              {r.company && (
                <p className="text-xs truncate" style={{ color: "var(--text-muted)" }}>{r.company}</p>
              )}
            </div>
            <div className="flex items-center gap-3 shrink-0 text-right">
              <div>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {r.days_since_applied}d since applied
                </p>
                <p
                  className="text-xs font-medium"
                  style={{ color: r.overdue ? "var(--danger)" : "var(--warning)" }}
                >
                  Follow-up #{r.follow_up_number} {r.overdue ? "overdue" : "due"}
                </p>
              </div>
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ background: r.overdue ? "var(--danger)" : "var(--warning)" }}
              />
            </div>
          </div>
        ))}
        {reminders.length > 5 && (
          <div className="px-4 py-2 text-xs text-center" style={{ color: "var(--text-muted)" }}>
            +{reminders.length - 5} more —{" "}
            <Link href="/applications" style={{ color: "var(--accent)" }}>
              view all
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Hero section ──────────────────────────────────────────────────────────────

function HeroSection({
  reviewCount,
  pipelineStats,
  agentStatus,
  scrapeIntervalHours,
}: {
  reviewCount: number;
  pipelineStats: PipelineStats | null;
  agentStatus: AllAgentStatus | null;
  scrapeIntervalHours: number;
}) {
  const health = getSystemHealth(agentStatus);
  const scout = agentStatus?.agents.find((a) => a.agent_name === "scout");
  const lastRunAt = scout?.last_run_at ? new Date(scout.last_run_at) : null;
  const nextRunAt = lastRunAt ? addHours(lastRunAt, scrapeIntervalHours) : null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-4 mb-6">
      <div
        className="rounded-xl p-6"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <h2 className="text-xl font-semibold mb-2" style={{ color: "var(--text)", letterSpacing: "-0.015em" }}>
          Good morning.
        </h2>
        <p className="text-sm mb-5" style={{ color: "var(--text-dim)", lineHeight: 1.6 }}>
          {reviewCount > 0 ? (
            <>
              Hatch found{" "}
              <strong style={{ color: "var(--text)" }}>{reviewCount} new roles</strong> that match
              your filters. Review them when you have a moment.
            </>
          ) : (
            "Your agents are working in the background. New matches will appear here."
          )}
        </p>
        <div className="flex flex-wrap gap-2">
          {reviewCount > 0 && (
            <Link
              href="/jobs"
              className="inline-flex items-center gap-1.5 rounded-lg font-medium text-sm"
              style={{
                padding: "10px 16px",
                background: "var(--accent)",
                color: "#fff",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <Inbox size={14} />
              Review {reviewCount} new role{reviewCount !== 1 ? "s" : ""}
            </Link>
          )}
          <Link
            href="/applications"
            className="inline-flex items-center gap-1.5 rounded-lg font-medium text-sm"
            style={{
              padding: "10px 16px",
              background: "var(--surface-2)",
              color: "var(--text)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            Open pipeline
          </Link>
        </div>
      </div>

      <div
        className="rounded-xl p-5"
        style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs font-medium uppercase" style={{ color: "var(--text-muted)", letterSpacing: "0.06em" }}>
            Status
          </span>
          <span
            className="flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full"
            style={{
              background: health === "green" ? "var(--success-soft)" : "var(--warning-soft)",
              color: health === "green" ? "var(--success)" : "var(--warning)",
            }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: health === "green" ? "var(--success)" : "var(--warning)" }}
            />
            {health === "green" ? "Active" : "Idle"}
          </span>
        </div>
        <div className="space-y-3">
          {[
            { label: "AI sourced", value: String(pipelineStats?.discovered ?? 0) },
            { label: "Shortlisted", value: String(pipelineStats?.shortlisted ?? 0) },
            { label: "Applied", value: String(pipelineStats?.approved ?? 0) },
            {
              label: "Last scrape",
              value: lastRunAt ? formatDistanceToNow(lastRunAt, { addSuffix: true }) : "—",
            },
            {
              label: "Next scrape",
              value: nextRunAt && nextRunAt > new Date()
                ? formatDistanceToNow(nextRunAt)
                : `every ${scrapeIntervalHours}h`,
            },
          ].map(({ label, value }) => (
            <div key={label} className="flex items-center justify-between text-sm">
              <span style={{ color: "var(--text-muted)" }}>{label}</span>
              <span className="font-medium" style={{ color: "var(--text)" }}>{value}</span>
            </div>
          ))}
        </div>
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

  const [rawProfile, agentStatus, pipelineStats, pendingApprovals, upcomingInterviews, followUpReminders, rateLimitStatus] =
    await Promise.all([
      fetchRawProfile().catch((): RawProfile => ({})),
      fetchAllAgentStatus().catch((): AllAgentStatus | null => null),
      fetchPipelineStats().catch((): PipelineStats | null => null),
      fetchPendingApprovals().catch((): PendingApproval[] => []),
      getUpcomingInterviews(14).catch(() => []),
      fetchFollowUpReminders().catch((): FollowUpReminder[] => []),
      fetchRateLimitStatus().catch((): RateLimitStatus | null => null),
    ]);

  const threshold = rawProfile.scoring?.shortlist_threshold ?? 0.75;
  const scrapeIntervalHours = rawProfile.preferences?.scrape_interval_hours ?? 4;

  const topJobs = await fetchJobs({ min_match_score: threshold, hide_ghosts: true }, 0, 5).catch(
    () => ({ items: [], total: 0 }),
  );

  const reviewCount = pendingApprovals.length;
  const noJobsYet = (pipelineStats?.discovered ?? 0) === 0;

  const prepCount = upcomingInterviews.filter(
    (i) => i.scheduled_at != null && new Date(i.scheduled_at) > new Date(),
  ).length;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text)", letterSpacing: "-0.015em" }}>
          Home
        </h1>
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          Your job search at a glance
        </p>
      </div>

      {/* Alert banners */}
      <AgentStatusBanner agentStatus={agentStatus} scrapeIntervalHours={scrapeIntervalHours} />
      <RateLimitBanner status={rateLimitStatus} />

      {noJobsYet ? (
        <EmptyState scrapeIntervalHours={scrapeIntervalHours} />
      ) : (
        <>
          {/* Hero: greeting + status */}
          <HeroSection
            reviewCount={reviewCount}
            pipelineStats={pipelineStats}
            agentStatus={agentStatus}
            scrapeIntervalHours={scrapeIntervalHours}
          />

          {/* KPI strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard
              icon={<Sparkles size={12} />}
              label="AI-sourced"
              value={pipelineStats?.discovered ?? 0}
            />
            <KpiCard
              icon={<CheckCircle2 size={12} />}
              label="Shortlisted"
              value={pipelineStats?.shortlisted ?? 0}
            />
            <KpiCard
              icon={<Send size={12} />}
              label="Applied"
              value={pipelineStats?.approved ?? 0}
            />
            <KpiCard
              icon={<Target size={12} />}
              label="Prep sessions"
              value={prepCount}
            />
          </div>

          {/* Follow-up reminders */}
          <FollowUpSection reminders={followUpReminders} />

          {/* Activity timeline */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
                Recent activity
              </h2>
            </div>
            <ActivityTimeline />
          </div>
        </>
      )}
    </div>
  );
}
