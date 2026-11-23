"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { BriefSection } from "@/components/coach/readiness/BriefSection";
import { formatInterviewTime } from "@/lib/formatInterviewTime";
import { useDisplayTimeZone } from "@/lib/useDisplayTimeZone";
import {
  fetchInterviewBrief,
  retryInterviewBriefTips,
  type InterviewBriefData,
} from "@/lib/coachReadinessApi";

const ENHANCEMENT_LABEL: Record<string, string> = {
  none: "Ready",
  enhancing: "Adding tips",
  current: "Ready · tips added",
  outdated: "Tips out of date",
  unavailable: "Tips unavailable",
};

export function InterviewBrief({ roundId }: { roundId: string }) {
  const timeZone = useDisplayTimeZone();
  const [brief, setBrief] = useState<InterviewBriefData | null>(null);
  const [error, setError] = useState(false);

  const load = () => {
    setError(false);
    fetchInterviewBrief(roundId)
      .then(setBrief)
      .catch(() => setError(true));
  };

  useEffect(load, [roundId]);

  if (error) return <p className="text-sm text-[var(--danger)]" role="alert">Brief unavailable.</p>;
  if (!brief) return <div className="h-24 animate-pulse rounded-[var(--radius-card)] bg-[var(--surface-3)]" />;

  const startsAt = brief.header.starts_at
    ? formatInterviewTime(brief.header.starts_at, timeZone)
    : "No interview date";

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)]">
            {brief.header.round_type.replaceAll("_", " ")} interview with {brief.header.company || "the company"}
          </h1>
          <p className="mt-1 text-sm text-[var(--text-dim)]">{startsAt}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge tone={brief.enhancement.state === "unavailable" ? "neutral" : "info"}>
            {ENHANCEMENT_LABEL[brief.enhancement.state] ?? "Ready"}
          </StatusBadge>
          {brief.enhancement.state === "unavailable" ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() =>
                void retryInterviewBriefTips(roundId).then(setBrief).catch(() => setError(true))
              }
            >
              Try again
            </Button>
          ) : null}
          <Button type="button" variant="outline" size="sm" onClick={() => window.print()}>
            Print brief
          </Button>
        </div>
      </div>

      <BriefSection title="Likely questions">
        {brief.likely_questions.length === 0 ? <p>No likely questions yet.</p> : (
          <ol className="list-decimal space-y-1 pl-4">
            {brief.likely_questions.map((item) => <li key={item.id}>{item.text}</li>)}
          </ol>
        )}
      </BriefSection>
      <BriefSection title="Your best stories">
        {brief.stories.length === 0 ? <p>No ready stories yet.</p> : (
          <ul className="space-y-2">
            {brief.stories.map((item) => (
              <li key={item.story_id}>
                <strong className="text-[var(--text)]">{item.title}</strong>
                <p className="text-xs">{item.competencies.join(" · ")}</p>
              </li>
            ))}
          </ul>
        )}
      </BriefSection>
      <BriefSection title="Watch-outs">
        {brief.watch_outs.length === 0 ? <p>Practise for this role to get watch-outs</p> : (
          <ul className="list-disc pl-4">
            {brief.watch_outs.map((item) => <li key={item.fingerprint}>{item.dimension.replaceAll("_", " ")}</li>)}
          </ul>
        )}
      </BriefSection>
      <BriefSection title="Gaps">
        {brief.gaps.length === 0 ? <p>No story gaps found.</p> : (
          <ul className="space-y-1">{brief.gaps.map((item) => (
            <li key={item.competency}>{item.competency} — <a className="text-[var(--accent)]" href={`/coach/stories/new?competency=${encodeURIComponent(item.competency)}`}>Draft a story</a></li>
          ))}</ul>
        )}
      </BriefSection>
      <BriefSection title="Questions to ask them">
        <ul className="list-disc pl-4">{brief.ask_them.map((item) => <li key={item}>{item}</li>)}</ul>
      </BriefSection>
      <BriefSection title="Logistics">
        <dl className="grid gap-1">
          <div><dt className="inline font-medium text-[var(--text)]">Time: </dt><dd className="inline">{startsAt}</dd></div>
          <div><dt className="inline font-medium text-[var(--text)]">Duration: </dt><dd className="inline">{brief.header.duration_minutes ?? 60} minutes</dd></div>
          {brief.header.location ? <div><dt className="inline font-medium text-[var(--text)]">Location: </dt><dd className="inline">{brief.header.location}</dd></div> : null}
          {brief.header.interviewer ? <div><dt className="inline font-medium text-[var(--text)]">Interviewer: </dt><dd className="inline">{brief.header.interviewer}</dd></div> : null}
        </dl>
      </BriefSection>
      <style jsx global>{`
        @media print {
          body * { visibility: hidden; }
          .brief-section, .brief-section * { visibility: visible; }
          .brief-section { break-inside: avoid; border: 0; padding: 0; }
          nav, button { display: none !important; }
        }
      `}</style>
    </div>
  );
}
