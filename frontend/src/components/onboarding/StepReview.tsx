"use client";

import { Zap, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import type { CandidateData } from "./StepAboutYou";
import type { SearchData, CompensationData } from "./StepJobSearch";
import type { SkillsData } from "./StepSkills";
import type { LLMData } from "./StepAIProvider";
import type { LocaleSummary } from "@/lib/api";

interface StepReviewProps {
  candidate: CandidateData;
  selectedLocale: string;
  locales: LocaleSummary[];
  search: SearchData;
  compensation: CompensationData;
  skills: SkillsData;
  llm: LLMData;
  enabledBoardsCount: number;
  totalBoardsCount: number;
  error: string;
  saving: boolean;
  onFinish: () => void;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1.5 text-sm border-b last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-right max-w-xs truncate">{value}</span>
    </div>
  );
}

export function StepReview({
  candidate, selectedLocale, locales, search, compensation, skills, llm,
  enabledBoardsCount, totalBoardsCount, error, saving, onFinish,
}: StepReviewProps) {
  const localeName = locales.find((l) => l.id === selectedLocale)?.name ?? selectedLocale;
  const rateDisplay = compensation.min_rate
    ? `${compensation.currency} ${compensation.min_rate}–${compensation.max_rate}/${compensation.rate_type}`
    : "—";

  return (
    <div className="space-y-5">
      <CardHeader className="px-0 pt-0">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-brand-600" />
          <CardTitle>Ready to launch</CardTitle>
        </div>
        <CardDescription>
          Review your settings. Everything can be changed later via Settings.
        </CardDescription>
      </CardHeader>

      <div className="rounded-lg border border-slate-200 divide-y divide-slate-100 bg-white">
        <Row label="Name" value={candidate.name || "—"} />
        <Row label="Title" value={candidate.title || "—"} />
        <Row label="Market" value={localeName} />
        <Row label="Target roles" value={search.target_roles.join(", ") || "—"} />
        <Row label="Rate" value={rateDisplay} />
        <Row label="Primary skills" value={skills.primary.slice(0, 5).join(", ") || "—"} />
        <Row label="AI provider" value={`${llm.provider} · ${llm.primary_model}`} />
        <Row label="Boards enabled" value={`${enabledBoardsCount} of ${totalBoardsCount}`} />
      </div>

      <p className="text-xs text-slate-400">
        Everything can be changed later via Settings or by editing{" "}
        <code>data/profile.yaml</code>.
      </p>

      {error && (
        <p className="text-sm text-red-600 p-3 bg-red-50 rounded">{error}</p>
      )}

      <Button
        onClick={onFinish}
        disabled={saving}
        className="w-full bg-brand-600 hover:bg-brand-700 text-white gap-2"
      >
        {saving
          ? <><Loader2 className="h-4 w-4 animate-spin" /> Saving…</>
          : <><Zap className="h-4 w-4" /> Start JobPilot</>}
      </Button>
    </div>
  );
}
