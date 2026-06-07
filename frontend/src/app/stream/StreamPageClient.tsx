"use client";
import { useState } from "react";
import { StreamScreen } from "@/components/hatch/screens/StreamScreen";
import { ReviewOverlay } from "@/components/hatch/ReviewOverlay";
import { ApplicationReadyCard } from "@/components/hatch/ApplicationReadyCard";
import { approveJob, rejectApplication, markApplied, revertApplication } from "@/lib/api";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";
import type { ApplicationPackage } from "@/lib/api";

interface StreamPageClientProps {
  jobs: HatchJob[];
}

export function StreamPageClient({ jobs: initialJobs }: StreamPageClientProps) {
  const [localJobs, setLocalJobs] = useState<HatchJob[]>(initialJobs);
  const [packages, setPackages] = useState<Record<string, ApplicationPackage>>({});
  const [reviewQueue, setReviewQueue] = useState<HatchJob[]>([]);
  const [reviewIdx, setReviewIdx] = useState(0);
  const [approving, setApproving] = useState(false);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  async function handleApprove(jobId: string, jobPostingId?: string) {
    setApprovingId(jobId);
    const pkg = await approveJob(jobPostingId ?? jobId).catch(() => null);
    setApprovingId(null);
    if (pkg) {
      setPackages((prev) => ({ ...prev, [jobId]: pkg }));
      setLocalJobs((prev) =>
        prev.map((j) =>
          j.id === jobId
            ? { ...j, state: "ready_to_apply" as const, jobUrl: pkg.job_url ?? undefined }
            : j
        )
      );
    }
  }

  async function handleAction(action: "approve" | "reject") {
    const job = reviewQueue[reviewIdx];
    if (!job) return;
    if (action === "approve") {
      setApproving(true);
      const pkg = await approveJob(job.jobPostingId ?? job.id).catch(() => null);
      setApproving(false);
      if (pkg) {
        setPackages((prev) => ({ ...prev, [job.id]: pkg }));
        setLocalJobs((prev) =>
          prev.map((j) =>
            j.id === job.id
              ? { ...j, state: "ready_to_apply" as const, jobUrl: pkg.job_url ?? undefined }
              : j
          )
        );
      }
    } else {
      await rejectApplication(job.id).catch(() => {});
      setLocalJobs((prev) => prev.filter((j) => j.id !== job.id));
    }
    if (reviewIdx < reviewQueue.length - 1) {
      setReviewIdx((i) => i + 1);
    } else {
      setReviewQueue([]);
    }
  }

  async function handleMarkApplied(id: string) {
    await markApplied(id).catch(() => {});
    setLocalJobs((prev) => prev.filter((j) => j.id !== id));
    setPackages((prev) => { const n = { ...prev }; delete n[id]; return n; });
  }

  async function handleRevert(id: string) {
    await revertApplication(id).catch(() => {});
    setLocalJobs((prev) =>
      prev.map((j) => j.id === id ? { ...j, state: "ready" as const } : j)
    );
    setPackages((prev) => { const n = { ...prev }; delete n[id]; return n; });
  }

  const readyToApplyWithPkg = localJobs
    .filter((j) => j.state === "ready_to_apply" && packages[j.id])
    .map((j) => ({ job: j, pkg: packages[j.id] }));

  return (
    <>
      <StreamScreen
        jobs={localJobs}
        onReview={(ids) => {
          const q = localJobs.filter((j) => ids.includes(j.id));
          setReviewQueue(q);
          setReviewIdx(0);
        }}
        onApprove={handleApprove}
        approvingId={approvingId}
      />
      {readyToApplyWithPkg.map(({ job, pkg }) => (
        <ApplicationReadyCard
          key={job.id}
          job={job}
          pkg={pkg}
          onMarkApplied={handleMarkApplied}
          onRevert={handleRevert}
        />
      ))}
      {reviewQueue.length > 0 && (
        <ReviewOverlay
          queue={reviewQueue}
          idx={reviewIdx}
          onAction={handleAction}
          onClose={() => { if (!approving) setReviewQueue([]); }}
          isLoading={approving}
        />
      )}
    </>
  );
}
