import {
  FunnelChart,
  TrendChart,
  SourceBreakdownChart,
  ScoreDistributionChart,
  DailyCostChart,
} from "@/components/AnalyticsCharts";
import {
  fetchAnalyticsDashboard,
  fetchAtsCorrelation,
  fetchSkillFrequency,
  fetchSkillGaps,
  fetchScoreDistribution,
  fetchCostsMonthly,
  fetchCostsDaily,
  fetchAgentPerformance,
  fetchSearchQuality,
} from "@/lib/api";
import Link from "next/link";

export const revalidate = 300;

function StatCard({ label, value, color, sub }: { label: string; value: string | number; color: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-slate-500 mt-1">{label}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
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
    agentPerf,
    searchQuality,
  ] = await Promise.all([
    fetchAnalyticsDashboard().catch(() => null),
    fetchAtsCorrelation().catch(() => null),
    fetchSkillFrequency(20).catch(() => null),
    fetchSkillGaps(15).catch(() => null),
    fetchScoreDistribution().catch(() => null),
    fetchCostsMonthly().catch(() => null),
    fetchCostsDaily(30).catch(() => null),
    fetchAgentPerformance().catch(() => null),
    fetchSearchQuality().catch(() => null),
  ]);

  const { stats, funnel, trends, sources, avg_days_to_interview } = dashboard ?? {
    stats: { active_count: 0, applied_count: 0, response_rate: 0 },
    funnel: { stages: [], total_tracked: 0 },
    trends: { weeks: [] },
    sources: [],
    avg_days_to_interview: null,
  };

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>

        {/* Section A: Summary stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatCard label="Active Applications" value={stats.active_count} color="text-indigo-600" />
          <StatCard label="Applied" value={stats.applied_count} color="text-blue-600" />
          <StatCard label="Response Rate" value={`${stats.response_rate.toFixed(1)}%`} color="text-emerald-600" />
          <StatCard
            label="Avg Days to Interview"
            value={avg_days_to_interview?.toFixed(1) ?? "–"}
            color="text-amber-600"
          />
          <StatCard
            label="API Cost (month)"
            value={costsMonthly ? `£${costsMonthly.total.toFixed(2)}` : "–"}
            color="text-purple-600"
            sub={costsMonthly ? `${costsMonthly.budget_pct}% of £${costsMonthly.budget} budget` : undefined}
          />
          <StatCard
            label="Search Quality"
            value={searchQuality ? `${searchQuality.triage_pass_rate}%` : "–"}
            color="text-cyan-600"
            sub={searchQuality ? `${searchQuality.shortlist_rate}% shortlisted` : undefined}
          />
        </div>

        {/* Section B: Score Distribution */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-1">Score Distribution</h2>
          <p className="text-xs text-slate-400 mb-4">
            {scoreDist ? `${scoreDist.total} jobs scored` : "No scored jobs yet"} — green bars are above your shortlist threshold
          </p>
          {scoreDist && scoreDist.total > 0 ? (
            <ScoreDistributionChart buckets={scoreDist.buckets} threshold={scoreDist.threshold} />
          ) : (
            <p className="text-sm text-slate-400 py-8 text-center">
              Run the scorer agent to see the distribution.{" "}
              <Link href="/" className="text-brand-600 underline">Trigger from Home →</Link>
            </p>
          )}
        </div>

        {/* Section C: Pipeline Funnel */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Application Funnel</h2>
          <FunnelChart stages={funnel.stages} />
        </div>

        {/* Section D: ATS Score → Response Rate */}
        {atsCorrelation && !atsCorrelation.message && atsCorrelation.buckets.length > 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-1">ATS Score → Response Rate</h2>
            <p className="text-xs text-slate-400 mb-4">
              {atsCorrelation.total_scored} CVs scored — does a higher ATS score translate to more responses?
            </p>
            <div className="space-y-3">
              {atsCorrelation.buckets.map((b) => (
                <div key={b.range} className="flex items-center gap-3">
                  <span className="w-28 text-xs text-slate-600 shrink-0">{b.label}</span>
                  <div className="flex-1 bg-slate-100 rounded-full h-3 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${b.response_rate_pct >= 30 ? "bg-green-500" : b.response_rate_pct >= 15 ? "bg-amber-400" : "bg-red-400"}`}
                      style={{ width: `${Math.min(b.response_rate_pct, 100)}%` }}
                    />
                  </div>
                  <div className="text-xs text-slate-500 w-32 text-right shrink-0">
                    {b.response_rate_pct}% ({b.responses}/{b.total})
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-2">ATS Score → Response Rate</h2>
            <p className="text-sm text-slate-400">{atsCorrelation?.message ?? "No data yet."}</p>
          </div>
        )}

        {/* Section E: Cost Tracking */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-700">LLM Cost Tracking (30 days)</h2>
              {costsMonthly && (
                <p className="text-xs text-slate-400 mt-0.5">
                  This month: <span className="font-medium text-slate-700">£{costsMonthly.total.toFixed(4)}</span>
                  {" "}/{" "}£{costsMonthly.budget} budget
                  {Object.keys(costsMonthly.by_agent).length > 0 && (
                    <span className="ml-2">
                      {Object.entries(costsMonthly.by_agent).map(([a, c]) => `${a}: £${c.toFixed(4)}`).join(" · ")}
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>
          {costsDaily && costsDaily.days.length > 0 ? (
            <DailyCostChart days={costsDaily.days} />
          ) : (
            <p className="text-sm text-slate-400 py-8 text-center">No cost data yet — costs are tracked when agents run LLM calls.</p>
          )}
        </div>

        {/* Section F: Agent Performance */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-4">Agent Performance</h2>
          {agentPerf && agentPerf.agents.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 border-b border-slate-100">
                    <th className="text-left py-2 pr-4 font-medium">Agent</th>
                    <th className="text-right py-2 px-4 font-medium">Today</th>
                    <th className="text-right py-2 px-4 font-medium">This week</th>
                    <th className="text-right py-2 px-4 font-medium">Success rate</th>
                    <th className="text-left py-2 pl-4 font-medium">Last run</th>
                    <th className="text-left py-2 pl-4 font-medium">Last error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {agentPerf.agents.map((a) => (
                    <tr key={a.agent} className="text-slate-700">
                      <td className="py-2 pr-4 font-medium capitalize">{a.agent}</td>
                      <td className="py-2 px-4 text-right tabular-nums">{a.runs_today}</td>
                      <td className="py-2 px-4 text-right tabular-nums">{a.runs_this_week}</td>
                      <td className="py-2 px-4 text-right">
                        <span className={`font-medium ${a.success_rate >= 95 ? "text-green-600" : a.success_rate >= 80 ? "text-amber-600" : "text-red-600"}`}>
                          {a.success_rate.toFixed(1)}%
                        </span>
                      </td>
                      <td className="py-2 pl-4 text-xs text-slate-400">
                        {a.last_run_at ? new Date(a.last_run_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"}
                      </td>
                      <td className="py-2 pl-4 text-xs text-red-500 max-w-xs truncate">
                        {a.last_error ? a.last_error.slice(0, 80) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-400">No agent activity recorded yet.</p>
          )}
        </div>

        {/* Section G: Skills */}
        {skillFrequency && !skillFrequency.message && skillFrequency.skills.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-1">Top Skills in Matched Jobs</h2>
            <p className="text-xs text-slate-400 mb-4">
              Keywords appearing most frequently across {skillFrequency.total_jobs_analyzed} scored jobs
            </p>
            <div className="flex flex-wrap gap-2">
              {skillFrequency.skills.map((s, i) => {
                const maxCount = skillFrequency.skills[0]?.count ?? 1;
                const opacity = 0.4 + 0.6 * (s.count / maxCount);
                return (
                  <span
                    key={s.skill}
                    className="rounded-full px-3 py-1 text-xs font-medium bg-brand-100 text-brand-800"
                    style={{ opacity }}
                  >
                    {s.skill}
                    <span className="ml-1.5 text-brand-500">{s.count}</span>
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Section G2: Skill Gaps */}
        {skillGaps && !skillGaps.message && skillGaps.skills.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-1">Skill Gaps to Address</h2>
            <p className="text-xs text-slate-400 mb-4">
              Skills required by matched jobs that aren&apos;t in your profile — consider adding them
            </p>
            <div className="flex flex-wrap gap-2">
              {skillGaps.skills.map((s) => {
                const maxCount = skillGaps.skills[0]?.count ?? 1;
                const opacity = 0.4 + 0.6 * (s.count / maxCount);
                return (
                  <span
                    key={s.skill}
                    className="rounded-full px-3 py-1 text-xs font-medium bg-red-100 text-red-700"
                    style={{ opacity }}
                  >
                    {s.skill}
                    <span className="ml-1.5 text-red-500">{s.count}</span>
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Section H + I: Source Breakdown & Weekly Trends */}
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Source Breakdown</h2>
            <SourceBreakdownChart sources={sources} />
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">
              Weekly Trends (last {trends.weeks.length} weeks)
            </h2>
            <TrendChart weeks={trends.weeks} />
          </div>
        </div>
      </div>
    </main>
  );
}
