import { FunnelChart, TrendChart, SourceBreakdownChart } from "@/components/AnalyticsCharts";
import { fetchAnalyticsDashboard, fetchAtsCorrelation, fetchSkillFrequency } from "@/lib/api";

export const revalidate = 300; // 5 minutes

export default async function AnalyticsPage() {
  let dashboard;
  try {
    dashboard = await fetchAnalyticsDashboard();
  } catch {
    dashboard = null;
  }

  const [atsCorrelation, skillFrequency] = await Promise.all([
    fetchAtsCorrelation().catch(() => null),
    fetchSkillFrequency(20).catch(() => null),
  ]);

  if (!dashboard) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Analytics</h1>
          <p className="text-slate-500 mb-6">
            Start tracking applications to see analytics. Go to{" "}
            <a href="/jobs" className="text-indigo-600 underline">
              Jobs
            </a>{" "}
            and click &ldquo;Track&rdquo; on any listing.
          </p>
        </div>
      </main>
    );
  }

  const { stats, funnel, trends, sources, avg_days_to_interview } = dashboard;

  return (
    <main className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "Active Applications", value: stats.active_count, color: "text-indigo-600" },
            { label: "Applied", value: stats.applied_count, color: "text-blue-600" },
            {
              label: "Response Rate",
              value: `${stats.response_rate.toFixed(1)}%`,
              color: "text-emerald-600",
            },
            {
              label: "Avg Days to Interview",
              value: avg_days_to_interview?.toFixed(1) ?? "–",
              color: "text-amber-600",
            },
          ].map(({ label, value, color }) => (
            <div
              key={label}
              className="bg-white rounded-xl border border-slate-200 p-4 text-center"
            >
              <div className={`text-2xl font-bold ${color}`}>{value}</div>
              <div className="text-xs text-slate-500 mt-1">{label}</div>
            </div>
          ))}
        </div>

        {/* ATS Correlation */}
        {atsCorrelation && !atsCorrelation.message && atsCorrelation.buckets.length > 0 && (
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
                      className={`h-full rounded-full ${
                        b.response_rate_pct >= 30
                          ? "bg-green-500"
                          : b.response_rate_pct >= 15
                          ? "bg-amber-400"
                          : "bg-red-400"
                      }`}
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
        )}
        {atsCorrelation?.message && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-2">ATS Score → Response Rate</h2>
            <p className="text-sm text-slate-400">{atsCorrelation.message}</p>
          </div>
        )}

        {/* Skill Frequency */}
        {skillFrequency && !skillFrequency.message && skillFrequency.skills.length > 0 && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-1">Top skills in matched jobs</h2>
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

        {/* Charts */}
        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Application Funnel</h2>
            <FunnelChart stages={funnel.stages} />
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Source Breakdown</h2>
            <SourceBreakdownChart sources={sources} />
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-6 md:col-span-2">
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
