"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { CalendarPlus } from "lucide-react";
import { CalendarView } from "@/components/CalendarView";
import { FollowUpList } from "@/components/FollowUpList";
import { buttonVariants } from "@/components/ui/button";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { cn } from "@/lib/utils";
import {
  getUpcomingInterviews,
  getOverdueFollowUps,
  completeFollowUp,
  type InterviewRound,
  type FollowUp,
} from "@/lib/api";

export default function CalendarPage() {
  const [interviews, setInterviews] = useState<InterviewRound[]>([]);
  const [overdue, setOverdue] = useState<FollowUp[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [i, o] = await Promise.all([
        getUpcomingInterviews(60),
        getOverdueFollowUps(),
      ]);
      setInterviews(i);
      setOverdue(o);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleComplete = async (id: string) => {
    await completeFollowUp(id);
    await load();
  };

  const isEmpty = !loading && interviews.length === 0 && overdue.length === 0;

  return (
    <PageContainer width="wide" className="px-4 py-8">
      <PageHeader
        title="Calendar"
        description="Upcoming interviews and follow-ups from tracked applications."
        actions={(
          <Link
            href="/tracker"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "min-h-11 sm:min-h-9")}
          >
            Open Applications
          </Link>
        )}
      />

        {loading ? (
          <div className="grid gap-6 md:grid-cols-3" role="status" aria-label="Loading Calendar">
            <div className="md:col-span-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <div className="h-6 w-44 animate-pulse rounded bg-[var(--surface-3)]" />
              <div className="mt-5 grid grid-cols-7 gap-1">
                {Array.from({ length: 35 }).map((_, index) => (
                  <div key={index} className="h-10 animate-pulse rounded-lg bg-[var(--surface-2)]" />
                ))}
              </div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <div className="h-5 w-36 animate-pulse rounded bg-[var(--surface-3)]" />
              <div className="mt-4 space-y-3">
                {[0, 1, 2].map((index) => (
                  <div key={index} className="h-14 animate-pulse rounded-lg bg-[var(--surface-2)]" />
                ))}
              </div>
            </div>
          </div>
        ) : isEmpty ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-14 text-center">
            <CalendarPlus className="mx-auto h-10 w-10 text-[var(--text-muted)]" />
            <h2 className="mt-4 text-base font-semibold text-[var(--text)]">
              No interviews or follow-ups scheduled
            </h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-[var(--text-dim)]">
              Add an interview round or follow-up from an application to see it here.
            </p>
            <div className="mt-5 flex justify-center">
              <Link href="/tracker" className={cn(buttonVariants({ variant: "default" }), "min-h-11")}>
                Open Applications
              </Link>
            </div>
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <CalendarView interviews={interviews} followUps={overdue} />
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
              <h2 className="text-sm font-semibold text-[var(--text)] mb-4">
                Overdue Follow-ups
                {overdue.length > 0 && (
                  <span className="ml-2 rounded-full bg-[var(--danger-soft)] px-2 py-0.5 text-xs text-[var(--danger)]">
                    {overdue.length}
                  </span>
                )}
              </h2>
              <FollowUpList followUps={overdue} onComplete={handleComplete} />
            </div>
          </div>
        )}
    </PageContainer>
  );
}
