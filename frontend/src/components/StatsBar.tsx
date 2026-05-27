import type { StatsResponse } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Briefcase, TrendingUp, Calendar, CheckCircle } from "lucide-react";

interface StatsBarProps {
  stats: StatsResponse;
}

interface StatCardProps {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  description?: string;
  highlight?: boolean;
}

function StatCard({ label, value, icon, description, highlight }: StatCardProps) {
  return (
    <Card className={highlight ? "border-brand-200 bg-brand-50" : undefined}>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-slate-500">{label}</p>
            <p
              className={`text-3xl font-bold mt-1 ${
                highlight ? "text-brand-700" : "text-slate-900"
              }`}
            >
              {value}
            </p>
            {description && (
              <p className="text-xs text-slate-400 mt-0.5">{description}</p>
            )}
          </div>
          <div
            className={`rounded-full p-3 ${
              highlight ? "bg-brand-100 text-brand-600" : "bg-slate-100 text-slate-500"
            }`}
          >
            {icon}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function StatsBar({ stats }: StatsBarProps) {
  const outsideCount = stats.by_ir35?.["outside"] ?? 0;
  const insideCount = stats.by_ir35?.["inside"] ?? 0;
  const unknownCount = stats.by_ir35?.["unknown"] ?? 0;

  return (
    <div className="space-y-4">
      {/* Top-level numbers */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Total Jobs"
          value={stats.total_jobs.toLocaleString()}
          icon={<Briefcase className="h-5 w-5" />}
          highlight
        />
        <StatCard
          label="New Today"
          value={stats.new_today.toLocaleString()}
          icon={<Calendar className="h-5 w-5" />}
          description="Scraped in last 24h"
        />
        <StatCard
          label="New This Week"
          value={stats.new_this_week.toLocaleString()}
          icon={<TrendingUp className="h-5 w-5" />}
          description="Scraped in last 7 days"
        />
        <StatCard
          label="Preferred Status"
          value={outsideCount.toLocaleString()}
          icon={<CheckCircle className="h-5 w-5" />}
          description={`${insideCount} inside · ${unknownCount} unknown`}
        />
      </div>

      {/* Source breakdown */}
      {Object.keys(stats.by_source).length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
            Jobs by Source
          </p>
          <div className="flex flex-wrap gap-3">
            {Object.entries(stats.by_source)
              .sort(([, a], [, b]) => b - a)
              .map(([source, count]) => {
                const labels: Record<string, string> = {
                  contractoruk: "ContractorUK",
                  reed: "Reed",
                  adzuna: "Adzuna",
                  cwjobs: "CWJobs",
                  jobserve: "JobServe",
                  itjobswatch: "ITJobsWatch",
                  linkedin: "LinkedIn",
                };
                return (
                  <div
                    key={source}
                    className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2"
                  >
                    <span className="text-sm font-medium text-slate-700">
                      {labels[source] ?? source}
                    </span>
                    <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-700">
                      {count}
                    </span>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
