"use client";

import { Building2, MapPin, Banknote, Sparkles, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import type { ApplicationListItem, Priority } from "@/lib/api";

function AgentScoreBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  const pct = Math.round(score * 100);
  if (pct >= 85) return (
    <Badge className="text-xs bg-green-100 text-green-700 border-green-200 flex items-center gap-0.5">
      <Sparkles className="h-2.5 w-2.5" />{pct}%
    </Badge>
  );
  if (pct >= 75) return (
    <Badge className="text-xs bg-amber-100 text-amber-700 border-amber-200 flex items-center gap-0.5">
      <Sparkles className="h-2.5 w-2.5" />{pct}%
    </Badge>
  );
  return (
    <Badge className="text-xs bg-red-100 text-red-600 border-red-200 flex items-center gap-0.5">
      <Sparkles className="h-2.5 w-2.5" />{pct}%
    </Badge>
  );
}

interface KanbanCardProps {
  application: ApplicationListItem;
  isDragging?: boolean;
  isOverdue?: boolean;
  onClick?: () => void;
}

const PRIORITY_LABELS: Record<Priority, string> = {
  urgent: "Urgent",
  high: "High",
  normal: "Normal",
  low: "Low",
};

export function KanbanCard({ application, isDragging = false, isOverdue = false, onClick }: KanbanCardProps) {
  const daysInStatus = Math.floor(
    (Date.now() - new Date(application.updated_at).getTime()) / (1000 * 60 * 60 * 24),
  );

  const title = application.job_title ?? application.agency_name ?? "Untitled Application";
  const company = application.job_company ?? application.recruiter_name ?? null;

  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-white border border-slate-200 rounded-lg p-3 cursor-pointer select-none",
        "hover:border-indigo-300 hover:shadow-sm transition-all",
        isDragging && "opacity-50 rotate-2 shadow-lg",
        isOverdue && "border-l-4 border-l-red-400",
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="text-sm font-medium text-slate-800 line-clamp-2 flex-1">{title}</p>
        <div className="flex items-center gap-1 shrink-0">
          <AgentScoreBadge score={application.agent_score} />
          <Badge variant={`priority-${application.priority}` as Parameters<typeof Badge>[0]["variant"]} className="text-xs">
            {PRIORITY_LABELS[application.priority]}
          </Badge>
        </div>
      </div>

      {company && (
        <div className="flex items-center gap-1 text-xs text-slate-500 mb-1">
          <Building2 className="h-3 w-3" />
          <span className="truncate">{company}</span>
        </div>
      )}

      {application.job_location && (
        <div className="flex items-center gap-1 text-xs text-slate-500 mb-1">
          <MapPin className="h-3 w-3" />
          <span className="truncate">{application.job_location}</span>
        </div>
      )}

      {application.job_rate_text && (
        <div className="flex items-center gap-1 text-xs text-slate-600 mb-2">
          <Banknote className="h-3 w-3" />
          <span>{application.job_rate_text}</span>
        </div>
      )}

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-slate-400">
            {daysInStatus === 0 ? "Today" : `${daysInStatus}d in status`}
          </span>
          {isOverdue && (
            <span className="flex items-center gap-0.5 text-xs text-red-500 font-medium" title="Follow-up overdue">
              <Clock className="h-3 w-3" /> overdue
            </span>
          )}
        </div>
        {application.job_source && (
          <Badge variant="secondary" className="text-xs">
            {application.job_source}
          </Badge>
        )}
      </div>
    </div>
  );
}
