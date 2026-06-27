"use client";

import { useState, useTransition } from "react";
import { Search, Loader2, Zap } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { API_BASE, type ScrapeResult } from "@/lib/api";

export interface FilterValues {
  search: string;
  ir35_status: string;
  source: string;
  min_rate: string;
  hide_ghosts: boolean;
}

interface FilterPanelProps {
  filters: FilterValues;
  onFilterChange: (filters: FilterValues) => void;
  onScrapeComplete?: (results: ScrapeResult[]) => void;
  currencySymbol?: string;
  rateUnit?: string;
}

const SOURCES = [
  { value: "", label: "All Sources" },
  { value: "contractoruk", label: "ContractorUK" },
  { value: "reed", label: "Reed" },
  { value: "adzuna", label: "Adzuna" },
  { value: "cwjobs", label: "CWJobs" },
  { value: "jobserve", label: "JobServe" },
  { value: "itjobswatch", label: "ITJobsWatch" },
  { value: "linkedin", label: "LinkedIn" },
];

const LEGAL_STATUS_OPTIONS = [
  { value: "", label: "All Contract Status" },
  { value: "outside", label: "Outside (preferred)" },
  { value: "inside", label: "Inside" },
  { value: "unknown", label: "Unknown" },
];

export function FilterPanel({
  filters,
  onFilterChange,
  currencySymbol = "£",
  rateUnit = "day",
}: FilterPanelProps) {
  const [isScraping, startScrapeTransition] = useTransition();
  const [scrapeMessage, setScrapeMessage] = useState<string | null>(null);

  function handleChange(key: keyof FilterValues, value: string) {
    onFilterChange({ ...filters, [key]: value });
  }

  function handleScrapeNow() {
    setScrapeMessage(null);
    startScrapeTransition(async () => {
      try {
        // Use the scout agent trigger — it respects profile job_boards and is DB-safe
        const res = await fetch(`${API_BASE}/api/agents/scout/trigger`, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json() as { agent: string; status: string };
        if (data.agent !== "scout" || data.status !== "started") {
          throw new Error("Unexpected scout trigger response");
        }
        setScrapeMessage("Scrape started — results will appear here shortly");
      } catch {
        setScrapeMessage("Scrape failed — is the backend running?");
      }
    });
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {/* Search */}
        <div className="relative lg:col-span-2">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            type="search"
            placeholder="Search jobs, companies..."
            value={filters.search}
            onChange={(e) => handleChange("search", e.target.value)}
            className="pl-9"
          />
        </div>

        {/* Contract status */}
        <Select
          value={filters.ir35_status}
          onChange={(e) => handleChange("ir35_status", e.target.value)}
          aria-label="Filter by contract status"
        >
          {LEGAL_STATUS_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>

        {/* Source */}
        <Select
          value={filters.source}
          onChange={(e) => handleChange("source", e.target.value)}
          aria-label="Filter by source"
        >
          {SOURCES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>

        {/* Min Rate */}
        <Input
          type="number"
          placeholder={`Min rate (${currencySymbol}/${rateUnit})`}
          value={filters.min_rate}
          onChange={(e) => handleChange("min_rate", e.target.value)}
          min={0}
          step={50}
        />
      </div>

      {/* Listing quality filters */}
      <div className="mt-3 flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-600 select-none">
          <input
            type="checkbox"
            checked={filters.hide_ghosts}
            onChange={(e) => onFilterChange({ ...filters, hide_ghosts: e.target.checked })}
            className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
          />
          Hide likely ghost jobs
        </label>
      </div>

      {/* Scrape button + feedback */}
      <div className="mt-3 flex items-center justify-between gap-3">
        <div>
          {scrapeMessage && (
            <p
              className={`text-sm ${
                scrapeMessage.includes("failed") || scrapeMessage.includes("errors")
                  ? "text-red-600"
                  : "text-emerald-600"
              }`}
            >
              {scrapeMessage}
            </p>
          )}
        </div>
        <Button
          onClick={handleScrapeNow}
          disabled={isScraping}
          size="sm"
          className="shrink-0"
        >
          {isScraping ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Scraping...
            </>
          ) : (
            <>
              <Zap className="mr-2 h-4 w-4" />
              Scrape Now
              {filters.source ? ` (${filters.source})` : ""}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
