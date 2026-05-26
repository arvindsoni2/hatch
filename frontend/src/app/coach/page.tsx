"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { listSessions, SessionListItem, SessionResponse } from "@/lib/api";
import { SessionLauncher } from "@/components/coach/SessionLauncher";
import { Brain, BookOpen, ChevronRight, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";

const STATUS_COLORS: Record<string, string> = {
  active: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  setup: "bg-slate-100 text-slate-600",
  abandoned: "bg-red-100 text-red-700",
};

export default function CoachPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showLauncher, setShowLauncher] = useState(false);

  useEffect(() => {
    listSessions(20)
      .then(setSessions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSessionCreated = (session: SessionResponse) => {
    router.push(`/coach/session/${session.id}`);
  };

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Brain className="h-6 w-6 text-indigo-600" />
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Interview Coach</h1>
            <p className="text-sm text-slate-500">AI-powered mock interview practice</p>
          </div>
        </div>
        <Button
          onClick={() => setShowLauncher(true)}
          className="gap-2 bg-indigo-600 hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" />
          New Session
        </Button>
      </div>

      {/* Sub-navigation */}
      <div className="mb-6 flex gap-1 rounded-xl border border-slate-200 bg-slate-100 p-1">
        <span className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white">
          <Brain className="h-3.5 w-3.5" /> Sessions
        </span>
        <Link
          href="/coach/stories"
          className="flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium text-slate-500 hover:bg-white hover:text-slate-900 transition-colors"
        >
          <BookOpen className="h-3.5 w-3.5" /> Story Bank
        </Link>
      </div>

      {/* Launcher modal */}
      {showLauncher && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="relative w-full max-w-lg">
            <button
              onClick={() => setShowLauncher(false)}
              className="absolute right-4 top-4 z-10 text-slate-500 hover:text-slate-700"
            >
              <X className="h-5 w-5" />
            </button>
            <SessionLauncher onSessionCreated={handleSessionCreated} />
          </div>
        </div>
      )}

      {/* Session history */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 py-16 text-center">
          <Brain className="h-10 w-10 text-slate-300" />
          <p className="text-slate-500">No sessions yet. Start your first mock interview!</p>
          <Button
            onClick={() => setShowLauncher(true)}
            className="gap-2 bg-indigo-600 hover:bg-indigo-700"
          >
            <Plus className="h-4 w-4" />
            New Session
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((session) => (
            <div
              key={session.id}
              className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 transition-colors hover:border-indigo-200 hover:shadow-sm shadow-sm"
              onClick={() =>
                session.status === "completed"
                  ? router.push(`/coach/report/${session.id}`)
                  : router.push(`/coach/session/${session.id}`)
              }
            >
              <div className="flex flex-col gap-0.5">
                <p className="font-medium text-slate-900">
                  {session.role_title} — {session.company_name}
                </p>
                <p className="text-xs text-slate-400">
                  {new Date(session.created_at).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLORS[session.status] ?? "bg-slate-100 text-slate-600"}`}>
                  {session.status}
                </span>
                {session.overall_score != null && (
                  <span className={`text-sm font-bold ${session.overall_score >= 8 ? "text-emerald-600" : session.overall_score >= 6 ? "text-amber-600" : "text-red-600"}`}>
                    {session.overall_score.toFixed(1)}/10
                  </span>
                )}
                <ChevronRight className="h-4 w-4 text-slate-400" />
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
