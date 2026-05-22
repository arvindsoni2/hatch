"use client"

import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import type { FilterCounts } from "@/lib/api"

export interface AdvancedFilters {
  search?: string
  ir35_status?: string
  employment_type?: string
  working_pattern?: string
  min_rate?: number
  max_rate?: number
  min_match_score?: number
  posted_after?: string
}

interface AdvancedFilterPanelProps {
  filters: AdvancedFilters
  filterCounts?: FilterCounts
  onChange: (filters: AdvancedFilters) => void
  hasMatchScores?: boolean
}

const EMPLOYMENT_TYPES = [
  { value: "contract", label: "Contract" },
  { value: "permanent", label: "Permanent" },
  { value: "fixed_term", label: "Fixed Term" },
  { value: "part_time", label: "Part Time" },
]

const WORKING_PATTERNS = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "on_site", label: "On-site" },
]

const IR35_OPTIONS = [
  { value: "outside", label: "Outside IR35" },
  { value: "inside", label: "Inside IR35" },
  { value: "unknown", label: "Unknown" },
]

const POSTED_DATE_PRESETS: Array<{ label: string; value: string }> = [
  { label: "Today", value: "today" },
  { label: "7 days", value: "7d" },
  { label: "30 days", value: "30d" },
  { label: "90 days", value: "90d" },
  { label: "Any", value: "" },
]

function getPostedAfterDate(preset: string): string | undefined {
  if (!preset) return undefined
  const now = new Date()
  if (preset === "today") {
    now.setHours(0, 0, 0, 0)
    return now.toISOString()
  }
  const days = parseInt(preset.replace("d", ""), 10)
  now.setDate(now.getDate() - days)
  return now.toISOString()
}

function getCurrentPreset(postedAfter: string | undefined): string {
  if (!postedAfter) return ""
  const postedDate = new Date(postedAfter)
  const now = new Date()
  const diffMs = now.getTime() - postedDate.getTime()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)

  if (diffDays < 1) return "today"
  if (diffDays <= 7) return "7d"
  if (diffDays <= 30) return "30d"
  if (diffDays <= 90) return "90d"
  return ""
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
      {children}
    </h3>
  )
}

export function AdvancedFilterPanel({
  filters,
  filterCounts,
  onChange,
  hasMatchScores = false,
}: AdvancedFilterPanelProps) {
  function toggleSingleValue(key: keyof AdvancedFilters, value: string) {
    onChange({
      ...filters,
      [key]: filters[key] === value ? undefined : value,
    })
  }

  function handleRateChange(key: "min_rate" | "max_rate", raw: string) {
    const parsed = raw === "" ? undefined : parseFloat(raw)
    onChange({ ...filters, [key]: parsed })
  }

  function handlePostedPreset(preset: string) {
    const postedAfter = getPostedAfterDate(preset)
    onChange({ ...filters, posted_after: postedAfter })
  }

  function handleMatchScoreChange(raw: string) {
    const val = raw === "" ? undefined : parseInt(raw, 10)
    onChange({ ...filters, min_match_score: val })
  }

  const currentPreset = getCurrentPreset(filters.posted_after)

  function countFor(section: keyof FilterCounts, value: string): number | null {
    if (!filterCounts) return null
    return filterCounts[section][value] ?? null
  }

  function labelWithCount(label: string, count: number | null) {
    if (count === null) return label
    return `${label} (${count.toLocaleString()})`
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-5">
      {/* Search */}
      <div>
        <SectionHeading>Search</SectionHeading>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            type="search"
            placeholder="Search jobs, companies, skills..."
            value={filters.search ?? ""}
            onChange={(e) => onChange({ ...filters, search: e.target.value || undefined })}
            className="pl-9"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {/* Employment Type */}
        <div>
          <SectionHeading>Employment Type</SectionHeading>
          <div className="space-y-1.5">
            {EMPLOYMENT_TYPES.map(({ value, label }) => {
              const count = countFor("employment_type", value)
              return (
                <label key={value} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={filters.employment_type === value}
                    onChange={() => toggleSingleValue("employment_type", value)}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-sm text-slate-700 group-hover:text-slate-900">
                    {labelWithCount(label, count)}
                  </span>
                </label>
              )
            })}
          </div>
        </div>

        {/* IR35 Status */}
        <div>
          <SectionHeading>IR35 Status</SectionHeading>
          <div className="space-y-1.5">
            {IR35_OPTIONS.map(({ value, label }) => {
              const count = countFor("ir35_status", value)
              const isOutside = value === "outside"
              return (
                <label key={value} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={filters.ir35_status === value}
                    onChange={() => toggleSingleValue("ir35_status", value)}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span
                    className={`text-sm group-hover:text-slate-900 ${
                      isOutside ? "text-emerald-700 font-medium" : "text-slate-700"
                    }`}
                  >
                    {labelWithCount(label, count)}
                  </span>
                </label>
              )
            })}
          </div>
        </div>

        {/* Working Pattern */}
        <div>
          <SectionHeading>Working Pattern</SectionHeading>
          <div className="space-y-1.5">
            {WORKING_PATTERNS.map(({ value, label }) => {
              const count = countFor("working_pattern", value)
              return (
                <label key={value} className="flex items-center gap-2 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={filters.working_pattern === value}
                    onChange={() => toggleSingleValue("working_pattern", value)}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <span className="text-sm text-slate-700 group-hover:text-slate-900">
                    {labelWithCount(label, count)}
                  </span>
                </label>
              )
            })}
          </div>
        </div>

        {/* Rate Range */}
        <div>
          <SectionHeading>Rate Range (£/day)</SectionHeading>
          <div className="space-y-2">
            <Input
              type="number"
              placeholder="Min rate"
              value={filters.min_rate ?? ""}
              onChange={(e) => handleRateChange("min_rate", e.target.value)}
              min={0}
              step={50}
            />
            <Input
              type="number"
              placeholder="Max rate"
              value={filters.max_rate ?? ""}
              onChange={(e) => handleRateChange("max_rate", e.target.value)}
              min={0}
              step={50}
            />
          </div>
        </div>
      </div>

      {/* Posted Date + Match Score */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {/* Posted Date */}
        <div>
          <SectionHeading>Posted Within</SectionHeading>
          <div className="flex flex-wrap gap-2">
            {POSTED_DATE_PRESETS.map(({ label, value }) => (
              <button
                key={value}
                onClick={() => handlePostedPreset(value)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  currentPreset === value
                    ? "border-brand-500 bg-brand-50 text-brand-700"
                    : "border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:text-brand-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Match Score — only shown when scores exist */}
        {hasMatchScores && (
          <div>
            <SectionHeading>
              Min Match Score: {filters.min_match_score ?? 0}%
            </SectionHeading>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={filters.min_match_score ?? 0}
              onChange={(e) => handleMatchScoreChange(e.target.value)}
              className="w-full accent-brand-600"
            />
            <div className="flex justify-between text-xs text-slate-400 mt-1">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
