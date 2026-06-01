"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Field, TagInput } from "./OnboardingPrimitives";

export interface SkillsData {
  primary: string[];
  secondary: string[];
  certifications: string[];
}

export interface DomainsData {
  preferred: string[];
  excluded: string[];
}

export interface ProofPoint {
  id: string;
  summary: string;
  context: string;
  metrics: string;
  tags: string[];
}

const SKILL_SUGGESTIONS = ["Agile delivery", "Stakeholder management", "Budget ownership", "Risk management", "Roadmapping"];

interface StepSkillsProps {
  skills: SkillsData;
  onSkillsChange: (skills: SkillsData) => void;
  domains: DomainsData;
  onDomainsChange: (domains: DomainsData) => void;
  proofPoints: ProofPoint[];
  onProofPointsChange: (points: ProofPoint[]) => void;
}

function ProofPointForm({ point, index, onChange, onRemove }: {
  point: ProofPoint; index: number;
  onChange: (p: ProofPoint) => void; onRemove: () => void;
}) {
  const [tagInput, setTagInput] = useState("");
  return (
    <div
      className="rounded-[var(--r-card,10px)] p-4 space-y-3 border border-[var(--border)]"
      style={{ background: "var(--surface-2)" }}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-[550] text-[var(--text)]">Achievement {index + 1}</p>
        <button type="button" onClick={onRemove} className="text-xs text-[var(--danger)] hover:underline">Remove</button>
      </div>
      <Field label="One-line summary" req hint="E.g. Led migration of 3 legacy systems to AWS, cutting infra costs 40%.">
        <Input value={point.summary} onChange={(e) => onChange({ ...point, summary: e.target.value })}
          placeholder="Led migration of 3 legacy systems to AWS, cutting infra costs 40%" />
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Context (Situation / Task)" hint="The challenge you inherited or were set.">
          <textarea rows={2} value={point.context} onChange={(e) => onChange({ ...point, context: e.target.value })}
            placeholder="Inherited a fragile on-prem estate…"
            className="flex w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none" />
        </Field>
        <Field label="Metrics / Result" hint="Concrete numbers make tailored CVs much stronger.">
          <textarea rows={2} value={point.metrics} onChange={(e) => onChange({ ...point, metrics: e.target.value })}
            placeholder="£1.2M annual saving, 99.9% uptime"
            className="flex w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] resize-none" />
        </Field>
      </div>
      <div className="space-y-1">
        <label className="text-[13px] font-[550] text-[var(--text)]">Tags (skills demonstrated)</label>
        <div className="flex flex-wrap gap-1.5 p-2 border border-[var(--border)] rounded-[var(--r-field,8px)] min-h-[34px]"
          style={{ background: "var(--surface)" }}>
          {point.tags.map((t, i) => (
            <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-[550] rounded-[var(--r-chip,6px)] text-[var(--text)]"
              style={{ background: "var(--accent-soft)" }}>
              {t}
              <button type="button" onClick={() => onChange({ ...point, tags: point.tags.filter((_, j) => j !== i) })}
                className="opacity-65 hover:opacity-100">×</button>
            </span>
          ))}
          <input
            className="flex-1 min-w-[80px] outline-none text-xs bg-transparent text-[var(--text)] placeholder:text-[var(--text-muted)]"
            value={tagInput} placeholder="AWS, Cloud…"
            onChange={(e) => setTagInput(e.target.value)}
            onKeyDown={(e) => {
              if ((e.key === "Enter" || e.key === ",") && tagInput.trim()) {
                e.preventDefault();
                onChange({ ...point, tags: [...point.tags, tagInput.trim()] });
                setTagInput("");
              }
            }}
          />
        </div>
      </div>
    </div>
  );
}

export function StepSkills({ skills, onSkillsChange, domains, onDomainsChange, proofPoints, onProofPointsChange }: StepSkillsProps) {
  const addProofPoint = () => {
    onProofPointsChange([...proofPoints, { id: `pp_${Date.now()}`, summary: "", context: "", metrics: "", tags: [] }]);
  };

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 5 · Skills &amp; proof
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        What makes you the match?
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        Skills drive scoring. Proof points power the tailoring — and the interview coach later.
      </p>

      <Field label="Core skills" req hint="Your strongest, most-relevant skills. These carry the most weight in scoring.">
        <TagInput
          tags={skills.primary}
          onChange={(t) => onSkillsChange({ ...skills, primary: t })}
          placeholder="Agile delivery"
          suggestions={SKILL_SUGGESTIONS}
        />
      </Field>

      <Field label="Supporting skills" optional hint="Good-to-have skills — weighted less than core skills in matching.">
        <TagInput
          tags={skills.secondary}
          onChange={(t) => onSkillsChange({ ...skills, secondary: t })}
          placeholder="Python, Terraform…"
        />
      </Field>

      <Field label="Certifications" optional hint="Listed on your profile and matched against job requirements.">
        <TagInput
          tags={skills.certifications}
          onChange={(t) => onSkillsChange({ ...skills, certifications: t })}
          placeholder="PMP, AWS SA, PSM-I…"
        />
      </Field>

      <Field label="Preferred domains" optional hint="Hatch boosts roles in sectors you've chosen; use exclusions to hide sectors.">
        <TagInput
          tags={domains.preferred}
          onChange={(t) => onDomainsChange({ ...domains, preferred: t })}
          placeholder="FinTech, Energy, Public Sector…"
        />
      </Field>

      <div className="space-y-3 pt-1">
        <div className="flex items-center justify-between">
          <p className="text-sm font-[550] text-[var(--text)]">
            Proof points <span className="text-[11px] font-[500] text-[var(--text-muted)] ml-1">Optional</span>
          </p>
          <button
            type="button"
            onClick={addProofPoint}
            className="text-[13px] font-[550] text-[var(--accent)] hover:text-[var(--accent-hover)]"
          >
            + Add proof point
          </button>
        </div>
        <p className="text-[12px] text-[var(--text-muted)]">
          1–2 wins with numbers. Hatch maps these to job requirements when writing your CV.
        </p>
        {proofPoints.map((p, i) => (
          <ProofPointForm
            key={p.id} point={p} index={i}
            onChange={(updated) => onProofPointsChange(proofPoints.map((x, j) => j === i ? updated : x))}
            onRemove={() => onProofPointsChange(proofPoints.filter((_, j) => j !== i))}
          />
        ))}
      </div>
    </div>
  );
}
