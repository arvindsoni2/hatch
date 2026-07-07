"use client";

import type { LocaleSummary } from "@/lib/api";
import { Field, Why, TagInput, Choice, Seg } from "./OnboardingPrimitives";
import type { SearchData } from "./StepJobSearch";

interface StepMarketProps {
  selectedLocale: string;
  locales: LocaleSummary[];
  loadingLocales: boolean;
  onLocaleChange: (locale: string) => void;
  search: SearchData;
  onSearchChange: (search: SearchData) => void;
  tried: boolean;
  rolesSkipped?: boolean;
  onRolesSkippedChange?: (skipped: boolean) => void;
}

const ROLE_SUGGESTIONS = [
  "Delivery Lead", "Programme Manager", "Scrum Master",
  "Agile Coach", "Project Manager",
];

export function StepMarket({
  selectedLocale, locales, loadingLocales, onLocaleChange,
  search, onSearchChange, tried, rolesSkipped = false, onRolesSkippedChange,
}: StepMarketProps) {
  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Your market
      </p>
      <h1 className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
        Where are you looking?
      </h1>

      <Why>
        <b>Your market sets your boards.</b> It controls which job sites Hatch scrapes and which
        local compliance details we&apos;ll ask for next.
      </Why>

      <Field label="Job market" req>
        {loadingLocales ? (
          <p className="text-sm text-[var(--text-muted)] py-2">Loading markets…</p>
        ) : (
          <div className="grid grid-cols-2 gap-2.5">
            {locales.map((l) => (
              <Choice
                key={l.id}
                on={selectedLocale === l.id}
                onClick={() => onLocaleChange(l.id)}
                flag={l.flag}
                title={l.name}
              />
            ))}
          </div>
        )}
      </Field>

      <Field
        label="Target job titles"
        req
        hint={
          tried && search.target_roles.length === 0
            ? "Add at least one target job title."
            : search.target_roles.length
            ? "Add a few variations to find more relevant matches."
            : "Press Enter to add each title. Tap a suggestion to start."
        }
        hintTone={tried && search.target_roles.length === 0 ? "err" : ""}
      >
        <TagInput
          tags={search.target_roles}
          onChange={(roles) => {
            onSearchChange({ ...search, target_roles: roles });
            if (roles.length > 0) onRolesSkippedChange?.(false);
          }}
          placeholder="Delivery Lead"
          suggestions={ROLE_SUGGESTIONS}
          invalid={tried && search.target_roles.length === 0}
        />
        {search.target_roles.length === 0 && (
          <button
            type="button"
            className="mt-3 min-h-11 text-sm font-semibold text-[var(--accent)] underline-offset-4 hover:underline"
            onClick={() => onRolesSkippedChange?.(!rolesSkipped)}
          >
            {rolesSkipped ? "I will add target roles later" : "Add target roles later"}
          </button>
        )}
        {rolesSkipped && (
          <p className="mt-1 text-[12px] text-[var(--warning)]" role="status">
            Job discovery will be broad until you add target roles in Settings.
          </p>
        )}
      </Field>

      <Field label="Employment type" hint="Filters matches to the kind of work you actually want.">
        <Seg
          value={search.contract_type}
          onChange={(v) => onSearchChange({ ...search, contract_type: v })}
          options={[
            { v: "contract",  l: "Contract"  },
            { v: "permanent", l: "Permanent" },
            { v: "any",       l: "Either"    },
          ]}
        />
      </Field>
    </div>
  );
}
