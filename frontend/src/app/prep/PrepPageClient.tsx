"use client";
import { useState } from "react";
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

export function PrepPageClient({ sessions: initialSessions }: PrepPageClientProps) {
  const router = useRouter();
  const firstReady = initialSessions.find((s) => s.status === "ready");
  const [openSessionId, setOpenSessionId] = useState<string | undefined>(firstReady?.id);
  const [sessionCache, setSessionCache] = useState<Record<string, SessionResponse>>({});
  const [showLauncher, setShowLauncher] = useState(false);

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
    const applicationId = full?.application_id;
    if (!applicationId) {
      alert("No linked application found for this prep session.");
      return;
    }
    try {
      const app = await fetchApplication(applicationId);
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
