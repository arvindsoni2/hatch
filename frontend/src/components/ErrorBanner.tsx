"use client";

import { AlertTriangle, XCircle, Inbox } from "lucide-react";
import Link from "next/link";

// ── Error state types ────────────────────────────────────────────────────────

export type ErrorBannerVariant =
  | "api_key_invalid"
  | "scraper_failure"
  | "no_matching_jobs";

interface ErrorBannerProps {
  variant: ErrorBannerVariant;
  /** Override the default message body. */
  message?: string;
  /** Called when the user dismisses the banner (if undefined, no dismiss button). */
  onDismiss?: () => void;
}

// ── Config per variant ───────────────────────────────────────────────────────

const CONFIG: Record<
  ErrorBannerVariant,
  {
    icon: React.ReactNode;
    title: string;
    defaultMessage: string;
    cta?: { label: string; href: string };
    colorClass: string;
    borderClass: string;
    iconClass: string;
  }
> = {
  api_key_invalid: {
    icon: <XCircle className="h-5 w-5 shrink-0" />,
    title: "AI provider key invalid",
    defaultMessage:
      "Hatch couldn't reach your configured LLM provider. Scoring and tailoring will be paused until the key is fixed.",
    cta: { label: "Fix in Settings", href: "/settings" },
    colorClass: "bg-red-50 text-red-800",
    borderClass: "border-red-200",
    iconClass: "text-red-500",
  },
  scraper_failure: {
    icon: <AlertTriangle className="h-5 w-5 shrink-0" />,
    title: "Scraper error",
    defaultMessage:
      "One or more scrapers failed on the last run. New jobs may be missing. Check the agent log for details.",
    cta: { label: "View agent status", href: "/settings" },
    colorClass: "bg-amber-50 text-amber-800",
    borderClass: "border-amber-200",
    iconClass: "text-amber-500",
  },
  no_matching_jobs: {
    icon: <Inbox className="h-5 w-5 shrink-0" />,
    title: "No high-match jobs found",
    defaultMessage:
      "None of the recently scraped jobs cleared your match threshold. Try lowering the threshold or broadening your search.",
    cta: { label: "Adjust in Settings", href: "/settings" },
    colorClass: "bg-slate-50 text-slate-700",
    borderClass: "border-slate-200",
    iconClass: "text-slate-400",
  },
};

// ── Component ────────────────────────────────────────────────────────────────

export function ErrorBanner({ variant, message, onDismiss }: ErrorBannerProps) {
  const cfg = CONFIG[variant];

  return (
    <div className={`flex items-start gap-3 rounded-xl border p-4 ${cfg.colorClass} ${cfg.borderClass}`}>
      <span className={cfg.iconClass}>{cfg.icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold">{cfg.title}</p>
        <p className="mt-0.5 text-sm opacity-80">{message ?? cfg.defaultMessage}</p>
        {cfg.cta && (
          <Link
            href={cfg.cta.href}
            className="mt-2 inline-block text-xs font-medium underline underline-offset-2 hover:opacity-70"
          >
            {cfg.cta.label} →
          </Link>
        )}
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="text-current opacity-50 hover:opacity-100 transition-opacity shrink-0"
          aria-label="Dismiss"
        >
          <XCircle className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
