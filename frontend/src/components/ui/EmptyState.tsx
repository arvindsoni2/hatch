"use client";

import { FileText, Search, Zap, Settings, RefreshCw } from "lucide-react";

export type EmptyStateCause =
  | "no-profile"       // user hasn't completed onboarding
  | "no-scrape"        // profile set but scraper hasn't run yet
  | "scraped-unscored" // jobs scraped but AI hasn't scored yet
  | "no-results"       // scored but nothing matches filters
  | "generic";

interface EmptyStateProps {
  cause?: EmptyStateCause;
  onAction?: () => void;
  secondaryHref?: string;
  secondaryLabel?: string;
  className?: string;
}

const VARIANTS: Record<
  EmptyStateCause,
  { icon: React.ReactNode; title: string; body: string; action?: string }
> = {
  "no-profile": {
    icon: <Settings className="h-10 w-10 text-[var(--text-dim)]" />,
    title: "Set up your profile first",
    body: "Hatch needs your target roles, location, and rate before Scout can search for matches.",
    action: "Go to Settings",
  },
  "no-scrape": {
    icon: <Search className="h-10 w-10 text-[var(--text-dim)]" />,
    title: "No jobs yet",
    body: "Run Job Scout to fetch roles that match your profile.",
  },
  "scraped-unscored": {
    icon: <Zap className="h-10 w-10 text-[var(--text-dim)]" />,
    title: "Scoring in progress",
    body: "Jobs have been fetched. The AI scorer is working through them. Check back in a few minutes.",
    action: "Refresh",
  },
  "no-results": {
    icon: <FileText className="h-10 w-10 text-[var(--text-dim)]" />,
    title: "No jobs match your filters",
    body: "Try widening your rate range, adding more roles, or clearing filters to see all scraped listings.",
    action: "Clear filters",
  },
  generic: {
    icon: <RefreshCw className="h-10 w-10 text-[var(--text-dim)]" />,
    title: "Nothing here yet",
    body: "Check back soon or trigger a manual scrape from the Today page.",
  },
};

export function EmptyState({
  cause = "generic",
  onAction,
  secondaryHref,
  secondaryLabel,
  className = "",
}: EmptyStateProps) {
  const v = VARIANTS[cause];
  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 rounded-[var(--r-card,12px)] border border-[var(--border)] bg-[var(--surface-2)] py-16 px-8 text-center ${className}`}
      role="status"
      aria-label={v.title}
      aria-live="polite"
    >
      <span aria-hidden="true">{v.icon}</span>
      <div className="space-y-1">
        <p className="text-[15px] font-[550] text-[var(--text)]">{v.title}</p>
        <p className="text-[13px] text-[var(--text-dim)] max-w-[320px]">{v.body}</p>
      </div>
      {v.action && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-2 px-4 py-2 rounded-[var(--r-field,8px)] bg-[var(--accent)] text-white text-[13px] font-[550] hover:opacity-90 transition-opacity"
        >
          {v.action}
        </button>
      )}
      {secondaryHref && secondaryLabel && (
        <a
          href={secondaryHref}
          className="text-[13px] font-[550] text-[var(--accent)] underline-offset-4 hover:underline"
        >
          {secondaryLabel}
        </a>
      )}
    </div>
  );
}
