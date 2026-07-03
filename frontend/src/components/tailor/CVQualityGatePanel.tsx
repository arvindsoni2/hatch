import type { TailoringReview } from "@/lib/api";

export function CVQualityGatePanel({ quality }: { quality: NonNullable<TailoringReview["quality_gate"]> }) {
  const post = quality.post_generation;
  const label = post.export_confidence === "good" ? "Good to export" :
    post.export_confidence === "review_recommended" ? "Review recommended" : "Acknowledgement required";
  return <section className="rounded-xl p-5 space-y-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
    <div className="flex items-center justify-between"><h3 className="font-semibold" style={{ color: "var(--text)" }}>CV quality check</h3>
      <strong style={{ color: post.export_confidence === "good" ? "var(--success)" : "var(--warning)" }}>{label}</strong></div>
    <div className="grid grid-cols-2 gap-2 text-sm" style={{ color: "var(--text-muted)" }}>
      <span>ATS readability: {post.ats_readability}</span><span>Keyword coverage: {post.keyword_coverage.coverage_pct}%</span>
    </div>
    {post.unsupported_claims.length ? <div><strong className="text-sm" style={{ color: "var(--warning)" }}>Unsupported claims</strong>
      {post.unsupported_claims.map((item) => <p key={item.claim} className="text-sm" style={{ color: "var(--text-muted)" }}>{item.claim}: {item.reason}</p>)}</div> : null}
  </section>;
}
