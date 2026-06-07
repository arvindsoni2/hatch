import {
  fetchPendingApprovals,
  fetchApplications,
  type PendingApproval,
  type ApplicationListItem,
} from "@/lib/api";
import { StreamPageClient } from "./StreamPageClient";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

export const revalidate = 30;

function pendingToHatchJob(a: PendingApproval): HatchJob {
  return {
    id: a.application_id,
    jobPostingId: a.job_id ?? undefined,
    title: a.job_title ?? "Untitled Role",
    company: a.company ?? "—",
    loc: "—",
    rate: a.rate_text ?? "—",
    score: a.overall_score ?? 0,
    state: "ready",
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
  };
}

export default async function StreamPage() {
  const [approvals, preparingApps, shortlistedApps, discoveredApps] = await Promise.all([
    fetchPendingApprovals().catch((): PendingApproval[] => []),
    fetchApplications({ status: "preparing" }, 0, 30).catch(() => ({ items: [] as ApplicationListItem[], total: 0, skip: 0, limit: 30 })),
    fetchApplications({ status: "shortlisted" }, 0, 30).catch(() => ({ items: [] as ApplicationListItem[], total: 0, skip: 0, limit: 30 })),
    fetchApplications({ status: "discovered" }, 0, 50).catch(() => ({ items: [] as ApplicationListItem[], total: 0, skip: 0, limit: 50 })),
  ]);

  const readyIds = new Set(approvals.map((a) => a.application_id));

  const readyJobs = approvals.map(pendingToHatchJob);
  const tailoringJobs = preparingApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "tailoring"));
  const parkedJobs = shortlistedApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "parked"));
  // Agent-created discovered jobs are in-pipeline (being scored/tailored)
  const inPipelineJobs = discoveredApps.items
    .filter((a) => a.agent_created && !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "tailoring"));

  const jobs: HatchJob[] = [...readyJobs, ...tailoringJobs, ...parkedJobs, ...inPipelineJobs];

  return <StreamPageClient jobs={jobs} />;
}
