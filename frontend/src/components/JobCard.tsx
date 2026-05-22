"use client";

import { formatDistanceToNow } from "date-fns";
import { Building2, MapPin, Clock, ExternalLink, Banknote } from "lucide-react";
import type { Job } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { MatchScoreBadge } from "@/components/MatchScoreBadge"
import { GhostBadge } from "@/components/GhostBadge";

interface JobCardProps {
  job: Job;
  className?: string;
}

function IR35Badge({ status }: { status: Job["ir35_status"] }) {
  if (!status) return null;
  const variant =
    status === "outside" ? "outside" : status === "inside" ? "inside" : "unknown";
  const label =
    status === "outside"
      ? "Outside IR35"
      : status === "inside"
        ? "Inside IR35"
        : "IR35 Unknown";
  return <Badge variant={variant}>{label}</Badge>;
}

function SourceBadge({ source }: { source: string }) {
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
    <Badge variant="source">{labels[source] ?? source}</Badge>
  );
}

function RateDisplay({ job }: { job: Job }) {
  if (!job.rate_text && !job.rate_min) return null;

  const displayText =
    job.rate_text ??
    (job.rate_min && job.rate_max && job.rate_min !== job.rate_max
      ? `£${job.rate_min.toLocaleString()}–£${job.rate_max.toLocaleString()}/day`
      : job.rate_min
        ? `£${job.rate_min.toLocaleString()}/day`
        : null);

  if (!displayText) return null;

  return (
    <span className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-700">
      <Banknote className="h-4 w-4" />
      {displayText}
    </span>
  );
}

export function JobCard({ job, className }: JobCardProps) {
  const postedAgo = job.scraped_at
    ? formatDistanceToNow(new Date(job.scraped_at), { addSuffix: true })
    : null;

  return (
    <Card
      className={cn(
        "hover:border-brand-300 hover:shadow-md transition-all duration-200",
        className,
      )}
    >
      <CardContent className="p-5">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center gap-1.5"
            >
              <h3 className="text-base font-semibold text-slate-900 group-hover:text-brand-600 transition-colors line-clamp-2">
                {job.title}
              </h3>
              <ExternalLink className="h-3.5 w-3.5 text-slate-400 group-hover:text-brand-500 shrink-0 mt-0.5" />
            </a>

            {/* Company / Location */}
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
              {job.company && (
                <span className="flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5" />
                  {job.company}
                </span>
              )}
              {job.location && (
                <span className="flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" />
                  {job.location}
                </span>
              )}
              {postedAgo && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {postedAgo}
                </span>
              )}
            </div>
          </div>

          {/* Rate */}
          <div className="shrink-0 text-right">
            <RateDisplay job={job} />
            {job.contract_length && (
              <p className="mt-0.5 text-xs text-slate-400">{job.contract_length}</p>
            )}
          </div>
        </div>

        {/* Description snippet */}
        {job.description && (
          <p className="mt-3 text-sm text-slate-600 line-clamp-2 leading-relaxed">
            {job.description}
          </p>
        )}

        {/* Badges row */}
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <IR35Badge status={job.ir35_status} />
          {job.employment_type && (
            <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
              {job.employment_type.replace(/_/g, " ")}
            </span>
          )}
          {job.working_pattern && (
            <span className="inline-flex items-center rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-700">
              {job.working_pattern.replace(/_/g, " ")}
            </span>
          )}
          <SourceBadge source={job.source} />
          <MatchScoreBadge score={job.match_score} reasons={job.match_reasons} />
          <GhostBadge
            score={job.ghost_score}
            verdict={job.ghost_verdict}
            signals={job.ghost_signals}
            jobId={job.id}
          />
          {job.skills?.slice(0, 5).map((skill) => (
            <Badge key={skill} variant="skill">
              {skill}
            </Badge>
          ))}
          {job.skills && job.skills.length > 5 && (
            <Badge variant="skill">+{job.skills.length - 5} more</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
