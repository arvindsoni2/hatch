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

const WORK_AUTH_OPTIONS = [
  { value: "permanent_resident", label: "Citizen / permanent resident" },
  { value: "visa_holder",        label: "Visa holder, currently eligible to work" },
  { value: "other",              label: "Other / prefer not to say" },
];

export function StepEligibility({
  locale, legalFields, compensation, onCompensationChange,
}: StepEligibilityProps) {
  const workAuth = compensation.legal_preferences["work_authorization"] ?? "permanent_resident";

  const header = (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Eligibility
      </p>
      <h1 className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
        {legalFields.length > 0 ? `A couple of ${locale?.name ?? ""} specifics.` : "Eligibility"}
      </h1>
      <Why>
        <b>These are used as hard filters.</b>{" "}
        Hatch uses them to avoid surfacing roles you cannot take.
      </Why>

      <Field label="Visa / work authorisation" hint="Your current right to work. Hatch uses it to filter roles that require sponsorship.">
        <div className="grid grid-cols-1 gap-2">
          {WORK_AUTH_OPTIONS.map((opt) => (
            <Choice
              key={opt.value}
              on={workAuth === opt.value}
              title={opt.label}
              onClick={() =>
                onCompensationChange({
                  ...compensation,
                  legal_preferences: { ...compensation.legal_preferences, work_authorization: opt.value },
                })
              }
            />
          ))}
        </div>
      </Field>
    </div>
  );

  if (legalFields.length === 0) return header;

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Eligibility
      </p>
      <h1 className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
        A couple of {locale?.name ?? ""} specifics.
      </h1>

      <Why>
        <b>These are hard filters.</b>{" "}
        {locale?.flag} {locale?.name} employers screen on them first, so Hatch uses them to avoid
        wasting your time on roles you can&apos;t take.
      </Why>

      <Field label="Visa / work authorisation" hint="Your current right to work.">
        <div className="grid grid-cols-1 gap-2">
          {WORK_AUTH_OPTIONS.map((opt) => (
            <Choice
              key={opt.value}
              on={workAuth === opt.value}
              title={opt.label}
              onClick={() =>
                onCompensationChange({
                  ...compensation,
                  legal_preferences: { ...compensation.legal_preferences, work_authorization: opt.value },
                })
              }
            />
          ))}
        </div>
      </Field>

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
              aria-label={field.label}
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
