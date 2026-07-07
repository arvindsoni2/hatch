"use client";

import { AlertTriangle, Loader2, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CandidateData } from "./StepAboutYou";
import type { SearchData, CompensationData, LocationData } from "./StepJobSearch";
import type { DomainsData, SkillsData } from "./StepSkills";
import type { LLMData } from "./StepAIProvider";
import type { LocaleSummary } from "@/lib/api";

interface StepReviewProps {
  candidate: CandidateData;
  selectedLocale: string;
  locales: LocaleSummary[];
  search: SearchData;
  locations: LocationData[];
  compensation: CompensationData;
  legalPreferences: Record<string, string>;
  skills: SkillsData;
  domains: DomainsData;
  llm: LLMData;
  enabledBoardsCount: number;
  totalBoardsCount: number;
  warnings: string[];
  error: string;
  saving: boolean;
  onFinish: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[112px_1fr] gap-3 py-2.5 text-sm">
      <dt className="text-[var(--text-muted)]">{label}</dt>
      <dd className="min-w-0 text-right font-medium text-[var(--text)] break-words">{value}</dd>
    </div>
  );
}

export function StepReview({
  candidate, selectedLocale, locales, search, locations, compensation,
  legalPreferences, skills, domains, llm, enabledBoardsCount, totalBoardsCount,
  warnings, error, saving, onFinish,
}: StepReviewProps) {
  const localeName = locales.find((locale) => locale.id === selectedLocale)?.name ?? selectedLocale;
  const location = locations[0];
  const rateDisplay = compensation.min_rate
    ? `${compensation.currency} ${compensation.min_rate}-${compensation.max_rate || "flexible"} / ${compensation.rate_type}`
    : "Not provided";
  const eligibility = legalPreferences.work_authorization?.replaceAll("_", " ") ?? "Prefer not to say";

  return (
    <section className="ob-fadein px-5 pb-5" aria-labelledby="review-title">
      <p className="mb-2 text-[12px] font-semibold text-[var(--text-muted)]">Review</p>
      <h1
        id="review-title"
        className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]"
      >
        Review your setup
      </h1>
      <p className="mb-5 text-[14px] leading-relaxed text-[var(--text-dim)]">
        Check what Hatch will save. You can go back to change anything before starting.
      </p>

      {warnings.length > 0 && (
        <section
          className="mb-5 rounded-[var(--radius-card)] border border-[var(--warning)]/40 bg-[var(--warning-soft)] p-4"
          aria-labelledby="review-warnings"
        >
          <div className="flex items-center gap-2 text-[var(--warning)]">
            <AlertTriangle size={17} aria-hidden="true" />
            <h2 id="review-warnings" className="text-sm font-semibold">Before you save</h2>
          </div>
          <ul className="mt-2 space-y-1.5 pl-6 text-[13px] leading-relaxed text-[var(--text-dim)]">
            {warnings.map((warning) => <li key={warning} className="list-disc">{warning}</li>)}
          </ul>
        </section>
      )}

      <dl className="divide-y divide-[var(--border)] rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] px-4">
        <Row label="Profile" value={`${candidate.name} - ${candidate.title}`} />
        <Row label="Market" value={localeName} />
        <Row label="Target roles" value={search.target_roles.join(", ") || "Add later"} />
        <Row
          label="Location"
          value={`${location?.city || "Not provided"} - ${location?.remote_preference || "Not provided"}`}
        />
        <Row label="Pay" value={rateDisplay} />
        <Row label="Eligibility" value={eligibility} />
        <Row label="Core skills" value={skills.primary.join(", ") || "Add later"} />
        <Row label="Domains" value={domains.preferred.join(", ") || "No preference"} />
        <Row label="AI provider" value={`${llm.provider} - ${llm.primary_model}`} />
        <Row label="Job boards" value={`${enabledBoardsCount} of ${totalBoardsCount} enabled`} />
      </dl>

      <p className="mt-4 text-[12px] leading-relaxed text-[var(--text-muted)]">
        Hatch saves this profile to your local installation. Progress saved in this browser excludes
        your name, location, pay, eligibility, and proof points.
      </p>

      {error && (
        <p
          className="mt-4 rounded-[var(--radius-control)] border border-[var(--danger)]/40 bg-[var(--danger-soft)] p-3 text-sm text-[var(--danger)]"
          role="alert"
        >
          {error} Your entries are still here. Review them and try saving again.
        </p>
      )}

      <Button
        type="button"
        onClick={onFinish}
        disabled={saving}
        className="mt-5 w-full gap-2"
      >
        {saving
          ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving profile...</>
          : <><Rocket className="h-4 w-4" /> Save and start Hatch</>}
      </Button>
    </section>
  );
}
