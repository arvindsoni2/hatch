import type {
  PendingApproval,
  PipelineStats,
  ApplicationListItem,
  AgentPerformance,
  PaginatedResponse,
  ProfileStatus,
  FollowUp,
  InterviewRound,
  Application,
} from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
import { TodayPageClient } from "./TodayPageClient";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

export const revalidate = 30;

function pendingToHatchJob(a: PendingApproval): HatchJob {
  const hasDims = a.skill_match != null || a.experience_match != null || a.rate_match != null || a.location_match != null;
  return {
    id: a.application_id,
    jobPostingId: a.job_id ?? undefined,
    title: a.job_title ?? "Untitled Role",
    company: a.company ?? "—",
    loc: "—",
    rate: a.rate_text ?? "—",
    score: a.overall_score ?? 0,
    ats: a.latest_cv_ats_score ?? undefined,
    dims: hasDims ? {
      Skills: a.skill_match ?? 0,
      Experience: a.experience_match ?? 0,
      Rate: a.rate_match ?? 0,
      Location: a.location_match ?? 0,
    } : undefined,
    state: "ready",
  };
}

function readyToApplyToHatchJob(a: ApplicationListItem): HatchJob {
  return {
    id: a.id,
    jobPostingId: a.job_id ?? undefined,
    title: a.job_title ?? "Untitled Role",
    company: a.job_company ?? "—",
    loc: a.job_location ?? "—",
    rate: a.job_rate_text ?? "—",
    score: a.agent_score ?? 0,
    ats: a.latest_cv_ats_score ?? undefined,
    state: "ready_to_apply",
  };
}

export default async function TodayPage() {
  const [approvals, readyToApplyPage, pipeline, profile, overdueFollowUps, agentPerf, upcomingInterviews] = await Promise.all([
    serverApiFetch<PendingApproval[]>("/api/agents/approvals/pending"),
    serverApiFetch<PaginatedResponse<ApplicationListItem>>("/api/applications?status=ready_to_apply&skip=0&limit=20"),
    serverApiFetch<PipelineStats>("/api/agents/dashboard/pipeline"),
    serverApiFetch<ProfileStatus>("/api/v2/profile/status"),
    serverApiFetch<FollowUp[]>("/api/interviews/follow-ups/overdue"),
    serverApiFetch<AgentPerformance>("/api/analytics/agent-performance"),
    serverApiFetch<InterviewRound[]>("/api/interviews/upcoming?days=14"),
  ]);

  // Build upcoming interview card data if a real interview is scheduled
  let upcomingInterview: { scheduledAt: string; title: string; company: string; daysUntil: number } | null = null;
  const next = upcomingInterviews[0] ?? null;
  if (next?.scheduled_at) {
    const daysUntil = Math.ceil(
      (new Date(next.scheduled_at).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    );
    if (daysUntil >= 0) {
      let title = "Interview";
      let company = "";
      try {
        const app = await serverApiFetch<Application>(`/api/applications/${next.application_id}`);
        title = app.job?.title ?? "Interview";
        company = app.job?.company ?? "";
      } catch {
        // use defaults
      }
      upcomingInterview = { scheduledAt: next.scheduled_at, title, company, daysUntil };
    }
  }

  const jobs: HatchJob[] = [
    ...approvals.map(pendingToHatchJob),
    ...readyToApplyPage.items.map(readyToApplyToHatchJob),
  ];

  // funnel.scorer = scored (jobs Scorer evaluated); arrow out = shortlisted (passed threshold)
  const funnel = {
    scout:  pipeline?.discovered  ?? 0,
    scorer: pipeline?.scored      ?? 0,
    tailor: pipeline?.tailored    ?? 0,
    coach:  pipeline?.coach_sessions ?? 0,
  };

  // transit = jobs moving between stages
  const transit = {
    scout_to_scorer:  pipeline?.scored      ?? 0,  // jobs Scorer evaluated
    scorer_to_tailor: pipeline?.shortlisted ?? 0,  // shortlisted → sent to tailor
    tailor_to_coach:  pipeline?.coach_sessions ?? 0,  // generated Coach sessions
  };

  return (
    <TodayPageClient
      jobs={jobs}
      funnel={funnel}
      transit={transit}
      profileName={profile?.candidate_name}
      followUpCount={overdueFollowUps.length}
      agentPerf={agentPerf}
      upcomingInterview={upcomingInterview}
    />
  );
}
