import type { ConversationalProgressRead, ConversationalTrend } from "@/lib/api";
import Link from "next/link";
import { LEVEL_LABELS, dimensionLabel, ReportAreas, ReportEvidence } from "./ConversationalReport";

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
        <p className="rounded-[var(--radius-control)] border border-dashed border-[var(--border)] p-5 text-sm text-[var(--text-muted)]">No compatible completed interviews are available for this context.</p>
      ) : (
        <div className="space-y-3">
          {progress.groups.map((group) => (
            <article key={group.compatibility_key} className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-medium text-[var(--text)]">{group.context.role_title ?? "Interview format"}</h3>
                <span className="text-sm text-[var(--text-muted)]">{group.sessions.length} {group.sessions.length === 1 ? "session" : "sessions"}</span>
              </div>
              <p className="mt-2 text-sm text-[var(--text-muted)]">
                {[group.context.role_level, group.context.interview_type].filter(Boolean).map((value) => dimensionLabel(value!)).join(", ")}
              </p>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm" aria-label={`Dimension comparison for ${group.compatibility_key}`}>
                  <thead className="text-[var(--text-muted)]"><tr>
                    {["Dimension", "Previous", "Current", "Trend"].map((column) => <th key={column} scope="col" className="pb-2 pr-4 font-medium">{column}</th>)}
                  </tr></thead>
                  <tbody>{Object.entries(group.current_levels).map(([dimension, current]) => <tr key={dimension} className="border-t border-[var(--border)]">
                    <th scope="row" className="py-3 pr-4 font-medium text-[var(--text)]">{dimensionLabel(dimension)}</th>
                    <td className="pr-4 text-[var(--text-dim)]">{LEVEL_LABELS[group.previous_levels[dimension as keyof typeof group.previous_levels]]}</td>
                    <td className="pr-4 text-[var(--text-dim)]">{LEVEL_LABELS[current]}</td>
                    <td className="text-[var(--text-dim)]">{TREND_LABELS[group.trends[dimension as keyof typeof group.trends]]}</td>
                  </tr>)}</tbody>
                </table>
              </div>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <section><h4 className="mb-2 font-medium text-[var(--text)]">Strongest areas</h4>
                  <ReportAreas items={group.strongest_areas} empty="No assessed strengths are available." />
                </section>
                <section><h4 className="mb-2 font-medium text-[var(--text)]">Priority areas</h4>
                  <ReportAreas items={group.priority_areas} empty="No assessed priorities are available." />
                </section>
              </div>
              <section className="mt-4"><h4 className="mb-2 font-medium text-[var(--text)]">Evidence review</h4>
                <ReportEvidence items={group.evidence_review_items} />
              </section>
              <details className="mt-4 text-sm text-[var(--text-muted)]">
                <summary className="min-h-11 cursor-pointer py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]">Session history and compatibility</summary>
                <p className="break-all">{group.compatibility_key}</p>
                <ul className="mt-2 space-y-2">{group.sessions.map((session) => <li key={session.session_id}>
                  <Link href={`/coach/report/${encodeURIComponent(session.session_id)}`} className="underline underline-offset-4">
                    {session.completed_at.replace("T", " ")} — {LEVEL_LABELS[session.session_level]}
                  </Link>
                </li>)}</ul>
              </details>
            </article>
          ))}
        </div>
      )}
      {progress.groups_truncated ? <p className="text-xs text-[var(--text-muted)]">Showing the first {progress.returned_groups} of {progress.total_groups} groups.</p> : null}
    </section>
  );
}
