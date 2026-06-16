import {
  FunnelChart,
  TrendChart,
  SourceBreakdownChart,
  ScoreDistributionChart,
  DailyCostChart,
} from "@/components/AnalyticsCharts";
import { AgentPerformanceTable } from "@/components/AgentPerformanceTable";
import { OutcomeLearningPanel } from "@/components/OutcomeLearningPanel";
import { BackButton } from "@/components/hatch/BackButton";
import {
  fetchAnalyticsDashboard,
  fetchAtsCorrelation,
  fetchSkillFrequency,
  fetchSkillGaps,
  fetchScoreDistribution,
  fetchCostsMonthly,
  fetchCostsDaily,
  fetchSearchQuality,
  fetchRateLimitStatus,
  fetchAgentPerformance,
  fetchOutcomeLearningSummary,
} from "@/lib/api";
import Link from "next/link";

export const revalidate = 60;

function formatCost(amount: number): string {
  if (amount === 0) return "£0.00";
  if (amount < 0.01) return `£${amount.toFixed(4)}`;
  return `£${amount.toFixed(2)}`;
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl p-4 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="text-2xl font-bold" style={{ color: "var(--accent)" }}>{value}</div>
      <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>{label}</div>
      {sub && <div className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{sub}</div>}
    </div>
  );
}

function SkillBar({
  label,
  count,
  max,
  tone,
}: {
  label: string;
  count: number;
  max: number;
  tone: "accent" | "danger";
}) {
  const width = max > 0 ? Math.max(8, Math.round((count / max) * 100)) : 0;
  const color = tone === "danger" ? "var(--danger)" : "var(--accent)";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="min-w-0 truncate font-medium" style={{ color: "var(--text-dim)" }}>{label}</span>
        <span className="shrink-0 tabular-nums" style={{ color: "var(--text-muted)" }}>{count}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }}>
        <div className="h-full rounded-full" style={{ width: `${width}%`, background: color }} />
      </div>
    </div>
  );
}

function EmptySkillPanel({ message }: { message: string }) {
  return (
    <div className="rounded-lg px-4 py-8 text-center text-sm" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
      {message}
    </div>
  );
}

