import {
  fetchPendingApprovals,
  fetchPipelineStats,
  fetchProfileStatus,
  getOverdueFollowUps,
  fetchApplications,
  type PendingApproval,
  type PipelineStats,
  type ApplicationListItem,
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
  const [approvals, readyToApplyPage, pipeline, profile, overdueFollowUps] = await Promise.all([
    fetchPendingApprovals().catch((): PendingApproval[] => []),
    fetchApplications({ status: "ready_to_apply" }, 0, 20).catch(() => ({ items: [] as ApplicationListItem[], total: 0, skip: 0, limit: 20 })),
    fetchPipelineStats().catch((): PipelineStats | null => null),
    fetchProfileStatus().catch(() => null),
    getOverdueFollowUps().catch(() => []),
  ]);

  const jobs: HatchJob[] = [
    ...approvals.map(pendingToHatchJob),
    ...readyToApplyPage.items.map(readyToApplyToHatchJob),
  ];

  const funnel = {
    scout:  pipeline?.discovered ?? 0,
    scorer: pipeline?.scored     ?? 0,
    tailor: pipeline?.tailored   ?? 0,
    coach:  pipeline?.approved   ?? 0,
  };

  return (
    <TodayPageClient
      jobs={jobs}
      funnel={funnel}
      profileName={profile?.candidate_name}
      followUpCount={overdueFollowUps.length}
    />
  );
}
