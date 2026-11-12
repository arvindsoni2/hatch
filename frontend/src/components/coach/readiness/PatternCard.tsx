"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  fetchPatternWhy,
  type Pattern,
  type PatternWhy,
} from "@/lib/coachReadinessApi";
import { WhyPanel } from "@/components/coach/readiness/WhyPanel";

const KIND: Record<
  Pattern["kind"],
  { label: string; tone: "neutral" | "success" | "warning"; icon?: string }
> = {
  focus: { label: "Focus area suggestion", tone: "warning", icon: "target" },
  strength: { label: "Strength", tone: "success", icon: "checkCircle" },
  mixed: { label: "Mixed results", tone: "neutral" },
  forming: { label: "Needs more practice", tone: "neutral" },
};

const TREND: Record<string, string> = {
  improving: "Improving",
  easier_difficulty: "Changed at an easier difficulty",
  getting_weaker: "Getting weaker",
  harder_difficulty: "Lower at a harder difficulty",
};

const LEVEL: Record<string, string> = {
  needs_work: "Needs work",
  developing: "Developing",
  interview_ready: "Interview ready",
  strong: "Strong",
  not_assessed: "Not assessed",
};

export function patternSummary(pattern: Pattern): string {
  const levels = pattern.supporting.map((item) => LEVEL[item.level] ?? item.level);
  if (pattern.kind === "forming") {
    return `${levels.join(", ")} in 1 of 2 sessions so far. Practise once more to see a pattern.`;
  }
  return `${levels.join(", then ")} in ${levels.length} of the last ${levels.length} sessions.`;
}

export function formatPatternDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(value));
}

export function PatternCard({
  pattern,
  onDismiss,
  onUndo,
  onWorkOnThis,
}: {
  pattern: Pattern;
  onDismiss?: (fingerprint: string) => void;
  onUndo?: (fingerprint: string) => void;
  onWorkOnThis?: (pattern: Pattern) => void;
}) {
  const [why, setWhy] = useState<PatternWhy | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const [whyError, setWhyError] = useState(false);
  const kind = KIND[pattern.kind];

  const toggleWhy = async () => {
    if (!pattern.stale && !why && !whyError) {
      try {
        setWhy(await fetchPatternWhy(pattern.fingerprint));
      } catch {
        setWhyError(true);
      }
    }
    setWhyOpen((open) => !open);
  };

  return (
    <article
      className={`rounded-[var(--radius-card)] border p-4 ${
        pattern.kind === "forming"
          ? "border-dashed border-[var(--border)]"
          : "border-[var(--border)] bg-[var(--surface-2)]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold capitalize text-[var(--text)]">
            {pattern.dimension.replaceAll("_", " ")}
          </h3>
          <StatusBadge tone={kind.tone} icon={kind.icon ? <Icon name={kind.icon} size={14} /> : undefined}>
            {kind.label}
          </StatusBadge>
          {pattern.trend_label === "improving" ? (
            <StatusBadge tone="info" icon={<Icon name="trending" size={14} />}>
              {TREND.improving}
            </StatusBadge>
          ) : pattern.trend_label ? (
            <span className="text-xs text-[var(--text-dim)]">
              {TREND[pattern.trend_label]}
            </span>
          ) : null}
          {pattern.stale ? <StatusBadge tone="neutral">Older</StatusBadge> : null}
        </div>
        <div className="ml-auto flex items-center gap-1">
          {!pattern.stale ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-expanded={whyOpen}
              onClick={() => void toggleWhy()}
            >
              Why?
            </Button>
          ) : null}
          {!pattern.dismissed ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Dismiss this pattern"
              onClick={() => onDismiss?.(pattern.fingerprint)}
            >
              <Icon name="x" size={16} />
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onUndo?.(pattern.fingerprint)}
            >
              Undo dismissal
            </Button>
          )}
        </div>
      </div>

      <p className="mt-2 text-sm text-[var(--text-dim)]">{patternSummary(pattern)}</p>
      {pattern.seen_again ? (
        <p className="mt-1 text-xs text-[var(--text-dim)]">
          Seen again since you dismissed it
        </p>
      ) : null}
      {pattern.kind === "focus" && !pattern.stale && !pattern.dismissed ? (
        <div className="mt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onWorkOnThis?.(pattern)}
          >
            Work on this
          </Button>
        </div>
      ) : null}

      {whyOpen ? (
        why ? (
          <WhyPanel why={why} />
        ) : (
          <p className="mt-3 text-sm text-[var(--text-dim)]" role="status">
            {whyError ? "Why is unavailable." : "Loading evidence…"}
          </p>
        )
      ) : null}
    </article>
  );
}
