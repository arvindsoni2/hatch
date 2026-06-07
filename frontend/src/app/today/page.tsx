import {
  fetchPendingApprovals,
  fetchPipelineStats,
  fetchProfileStatus,
  getOverdueFollowUps,
  fetchApplications,
  fetchAgentPerformance,
  type PendingApproval,
  type PipelineStats,
  type ApplicationListItem,
  type AgentPerformance,
} from "@/lib/api";
import { TodayPageClient } from "./TodayPageClient";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

export const revalidate = 30;

function pendingToHatchJob(a: PendingApproval): HatchJob {
  return {
    id: a.application_id,
    title: a.job_title ?? "Untitled Role",
    company: a.company ?? "—",
    loc: "—",
    rate: a.rate_text ?? "—",
    score: a.overall_score ?? 0,
    state: "ready",
  };
}

function readyToApplyToHatchJob(a: ApplicationListItem): HatchJob {
  return {
    id: a.id,
    title: a.job_title ?? "Untitled Role",
    company: a.job_company ?? "—",
    loc: a.job_location ?? "—",
    rate: a.job_rate_text ?? "—",
    score: a.agent_score ?? 0,
    state: "ready_to_apply",
  };
}

export default async function TodayPage() {
  const [approvals, readyToApplyPage, pipeline, profile, overdueFollowUps, agentPerf] = await Promise.all([
    fetchPendingApprovals().catch((): PendingApproval[] => []),
    fetchApplications({ status: "ready_to_apply" }, 0, 20).catch(() => ({ items: [] as ApplicationListItem[], total: 0, skip: 0, limit: 20 })),
    fetchPipelineStats().catch((): PipelineStats | null => null),
    fetchProfileStatus().catch(() => null),
    getOverdueFollowUps().catch(() => []),
    fetchAgentPerformance().catch((): AgentPerformance | null => null),
  ]);

  const jobs: HatchJob[] = [
    ...approvals.map(pendingToHatchJob),
    ...readyToApplyPage.items.map(readyToApplyToHatchJob),
  ];

  // funnel.scorer = shortlisted (jobs that cleared the score threshold)
  const funnel = {
    scout:  pipeline?.discovered  ?? 0,
    scorer: pipeline?.shortlisted ?? 0,
    tailor: pipeline?.tailored    ?? 0,
    coach:  pipeline?.approved    ?? 0,
  };

  // transit = jobs moving between stages
  const transit = {
    scout_to_scorer:  pipeline?.scored      ?? 0,  // total processed by scorer
    scorer_to_tailor: pipeline?.shortlisted ?? 0,  // shortlisted → sent to tailor
    tailor_to_coach:  pipeline?.tailored    ?? 0,  // tailored → ready for coach
  };

  return (
    <TodayPageClient
      jobs={jobs}
      funnel={funnel}
      transit={transit}
      profileName={profile?.candidate_name}
      followUpCount={overdueFollowUps.length}
      agentPerf={agentPerf}
    />
  );
}
