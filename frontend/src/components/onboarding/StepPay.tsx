"use client";

import { Field, Help, Seg, ChipInfo } from "./OnboardingPrimitives";
import { Input } from "@/components/ui/input";
import type { LocationData, CompensationData } from "./StepJobSearch";
import type { LocaleSummary } from "@/lib/api";

interface StepPayProps {
  locale: LocaleSummary | undefined;
  locations: LocationData[];
  onLocationsChange: (locations: LocationData[]) => void;
  compensation: CompensationData;
  onCompensationChange: (compensation: CompensationData) => void;
  tried: boolean;
}

export function StepPay({
  locale, locations, onLocationsChange, compensation, onCompensationChange, tried,
}: StepPayProps) {
  const loc = locations[0];
  const currency = locale?.currency ?? compensation.currency;
  const rateType = locale?.default_rate_type ?? compensation.rate_type;
  const maxBelowMin = compensation.max_rate > 0
    && compensation.max_rate < compensation.min_rate;

  return (
    <div className="ob-fadein px-5 pb-4">
      <p className="text-[11px] font-[600] tracking-[0.1em] uppercase text-[var(--text-dim)] mb-2">
        Location and pay
      </p>
      <h1 className="mb-3 text-[31px] font-semibold leading-[1.16] tracking-[-0.025em] text-[var(--text)]">
        What are you worth, and where?
      </h1>
      <p className="text-[14px] leading-[1.5] text-[var(--text-dim)] mb-4">
        Pay weighs into every match score. A realistic range helps Hatch surface better-fitting roles.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <Field
          label="City"
          req
          hint={tried && !loc.city.trim() ? "City is required." : undefined}
          hintTone={tried && !loc.city.trim() ? "err" : ""}
        >
          <Input
            aria-label="City"
            value={loc.city}
            onChange={(e) => onLocationsChange([{ ...loc, city: e.target.value }])}
            placeholder="London"
            className={tried && !loc.city.trim() ? "border-[var(--danger)]" : ""}
          />
        </Field>

        <Field label="Remote preference">
          <Seg
            value={loc.remote_preference}
            onChange={(v) => onLocationsChange([{ ...loc, remote_preference: v }])}
            options={[
              { v: "remote", l: "Remote"  },
              { v: "hybrid", l: "Hybrid"  },
              { v: "onsite", l: "On-site" },
            ]}
          />
        </Field>
      </div>

      <Field
        label={`Expected rate (${currency})`}
        req
        hint={`Your ${locale?.name ?? ""} market uses ${rateType} rates. Leave max blank if you are flexible.`}
      >
        <div className="grid grid-cols-3 gap-2.5">
          <Input
            aria-label="Minimum expected rate"
            type="number"
            min={0}
            value={compensation.min_rate || ""}
            onChange={(e) => onCompensationChange({ ...compensation, min_rate: parseFloat(e.target.value) || 0 })}
            placeholder="Min"
            className={tried && compensation.min_rate <= 0 ? "border-[var(--danger)]" : ""}
          />
          <Input
            aria-label="Maximum expected rate"
            aria-describedby={tried && maxBelowMin ? "maximum-rate-error" : undefined}
            aria-invalid={tried && maxBelowMin}
            type="number"
            min={0}
            value={compensation.max_rate || ""}
            onChange={(e) => onCompensationChange({ ...compensation, max_rate: parseFloat(e.target.value) || 0 })}
            placeholder="Max"
            className={tried && maxBelowMin ? "border-[var(--danger)]" : ""}
          />
          <ChipInfo>{currency} / {rateType}</ChipInfo>
        </div>
        {tried && compensation.min_rate <= 0 && (
          <Help tone="err">Minimum rate is required.</Help>
        )}
        {tried && maxBelowMin && (
          <div id="maximum-rate-error">
            <Help tone="err">Maximum rate must be greater than or equal to minimum rate.</Help>
          </div>
        )}
      </Field>
    </div>
  );
}
