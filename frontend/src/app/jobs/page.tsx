"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchJobs,
  fetchFilterCounts,
  type Job,
  type ScrapeResult,
  type FilterCounts,
} from "@/lib/api";
import { JobTable } from "@/components/JobTable";
import { FilterPanel, type FilterValues } from "@/components/FilterPanel";
import {
  AdvancedFilterPanel,
  type AdvancedFilters,
} from "@/components/AdvancedFilterPanel";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Loader2, SlidersHorizontal } from "lucide-react";

const PAGE_SIZE = 50;

interface JobsState {
  jobs: Job[];
  total: number;
  loading: boolean;
  error: string | null;
}

export default function JobsPage() {
  // Legacy filter panel state (source + scrape trigger)
  const [filters, setFilters] = useState<FilterValues>({
    search: "",
    ir35_status: "",
    source: "",
    min_rate: "",
    hide_ghosts: true,
  });

  // V2 advanced filters
  const [advancedFilters, setAdvancedFilters] = useState<AdvancedFilters>({});
  const [filterCounts, setFilterCounts] = useState<FilterCounts | undefined>(undefined);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [page, setPage] = useState(0);
  const [state, setState] = useState<JobsState>({
    jobs: [],
    total: 0,
    loading: true,
    error: null,
  });

  // Fetch filter counts on mount
  useEffect(() => {
    fetchFilterCounts()
      .then((counts) => setFilterCounts(counts))
      .catch(() => {
        // Non-critical — counts are just display hints
      });
  }, []);

  const loadJobs = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const apiFilters = {
        search: advancedFilters.search || filters.search || undefined,
        ir35_status: advancedFilters.ir35_status || filters.ir35_status || undefined,
        source: filters.source || undefined,
        min_rate: advancedFilters.min_rate ?? (filters.min_rate ? parseFloat(filters.min_rate) : undefined),
        max_rate: advancedFilters.max_rate,
        employment_type: advancedFilters.employment_type,
        working_pattern: advancedFilters.working_pattern,
        min_match_score: advancedFilters.min_match_score,
        posted_after: advancedFilters.posted_after,
        hide_ghosts: filters.hide_ghosts,
      };

      const response = await fetchJobs(apiFilters, page, PAGE_SIZE);
      setState({
        jobs: response.items,
        total: response.total,
        loading: false,
        error: null,
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load jobs";
      setState({ jobs: [], total: 0, loading: false, error: message });
    }
  }, [filters, advancedFilters, page]);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  // Reset to page 0 when filters change
  function handleFilterChange(newFilters: FilterValues) {
    setFilters(newFilters);
    setPage(0);
  }

  function handleAdvancedFilterChange(newFilters: AdvancedFilters) {
    setAdvancedFilters(newFilters);
    setPage(0);
  }

  function handleScrapeComplete(_results: ScrapeResult[]) {
    void loadJobs();
  }

  // Determine if any jobs have match scores
  const hasMatchScores = state.jobs.some((j) => j.match_score != null);

  const totalPages = Math.ceil(state.total / PAGE_SIZE);
  const startItem = page * PAGE_SIZE + 1;
  const endItem = Math.min((page + 1) * PAGE_SIZE, state.total);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Contract Jobs</h1>
          <p className="mt-1 text-sm text-slate-500">
            {state.total > 0
              ? `${state.total.toLocaleString()} contract roles found`
              : "Browse and filter UK IT contract roles"}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-2"
        >
          <SlidersHorizontal className="h-4 w-4" />
          {showAdvanced ? "Hide filters" : "Advanced filters"}
        </Button>
      </div>

      {/* Legacy filter panel (source selector + scrape trigger) */}
      <FilterPanel
        filters={filters}
        onFilterChange={handleFilterChange}
        onScrapeComplete={handleScrapeComplete}
      />

      {/* Advanced filter panel */}
      {showAdvanced && (
        <AdvancedFilterPanel
          filters={advancedFilters}
          filterCounts={filterCounts}
          onChange={handleAdvancedFilterChange}
          hasMatchScores={hasMatchScores}
        />
      )}

      {/* Results */}
      {state.loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
          <span className="ml-3 text-slate-500">Loading jobs...</span>
        </div>
      ) : state.error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-red-700">{state.error}</p>
          <Button
            onClick={() => void loadJobs()}
            variant="outline"
            size="sm"
            className="mt-4"
          >
            Retry
          </Button>
        </div>
      ) : (
        <>
          <JobTable jobs={state.jobs} />

          {/* Pagination */}
          {state.total > PAGE_SIZE && (
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-500">
                Showing {startItem}–{endItem} of {state.total.toLocaleString()} jobs
              </p>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
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
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
