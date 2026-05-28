"use client";

import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ExternalLink, BookmarkPlus, Check, Loader2 } from "lucide-react";
import type { Job } from "@/lib/api";
import { trackFromJob } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { MatchScoreBadge } from "@/components/MatchScoreBadge";

interface JobTableProps {
  jobs: Job[];
  className?: string;
}

type TrackState = "idle" | "loading" | "done" | "exists";

function LegalFieldCell({ job }: { job: Job }) {
  const fields = job.legal_fields ?? (job.ir35_status ? { ir35_status: job.ir35_status } : {});
  const entries = Object.entries(fields);
  if (!entries.length) return <span className="text-slate-400">—</span>;
  const [, value] = entries[0];
  const variant = value === "outside" ? "outside" : value === "inside" ? "inside" : "unknown";
  return <Badge variant={variant}>{value}</Badge>;
}

function SourceCell({ source }: { source: string }) {
  const labels: Record<string, string> = {
    contractoruk: "ContractorUK",
    reed: "Reed",
    adzuna: "Adzuna",
    cwjobs: "CWJobs",
    jobserve: "JobServe",
    itjobswatch: "ITJobsWatch",
    linkedin: "LinkedIn",
  };
  return <Badge variant="source">{labels[source] ?? source}</Badge>;
}

function RateCell({ job }: { job: Job }) {
  if (!job.rate_text && !job.rate_min) {
    return <span className="text-slate-400">—</span>;
  }

  const displayText =
    job.rate_text ??
    (job.rate_min && job.rate_max && job.rate_min !== job.rate_max
      ? `£${job.rate_min.toLocaleString()}–£${job.rate_max.toLocaleString()}`
      : job.rate_min
        ? `£${job.rate_min.toLocaleString()}`
        : null);

  return (
    <span className="font-medium text-emerald-700 whitespace-nowrap">
      {displayText ?? "—"}
    </span>
  );
}

function TrackButton({ jobId }: { jobId: string }) {
  const [state, setState] = useState<TrackState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const handleTrack = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (state !== "idle") return;
    setState("loading");
    try {
      await trackFromJob(jobId);
      setState("done");
      setMessage("Tracked!");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Error";
      // 409 Conflict means already tracked
      if (msg.includes("409") || msg.toLowerCase().includes("already") || msg.toLowerCase().includes("exist")) {
        setState("exists");
        setMessage("Already tracked");
      } else {
        setState("exists");
        setMessage("Already tracked");
      }
    }
  };

  if (state === "done") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600 font-medium">
        <Check className="h-3.5 w-3.5" />
        Tracked
      </span>
    );
  }

  if (state === "exists") {
    return (
      <span className="text-xs text-slate-400 italic">{message}</span>
    );
  }

  return (
    <button
      onClick={handleTrack}
      disabled={state === "loading"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-2.5 py-1",
        "text-xs font-medium text-indigo-700 transition-colors",
        "hover:bg-indigo-100 hover:border-indigo-300",
        "disabled:opacity-50 disabled:cursor-not-allowed",
      )}
    >
      {state === "loading" ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <BookmarkPlus className="h-3.5 w-3.5" />
      )}
      Track
    </button>
  );
}

export function JobTable({ jobs, className }: JobTableProps) {
  if (jobs.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-12 text-center">
        <p className="text-slate-500 text-lg">No jobs found.</p>
        <p className="text-slate-400 text-sm mt-1">
          Try adjusting your filters or click &quot;Scrape Now&quot; to fetch fresh listings.
        </p>
      </div>
    );
  }

  return (
    <div className={cn("overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm", className)}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-100">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Title / Company
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Job Type
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Location
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Rate
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Source
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Posted
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Match
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                Track
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {jobs.map((job) => (
              <tr
                key={job.id}
                className="hover:bg-brand-50 transition-colors duration-100 group"
              >
                {/* Title + Company */}
                <td className="px-4 py-3 max-w-xs">
                  <a
                    href={job.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group/link flex items-start gap-1.5"
                  >
                    <div>
                      <span className="block text-sm font-semibold text-slate-900 group-hover/link:text-brand-600 transition-colors line-clamp-2">
                        {job.title}
                      </span>
                      {job.company && (
                        <span className="block text-xs text-slate-500 mt-0.5">
                          {job.company}
                        </span>
                      )}
                    </div>
                    <ExternalLink className="h-3 w-3 text-slate-300 group-hover/link:text-brand-400 mt-0.5 shrink-0" />
                  </a>
                </td>

                {/* Job Type */}
                <td className="px-4 py-3 text-sm">
                  {(() => {
                    const type = job.working_pattern || job.employment_type;
                    return type ? (
                      <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700 whitespace-nowrap capitalize">
                        {type.replace(/_/g, " ")}
                      </span>
                    ) : <span className="text-slate-400">—</span>;
                  })()}
                </td>

                {/* Location */}
                <td className="px-4 py-3 text-sm text-slate-600 whitespace-nowrap max-w-[140px] truncate">
                  {job.location ?? <span className="text-slate-400">—</span>}
                </td>

                {/* Rate */}
                <td className="px-4 py-3 text-sm">
                  <RateCell job={job} />
                </td>

                {/* Contract status */}
                <td className="px-4 py-3 text-sm">
                  <LegalFieldCell job={job} />
                </td>

                {/* Source */}
                <td className="px-4 py-3 text-sm">
                  <SourceCell source={job.source} />
                </td>

                {/* Posted */}
                <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                  {job.scraped_at
                    ? formatDistanceToNow(new Date(job.scraped_at), { addSuffix: true })
                    : "—"}
                </td>

                {/* Match Score */}
                <td className="px-4 py-3 text-sm whitespace-nowrap">
                  <MatchScoreBadge score={job.match_score} reasons={job.match_reasons} />
                  {job.match_score == null && <span className="text-slate-400">—</span>}
                </td>

                {/* Track */}
                <td className="px-4 py-3 text-sm whitespace-nowrap">
                  <TrackButton jobId={job.id} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
