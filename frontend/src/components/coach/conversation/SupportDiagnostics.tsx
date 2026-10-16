import type { SupportDiagnosticsRead } from "@/lib/api";

export function SupportDiagnostics({ diagnostics }: { diagnostics: SupportDiagnosticsRead }) {
  return (
    <details className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <summary className="cursor-pointer font-medium text-[var(--text)]">Support details</summary>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <div><dt className="text-[var(--text-muted)]">Status</dt><dd className="text-[var(--text)]">{diagnostics.status}</dd></div>
        <div><dt className="text-[var(--text-muted)]">Conversation state</dt><dd className="text-[var(--text)]">{diagnostics.conversation_state}</dd></div>
        <div><dt className="text-[var(--text-muted)]">Report state</dt><dd className="text-[var(--text)]">{diagnostics.report_state}</dd></div>
        {diagnostics.error_code ? <div><dt className="text-[var(--text-muted)]">Error code</dt><dd className="text-[var(--text)]">{diagnostics.error_code}</dd></div> : null}
      </dl>
    </details>
  );
}
