import type { ConversationalLevel, ConversationalReportRead } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const LEVEL_LABELS: Record<ConversationalLevel, string> = {
  needs_work: "Needs work",
  developing: "Developing",
  interview_ready: "Interview ready",
  strong: "Strong",
  not_assessed: "Not assessed",
};

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
