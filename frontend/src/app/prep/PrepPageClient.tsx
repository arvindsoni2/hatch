"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { PrepScreen } from "@/components/hatch/screens/PrepScreen";
import type { PrepSession, PrepQuestion } from "@/components/hatch/screens/PrepScreen";
import { SessionLauncher } from "@/components/coach/SessionLauncher";
import { getSession, fetchApplication } from "@/lib/api";
import type { SessionResponse } from "@/lib/api";

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
  const [openSessionId, setOpenSessionId] = useState<string | undefined>(firstReady?.id);
  const [sessionCache, setSessionCache] = useState<Record<string, SessionResponse>>({});
  const [showLauncher, setShowLauncher] = useState(false);

  // Auto-fetch detail for the initially-selected session (state setter never triggers handleSelectSession)
  useEffect(() => {
    if (!openSessionId || sessionCache[openSessionId]) return;
    getSession(openSessionId)
      .then((full) => setSessionCache((prev) => ({ ...prev, [openSessionId]: full })))
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openSessionId]);

  const enrichedSessions: PrepSession[] = initialSessions.map((s) => {
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
        alert("No interview date on record — create a new session and enter the interview date to use this feature.");
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
        alert("No interview rounds found — add an interview round in the application first.");
        return;
      }
      const a = document.createElement("a");
      a.href = `/api/v2/interviews/${interview.id}/ical`;
      a.download = "interview.ics";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch {
      alert("Could not download calendar file.");
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
      />

      {showLauncher && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="relative w-full max-w-lg">
            <button
              onClick={() => setShowLauncher(false)}
              className="absolute right-4 top-4 z-10 text-slate-500 hover:text-slate-700"
            >
              <X className="h-5 w-5" />
            </button>
            <SessionLauncher onSessionCreated={(session) => router.push(`/coach/session/${session.id}`)} />
          </div>
        </div>
      )}
    </>
  );
}
