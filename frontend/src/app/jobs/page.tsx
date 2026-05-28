"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchJobs,
  fetchRawProfile,
  runArchive,
  type Job,
  type ScrapeResult,
} from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { FilterPanel, type FilterValues } from "@/components/FilterPanel";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Loader2, Eye, Archive } from "lucide-react";

const PAGE_SIZE = 50;

export default function JobsPage() {
  const [threshold, setThreshold] = useState(0.75);
  const [thresholdLoaded, setThresholdLoaded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [archiveResult, setArchiveResult] = useState<{ archived: number } | null>(null);
  const [scraperError, setScraperError] = useState<string | null>(null);

  const [filters, setFilters] = useState<FilterValues>({
    search: "",
    ir35_status: "",
    source: "",
    min_rate: "",
    hide_ghosts: true,
  });

  const [page, setPage] = useState(0);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load threshold from profile once
  useEffect(() => {
    fetchRawProfile()
      .then((p) => {
        setThreshold(p.scoring?.shortlist_threshold ?? 0.75);
      })
      .catch(() => {})
      .finally(() => setThresholdLoaded(true));
  }, []);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchJobs(
        {
          search: filters.search || undefined,
          legal_fields: filters.ir35_status ? { ir35_status: filters.ir35_status } : undefined,
          source: filters.source || undefined,
          min_rate: filters.min_rate ? parseFloat(filters.min_rate) : undefined,
          hide_ghosts: showArchived ? false : filters.hide_ghosts,
          min_match_score: showAll || showArchived ? undefined : threshold,
        },
        page,
        PAGE_SIZE,
      );
      setJobs(res.items);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [filters, page, threshold, showAll, showArchived]);

  useEffect(() => {
    if (thresholdLoaded) void loadJobs();
  }, [loadJobs, thresholdLoaded]);

  function handleFilterChange(newFilters: FilterValues) {
    setFilters(newFilters);
    setPage(0);
  }

  function handleScrapeComplete(results: ScrapeResult[]) {
    const hadErrors = results.some((r) => r.errors > 0);
    if (hadErrors) {
      setScraperError("One or more scrapers reported errors on this run.");
    } else {
      setScraperError(null);
    }
    void loadJobs();
  }

  async function handleRunArchive() {
    setArchiving(true);
    try {
      const result = await runArchive();
      setArchiveResult(result);
      void loadJobs();
    } catch {
      // silently ignore archive errors — non-critical
    } finally {
      setArchiving(false);
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const startItem = page * PAGE_SIZE + 1;
  const endItem = Math.min((page + 1) * PAGE_SIZE, total);
  const thresholdPct = Math.round(threshold * 100);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Jobs</h1>
          <p className="mt-1 text-sm text-slate-500">
            {showArchived
              ? `Archived jobs — ${total.toLocaleString()} total`
              : !showAll
              ? `Showing matches ≥ ${thresholdPct}% — ${total.toLocaleString()} jobs`
              : `All ${total.toLocaleString()} jobs`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setShowArchived((v) => !v); setPage(0); }}
            className="flex items-center gap-2 min-h-[44px]"
          >
            <Archive className="h-4 w-4" />
            {showArchived ? "Active jobs" : "Archived"}
          </Button>
          {!showArchived && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => { setShowAll((v) => !v); setPage(0); }}
              className="flex items-center gap-2"
            >
              <Eye className="h-4 w-4" />
              {showAll ? `Show ≥${thresholdPct}% only` : "Show all"}
            </Button>
          )}
          {showArchived && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleRunArchive()}
              disabled={archiving}
              className="flex items-center gap-2 text-amber-700 border-amber-300 hover:bg-amber-50"
            >
              {archiving ? "Archiving…" : "Run archive now"}
            </Button>
          )}
        </div>
      </div>

      {/* Scraper error banner */}
      {scraperError && (
        <ErrorBanner
          variant="scraper_failure"
          message={scraperError}
          onDismiss={() => setScraperError(null)}
        />
      )}

      {/* Archive result notice */}
      {archiveResult && (
        <div className="flex items-center gap-2 text-sm text-slate-600 bg-slate-100 rounded-lg px-4 py-2.5">
          <Archive className="h-4 w-4 text-slate-400" />
          Archived {archiveResult.archived} job{archiveResult.archived !== 1 ? "s" : ""}.
          <button onClick={() => setArchiveResult(null)} className="ml-auto text-xs underline">Dismiss</button>
        </div>
      )}

      {/* Filter panel */}
      <FilterPanel
        filters={filters}
        onFilterChange={handleFilterChange}
        onScrapeComplete={handleScrapeComplete}
      />

      {/* Score band legend */}
      {!showAll && (
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-green-400 inline-block" />
            ≥{thresholdPct}% auto-shortlisted
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-300 inline-block" />
            50–{thresholdPct - 1}% parked
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-slate-300 inline-block" />
            &lt;50% hidden
          </span>
        </div>
      )}

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
          <span className="ml-3 text-slate-500">Loading jobs…</span>
        </div>
      ) : error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-red-700">{error}</p>
          <Button onClick={() => void loadJobs()} variant="outline" size="sm" className="mt-4">
            Retry
          </Button>
        </div>
      ) : jobs.length === 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white p-12 text-center">
          {showArchived ? (
            <p className="text-slate-500">No archived jobs. Jobs older than your configured threshold will appear here after running the archive.</p>
          ) : showAll ? (
            <p className="text-slate-500">No jobs found. Try adjusting your filters or trigger a scrape.</p>
          ) : (
            <div className="space-y-2">
              <p className="text-slate-700 font-medium">No high-match jobs right now.</p>
              <p className="text-sm text-slate-500">
                Your threshold is {thresholdPct}%. Try{" "}
                <button onClick={() => setShowAll(true)} className="text-brand-600 underline">
                  showing all jobs
                </button>{" "}
                or broaden your search in Settings.
              </p>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} threshold={threshold} />
            ))}
          </div>

          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-500">
                Showing {startItem}–{endItem} of {total.toLocaleString()} jobs
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" /> Previous
                </Button>
                <span className="text-sm text-slate-600">
                  Page {page + 1} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Next <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