export default async function AnalyticsPage() {
  const [
    dashboard,
    atsCorrelation,
    skillFrequency,
    skillGaps,
    scoreDist,
    costsMonthly,
    costsDaily,
    searchQuality,
    rateLimitStatus,
    agentPerf,
    outcomeSummary,
  ] = await Promise.all([
    fetchAnalyticsDashboard().catch(() => null),
    fetchAtsCorrelation().catch(() => null),
    fetchSkillFrequency(20).catch(() => null),
    fetchSkillGaps(15).catch(() => null),
    fetchScoreDistribution().catch(() => null),
    fetchCostsMonthly().catch(() => null),
    fetchCostsDaily(30).catch(() => null),
    fetchSearchQuality().catch(() => null),
    fetchRateLimitStatus().catch(() => null),
    fetchAgentPerformance().catch(() => null),
    fetchOutcomeLearningSummary().catch(() => null),
  ]);

  const { stats, funnel, trends, sources, avg_days_to_interview } = dashboard ?? {
    stats: { active_count: 0, applied_count: 0, response_rate: 0 },
    funnel: { stages: [], total_tracked: 0 },
    trends: { weeks: [] },
    sources: [],
    avg_days_to_interview: null,
  };

  return (
    <main className="min-h-screen" style={{ background: "var(--bg)" }}>
      <div className="max-w-6xl mx-auto px-4 py-6 sm:px-6 sm:py-8 space-y-8">
        <div>
          <BackButton href="/today" label="Today" />
          <h1 className="text-[28px] font-semibold tracking-tight mt-3" style={{ color: "var(--text)", letterSpacing: "-0.025em" }}>Analytics</h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>How your search is performing</p>
        </div>

        {/* Section A: Summary stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard label="Active Applications" value={stats.active_count} />
          <StatCard label="Applied" value={stats.applied_count} />
          <StatCard label="Response Rate" value={`${stats.response_rate.toFixed(1)}%`} />
          <StatCard
            label="Avg Days to Interview"
            value={avg_days_to_interview?.toFixed(1) ?? "–"}
          />
          <StatCard
            label="API Cost (month)"
            value={costsMonthly ? formatCost(costsMonthly.total) : "–"}
            sub={costsMonthly ? `${costsMonthly.budget_pct}% of £${costsMonthly.budget} budget` : undefined}
          />
          <StatCard
            label="Search Quality"
            value={searchQuality ? `${searchQuality.triage_pass_rate}%` : "–"}
            sub={searchQuality ? `${searchQuality.shortlist_rate}% shortlisted` : undefined}
          />
        </div>

        {/* Section B: Score Distribution */}
        <OutcomeLearningPanel summary={outcomeSummary} />

        <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <h2 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>Score Distribution</h2>
          <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
            {scoreDist ? `${scoreDist.total} jobs scored` : "No scored jobs yet"} — green bars are above your shortlist threshold
          </p>
          {scoreDist && scoreDist.total > 0 ? (
            <ScoreDistributionChart buckets={scoreDist.buckets} threshold={scoreDist.threshold} />
          ) : (
            <p className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>
              Run the scorer agent to see the distribution.{" "}
              <Link href="/today" style={{ color: "var(--accent)" }} className="underline">Trigger from Today →</Link>
            </p>
          )}
        </div>

        {/* Section C: Pipeline Funnel */}
        <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text)" }}>Application Funnel</h2>
          <FunnelChart stages={funnel.stages} />
        </div>

        {/* Section D: ATS Score → Response Rate */}
        {atsCorrelation && !atsCorrelation.message && atsCorrelation.buckets.length > 0 ? (
          <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>ATS Score → Response Rate</h2>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>
              {atsCorrelation.total_scored} CVs scored — does a higher ATS score translate to more responses?
            </p>
            <div className="space-y-3">
              {atsCorrelation.buckets.map((b) => (
                <div key={b.range} className="flex items-center gap-3">
                  <span className="w-28 text-xs shrink-0" style={{ color: "var(--text-dim)" }}>{b.label}</span>
                  <div className="flex-1 rounded-full h-3 overflow-hidden" style={{ background: "var(--surface-2)" }}>
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.min(b.response_rate_pct, 100)}%`,
                        background: b.response_rate_pct >= 30 ? "var(--success)" : b.response_rate_pct >= 15 ? "var(--warning)" : "var(--danger)",
                      }}
                    />
                  </div>
                  <div className="text-xs w-32 text-right shrink-0" style={{ color: "var(--text-muted)" }}>
                    {b.response_rate_pct}% ({b.responses}/{b.total})
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--text)" }}>ATS Score → Response Rate</h2>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>{atsCorrelation?.message ?? "No applications yet"}</p>
          </div>
        )}

        {/* Section E: Cost Tracking */}
        <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>LLM Cost Tracking (30 days)</h2>
              {costsMonthly && (
                <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                  This month:{" "}
                  <span className="font-medium" style={{ color: "var(--text-dim)" }}>{formatCost(costsMonthly.total)}</span>
                  {" "}/{" "}£{costsMonthly.budget} budget
                  {Object.keys(costsMonthly.by_agent).length > 0 && (
                    <span className="ml-2" style={{ color: "var(--text-muted)" }}>
                      {Object.entries(costsMonthly.by_agent).map(([a, c]) => `${a}: ${formatCost(c as number)}`).join(" · ")}
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
          {costsDaily && costsDaily.days.length > 0 ? (
            <DailyCostChart days={costsDaily.days} />
          ) : (
            <p className="text-sm py-8 text-center" style={{ color: "var(--text-muted)" }}>No cost data yet — costs are tracked when agents run LLM calls.</p>
          )}
        </div>

        {/* Section G: Skills */}
        <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>Skill Demand & Profile Gaps</h2>
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                Demand is counted across scored jobs; gaps are demanded skills missing from your profile.
              </p>
            </div>
            {skillFrequency && !skillFrequency.message && (
              <span className="rounded-full px-2.5 py-1 text-xs font-medium" style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}>
                {skillFrequency.total_jobs_analyzed} jobs analysed
              </span>
            )}
          </div>

          {(() => {
            const demand = skillFrequency && !skillFrequency.message ? skillFrequency.skills.slice(0, 8) : [];
            const gaps = skillGaps && !skillGaps.message ? skillGaps.skills.slice(0, 8) : [];
            const gapNames = new Set(gaps.map((s) => s.skill.toLowerCase()));
            const overlap = demand.filter((s) => gapNames.has(s.skill.toLowerCase())).slice(0, 4);
            const maxDemand = Math.max(1, ...demand.map((s) => s.count));
            const maxGap = Math.max(1, ...gaps.map((s) => s.count));

            return (
              <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1fr_0.8fr]">
                <div className="space-y-3">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>Market Demand</h3>
                    <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>Most repeated skills in matched jobs.</p>
                  </div>
                  {demand.length > 0 ? (
                    <div className="space-y-3">
                      {demand.map((s) => <SkillBar key={s.skill} label={s.skill} count={s.count} max={maxDemand} tone="accent" />)}
                    </div>
                  ) : (
                    <EmptySkillPanel message={skillFrequency?.message ?? "Score more jobs to see skill demand."} />
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>Missing From Profile</h3>
                    <p className="mt-0.5 text-xs" style={{ color: "var(--text-muted)" }}>Add only skills you can honestly evidence.</p>
                  </div>
                  {gaps.length > 0 ? (
                    <div className="space-y-3">
                      {gaps.map((s) => <SkillBar key={s.skill} label={s.skill} count={s.count} max={maxGap} tone="danger" />)}
                    </div>
                  ) : (
                    <EmptySkillPanel message={skillGaps?.message ?? "No missing skills detected in the analysed jobs."} />
                  )}
                </div>

                <div className="rounded-lg p-4" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  <h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-dim)" }}>Next Action</h3>
                  {gaps.length > 0 ? (
                    <>
                      <p className="mt-2 text-sm" style={{ color: "var(--text)" }}>
                        Prioritise the top {Math.min(3, gaps.length)} missing skills when updating your CV, then rerun tailoring.
                      </p>
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {gaps.slice(0, 3).map((s) => (
                          <span key={s.skill} className="rounded-full px-2 py-0.5 text-xs font-medium" style={{ background: "var(--danger-soft)", color: "var(--danger)" }}>
                            {s.skill}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="mt-2 text-sm" style={{ color: "var(--text)" }}>
                      Your profile covers the detected demand. Use score distribution and ATS response rate to tune applications.
                    </p>
                  )}
                  {overlap.length > 0 && (
                    <p className="mt-3 text-xs" style={{ color: "var(--text-muted)" }}>
                      High-demand gaps: {overlap.map((s) => s.skill).join(", ")}.
                    </p>
                  )}
                </div>
              </div>
            );
          })()}
        </div>

        {/* Section H: Rate Limit Health */}
        {rateLimitStatus && (
          <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>LLM Rate Limit Health</h2>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Current scorer API usage against provider limits</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: rateLimitStatus.throttled ? "var(--warning)" : "var(--success)" }}>
                  {rateLimitStatus.rpm_used}
                </div>
                <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>RPM used</div>
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>of {rateLimitStatus.rpm_limit}</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: "var(--text)" }}>{rateLimitStatus.rpm_remaining}</div>
                <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>RPM remaining</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: "var(--text)" }}>{rateLimitStatus.rpd_used}</div>
                <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>RPD used</div>
                <div className="text-xs" style={{ color: "var(--text-muted)" }}>of {rateLimitStatus.rpd_limit}</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: rateLimitStatus.last_429_at !== null ? "var(--danger)" : "var(--success)" }}>
                  {rateLimitStatus.last_429_at !== null ? "429" : "OK"}
                </div>
                <div className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>Provider status</div>
                {rateLimitStatus.wait_seconds > 0 && (
                  <div className="text-xs" style={{ color: "var(--warning)" }}>wait {Math.round(rateLimitStatus.wait_seconds)}s</div>
                )}
              </div>
            </div>
            {rateLimitStatus.throttled && (
              <div className="mt-3 rounded-md px-3 py-2 text-xs" style={{ background: "var(--warning-soft)", border: "1px solid var(--warning)", color: "var(--warning)" }}>
                Scorer is throttled — waiting {Math.round(rateLimitStatus.wait_seconds)}s before next call.
                Set <code className="rounded px-0.5" style={{ background: "var(--surface-2)" }}>scoring.method: hybrid</code> or <code className="rounded px-0.5" style={{ background: "var(--surface-2)" }}>local</code> in profile.yaml to reduce API usage.
              </div>
            )}
          </div>
        )}

        {/* Section I + J: Source Breakdown & Weekly Trends */}
        <div className="grid md:grid-cols-2 gap-6">
          <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text)" }}>Source Breakdown</h2>
            <SourceBreakdownChart sources={sources} />
          </div>
          <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <h2 className="text-sm font-semibold mb-4" style={{ color: "var(--text)" }}>
              Weekly Trends (last {trends.weeks.length} weeks)
            </h2>
            <TrendChart weeks={trends.weeks} />
          </div>
        </div>

        {/* Section K: Agent Performance */}
        <div className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <AgentPerformanceTable initialData={agentPerf} />
        </div>
      </div>
    </main>
  );
}
