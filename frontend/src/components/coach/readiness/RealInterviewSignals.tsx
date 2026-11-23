"use client";

import Link from "next/link";
import { Mic, Target } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import type { CoverageOverviewSignal } from "@/lib/coachReadinessApi";

export function RealInterviewSignals({ signals }: { signals: CoverageOverviewSignal[] }) {
  return (
    <SectionCard
      title="From your real interviews"
      description="A signal needs at least two rounds"
    >
      {signals.length === 0 ? (
        <p className="m-0 text-sm text-[var(--text-dim)]">
          No signals yet. They appear once a competency comes up in two saved debriefs.
        </p>
      ) : (
        <ul className="space-y-2">
          {signals.map((signal) => (
            <li
              key={signal.fingerprint}
              className="flex flex-wrap items-center justify-between gap-2 rounded-[var(--radius-card)] bg-[var(--surface-2)] p-3"
            >
              <div>
                <p className="m-0 text-sm font-semibold text-[var(--text)]">{signal.display}</p>
                <p className="mb-0 mt-1 flex flex-wrap items-center gap-3 text-xs text-[var(--text-dim)]">
                  <span className="inline-flex items-center gap-1">
                    <Mic aria-hidden="true" className="h-3.5 w-3.5" />
                    Asked in {signal.asked_rounds} real interview
                    {signal.asked_rounds === 1 ? "" : "s"}
                  </span>
                  {signal.low_rating_debriefs >= 2 ? (
                    <span className="inline-flex items-center gap-1 text-[var(--warning)]">
                      <Target aria-hidden="true" className="h-3.5 w-3.5" />
                      You rated yourself 2 or less in {signal.low_rating_debriefs} debrief
                      {signal.low_rating_debriefs === 1 ? "" : "s"}
                    </span>
                  ) : null}
                </p>
              </div>
              <a
                className={buttonVariants({ variant: "outline", size: "sm" })}
                href={`/coach/stories/new?competency=${encodeURIComponent(signal.display)}`}
              >
                Draft a story
              </a>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
