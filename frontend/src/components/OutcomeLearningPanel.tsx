import type { OutcomeLearningSummary } from "@/lib/api";

export function OutcomeLearningPanel({ summary }: { summary: OutcomeLearningSummary | null }) {
  if (!summary) {
    return <section className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}><h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>What Hatch has learned</h2><p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>Outcome learning data is temporarily unavailable.</p></section>;
  }
  const insufficient = summary.confidence === "insufficient";
  return (
    <section className="rounded-xl p-6" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>What Hatch has learned</h2><p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>Local correlations from your resolved applications. Opportunity scores are ranking aids, not response probabilities.</p></div>
        <span className="rounded-full px-2.5 py-1 text-xs capitalize" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>{summary.enabled ? summary.confidence : "Disabled"}</span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[['Resolved', summary.resolved_applications], ['Effective sample', summary.effective_sample_size.toFixed(1)], ['Responses', summary.positive_responses], ['Recent response rate', `${(summary.global_response_rate * 100).toFixed(1)}%`]].map(([label, value]) => <div key={String(label)} className="rounded-lg p-3" style={{ background: "var(--surface-2)" }}><div className="text-lg font-semibold" style={{ color: "var(--text)" }}>{value}</div><div className="text-xs" style={{ color: "var(--text-muted)" }}>{label}</div></div>)}
      </div>
      {insufficient ? <p className="mt-4 rounded-lg p-3 text-sm" style={{ background: "var(--warning-soft)", color: "var(--text-dim)" }}>Opportunity ranking will activate after {summary.minimum_required} resolved applications. {summary.additional_required} more are needed.</p> : (
        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <SignalList title="Positive signals" reasons={summary.top_positive_signals} />
          <SignalList title="Negative signals" reasons={summary.top_negative_signals} />
        </div>
      )}
      {summary.variant_recommendations.length > 0 && <div className="mt-5 space-y-2"><h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>Document variants</h3>{summary.variant_recommendations.map((item) => <div key={item.document_type} className="rounded-lg p-3 text-sm" style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}><strong>{item.document_type === 'cv' ? 'CV' : 'Cover letter'} {item.recommended_variant}</strong>: {item.reason} ({item.sample_size} resolved)</div>)}</div>}
    </section>
  );
}

function SignalList({ title, reasons }: { title: string; reasons: OutcomeLearningSummary['top_positive_signals'] }) {
  return <div><h3 className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-muted)" }}>{title}</h3>{reasons.length ? <ul className="mt-2 space-y-2">{reasons.map((reason) => <li key={`${reason.signal}-${reason.value}`} className="text-sm" style={{ color: "var(--text-dim)" }}><span className="font-medium">{reason.value}</span> · {reason.message} <span className="text-xs">({reason.sample_size})</span></li>)}</ul> : <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>No signal currently meets the explanation threshold.</p>}</div>;
}
