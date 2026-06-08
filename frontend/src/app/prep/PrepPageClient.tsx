"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { PrepScreen } from "@/components/hatch/screens/PrepScreen";
import type { PrepSession } from "@/components/hatch/screens/PrepScreen";
import { SessionLauncher } from "@/components/coach/SessionLauncher";
import type { SessionResponse } from "@/lib/api";

interface PrepPageClientProps {
  sessions: PrepSession[];
}

export function PrepPageClient({ sessions }: PrepPageClientProps) {
  const router = useRouter();
  const firstReady = sessions.find((s) => s.status === "ready");
  const [openSessionId] = useState<string | undefined>(firstReady?.id);
  const [showLauncher, setShowLauncher] = useState(false);

  const handleSessionCreated = (session: SessionResponse) => {
    router.push(`/coach/session/${session.id}`);
  };

  return (
    <>
      <PrepScreen
        sessions={sessions}
        openSessionId={openSessionId}
        onNewSession={() => setShowLauncher(true)}
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
            <SessionLauncher onSessionCreated={handleSessionCreated} />
          </div>
        </div>
      )}
    </>
  );
}
