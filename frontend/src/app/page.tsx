import Link from "next/link";
import { redirect } from "next/navigation";
import { fetchStats, fetchJobs, fetchPendingEmails, fetchEmailStats, fetchGhostStats, fetchProfileStatus } from "@/lib/api";
import { StatsBar } from "@/components/StatsBar";
import { JobTable } from "@/components/JobTable";
import { Button } from "@/components/ui/button";
import { ArrowRight, RefreshCw, Mail, Ghost } from "lucide-react";

// Revalidate dashboard every 60 seconds
export const revalidate = 60;

async function getDashboardData() {
  try {
    const [stats, recentJobsResponse, pendingEmails, ghostStats] = await Promise.all([
      fetchStats(),
      fetchJobs({ hide_ghosts: false }, 0, 10),
      fetchPendingEmails().catch(() => []),
      fetchGhostStats().catch(() => null),
    ]);
    return { stats, recentJobs: recentJobsResponse.items, pendingEmails, ghostStats, error: null };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return {
      stats: null,
      recentJobs: [],
      pendingEmails: [],
      ghostStats: null,
      error: `Failed to connect to API: ${message}. Is the backend running on port 8000?`,
    };
  }
}

export default async function DashboardPage() {
  const profileStatus = await fetchProfileStatus().catch(() => null);
  if (profileStatus?.onboarding_required) {
    redirect("/onboarding");
  }

  const { stats, recentJobs, pendingEmails, ghostStats, error } = await getDashboardData();

  if (error) {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 max-w-lg">
          <h2 className="text-xl font-semibold text-red-800 mb-2">
            Backend Unavailable
          </h2>
          <p className="text-red-700 text-sm mb-4">{error}</p>
          <p className="text-slate-500 text-xs">
            Run <code className="bg-slate-100 px-1 py-0.5 rounded">make dev-back</code> to start the API server.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Outside-IR35 UK contract roles — scraped automatically every 4 hours
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/jobs">
            <Button variant="outline" size="sm">
              View All Jobs
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>

      {/* Stats */}
      {stats && <StatsBar stats={stats} />}

      {/* Pending emails card */}
      {pendingEmails.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Mail className="h-5 w-5 text-amber-600" />
            <div>
              <p className="text-sm font-semibold text-amber-900">
                {pendingEmails.length} follow-up email{pendingEmails.length !== 1 ? "s" : ""} awaiting review
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                {pendingEmails.slice(0, 2).map((e) =>
                  `${e.email_type === "post_interview_thankyou" ? "Thank-you" : "Follow-up"}${e.company ? ` · ${e.company}` : ""}`
                ).join(" · ")}
                {pendingEmails.length > 2 && ` · +${pendingEmails.length - 2} more`}
              </p>
            </div>
          </div>
          <Link href="/applications">
            <Button variant="outline" size="sm" className="border-amber-300 text-amber-800 hover:bg-amber-100">
              Review
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </Link>
        </div>
      )}

      {/* Ghost stats card */}
      {ghostStats && ghostStats.likely_ghost > 0 && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Ghost className="h-5 w-5 text-red-500" />
            <div>
              <p className="text-sm font-semibold text-red-900">
                {ghostStats.likely_ghost} likely ghost job{ghostStats.likely_ghost !== 1 ? "s" : ""} filtered
                {ghostStats.suspicious > 0 && ` · ${ghostStats.suspicious} suspicious`}
              </p>
              <p className="text-xs text-red-700 mt-0.5">
                Saving ~{Math.round(ghostStats.likely_ghost * 0.5 * 10) / 10} hrs of wasted applications
              </p>
            </div>
          </div>
          <Link href="/jobs?hide_ghosts=false">
            <Button variant="outline" size="sm" className="border-red-300 text-red-800 hover:bg-red-100">
              Review
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </Button>
          </Link>
        </div>
      )}

      {/* Recent jobs */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">
            Recent Listings
          </h2>
          <Link href="/jobs">
            <Button variant="ghost" size="sm" className="text-brand-600">
              View all {stats?.total_jobs ?? ""} jobs
              <ArrowRight className="ml-1 h-4 w-4" />
            </Button>
          </Link>
        </div>
        <JobTable jobs={recentJobs} />
      </div>

      {/* Refresh hint */}
      <p className="flex items-center gap-1.5 text-xs text-slate-400">
        <RefreshCw className="h-3.5 w-3.5" />
        Dashboard refreshes every 60 seconds. Scraping runs every 4 hours automatically.
      </p>
    </div>
  );
}
