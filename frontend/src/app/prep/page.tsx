import type { SessionListItem } from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { PrepPageClient } from "./PrepPageClient";
import type { PrepSession } from "@/components/hatch/screens/PrepScreen";

export const revalidate = 60;

function sessionToPrep(s: SessionListItem): PrepSession {
  const startedAt = s.started_at ?? s.created_at;
  const ageMs = Date.now() - new Date(startedAt).getTime();
  const status =
    s.status === "completed" || s.status === "active"
      ? "ready"
      : s.status === "abandoned"
      ? "failed"
      : s.status === "in_progress"
      ? "progress"
      : ageMs > 30 * 60 * 1000
      ? "stale"
      : "generating";

  return {
    id: s.id,
    title: s.role_title,
    company: s.company_name,
    status,
    createdAt: s.created_at,
    startedAt,
  };
}

export default async function PrepPage() {
  const raw = await serverApiFetch<SessionListItem[]>("/api/coach/sessions?limit=20");
  const sessions = raw.map(sessionToPrep);

  return <PrepPageClient sessions={sessions} />;
}
