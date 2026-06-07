import { fetchKanban, type ApplicationListItem } from "@/lib/api";
import { TrackerScreen } from "@/components/hatch/screens/TrackerScreen";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

export const revalidate = 30;

interface KanbanJob {
  id: string;
  title: string;
  company: string;
  loc: string;
  rate: string;
  score: number;
  when?: string;
  jobUrl?: string;
}

function appToKanbanJob(a: ApplicationListItem): KanbanJob {
  return {
    id: a.id,
    title: a.job_title ?? "Untitled Role",
    company: a.job_company ?? "—",
    loc: a.job_location ?? "—",
    rate: a.job_rate_text ?? "—",
    score: a.agent_score ?? 0,
    jobUrl: a.job_url ?? undefined,
  };
}

function appToHatchJob(a: ApplicationListItem, state: HatchJob["state"]): HatchJob {
  return {
    id: a.id,
    title: a.job_title ?? "Untitled Role",
    company: a.job_company ?? "—",
    loc: a.job_location ?? "—",
    rate: a.job_rate_text ?? "—",
    score: a.agent_score ?? 0,
    state,
    jobUrl: a.job_url ?? undefined,
  };
}

export default async function TrackerPage() {
  const kanban = await fetchKanban().catch(() => ({ columns: {} as Record<string, ApplicationListItem[]>, stats: { active_count: 0, applied_count: 0, response_rate: 0, overdue_count: 0 } }));

  const cols = kanban.columns;

  const discovered = [
    ...(cols["discovered"] ?? []),
    ...(cols["shortlisted"] ?? []),
  ].map((a) => appToHatchJob(a, "parked"));

  const ready = (cols["ready_to_apply"] ?? []).map((a: ApplicationListItem) =>
    appToHatchJob(a, "ready")
  );

  const appliedJobs = (cols["applied"] ?? []).map(appToKanbanJob);
  const interviewJobs = (cols["interview"] ?? []).map(appToKanbanJob);

  const jobs: HatchJob[] = [...ready, ...discovered];

  return (
    <TrackerScreen
      jobs={jobs}
      appliedJobs={appliedJobs}
      interviewJobs={interviewJobs}
    />
  );
}
