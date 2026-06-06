"use client";
import { useState } from "react";
import { StreamScreen } from "@/components/hatch/screens/StreamScreen";
import { ReviewOverlay } from "@/components/hatch/ReviewOverlay";
import { approveApplication, rejectApplication } from "@/lib/api";
import type { HatchJob } from "@/components/hatch/screens/TodayScreen";

interface StreamPageClientProps {
  jobs: HatchJob[];
}

export function StreamPageClient({ jobs }: StreamPageClientProps) {
  const [reviewQueue, setReviewQueue] = useState<HatchJob[]>([]);
  const [reviewIdx, setReviewIdx] = useState(0);

  async function handleAction(action: "approve" | "reject") {
    const job = reviewQueue[reviewIdx];
    if (!job) return;
    if (action === "approve") await approveApplication(job.id).catch(() => {});
    else await rejectApplication(job.id).catch(() => {});
    if (reviewIdx < reviewQueue.length - 1) {
      setReviewIdx((i) => i + 1);
    } else {
      setReviewQueue([]);
    }
  }

  return (
    <>
      <StreamScreen
        jobs={jobs}
        onReview={(ids) => {
          const q = jobs.filter((j) => ids.includes(j.id));
          setReviewQueue(q);
          setReviewIdx(0);
        }}
        onApprove={async (id) => {
          await approveApplication(id).catch(() => {});
        }}
      />
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
