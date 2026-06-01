"use client";

import { Input } from "@/components/ui/input";
import { Field } from "./OnboardingPrimitives";

export interface CandidateData {
  name: string;
  title: string;
  years_experience: number;
  summary: string;
}

interface StepAboutYouProps {
  candidate: CandidateData;
  onChange: (candidate: CandidateData) => void;
  tried: boolean;
}

export function StepAboutYou({ candidate, onChange, tried }: StepAboutYouProps) {
  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 1 · About you
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        Who are we writing for?
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        These details go straight into your tailored CVs and cover letters.
      </p>

      <div className="grid grid-cols-1 gap-0 sm:grid-cols-2 sm:gap-3">
        <Field
          label="Full name"
          req
          hint={tried && !candidate.name.trim() ? "Name is required." : "As it should appear on your CV."}
          hintTone={tried && !candidate.name.trim() ? "err" : ""}
        >
          <Input
            id="name"
            value={candidate.name}
            onChange={(e) => onChange({ ...candidate, name: e.target.value })}
            placeholder="Arvind Soni"
            className={tried && !candidate.name.trim() ? "border-[var(--danger)]" : ""}
          />
        </Field>

        <Field
          label="Current or target title"
          req
          hint={tried && !candidate.title.trim() ? "Title is required." : "The role you're aiming for — Hatch matches and writes toward this."}
          hintTone={tried && !candidate.title.trim() ? "err" : ""}
        >
          <Input
            id="title"
            value={candidate.title}
            onChange={(e) => onChange({ ...candidate, title: e.target.value })}
            placeholder="Delivery Lead"
            className={tried && !candidate.title.trim() ? "border-[var(--danger)]" : ""}
          />
        </Field>
      </div>

      <Field label="Years of experience" hint="Used to calibrate how senior the matched roles are.">
        <Input
          id="years"
          type="number"
          min={0}
          value={candidate.years_experience || ""}
          onChange={(e) => onChange({ ...candidate, years_experience: parseInt(e.target.value) || 0 })}
          placeholder="12"
        />
      </Field>

      <Field label="Professional summary" optional hint="2–3 sentences in your voice. Hatch adapts — not copies — this per application.">
        <textarea
          id="summary"
          rows={3}
          value={candidate.summary}
          onChange={(e) => onChange({ ...candidate, summary: e.target.value })}
          placeholder="Senior delivery lead with 12 years running complex transformation programmes across financial services…"
          className="flex w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none leading-[1.5]"
        />
      </Field>
    </div>
  );
}
