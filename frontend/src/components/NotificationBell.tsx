"use client";

import { useCallback, useEffect, useState } from "react";
import { Bell, AlertCircle, CheckCircle2 } from "lucide-react";
import { listCompletedJobs, AsyncJobResponse } from "@/lib/api";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

const JOB_LABELS: Record<string, string> = {
  tailor_analyse:      "JD Analysis complete",
  tailor_generate_cv:  "CV tailoring complete",
  tailor_generate_cl:  "Cover letter complete",
  tailor_generate:     "CV & cover letter complete",
  coach_session:       "Interview session ready",
  submit_answer:       "Answer evaluated",
  end_session:         "Feedback report ready",
  email_generate:      "Email draft ready",
  ghost_analyse:       "Job posting analysed",
};

const LAST_SEEN_KEY = "notif_last_seen_at";
const TIME_FORMATTER = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

export function NotificationBell() {
  const [jobs, setJobs] = useState<AsyncJobResponse[]>([]);
  const [open, setOpen] = useState(false);

  const fetchUnseen = useCallback(async () => {
    const lastSeen = localStorage.getItem(LAST_SEEN_KEY) ?? new Date(0).toISOString();
    try {
      const result = await listCompletedJobs(lastSeen, 10);
      setJobs(result);
    } catch {
      // Non-critical
    }
  }, []);

  useEffect(() => {
    void fetchUnseen();
    const interval = setInterval(() => void fetchUnseen(), 15_000);
    return () => clearInterval(interval);
  }, [fetchUnseen]);

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (nextOpen) {
      localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
    } else {
      setJobs([]);
    }
  }

  function handleMarkRead() {
    setOpen(false);
    setJobs([]);
  }

  return (
    <Popover onOpenChange={handleOpenChange} open={open}>
      <PopoverTrigger asChild>
        <button
          aria-label="Notifications"
          className="hatch-interactive relative inline-flex h-11 w-11 items-center justify-center rounded-[var(--radius-control)] text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
        >
          <Bell aria-hidden="true" className="h-5 w-5" />
          {jobs.length > 0 ? (
            <span
              data-testid="bell-badge"
              className={`absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-bold text-white ${jobs.some(j => j.status === "failed") ? "bg-red-500" : "bg-indigo-600"}`}
            >
              {jobs.length > 9 ? "9+" : String(jobs.length)}
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent aria-label="Notifications" className="w-72 overflow-hidden p-0" role="dialog">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5 dark:border-slate-800">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              Notifications
            </span>
            {jobs.length > 0 ? (
              <button
                onClick={handleMarkRead}
                className="hatch-interactive min-h-11 rounded-[var(--radius-control)] px-2 text-xs text-[var(--text-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
              >
                Mark All Read
              </button>
            ) : null}
          </div>

          {jobs.length === 0 ? (
            <p className="px-4 py-4 text-center text-sm text-slate-400">No new notifications</p>
          ) : (
            <ul className="max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
              {jobs.map((job) => (
                <li key={job.id} className="px-4 py-3">
                  <div className="flex items-start gap-2">
                    {job.status === "failed"
                      ? <AlertCircle aria-hidden="true" className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
                      : <CheckCircle2 aria-hidden="true" className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
                    }
                    <div className="min-w-0">
                      <p className={`text-sm font-medium ${job.status === "failed" ? "text-red-700 dark:text-red-400" : "text-slate-800 dark:text-slate-100"}`}>
                        {job.status === "failed"
                          ? `Failed: ${JOB_LABELS[job.type] ?? job.type}`
                          : (JOB_LABELS[job.type] ?? job.type)}
                      </p>
                      {job.status === "failed" && job.error && (
                        <p className="mt-0.5 truncate text-xs text-red-500">{job.error}</p>
                      )}
                      <p className="text-xs text-slate-400">
                        {TIME_FORMATTER.format(new Date(job.created_at))}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
      </PopoverContent>
    </Popover>
  );
}
