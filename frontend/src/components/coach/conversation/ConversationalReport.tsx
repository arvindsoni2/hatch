import type { ReactNode } from "react";
import type { ConversationalLevel, ConversationalReportRead, ConversationalReportStrength,
  ConversationalReportPriority, ConversationalReportEvidence } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const LEVEL_LABELS: Record<ConversationalLevel, string> = {
  needs_work: "Needs work",
  developing: "Developing",
  interview_ready: "Interview ready",
  strong: "Strong",
  not_assessed: "Not assessed",
};

export function dimensionLabel(value: string): string {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function ReportSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-3 border-t border-[var(--border)] pt-5">
    <h2 className="text-lg font-semibold text-[var(--text)]">{title}</h2>
    {children}
  </section>;
}

export function ReportAreas({ items, empty }: {
  items: Array<ConversationalReportStrength | ConversationalReportPriority>; empty: string;
}) {
  return items.length ? <ul className="space-y-3 text-sm text-[var(--text-dim)]">
    {items.map((item) => <li key={item.dimension}>
      <p className="font-medium text-[var(--text)]">{dimensionLabel(item.dimension)}: {LEVEL_LABELS[item.level]}</p>
      <p>{item.assessed_bundle_count} assessed {item.assessed_bundle_count === 1 ? "question bundle" : "question bundles"}</p>
      {"next_action" in item ? <p className="mt-1 leading-6">{item.next_action}</p> : null}
    </li>)}
  </ul> : <p className="text-sm text-[var(--text-muted)]">{empty}</p>;
}

export function ReportEvidence({ items }: { items: ConversationalReportEvidence[] }) {
  return <div className="space-y-3 text-sm text-[var(--text-dim)]">
    <p>Hatch source matching, not independent verification.</p>
    {items.length ? <ul className="space-y-4">{items.map((item) => <li key={`${item.attempt_id}-${item.claim_id}`}>
      <blockquote className="border-l-2 border-[var(--border-strong)] pl-3 leading-6">{item.claim_text}</blockquote>
      <p className="mt-2 font-medium text-[var(--text)]">{dimensionLabel(item.status)}</p>
      <p className="leading-6">{item.explanation}</p>
      <p className="leading-6">{item.candidate_action}</p>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {item.evidence_ids.length ? `Selected sources: ${item.evidence_ids.join(", ")}` : "No selected source supports this finding."}
      </p>
    </li>)}</ul> : <p>No evidence findings are available.</p>}
  </div>;
}

function label(value: unknown): string {
  return typeof value === "string" && value in LEVEL_LABELS
    ? LEVEL_LABELS[value as ConversationalLevel]
    : "Not assessed";
}

export function ConversationalReport({ report }: { report: ConversationalReportRead }) {
  return (
    <main aria-labelledby="conversational-report-title" className="space-y-6">
      <header className="border-b border-[var(--border)] pb-5">
        <p className="text-sm font-medium text-[var(--accent)]">Interview report</p>
        <h1 id="conversational-report-title" className="mt-2 text-3xl font-semibold tracking-tight text-[var(--text)]">
          {label(report.session_level)}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
          A named-level summary grounded in the accepted answers from this interview.
        </p>
      </header>

      <section aria-labelledby="report-dimensions-title">
        <h2 id="report-dimensions-title" className="text-lg font-semibold text-[var(--text)]">Dimensions</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(report.dimensions).map(([dimension, value]) => (
            <Card key={dimension} className="shadow-none">
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-sm capitalize">{dimension.replaceAll("_", " ")}</CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-0 text-sm text-[var(--text-muted)]">{label(value)}</CardContent>
            </Card>
          ))}
        </div>
      </section>

      <ReportSection title="Interview counts">
        <dl className="grid gap-3 text-sm sm:grid-cols-3">
          {([
            ["Planned questions", report.counts.planned_questions_total],
            ["Planned answered", report.counts.planned_questions_answered],
            ["Planned skipped", report.counts.planned_questions_skipped],
            ["Follow-ups asked", report.counts.follow_ups_asked],
            ["Follow-ups answered", report.counts.follow_ups_answered],
            ["Accepted attempts", report.counts.accepted_attempts],
            ["Retry attempts", report.counts.retry_attempts],
            ["Unavailable attempts", report.counts.unavailable_attempts],
            ["Hints used", report.counts.hints_used],
          ] as const).map(([name, count]) => <div key={name}>
            <dt className="text-[var(--text-muted)]">{name}</dt>
            <dd className="mt-1 font-medium tabular-nums text-[var(--text)]">{count}</dd>
          </div>)}
        </dl>
      </ReportSection>
      <ReportSection title="Strengths">
        <ReportAreas items={report.strengths} empty="No assessed strengths are available." />
      </ReportSection>
      <ReportSection title="Improvement priorities">
        <ReportAreas items={report.improvement_priorities} empty="No assessed priorities are available." />
      </ReportSection>
      <ReportSection title="Unassessed areas">
        <p className="text-sm leading-6 text-[var(--text-muted)]">
          {Object.entries(report.dimensions).filter(([, level]) => level === "not_assessed")
            .map(([dimension]) => dimensionLabel(dimension)).join(", ") || "All dimensions have assessed evidence."}
        </p>
      </ReportSection>
      <ReportSection title="Question summaries">
        {report.question_summaries.length ? <ul className="space-y-4 text-sm text-[var(--text-dim)]">
          {report.question_summaries.map((question) => <li key={question.question_id} id={`report-question-${question.question_id}`}>
            <p className="font-medium leading-6 text-[var(--text)]">{question.question_text}</p>
            <p>{dimensionLabel(question.question_kind)} · {dimensionLabel(question.question_state)}</p>
            <p>{question.accepted_attempt_id ? `Accepted answer: ${LEVEL_LABELS[question.answer_level]}` : "No accepted answer."}</p>
          </li>)}
        </ul> : <p className="text-sm text-[var(--text-muted)]">No question summaries are available.</p>}
      </ReportSection>
      <ReportSection title="Evidence review">
        <ReportEvidence items={report.evidence_review_items} />
      </ReportSection>
      <ReportSection title="Practice suggestions">
        {report.practice_suggestions.length ? <ul className="space-y-3 text-sm text-[var(--text-dim)]">
          {report.practice_suggestions.map((item) => <li key={item.dimension}>
            <p className="font-medium text-[var(--text)]">{dimensionLabel(item.dimension)}</p>
            <p className="mt-1 leading-6">{item.next_action}</p>
          </li>)}
        </ul> : <p className="text-sm text-[var(--text-muted)]">No practice suggestions are available.</p>}
      </ReportSection>

      {report.candidate_reflection ? (
        <section aria-labelledby="report-reflection-title" className="border-l-2 border-[var(--accent)] pl-4">
          <h2 id="report-reflection-title" className="text-lg font-semibold text-[var(--text)]">Your reflection</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--text-muted)]">
            {typeof report.candidate_reflection.note === "string" ? report.candidate_reflection.note : "Reflection recorded for this report."}
          </p>
        </section>
      ) : null}

      {report.report_state === "fallback" ? (
        <p role="status" className="rounded-[var(--radius-control)] border border-[var(--border)] bg-[var(--surface-2)] p-3 text-sm text-[var(--text-muted)]">
          The report is available in a deterministic fallback form.
        </p>
      ) : null}
    </main>
  );
}
