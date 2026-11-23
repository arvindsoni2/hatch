import type { ReactNode } from "react";

export function BriefSection(
  { title, note, children }: { title: string; note?: string; children: ReactNode },
) {
  return (
    <section className="brief-section rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="m-0 text-base font-semibold text-[var(--text)]">{title}</h2>
        {note ? <span className="text-xs text-[var(--text-dim)]">{note}</span> : null}
      </div>
      <div className="mt-2 text-sm text-[var(--text-dim)]">{children}</div>
    </section>
  );
}
