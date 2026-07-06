"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { PrepScreen } from "@/components/hatch/screens/PrepScreen";
import type { PrepSession, PrepQuestion } from "@/components/hatch/screens/PrepScreen";
import { SessionLauncherDialog } from "@/components/coach/SessionLauncher";
import { getSession, fetchApplication, abandonSession, retrySession } from "@/lib/api";
import type { SessionResponse } from "@/lib/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

interface PrepPageClientProps {
  sessions: PrepSession[];
}

function normaliseCat(raw: string): PrepQuestion["cat"] {
  const lower = raw.toLowerCase();
  if (lower.includes("technical")) return "Technical";
  if (lower.includes("leadership") || lower.includes("management")) return "Leadership";
  return "Behavioural";
}

function buildIcs(title: string, company: string, isoDate: string): string {
  const start = new Date(isoDate);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//JobPilot//Coach//EN",
    "BEGIN:VEVENT",
    `UID:${Date.now()}@jobpilot`,
    `DTSTART:${fmt(start)}`,
    `DTEND:${fmt(end)}`,
    `SUMMARY:${title} Interview — ${company}`,
    "DESCRIPTION:Interview prep session from Coach",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
}

export function PrepPageClient({ sessions: initialSessions }: PrepPageClientProps) {
  const router = useRouter();
  const firstReady = initialSessions.find((s) => s.status === "ready");
  const [sessions, setSessions] = useState<PrepSession[]>(initialSessions);
  const [openSessionId, setOpenSessionId] = useState<string | undefined>(firstReady?.id);
  const [sessionCache, setSessionCache] = useState<Record<string, SessionResponse>>({});
  const [showLauncher, setShowLauncher] = useState(false);
  const [retryingIds, setRetryingIds] = useState<Record<string, boolean>>({});
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Auto-fetch detail for the initially-selected session (state setter never triggers handleSelectSession)
  useEffect(() => {
    if (!openSessionId || sessionCache[openSessionId]) return;
    getSession(openSessionId)
      .then((full) => setSessionCache((prev) => ({ ...prev, [openSessionId]: full })))
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSessionId]);

  const handleDeleteSession = (id: string) => {
    setPendingDeleteId(id);
  };

  const confirmDeleteSession = async () => {
    if (!pendingDeleteId) return;
    const id = pendingDeleteId;
    setPendingDeleteId(null);
    try {
      await abandonSession(id);
    } catch {
      setNotice("Hatch could not remove this session from storage. Refresh and try again.");
      return;
    }
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (openSessionId === id) setOpenSessionId(undefined);
  };

  const handleRetrySession = async (id: string) => {
    const source = sessions.find((s) => s.id === id);
    if (!source) return;
    setRetryingIds((prev) => ({ ...prev, [id]: true }));
    try {
      const ref = await retrySession(id);
      setSessions((prev) => [
        {
          id: ref.session_id ?? ref.job_id,
          title: source.title,
          company: source.company,
          status: "generating",
          createdAt: new Date().toISOString(),
          startedAt: new Date().toISOString(),
        },
        ...prev.filter((s) => s.id !== id),
      ]);
      setOpenSessionId(undefined);
      router.refresh();
    } catch {
      setNotice("Hatch could not retry this prep session. Check the connection and try again.");
    } finally {
      setRetryingIds((prev) => ({ ...prev, [id]: false }));
    }
  };

  const enrichedSessions: PrepSession[] = sessions.map((s) => {
    const full = sessionCache[s.id];
    if (!full) return s;
    return {
      ...s,
      questions: full.questions.map((q) => ({
        q: q.text,
        cat: normaliseCat(q.category),
        star: q.model_answer ?? undefined,
      })),
    };
  });

  const handleSelectSession = async (id: string) => {
    setOpenSessionId(id);
    if (!sessionCache[id]) {
      try {
        const full = await getSession(id);
        setSessionCache((prev) => ({ ...prev, [id]: full }));
      } catch {
        // session detail unavailable — show what we have
      }
    }
  };

  const handleCalendar = async () => {
    if (!openSessionId) return;
    const full = sessionCache[openSessionId];

    // Manual session (no linked application) — generate ICS client-side from stored interview_date
    if (!full?.application_id) {
      if (!full?.interview_date) {
        setNotice("No interview date is saved. Create a new session and add the date first.");
        return;
      }
      const ics = buildIcs(full.role_title, full.company_name, full.interview_date);
      const blob = new Blob([ics], { type: "text/calendar" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "interview.ics";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      return;
    }

    // Application-linked session — fetch from backend iCal endpoint
    try {
      const app = await fetchApplication(full.application_id);
      const upcoming = app.interviews
        .filter((i) => i.scheduled_at)
        .sort((a, b) => new Date(a.scheduled_at!).getTime() - new Date(b.scheduled_at!).getTime())
        .find((i) => new Date(i.scheduled_at!) >= new Date());
      const interview = upcoming ?? app.interviews[0];
      if (!interview) {
        setNotice("No interview rounds were found. Add an interview round to the application first.");
        return;
      }
      const a = document.createElement("a");
      a.href = `/api/v2/interviews/${interview.id}/ical`;
      a.download = "interview.ics";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      setNotice("Hatch could not download the calendar file. Check the connection and try again.");
    }
  };

  return (
    <>
      <PrepScreen
        sessions={enrichedSessions}
        openSessionId={openSessionId}
        onNewSession={() => setShowLauncher(true)}
        onSelectSession={handleSelectSession}
        onCalendar={handleCalendar}
        onPractice={(id) => router.push(`/coach/session/${id}`)}
        onDeleteSession={handleDeleteSession}
        onRetrySession={handleRetrySession}
        retryingIds={retryingIds}
      />

      {notice ? (
        <div
          className="my-3 flex items-start justify-between gap-3 rounded-[var(--radius-control)] border border-[var(--danger)] bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]"
          role="alert"
        >
          <p>{notice}</p>
          <Button onClick={() => setNotice(null)} size="sm" variant="ghost">
            Dismiss
          </Button>
        </div>
      ) : null}

      <AlertDialog
        onOpenChange={(open) => { if (!open) setPendingDeleteId(null); }}
        open={Boolean(pendingDeleteId)}
      >
        <AlertDialogContent>
          <AlertDialogTitle className="text-lg font-semibold text-[var(--text)]">
            Remove Prep Session?
          </AlertDialogTitle>
          <AlertDialogDescription>
            This permanently removes the selected preparation session and cannot be undone.
          </AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void confirmDeleteSession()}>
              Remove Session
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {showLauncher && (
        <SessionLauncherDialog
          onClose={() => setShowLauncher(false)}
          onSessionCreated={(session) => router.push(`/coach/session/${session.id}`)}
        />
      )}
    </>
  );
}
