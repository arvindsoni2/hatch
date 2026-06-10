"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, AlertCircle, CheckCircle2 } from "lucide-react";
import { listCompletedJobs, AsyncJobResponse } from "@/lib/api";

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

export function NotificationBell() {
  const [jobs, setJobs] = useState<AsyncJobResponse[]>([]);
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setJobs([]);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleOpen() {
    setOpen((prev) => {
      const opening = !prev;
      if (opening) {
        localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
      } else {
        setJobs([]);
      }
      return opening;
    });
  }

  function handleMarkRead() {
    setOpen(false);
    setJobs([]);
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        aria-label="notifications"
        onClick={handleOpen}
        className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
      >
        <Bell className="h-5 w-5" />
        {jobs.length > 0 && (
          <span
            data-testid="bell-badge"
            className={`absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white ${jobs.some(j => j.status === "failed") ? "bg-red-500" : "bg-indigo-600"}`}
          >
            {jobs.length > 9 ? "9+" : String(jobs.length)}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5 dark:border-slate-800">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              Notifications
            </span>
            {jobs.length > 0 && (
              <button
                onClick={handleMarkRead}
                className="text-xs text-slate-400 hover:text-slate-600"
              >
                Mark all read
              </button>
            )}
          </div>

          {jobs.length === 0 ? (
            <p className="px-4 py-4 text-center text-sm text-slate-400">No new notifications</p>
          ) : (
            <ul className="max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
              {jobs.map((job) => (
                <li key={job.id} className="px-4 py-3">
                  <div className="flex items-start gap-2">
                    {job.status === "failed"
                      ? <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
                      : <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
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
                        {new Date(job.created_at).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
