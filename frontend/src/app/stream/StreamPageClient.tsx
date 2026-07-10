"use client";
import { useState, useRef, useCallback, useEffect } from "react";
import { StreamScreen } from "@/components/hatch/screens/StreamScreen";
import { ReviewOverlay } from "@/components/hatch/ReviewOverlay";
import { ApplicationReadyCard } from "@/components/hatch/ApplicationReadyCard";
import { approveJob, rejectApplication, markApplied, revertApplication, getAsyncJob, getApplicationPackage } from "@/lib/api";
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
  const [approvingIds, setApprovingIds] = useState<Set<string>>(() => new Set());
  const pollRefs = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  const addApprovingId = useCallback((id: string) => {
    setApprovingIds((prev) => new Set(prev).add(id));
  }, []);

  const removeApprovingId = useCallback((id: string) => {
    setApprovingIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  }, []);

  // Hydrate packages for any ready_to_apply jobs that arrived via server props
  useEffect(() => {
    const missing = initialJobs.filter((j) => j.state === "ready_to_apply");
    if (missing.length === 0) return;
    missing.forEach(async (job) => {
      try {
        const pkg = await getApplicationPackage(job.id);
        setPackages((prev) => ({ ...prev, [job.id]: pkg }));
      } catch {
        // package not ready yet — ignore
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startPolling = useCallback((asyncJobId: string, jobId: string, jobTitle: string, company: string | null) => {
    const existing = pollRefs.current.get(jobId);
    if (existing) clearInterval(existing);

    const interval = setInterval(async () => {
      try {
        const asyncJob = await getAsyncJob<ApplicationPackage>(asyncJobId);
        if (asyncJob.status === "done" && asyncJob.result) {
          clearInterval(interval);
          pollRefs.current.delete(jobId);
          removeApprovingId(jobId);
          const pkg = asyncJob.result;
          setPackages((prev) => ({ ...prev, [jobId]: pkg }));
          setLocalJobs((prev) =>
            prev.map((j) =>
              j.id === jobId
                ? { ...j, state: "ready_to_apply" as const, jobUrl: pkg.job_url ?? undefined }
                : j
            )
          );
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            new Notification("Application ready", {
              body: `Your CV and cover letter for ${jobTitle}${company ? ` at ${company}` : ""} are ready to review.`,
            });
          }
        } else if (asyncJob.status === "failed") {
          clearInterval(interval);
          pollRefs.current.delete(jobId);
          removeApprovingId(jobId);
          setLocalJobs((prev) => prev.map((j) => j.id === jobId ? {
            ...j,
            state: "tailoring_failed" as const,
            failureReason: asyncJob.error || "Tailoring did not complete. Retry to generate a fresh package.",
          } : j));
        }
      } catch {
        // network hiccup — keep polling
      }
    }, 5000);
    pollRefs.current.set(jobId, interval);
  }, [removeApprovingId]);

  useEffect(() => () => {
    pollRefs.current.forEach((interval) => clearInterval(interval));
    pollRefs.current.clear();
  }, []);

  async function handleApprove(jobId: string, jobPostingId?: string) {
    addApprovingId(jobId);
    try {
      const ref = await approveJob(jobPostingId ?? jobId);
      if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
        Notification.requestPermission();
      }
      const job = localJobs.find((j) => j.id === jobId);
      setLocalJobs((prev) =>
        prev.map((j) => j.id === jobId ? { ...j, state: "tailoring" as const, failureReason: undefined } : j)
      );
      startPolling(ref.async_job_id, jobId, job?.title ?? "", job?.company ?? null);
    } catch {
      removeApprovingId(jobId);
    }
  }

  async function handleAction(action: "approve" | "reject") {
    const job = reviewQueue[reviewIdx];
    if (!job) return;
    if (action === "approve") {
      addApprovingId(job.id);
      try {
        const ref = await approveJob(job.jobPostingId ?? job.id);
        if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
          Notification.requestPermission();
        }
        if (reviewIdx < reviewQueue.length - 1) {
          setReviewIdx((i) => i + 1);
        } else {
          setReviewQueue([]);
        }
        setLocalJobs((prev) =>
          prev.map((j) => j.id === job.id ? { ...j, state: "tailoring" as const } : j)
        );
        startPolling(ref.async_job_id, job.id, job.title, job.company ?? null);
        return;
      } catch {
        removeApprovingId(job.id);
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

  async function handleRetry(job: HatchJob) {
    addApprovingId(job.id);
    try {
      const ref = await approveJob(job.jobPostingId ?? job.id);
      setLocalJobs((prev) => prev.map((j) => j.id === job.id ? { ...j, state: "tailoring" as const, failureReason: undefined } : j));
      startPolling(ref.async_job_id, job.id, job.title, job.company ?? null);
    } catch {
      removeApprovingId(job.id);
    }
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
  const currentReviewJob = reviewQueue[reviewIdx];
  const currentReviewApproving = currentReviewJob ? approvingIds.has(currentReviewJob.id) : false;
  const approvingMessage = currentReviewApproving
    ? "Preparing your CV and cover letter… this may take a few minutes."
    : "";

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
        approvingIds={[...approvingIds]}
      />
      {readyToApplyWithPkg.map(({ job, pkg }) => (
        <ApplicationReadyCard
          key={job.id}
          job={job}
          pkg={pkg}
          onMarkApplied={handleMarkApplied}
          onRevert={handleRevert}
          onRetry={handleRetry}
        />
      ))}
      {reviewQueue.length > 0 && (
        <ReviewOverlay
          queue={reviewQueue}
          idx={reviewIdx}
          onAction={handleAction}
          onClose={() => { if (!currentReviewApproving) setReviewQueue([]); }}
          isLoading={currentReviewApproving}
          loadingMessage={approvingMessage}
        />
      )}
    </>
  );
}
