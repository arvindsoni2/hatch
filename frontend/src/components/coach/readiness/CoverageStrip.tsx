import type { CoverageOverview } from "@/lib/coachReadinessApi";

export interface CoverageStripProps {
  overview: CoverageOverview;
}

export function CoverageStrip({ overview }: CoverageStripProps) {
  const count = overview.gaps.length;
  return (
    <section
      aria-label="Story coverage"
      className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3"
    >
      <p className="text-sm text-[var(--text)]">
        {count === 0
          ? "No shared gaps across your active interviews."
          : `${count} ${count === 1 ? "gap" : "gaps"} across your active interviews.`}
      </p>
    </section>
  );
}
