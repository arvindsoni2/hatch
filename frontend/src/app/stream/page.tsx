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
    title: a.job_title ?? "Untitled Role",
    company: a.company ?? "—",
    loc: "—",
    rate: a.rate_text ?? "—",
    score: a.overall_score ?? 0,
    state: "ready",
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
  const [approvals, preparingApps, shortlistedApps] = await Promise.all([
    fetchPendingApprovals().catch((): PendingApproval[] => []),
    fetchApplications({ status: "preparing" }, 0, 30).catch(() => ({ items: [] as ApplicationListItem[], total: 0 })),
    fetchApplications({ status: "shortlisted" }, 0, 30).catch(() => ({ items: [] as ApplicationListItem[], total: 0 })),
  ]);

  const readyIds = new Set(approvals.map((a) => a.application_id));

  const readyJobs = approvals.map(pendingToHatchJob);
  const tailoringJobs = preparingApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "tailoring"));
  const parkedJobs = shortlistedApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "parked"));

  const jobs: HatchJob[] = [...readyJobs, ...tailoringJobs, ...parkedJobs];

  return <StreamPageClient jobs={jobs} />;
}
