"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchJobs,
  fetchRawProfile,
  fetchScoringInsights,
  runArchive,
  rescoreUnscored,
  type Job,
  type ScrapeResult,
  type ScoringInsights,
} from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { FilterPanel, type FilterValues } from "@/components/FilterPanel";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Loader2, Eye, Archive, Zap } from "lucide-react";

const PAGE_SIZE = 50;

export default function JobsPage() {
  const [threshold, setThreshold] = useState(0.75);
  const [thresholdLoaded, setThresholdLoaded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [archiveResult, setArchiveResult] = useState<{ archived: number } | null>(null);
  const [scraperError, setScraperError] = useState<string | null>(null);
  const [rescoring, setRescoring] = useState(false);
  const [rescoreResult, setRescoreResult] = useState<{ queued: number } | null>(null);

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
  const [insights, setInsights] = useState<ScoringInsights | null>(null);

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

  // Load scoring insights when not in archive/show-all mode
  useEffect(() => {
    if (!showAll && !showArchived) {
      fetchScoringInsights().then(setInsights).catch(() => {});
    }
  }, [showAll, showArchived]);

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

  async function handleRescore() {
    setRescoring(true);
    setRescoreResult(null);
    try {
      const result = await rescoreUnscored();
      setRescoreResult(result);
      void loadJobs();
    } catch {
      // non-critical
    } finally {
      setRescoring(false);
    }
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
          <h1 className="text-[28px] font-semibold" style={{ color: "var(--text)", letterSpacing: "-0.025em" }}>Inbox</h1>
          <p className="mt-0.5 text-sm" style={{ color: "var(--text-muted)" }} aria-live="polite" aria-atomic="true">
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
        <div className="flex items-center gap-2 text-sm rounded-lg px-4 py-2.5" style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}>
          <Archive className="h-4 w-4 text-slate-400" />
          Archived {archiveResult.archived} job{archiveResult.archived !== 1 ? "s" : ""}.
          <button onClick={() => setArchiveResult(null)} className="ml-auto text-xs underline">Dismiss</button>
        </div>
      )}

      {/* Rescore result notice */}
      {rescoreResult && (
        <div className="flex items-center gap-2 text-sm rounded-lg px-4 py-2.5" style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}>
          <Zap className="h-4 w-4" style={{ color: "var(--accent)" }} />
          {rescoreResult.queued > 0
            ? `${rescoreResult.queued} job${rescoreResult.queued !== 1 ? "s" : ""} queued for scoring — results will appear within the next scrape cycle.`
            : "All jobs are already scored."}
          <button onClick={() => setRescoreResult(null)} className="ml-auto text-xs underline">Dismiss</button>
        </div>
      )}

      {/* Unscored jobs banner (visible in Show All mode) */}
      {showAll && !loading && (() => {
        const unscoredCount = jobs.filter((j) => j.match_score == null).length;
        if (unscoredCount === 0) return null;
        return (
          <div className="flex items-center gap-3 rounded-xl px-4 py-3 text-sm" style={{ background: "var(--warning-soft, #fef3c7)", border: "1px solid var(--warning, #f59e0b)", color: "var(--text-dim)" }}>
            <Zap className="h-4 w-4 shrink-0" style={{ color: "var(--warning, #f59e0b)" }} />
            <span><strong>{unscoredCount}</strong> job{unscoredCount !== 1 ? "s" : ""} {unscoredCount !== 1 ? "haven't" : "hasn't"} been scored yet — they were stored before the scoring pipeline ran.</span>
            <button
              onClick={() => void handleRescore()}
              disabled={rescoring}
              className="ml-auto shrink-0 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold"
              style={{ background: "var(--warning, #f59e0b)", color: "#fff" }}
            >
              {rescoring ? <Loader2 className="h-3 w-3 animate-spin" /> : <Zap className="h-3 w-3" />}
              {rescoring ? "Queuing…" : "Score now"}
            </button>
          </div>
        );
      })()}

      {/* Filter panel */}
      <FilterPanel
        filters={filters}
        onFilterChange={handleFilterChange}
        onScrapeComplete={handleScrapeComplete}
      />

      {/* Score band legend — all bounds derived from threshold */}
      {!showAll && (() => {
        const midPct = Math.max(1, Math.round(thresholdPct / 2));
        return (
          <div className="flex items-center gap-4 text-xs" style={{ color: "var(--text-muted)" }}>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full inline-block" style={{ background: "var(--success)" }} />
              ≥{thresholdPct}% auto-shortlisted
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full inline-block" style={{ background: "var(--warning)" }} />
              {midPct}–{thresholdPct - 1}% parked
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full inline-block" style={{ background: "var(--border)" }} />
              &lt;{midPct}% hidden
            </span>
          </div>
        );
      })()}

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center py-16" role="status" aria-live="polite" aria-label="Loading jobs">
          <Loader2 className="h-8 w-8 animate-spin text-brand-500" aria-hidden="true" />
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
        <div className="rounded-xl p-12 text-center" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          {showArchived ? (
            <p style={{ color: "var(--text-muted)" }}>No archived jobs. Jobs older than your configured threshold will appear here after running the archive.</p>
          ) : showAll ? (
            <p style={{ color: "var(--text-muted)" }}>No jobs found. Try adjusting your filters or trigger a scrape.</p>
          ) : (
            <div className="space-y-3 max-w-md mx-auto">
              <p className="font-medium" style={{ color: "var(--text)" }}>No high-match jobs right now.</p>
              {insights?.recommendation ? (
                <div className="rounded-lg px-4 py-3 text-sm text-left" style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  <p style={{ color: "var(--text-dim)" }}>{insights.recommendation}</p>
                  {insights.in_band_below > 0 && (
                    <button
                      onClick={() => setShowAll(true)}
                      className="mt-2 text-sm font-medium underline"
                      style={{ color: "var(--accent)" }}
                    >
                      Show {insights.in_band_below} near-match job{insights.in_band_below !== 1 ? "s" : ""}
                    </button>
                  )}
                </div>
              ) : (
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  Your threshold is {thresholdPct}%. Try{" "}
                  <button onClick={() => setShowAll(true)} className="underline" style={{ color: "var(--accent)" }}>
                    showing all jobs
                  </button>{" "}
                  or trigger a scrape to get fresh results.
                </p>
              )}
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
