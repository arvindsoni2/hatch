"use client";

import { Check } from "lucide-react";
import type { CandidateData } from "./StepAboutYou";
import type { LocaleSummary } from "@/lib/api";

interface ScreenSuccessProps {
  candidate: CandidateData;
  selectedLocale: string;
  locales: LocaleSummary[];
  targetRolesCount: number;
  minRate: number;
  providerName: string;
  enabledBoardsCount: number;
  onDashboard: () => void;
}

export function ScreenSuccess({
  candidate, selectedLocale, locales, targetRolesCount,
  minRate, providerName, enabledBoardsCount, onDashboard,
}: ScreenSuccessProps) {
  const locale = locales.find((l) => l.id === selectedLocale);
  const localeName = locale?.name ?? selectedLocale;
  const localeFlag = locale?.flag ?? "";
  const currency = locale?.currency ?? "";
  const rateType = locale?.default_rate_type ?? "annual";

  return (
    <div className="ob-fadein flex flex-col min-h-full px-5 pt-6 pb-2">
      {/* Pulsing check */}
      <div className="flex flex-col items-center text-center mb-6">
        <div
          className="w-[72px] h-[72px] rounded-full grid place-items-center mb-5 ob-pulse"
          style={{ background: "var(--success-soft)", color: "var(--success)" }}
        >
          <Check size={34} strokeWidth={2.4} />
        </div>

        <h1 className="mb-2 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
          Your search is hatching.
        </h1>

        <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
          Scout is scanning {enabledBoardsCount} {localeName} board{enabledBoardsCount !== 1 ? "s" : ""} right now.
          Matches will land in your inbox. You approve before anything goes out.
        </p>

        {/* Live indicator */}
        <span
          className="inline-flex items-center gap-1.5 text-[12px] text-[var(--success)] px-3 py-1.5 rounded-full"
          style={{ background: "var(--success-soft)" }}
        >
          <span className="w-[7px] h-[7px] rounded-full ob-blink" style={{ background: "var(--success)" }} />
          Scout agent running
        </span>
      </div>

      {/* Summary */}
      <div className="border border-[var(--border)] rounded-[var(--r-card,10px)] overflow-hidden mb-6">
        {[
          { k: "Profile",  v: `${candidate.name || "Not provided"} - ${candidate.title || "Not provided"}` },
          { k: "Market",   v: `${localeFlag} ${localeName} - ${targetRolesCount} title${targetRolesCount !== 1 ? "s" : ""}` },
          { k: "Pay",      v: minRate ? `${currency} ${minRate}+ ${rateType}` : "Not provided" },
          { k: "Engine",   v: providerName },
        ].map(({ k, v }) => (
          <div key={k} className="flex items-start gap-3 px-3.5 py-3 border-b border-[var(--border)] last:border-b-0">
            <span className="text-[12px] text-[var(--text-muted)] w-[88px] flex-shrink-0 pt-px">{k}</span>
            <span className="text-[13px] font-[500] text-[var(--text)] flex-1">{v}</span>
          </div>
        ))}
      </div>

      {/* CTA */}
      <button
        type="button"
        onClick={onDashboard}
        className="w-full py-3 rounded-[var(--r-btn,8px)] text-[14px] font-[600] text-[var(--on-accent)] flex items-center justify-center gap-2 transition-colors hover:opacity-90"
        style={{ background: "var(--accent)" }}
      >
        Go to dashboard →
      </button>
    </div>
  );
}
