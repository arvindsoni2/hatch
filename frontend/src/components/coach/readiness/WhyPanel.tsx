"use client";

import type { PatternWhy } from "@/lib/coachReadinessApi";

const LEVEL: Record<string, string> = {
  needs_work: "Needs work",
  developing: "Developing",
  interview_ready: "Interview ready",
  strong: "Strong",
  not_assessed: "Not assessed",
};

const DIFFICULTY: Record<string, string> = {
  supportive: "Supportive",
  realistic: "Realistic",
  challenging: "Challenging",
};

function formatPatternDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(value));
}

export function WhyPanel({ why }: { why: PatternWhy }) {
  return (
    <div className="mt-4 rounded-[var(--radius-control)] bg-[var(--surface)] p-3">
      <h4 className="text-xs font-semibold text-[var(--text)]">Why?</h4>
      <ul className="mt-2 space-y-1.5">
        {why.pattern.supporting.map((item) => (
          <li
            key={item.session_id}
            className="flex flex-wrap items-center justify-between gap-2 text-xs text-[var(--text-dim)]"
          >
            <span>{formatPatternDate(item.completed_at)}</span>
            <span>{item.difficulty ? DIFFICULTY[item.difficulty] ?? item.difficulty : "Difficulty unknown"}</span>
            <span className="font-medium text-[var(--text)]">
              {LEVEL[item.level] ?? item.level}
            </span>
          </li>
        ))}
      </ul>
      {why.excerpts.length > 0 ? (
        <div className="mt-3 space-y-2">
          {why.excerpts.map((excerpt) => (
            <blockquote
              key={`${excerpt.session_id}-${excerpt.text}`}
              className="border-l-2 border-[var(--accent)] pl-3 text-sm text-[var(--text-dim)]"
            >
              “{excerpt.text}”
              <span className="mt-1 block text-xs text-[var(--text-muted)]">
                From your {formatPatternDate(excerpt.completed_at)} report
              </span>
            </blockquote>
          ))}
        </div>
      ) : null}
    </div>
  );
}
