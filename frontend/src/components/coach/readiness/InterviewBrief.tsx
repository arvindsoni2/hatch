"use client";

import { useEffect, useRef, useState } from "react";
import { Mic, Target, TriangleAlert } from "lucide-react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { BriefSection } from "@/components/coach/readiness/BriefSection";
import { formatInterviewClock, formatInterviewTime, parseInterviewTime } from "@/lib/formatInterviewTime";
import { useDisplayTimeZone } from "@/lib/useDisplayTimeZone";
import {
  fetchInterviewBrief,
  retryInterviewBriefTips,
  type InterviewBriefData,
} from "@/lib/coachReadinessApi";

const ENHANCEMENT_BADGE: Record<string, { tone: "neutral" | "info" | "success" | "warning"; label: string }> = {
  none: { tone: "neutral", label: "Ready" },
  enhancing: { tone: "info", label: "Adding tips" },
  current: { tone: "success", label: "Ready · tips added" },
  outdated: { tone: "warning", label: "Tips out of date" },
  unavailable: { tone: "neutral", label: "Tips unavailable" },
};

const POLL_MS = 2_000;

function sentenceCase(value: string): string {
  const text = value.replaceAll("_", " ");
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

export function InterviewBrief({ roundId }: { roundId: string }) {
  const timeZone = useDisplayTimeZone();
  const [brief, setBrief] = useState<InterviewBriefData | null>(null);
  const [error, setError] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const load = () => {
    setError(false);
    fetchInterviewBrief(roundId)
      .then((data) => { if (mounted.current) setBrief(data); })
      .catch(() => { if (mounted.current) setError(true); });
  };

  useEffect(load, [roundId]);

  const enhancement = brief?.enhancement.state;
  useEffect(() => {
    if (!brief || brief.state === "archived") return;
    if (enhancement !== "enhancing" && enhancement !== "outdated") return;
    const id = setInterval(() => {
      void fetchInterviewBrief(roundId)
        .then((data) => { if (mounted.current) setBrief(data); })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [brief, enhancement, roundId]);

  if (error) return <p className="text-sm text-[var(--danger)]" role="alert">Brief unavailable.</p>;
  if (!brief) return <div className="h-24 animate-pulse rounded-[var(--radius-card)] bg-[var(--surface-3)]" />;

  const archived = brief.state === "archived";
  const badge = archived
    ? { tone: "neutral" as const, label: "Archived" }
    : ENHANCEMENT_BADGE[brief.enhancement.state] ?? ENHANCEMENT_BADGE.none;
  const enhancing = !archived && brief.enhancement.state === "enhancing";
  const when = brief.header.starts_at
    ? `${formatInterviewTime(brief.header.starts_at, timeZone)}${
        brief.header.duration_minutes
          ? ` to ${formatInterviewClock(
              new Date(parseInterviewTime(brief.header.starts_at).getTime() + brief.header.duration_minutes * 60_000),
              timeZone,
            )}`
          : ""
      }`
    : "No interview date";

  return (
    <div className="space-y-3">
      <div className="brief-header flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)] sm:text-2xl">
            {sentenceCase(brief.header.round_type)} interview with {brief.header.company || "the company"}
          </h1>
          <p className="mt-1 text-sm text-[var(--text-dim)]">
            {[brief.header.role || null, when, brief.header.duration_minutes ? `${brief.header.duration_minutes} min` : null, brief.header.interviewer]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => window.print()}>
          Print brief
        </Button>
      </div>

      <div className="brief-status flex flex-wrap items-center gap-2 text-sm text-[var(--text-dim)]">
        <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
        {brief.enhancement.state === "unavailable" && !archived ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() =>
              void retryInterviewBriefTips(roundId).then((data) => {
                if (mounted.current) setBrief(data);
              }).catch(() => { if (mounted.current) setError(true); })
            }
          >
            Try again
          </Button>
        ) : null}
        <p className="m-0">
          {brief.enhancement.state === "current"
            ? "Built from your stories, this job description and your practice. Tips added by your local model."
            : "Built from your stories, this job description and your practice."}
        </p>
      </div>

      <div className="brief-grid grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          <BriefSection title="Likely questions" note="From your Question Bank and practice">
            {brief.likely_questions.length === 0 ? <p>No likely questions yet.</p> : (
              <ol className="list-decimal space-y-2 pl-4">
                {brief.likely_questions.map((item) => (
                  <li key={item.id} className="marker:text-[var(--text-dim)]">
                    <p className="m-0 text-[var(--text)]">{item.text}</p>
                    <p className="m-0 text-xs text-[var(--text-dim)]">
                      {item.source === "question_bank" ? "Question Bank" : "Your last practice session for this application"}
                    </p>
                    <a
                      className="text-sm font-medium text-[var(--accent)] underline-offset-4 hover:underline"
                      href={item.source === "question_bank" ? "/prep/question-bank" : "/coach"}
                    >
                      {item.source === "question_bank" ? "Open answer" : "Draft answer"}
                    </a>
                  </li>
                ))}
              </ol>
            )}
          </BriefSection>
          <BriefSection title="Your best stories" note="Matched to what this role asks for">
            {brief.stories.length === 0 ? <p>No ready stories yet.</p> : (
              <ul className="space-y-2">
                {brief.stories.map((item) => (
                  <li key={item.story_id} className="rounded-[var(--radius-card)] bg-[var(--surface-2)] p-3">
                    <div className="flex items-start justify-between gap-2">
                      <strong className="text-[var(--text)]">{item.title}</strong>
                      <StatusBadge tone="success">Ready story</StatusBadge>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      <span className="text-xs text-[var(--text-dim)]">Covers</span>
                      {item.competencies.map((competency) => (
                        <span key={competency} className="rounded-full bg-[var(--surface-3)] px-2 py-0.5 text-xs text-[var(--text)]">
                          {competency}
                        </span>
                      ))}
                    </div>
                    <div aria-live="polite">
                      {enhancing ? (
                        <div className="mt-2 space-y-1" data-testid="tips-skeleton">
                          <Skeleton className="h-3 w-3/4" />
                          <Skeleton className="h-3 w-1/2" />
                        </div>
                      ) : item.talking_point ? (
                        <p className="mt-2 mb-0 text-sm text-[var(--text)]">{item.talking_point}</p>
                      ) : null}
                    </div>
                    {item.talking_point && !enhancing ? (
                      <p className="mt-1 mb-0 text-xs text-[var(--text-dim)]">
                        Talking point written by your local model and checked against this story.
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </BriefSection>
        </div>

        <div className="space-y-3">
          <BriefSection title="Watch-outs">
            {brief.watch_outs.length === 0 ? <p>Practise for this role to get watch-outs</p> : (
              <ul className="space-y-2">
                {brief.watch_outs.map((item) => (
                  <li key={item.fingerprint}>
                    <p className="m-0 flex items-center gap-1.5 text-sm font-medium text-[var(--text)]">
                      <Target aria-hidden="true" className="h-4 w-4 text-[var(--warning)]" />
                      {sentenceCase(item.dimension)}
                    </p>
                    <p className="m-0 text-xs text-[var(--text-dim)]">
                      {item.source === "real_interview" ? "From your real interviews" : "From your practice"}
                    </p>
                    <div aria-live="polite">
                      {enhancing ? (
                        <Skeleton className="mt-1 h-3 w-2/3" data-testid="tips-skeleton" />
                      ) : item.sentence ? (
                        <p className="m-0 text-sm text-[var(--text)]">
                          <Mic aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 text-[var(--text-dim)]" />
                          {item.sentence}
                        </p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </BriefSection>
          <BriefSection title="Gaps">
            <p className="m-0 text-sm text-[var(--text-dim)]">This role asks for these and you have no story yet.</p>
            {brief.gaps.length === 0 ? <p className="mt-2 mb-0 text-sm">No story gaps found.</p> : (
              <ul className="mt-2 space-y-2">
                {brief.gaps.map((item) => (
                  <li key={item.competency} className="flex flex-wrap items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-sm text-[var(--text)]">
                      {item.competency}
                      <StatusBadge tone="warning">
                        <TriangleAlert aria-hidden="true" className="h-3 w-3" />
                        No story yet
                      </StatusBadge>
                    </span>
                    <a
                      className={buttonVariants({ variant: "outline", size: "sm" })}
                      href={`/coach/stories/new?competency=${encodeURIComponent(item.competency)}`}
                    >
                      Draft a story
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </BriefSection>
          <BriefSection title="Questions to ask them" note="From your company research or this round type">
            <ul className="list-disc space-y-1 pl-4">
              {brief.ask_them.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </BriefSection>
          <BriefSection title="Logistics">
            <dl className="grid gap-1">
              <div><dt className="inline font-medium text-[var(--text)]">When: </dt><dd className="inline">{when}</dd></div>
              <div><dt className="inline font-medium text-[var(--text)]">Where: </dt><dd className="inline">{brief.header.location || "Not set yet"}</dd></div>
              <div><dt className="inline font-medium text-[var(--text)]">With: </dt><dd className="inline">{brief.header.interviewer || "Not set yet"}</dd></div>
              <div><dt className="inline font-medium text-[var(--text)]">Round: </dt><dd className="inline">{sentenceCase(brief.header.round_type)}</dd></div>
            </dl>
          </BriefSection>
        </div>
      </div>
      <style jsx global>{`
        @media print {
          body * { visibility: hidden; }
          .brief-header, .brief-header *,
          .brief-section, .brief-section * { visibility: visible; }
          .brief-header, .brief-section { break-inside: avoid; }
          .brief-section { border: 0; padding: 0; }
          .brief-status, nav, button { display: none !important; }
          .brief-grid { display: block; }
        }
      `}</style>
    </div>
  );
}
