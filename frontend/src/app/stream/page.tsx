import type {
  PendingApproval,
  ApplicationListItem,
  PaginatedResponse,
} from "@/lib/api";
import { serverApiFetch } from "@/lib/server-api";
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
    ats: a.latest_cv_ats_score ?? undefined,
    state: "ready",
    jobUrl: a.job_url ?? undefined,
  };
}

function appToHatchJob(a: ApplicationListItem, state: HatchJob["state"]): HatchJob {
  return {
    id: a.id,
    jobPostingId: a.job_id ?? undefined,
    title: a.job_title ?? "Untitled Role",
    company: a.job_company ?? "—",
    loc: a.job_location ?? "—",
    rate: a.job_rate_text ?? "—",
    score: a.agent_score ?? 0,
    ats: a.latest_cv_ats_score ?? undefined,
    state,
  };
}

export default async function StreamPage() {
  const [approvals, preparingApps, failedApps, shortlistedApps, discoveredApps, readyToApplyApps] = await Promise.all([
    serverApiFetch<PendingApproval[]>("/api/agents/approvals/pending"),
    serverApiFetch<PaginatedResponse<ApplicationListItem>>("/api/applications?status=preparing&skip=0&limit=30"),
    serverApiFetch<PaginatedResponse<ApplicationListItem>>("/api/applications?status=approved&skip=0&limit=30"),
    serverApiFetch<PaginatedResponse<ApplicationListItem>>("/api/applications?status=shortlisted&skip=0&limit=30"),
    serverApiFetch<PaginatedResponse<ApplicationListItem>>("/api/applications?status=discovered&skip=0&limit=50"),
    serverApiFetch<PaginatedResponse<ApplicationListItem>>("/api/applications?status=ready_to_apply&skip=0&limit=50"),
  ]);

  const readyIds = new Set(approvals.map((a) => a.application_id));

  const readyJobs = approvals.map(pendingToHatchJob);
  const tailoringJobs = preparingApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "tailoring"));
  const failedJobs = failedApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => ({
      ...appToHatchJob(a, "tailoring_failed"),
      failureReason: "The previous tailoring run did not complete. Retry to generate a fresh package.",
    }));
  const parkedJobs = shortlistedApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "parked"));
  // Agent-created discovered jobs are in-pipeline (being scored/tailored)
  const inPipelineJobs = discoveredApps.items
    .filter((a) => a.agent_created && !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "tailoring"));
  // Approved and tailored — ready for user to submit
  const applyJobs = readyToApplyApps.items
    .filter((a) => !readyIds.has(a.id))
    .map((a) => appToHatchJob(a, "ready_to_apply"));

  const jobs: HatchJob[] = [...readyJobs, ...failedJobs, ...tailoringJobs, ...applyJobs, ...parkedJobs, ...inPipelineJobs];

  return <StreamPageClient jobs={jobs} />;
}
