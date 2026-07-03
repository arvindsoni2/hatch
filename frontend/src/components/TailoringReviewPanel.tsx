"use client";

import type { TailoringReview } from "@/lib/api";
import { CVQualityGatePanel } from "@/components/tailor/CVQualityGatePanel";

const OPTIONS = [
  "Make more concise",
  "Make more senior",
  "Make more ATS-focused",
  "Reduce unsupported claims",
] as const;

function Tags({ values, tone = "neutral" }: { values: string[]; tone?: "good" | "warn" | "neutral" }) {
  const color = tone === "good" ? "var(--success)" : tone === "warn" ? "var(--warning)" : "var(--text-muted)";
  return <div className="flex flex-wrap gap-1.5">{values.map((value) => <span key={value} className="rounded-full px-2 py-1 text-xs" style={{ background: "var(--surface-2)", color }}>{value}</span>)}</div>;
}

export function TailoringReviewPanel({
  review,
  regenerating,
  onRegenerate,
}: {
  review: TailoringReview | null;
  regenerating: boolean;
  onRegenerate: (instruction: string) => void;
}) {
  if (!review || review.available === false) {
    return <div className="rounded-xl p-6 text-sm" style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>No review data available for this generation.</div>;
  }
  return (
    <div className="space-y-4">
      {review.quality_gate ? <CVQualityGatePanel quality={review.quality_gate} /> : null}
      <section className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <div className="flex items-start justify-between gap-4">
          <div><p className="text-xs uppercase" style={{ color: "var(--text-muted)" }}>Match summary</p><h3 className="mt-1 font-semibold" style={{ color: "var(--text)" }}>{review.match_summary.role_title}</h3></div>
          <span className="text-xl font-bold" style={{ color: "var(--accent)" }}>{review.match_summary.overall_match}%</span>
        </div>
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>{review.match_summary.summary}</p>
      </section>
      <section className="rounded-xl p-5 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <h3 className="font-semibold" style={{ color: "var(--text)" }}>ATS keyword coverage · {review.ats_keyword_coverage.coverage_pct}%</h3>
        <Tags values={review.ats_keyword_coverage.covered} tone="good" />
        {review.ats_keyword_coverage.missing.length ? <><p className="text-xs" style={{ color: "var(--text-muted)" }}>Missing</p><Tags values={review.ats_keyword_coverage.missing} tone="warn" /></> : null}
      </section>
      <section className="rounded-xl p-5 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <h3 className="font-semibold" style={{ color: "var(--text)" }}>Evidence used</h3>
        {review.evidence_used.map((item) => <div key={item.requirement} className="rounded-lg p-3 text-sm" style={{ background: "var(--surface-2)" }}><strong>{item.requirement}</strong><p className="mt-1" style={{ color: "var(--text-muted)" }}>{item.evidence}</p></div>)}
      </section>
      {review.weak_or_unsupported_requirements.length ? (
        <section className="rounded-xl p-5 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
          <h3 className="font-semibold" style={{ color: "var(--text)" }}>Weak or unsupported requirements</h3>
          {review.weak_or_unsupported_requirements.map((item) => <div key={item.requirement} className="text-sm"><strong>{item.requirement}</strong><p style={{ color: "var(--text-muted)" }}>{item.reason} {item.suggestion}</p></div>)}
        </section>
      ) : null}
      {review.warnings.length ? <section className="rounded-xl p-5"><h3 className="font-semibold">Concerns</h3>{review.warnings.map((item) => <p key={item.message} className="mt-2 text-sm" style={{ color: "var(--warning)" }}>{item.message}</p>)}</section> : null}
      <section className="rounded-xl p-5" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
        <h3 className="font-semibold" style={{ color: "var(--text)" }}>Regenerate full pack</h3>
        <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>Creates new CV and cover-letter versions; previous files remain in history.</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {OPTIONS.map((option) => <button key={option} disabled={regenerating} onClick={() => onRegenerate(option)} className="rounded-lg border px-3 py-2 text-left text-sm disabled:opacity-50" style={{ borderColor: "var(--border)", color: "var(--text)" }}>{option}</button>)}
        </div>
      </section>
    </div>
  );
}
