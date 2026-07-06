"use client";

import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { CalendarView } from "@/components/CalendarView";
import { FollowUpList } from "@/components/FollowUpList";
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

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-6">Calendar</h1>
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="md:col-span-2 bg-white rounded-xl border border-slate-200 p-6">
              <CalendarView interviews={interviews} followUps={overdue} />
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-6">
              <h2 className="text-sm font-semibold text-slate-700 mb-4">
                Overdue Follow-ups
                {overdue.length > 0 && (
                  <span className="ml-2 bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full">
                    {overdue.length}
                  </span>
                )}
              </h2>
              <FollowUpList followUps={overdue} onComplete={handleComplete} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
