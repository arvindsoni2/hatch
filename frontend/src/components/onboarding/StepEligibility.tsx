"use client";

import type { LocaleLegalField, LocaleSummary } from "@/lib/api";
import { Field, Why, Choice } from "./OnboardingPrimitives";
import type { CompensationData } from "./StepJobSearch";

interface StepEligibilityProps {
  locale: LocaleSummary | undefined;
  legalFields: LocaleLegalField[];
  compensation: CompensationData;
  onCompensationChange: (compensation: CompensationData) => void;
}

export function StepEligibility({
  locale, legalFields, compensation, onCompensationChange,
}: StepEligibilityProps) {
  if (legalFields.length === 0) {
    return (
      <div className="ob-fadein px-5 pb-4">
        <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
          Step 4 · Eligibility
        </p>
        <h1
          className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
          style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
        >
          No eligibility questions for this market.
        </h1>
        <p className="text-sm text-[var(--text-dim)]">Continue to the next step.</p>
      </div>
    );
  }

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Step 4 · Eligibility
      </p>
      <h1
        className="text-[31px] font-[500] leading-[1.16] tracking-[-0.015em] text-[var(--text)] mb-3"
        style={{ fontFamily: "var(--font-hero, 'Newsreader', Georgia, serif)" }}
      >
        A couple of {locale?.name ?? ""} specifics.
      </h1>

      <Why>
        <b>These are hard filters.</b>{" "}
        {locale?.flag} {locale?.name} employers screen on them first, so Hatch uses them to avoid
        wasting your time on roles you can&apos;t take.
      </Why>

      {legalFields.map((field) => (
        <Field
          key={field.id}
          label={field.label}
          hint={field.help}
        >
          {field.type === "select" && field.options ? (
            <div className="grid grid-cols-1 gap-2">
              {field.options.map((opt) => (
                <Choice
                  key={opt.value}
                  on={(compensation.legal_preferences[field.id] ?? field.default) === opt.value}
                  title={opt.label}
                  onClick={() =>
                    onCompensationChange({
                      ...compensation,
                      legal_preferences: { ...compensation.legal_preferences, [field.id]: opt.value },
                    })
                  }
                />
              ))}
            </div>
          ) : (
            <input
              className="flex h-10 w-full rounded-[var(--r-field,8px)] border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
              value={compensation.legal_preferences[field.id] ?? ""}
              onChange={(e) =>
                onCompensationChange({
                  ...compensation,
                  legal_preferences: { ...compensation.legal_preferences, [field.id]: e.target.value },
                })
              }
            />
          )}
        </Field>
      ))}
    </div>
  );
}
