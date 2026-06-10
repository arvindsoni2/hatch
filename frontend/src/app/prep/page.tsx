import { listSessions, type SessionListItem } from "@/lib/api";
import { PrepPageClient } from "./PrepPageClient";
import type { PrepSession } from "@/components/hatch/screens/PrepScreen";

export const revalidate = 60;

function sessionToPrep(s: SessionListItem): PrepSession {
  const status =
    s.status === "completed" || s.status === "active"
      ? "ready"
      : s.status === "in_progress"
      ? "progress"
      : "generating";

  return {
    id: s.id,
    title: s.role_title,
    company: s.company_name,
    status,
  };
}

export default async function PrepPage() {
  const raw = await listSessions(20).catch((): SessionListItem[] => []);
  const sessions = raw.filter((s) => s.status !== "abandoned").map(sessionToPrep);

  return <PrepPageClient sessions={sessions} />;
}
