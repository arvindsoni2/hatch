"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { ConversationSession } from "@/components/coach/conversation/ConversationSession";
import { ApiError, getSession, type SessionResponse } from "@/lib/api";

const LegacyCoachSession = dynamic(
  () => import("@/components/coach/LegacyCoachSession").then((module) => module.LegacyCoachSession),
  { ssr: false },
);

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  const loadSession = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setSession(await getSession(id));
    } catch (caught) {
      setSession(null);
      setError(caught);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 aria-label="Loading interview" className="h-8 w-8 animate-spin text-indigo-400" />
      </div>
    );
  }

  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-slate-400">Session not found</p>
      </div>
    );
  }

  if (error !== null || session === null) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-4">
        <p className="text-slate-400">We could not load this interview. Try again.</p>
        <button
          type="button"
          onClick={() => void loadSession()}
          className="hatch-interactive rounded-[var(--radius-control)] border border-[var(--border)] px-4 py-2 text-sm font-semibold text-[var(--text)] focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
        >
          Try loading interview again
        </button>
      </div>
    );
  }

  if (session.experience_version === "conversational_v1") {
    return <ConversationSession sessionId={session.id} />;
  }

  return <LegacyCoachSession initialSession={session} />;
}
