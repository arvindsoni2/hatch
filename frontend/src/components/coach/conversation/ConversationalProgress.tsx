import type { ConversationalProgressRead, ConversationalTrend } from "@/lib/api";

const TREND_LABELS: Record<ConversationalTrend, string> = {
  improving: "Improving",
  stable: "Stable",
  mixed: "Mixed",
  declining: "Declining",
  not_enough_evidence: "Not enough evidence",
};

export function ConversationalProgress({ progress }: { progress: ConversationalProgressRead }) {
  return (
    <section aria-labelledby="conversational-progress-title" className="space-y-4">
      <div>
        <h2 id="conversational-progress-title" className="text-xl font-semibold text-[var(--text)]">Progress by interview format</h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">Sessions with different compatibility keys stay separate.</p>
      </div>
      {progress.groups.length === 0 ? (
        <p className="rounded-[var(--radius-control)] border border-dashed border-[var(--border)] p-5 text-sm text-[var(--text-muted)]">Complete another conversational interview to see progress here.</p>
      ) : (
        <div className="space-y-3">
          {progress.groups.map((group) => (
            <article key={group.compatibility_key} className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-medium text-[var(--text)]">{group.compatibility_key}</h3>
                <span className="text-sm text-[var(--text-muted)]">{TREND_LABELS[group.trend]}</span>
              </div>
              <p className="mt-2 text-sm text-[var(--text-muted)]">{group.session_count} {group.session_count === 1 ? "session" : "sessions"}</p>
            </article>
          ))}
        </div>
      )}
      {progress.groups_truncated ? <p className="text-xs text-[var(--text-muted)]">Showing the first {progress.returned_groups} of {progress.total_groups} groups.</p> : null}
    </section>
  );
}
