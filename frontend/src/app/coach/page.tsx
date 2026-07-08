"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { listSessions, SessionListItem, SessionResponse } from "@/lib/api";
import { SessionLauncherDialog } from "@/components/coach/SessionLauncher";
import { Brain, BookOpen, ChevronRight, Loader2, Plus } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/utils";

const STATUS_TONES: Record<string, "info" | "success" | "warning" | "danger" | "neutral"> = {
  active: "info",
  completed: "success",
  setup: "warning",
  abandoned: "danger",
};

const STATUS_LABELS: Record<string, string> = {
  setup: "Generating…",
  active: "In progress",
  completed: "Completed",
  abandoned: "Failed",
};

export default function CoachPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showLauncher, setShowLauncher] = useState(false);

  const fetchSessions = () =>
    listSessions(20)
      .then(setSessions)
      .catch(console.error)
      .finally(() => setLoading(false));

  useEffect(() => {
    fetchSessions();
  }, []);

  // Poll while any session is still generating so the list auto-updates
  useEffect(() => {
    const hasGenerating = sessions.some((s) => s.status === "setup");
    if (!hasGenerating) return;
    const id = setInterval(fetchSessions, 10_000);
    return () => clearInterval(id);
  }, [sessions]);

  const handleSessionCreated = (session: SessionResponse) => {
    router.push(`/coach/session/${session.id}`);
  };

  return (
    <PageContainer width="default" className="px-4 py-8">
      <PageHeader
        title="Interview Coach"
        description="Run live mock interviews and score answers. Use Interview Prep when you want saved research, likely questions, and calendar material before practice."
        actions={(
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/prep"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "min-h-11 sm:min-h-9")}
            >
              <BookOpen className="h-4 w-4" />
              Review Prep Materials
            </Link>
            <Button onClick={() => setShowLauncher(true)} className="gap-2" size="sm">
              <Plus className="h-4 w-4" />
              New Session
            </Button>
          </div>
        )}
      />

      <div className="mb-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
              <BookOpen className="h-4 w-4 text-[var(--accent)]" />
              Interview Prep
            </div>
            <p className="mt-1 text-sm text-[var(--text-dim)]">
              Prepared material for confirmed interviews: research, likely questions, and saved session notes.
            </p>
          </div>
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
              <Brain className="h-4 w-4 text-[var(--accent)]" />
              Interview Coach
            </div>
            <p className="mt-1 text-sm text-[var(--text-dim)]">
              Live mock interviews that evaluate answers, generate feedback, and build follow-up practice.
            </p>
          </div>
        </div>
      </div>

      {/* Sub-navigation */}
      <div className="mb-6 flex gap-1 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-1">
        <span className="flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-4 py-1.5 text-sm font-medium text-[var(--on-accent)]">
          <Brain className="h-3.5 w-3.5" /> Sessions
        </span>
        <Link
          href="/coach/stories"
          className="flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium text-[var(--text-dim)] hover:bg-[var(--surface)] hover:text-[var(--text)] transition-colors"
        >
          <BookOpen className="h-3.5 w-3.5" /> Story Bank
        </Link>
      </div>

      {/* Launcher modal */}
      {showLauncher && (
        <SessionLauncherDialog
          onClose={() => setShowLauncher(false)}
          onSessionCreated={handleSessionCreated}
        />
      )}

      {/* Session history */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-[var(--surface-2)]" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface)] px-4 py-16 text-center">
          <Brain className="h-10 w-10 text-[var(--text-muted)]" />
          <div>
            <p className="font-semibold text-[var(--text)]">No live practice sessions yet</p>
            <p className="mt-1 max-w-md text-sm text-[var(--text-dim)]">
              Start a mock interview when you are ready to answer questions out loud or in writing.
            </p>
          </div>
          <Button onClick={() => setShowLauncher(true)} className="gap-2">
            <Plus className="h-4 w-4" />
            New Session
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {sessions.map((session) => {
            const isGenerating = session.status === "setup";
            const isFailed = session.status === "abandoned";
            return (
              <div
                key={session.id}
                className={`flex items-center justify-between rounded-xl border bg-[var(--surface)] px-4 py-3 shadow-sm transition-colors ${
                  isGenerating
                    ? "border-[var(--warning)] cursor-default"
                    : isFailed
                    ? "border-[var(--danger)] cursor-default opacity-70"
                    : "border-[var(--border)] cursor-pointer hover:border-[var(--accent)] hover:shadow-sm"
                }`}
                onClick={() => {
                  if (isGenerating || isFailed) return;
                  session.status === "completed"
                    ? router.push(`/coach/report/${session.id}`)
                    : router.push(`/coach/session/${session.id}`);
                }}
              >
                <div className="flex items-center gap-3 min-w-0">
                  {isGenerating && (
                    <Loader2 className="h-4 w-4 flex-shrink-0 animate-spin text-amber-500" />
                  )}
                  <div className="flex flex-col gap-0.5 min-w-0">
                    <p className="font-medium text-[var(--text)] truncate">
                      {session.role_title} - {session.company_name}
                    </p>
                    <p className="text-xs text-[var(--text-muted)]">
                      {isGenerating
                        ? "Questions being generated — check the notification bell when ready"
                        : new Date(session.created_at).toLocaleDateString("en-GB", {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                    </p>
                  </div>
                </div>
                <div className="flex flex-shrink-0 items-center gap-3">
                  <StatusBadge tone={STATUS_TONES[session.status] ?? "neutral"}>
                    {STATUS_LABELS[session.status] ?? session.status}
                  </StatusBadge>
                  {session.overall_score != null && (
                    <span className={`text-sm font-bold ${session.overall_score >= 8 ? "text-[var(--success)]" : session.overall_score >= 6 ? "text-[var(--warning)]" : "text-[var(--danger)]"}`}>
                      {session.overall_score.toFixed(1)}/10
                    </span>
                  )}
                  {!isGenerating && !isFailed && (
                    <ChevronRight className="h-4 w-4 text-[var(--text-muted)]" />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </PageContainer>
  );
}
