import { FunnelChart, TrendChart, SourceBreakdownChart } from "@/components/AnalyticsCharts";
import { fetchAnalyticsDashboard } from "@/lib/api";

export const revalidate = 300; // 5 minutes

export default async function AnalyticsPage() {
  let dashboard;
  try {
    dashboard = await fetchAnalyticsDashboard();
  } catch {
    dashboard = null;
  }

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
      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Analytics</h1>

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
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
