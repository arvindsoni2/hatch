"use client";

import Link from "next/link";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { ExternalLink, BookmarkPlus, Check, Loader2, GitCompareArrows } from "lucide-react";
import type { Job } from "@/lib/api";
import { trackFromJob } from "@/lib/api";
import { ScoreBadge } from "@/components/ScoreBadge";
import { cn } from "@/lib/utils";
import { formatJobRateFull } from "@/lib/currency";

const SOURCE_LABELS: Record<string, string> = {
  contractoruk: "ContractorUK",
  reed: "Reed",
  adzuna: "Adzuna",
  cwjobs: "CWJobs",
  jobserve: "JobServe",
  itjobswatch: "ITJobsWatch",
  linkedin: "LinkedIn",
};

interface JobCardProps {
  job: Job;
  threshold?: number;
  currencySymbol?: string;
}

export function JobCard({ job, threshold = 0.75, currencySymbol = "£" }: JobCardProps) {
  const [trackState, setTrackState] = useState<"idle" | "loading" | "done" | "exists">("idle");

  const rate = formatJobRateFull(job.rate_text, job.rate_min, job.rate_max, currencySymbol);
  // Prefer legal_fields (locale-neutral); fall back to ir35_status for legacy data
  const legalLabel = (() => {
    const fields = job.legal_fields ?? (job.ir35_status ? { ir35_status: job.ir35_status } : {});
    const [, val] = Object.entries(fields)[0] ?? [];
    return val ?? null;
  })();

  const timeLabel = job.posted_at
    ? `Posted ${formatDistanceToNow(new Date(job.posted_at), { addSuffix: true })}`
    : job.scraped_at
    ? `Discovered ${formatDistanceToNow(new Date(job.scraped_at), { addSuffix: true })}`
    : null;

  const metaParts = [job.company, job.location, rate, legalLabel].filter(
    (p): p is string => p != null && p !== "",
  );

  async function handleTrack(e: React.MouseEvent) {
    e.stopPropagation();
    if (trackState !== "idle") return;
    setTrackState("loading");
    try {
      await trackFromJob(job.id);
      setTrackState("done");
    } catch {
      setTrackState("exists");
    }
  }

  const dimensions =
    job.skill_match != null || job.experience_match != null || job.rate_match != null || job.location_match != null
      ? {
          skill_match: job.skill_match,
          experience_match: job.experience_match,
          rate_match: job.rate_match,
          location_match: job.location_match,
        }
      : undefined;

  return (
    <div className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm hover:border-brand-200 hover:shadow-md transition-all">
      <div className="shrink-0 w-12 flex justify-center">
        <ScoreBadge score={job.match_score} threshold={threshold} dimensions={dimensions} />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Link
            href={`/jobs/${job.id}`}
            className="text-sm font-semibold text-slate-900 hover:text-brand-600 transition-colors truncate"
            onClick={(e) => e.stopPropagation()}
          >
            {job.title}
          </Link>
          {job.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3 text-slate-300 hover:text-brand-400" />
            </a>
          )}
        </div>
        {metaParts.length > 0 && (
          <p className="mt-0.5 text-xs text-slate-500 truncate">{metaParts.join(" · ")}</p>
        )}
      </div>

      <div className="hidden shrink-0 min-w-[140px] text-right sm:block">
        {timeLabel && <p className="text-xs text-slate-400">{timeLabel}</p>}
        <p className="text-xs text-slate-400">{SOURCE_LABELS[job.source] ?? job.source}</p>
        <Link
          href={`/jobs/${job.id}#gap`}
          className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-600 mt-1"
          onClick={(e) => e.stopPropagation()}
        >
          <GitCompareArrows className="h-3 w-3" /> Gap analysis
        </Link>
      </div>

      <div className="shrink-0">
        {trackState === "done" ? (
          <span className="flex items-center gap-1 text-xs font-medium text-emerald-600">
            <Check className="h-3.5 w-3.5" /> Tracked
          </span>
        ) : trackState === "exists" ? (
          <span className="text-xs text-slate-400 italic">In pipeline</span>
        ) : (
          <button
            onClick={handleTrack}
            disabled={trackState === "loading"}
            className={cn(
              "flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50",
              "px-2.5 py-1.5 text-xs font-medium text-indigo-700 transition-colors",
              "hover:bg-indigo-100 hover:border-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {trackState === "loading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <BookmarkPlus className="h-3.5 w-3.5" />
            )}
            Track
          </button>
        )}
      </div>
    </div>
  );
}
