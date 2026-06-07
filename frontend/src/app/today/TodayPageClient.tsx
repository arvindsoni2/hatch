"use client";
import { useState } from "react";
import { TodayScreen } from "@/components/hatch/screens/TodayScreen";
import { ReviewOverlay } from "@/components/hatch/ReviewOverlay";
import { ApplicationReadyCard } from "@/components/hatch/ApplicationReadyCard";
import { AgentActivityPanel } from "@/components/hatch/AgentActivityPanel";
import { approveJob, rejectApplication, markApplied, revertApplication } from "@/lib/api";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";
import type { ApplicationPackage, AgentPerformance } from "@/lib/api";

interface UpcomingInterview {
  scheduledAt: string;
  title: string;
  company: string;
  daysUntil: number;
}

interface TodayPageClientProps {
  jobs: HatchJob[];
  funnel: { scout: number; scorer: number; tailor: number; coach: number };
  transit?: { scout_to_scorer: number; scorer_to_tailor: number; tailor_to_coach: number };
  profileName?: string;
  followUpCount?: number;
  agentPerf?: AgentPerformance | null;
  upcomingInterview?: UpcomingInterview | null;
}

export function TodayPageClient({ jobs, funnel, transit, profileName, followUpCount, agentPerf, upcomingInterview }: TodayPageClientProps) {
  const [localJobs, setLocalJobs] = useState<HatchJob[]>(jobs);
  const [reviewQueue, setReviewQueue] = useState<HatchJob[]>([]);
  const [reviewIdx, setReviewIdx] = useState(0);
  const [packages, setPackages] = useState<Record<string, ApplicationPackage>>({});
  const [approving, setApproving] = useState(false);

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

  const avgMatch = localJobs.length > 0
    ? Math.round(localJobs.reduce((sum, j) => sum + j.score, 0) / localJobs.length * 100)
    : undefined;

  return (
    <>
      {/* Desktop 2-col: Today content left, Agent activity right */}
      <div className="flex gap-6 items-start">
        <div className="flex-1 min-w-0">
          <TodayScreen
            jobs={localJobs}
            funnel={funnel}
            transit={transit}
            profileName={profileName ?? "there"}
            followUpCount={followUpCount}
            upcomingInterview={upcomingInterview ?? null}
            onReview={(ids) => {
              const q = localJobs.filter((j) => ids.includes(j.id));
              setReviewQueue(q);
              setReviewIdx(0);
            }}
            onMarkApplied={handleMarkApplied}
            onRevert={handleRevert}
          />
        </div>
        {/* Agent activity panel — desktop right column, mobile hidden (shows below) */}
        <div className="hidden lg:block shrink-0" style={{ width: 272, paddingTop: 0 }}>
          <AgentActivityPanel
            initialData={agentPerf ?? null}
            funnel={funnel}
            transit={transit}
            avgMatch={avgMatch}
          />
        </div>
      </div>
      {/* Agent activity — mobile only, below main content */}
      <div className="lg:hidden mt-6">
        <AgentActivityPanel
          initialData={agentPerf ?? null}
          funnel={funnel}
          transit={transit}
          avgMatch={avgMatch}
        />
      </div>
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
