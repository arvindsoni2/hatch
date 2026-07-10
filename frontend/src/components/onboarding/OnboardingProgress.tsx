"use client";

const STEP_LABELS = [
  "About you",
  "Your market",
  "Location & pay",
  "Eligibility",
  "Skills",
  "Experience",
  "AI & launch",
];

interface OnboardingProgressProps {
  formStep: number;  // 1-7 for form steps; 0 = no progress shown (Welcome/Success)
}

export function OnboardingProgress({ formStep }: OnboardingProgressProps) {
  if (formStep === 0) return null;

  const label = STEP_LABELS[formStep - 1] ?? "";

  return (
    <div
      className="flex items-baseline gap-2 px-5 pt-3.5 pb-1.5"
      role="progressbar"
      aria-valuenow={formStep}
      aria-valuemax={7}
      aria-label={`Step ${formStep} of 7: ${label}`}
    >
      <span className="text-[40px] leading-[0.9] font-semibold tracking-[-0.025em] text-[var(--text)]">
        {String(formStep).padStart(2, "0")}
      </span>
      <span className="text-[15px] text-[var(--text-muted)]">/ 07</span>
      <span className="ml-auto text-[12px] text-[var(--text-dim)] uppercase tracking-[0.08em]">
        {label}
      </span>
    </div>
  );
}
