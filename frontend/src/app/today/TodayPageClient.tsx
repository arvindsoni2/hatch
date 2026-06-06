"use client";
import { useState } from "react";
import { TodayScreen } from "@/components/hatch/screens/TodayScreen";
import { ReviewOverlay } from "@/components/hatch/ReviewOverlay";
import { ApplicationReadyCard } from "@/components/hatch/ApplicationReadyCard";
import { approveJob, rejectApplication, markApplied, revertApplication } from "@/lib/api";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";
import type { ApplicationPackage } from "@/lib/api";

interface TodayPageClientProps {
  jobs: HatchJob[];
  funnel: { scout: number; scorer: number; tailor: number; coach: number };
  profileName?: string;
  followUpCount?: number;
}

export function TodayPageClient({ jobs, funnel, profileName, followUpCount }: TodayPageClientProps) {
  const [localJobs, setLocalJobs] = useState<HatchJob[]>(jobs);
  const [reviewQueue, setReviewQueue] = useState<HatchJob[]>([]);
  const [reviewIdx, setReviewIdx] = useState(0);
  const [packages, setPackages] = useState<Record<string, ApplicationPackage>>({});

  async function handleAction(action: "approve" | "reject") {
    const job = reviewQueue[reviewIdx];
    if (!job) return;
    if (action === "approve") {
      const pkg = await approveJob(job.id).catch(() => null);
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
      <TodayScreen
        jobs={localJobs}
        funnel={funnel}
        profileName={profileName ?? "there"}
        followUpCount={followUpCount}
        onReview={(ids) => {
          const q = localJobs.filter((j) => ids.includes(j.id));
          setReviewQueue(q);
          setReviewIdx(0);
        }}
        onMarkApplied={handleMarkApplied}
        onRevert={handleRevert}
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
          onClose={() => setReviewQueue([])}
        />
      )}
    </>
  );
}
