import type { ReactNode } from "react";

export function BriefSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="brief-section rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <h2 className="text-sm font-semibold text-[var(--text)]">{title}</h2>
      <div className="mt-2 text-sm text-[var(--text-dim)]">{children}</div>
    </section>
  );
}
