"use client";
import { useState } from "react";
import { PrepScreen } from "@/components/hatch/screens/PrepScreen";
import type { PrepSession } from "@/components/hatch/screens/PrepScreen";

interface PrepPageClientProps {
  sessions: PrepSession[];
}

export function PrepPageClient({ sessions }: PrepPageClientProps) {
  const firstReady = sessions.find((s) => s.status === "ready");
  const [openSessionId] = useState<string | undefined>(firstReady?.id);

  return (
    <PrepScreen
      sessions={sessions}
      openSessionId={openSessionId}
    />
  );
}
